import asyncio
import logging
import shutil
import subprocess
import time
from collections.abc import AsyncIterator
from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.investigation import build_investigation_graph
from app.core.config import Settings
from app.domain.models import Investigation, InvestigationEvent, InvestigationStatus, LogChunk, LogFile
from app.domain.schemas import IncidentSummary, LogChunkRead, LogFileRead, MetricsRead, SearchResult
from app.infrastructure.vector_store import VectorStore
from app.services.embeddings import EmbeddingProvider
from app.services.log_parser import LogParser

logger = logging.getLogger(__name__)


class LogAnalysisService:
    def __init__(
        self,
        settings: Settings,
        session: AsyncSession,
        parser: LogParser,
        embeddings: EmbeddingProvider,
        vector_store: VectorStore,
    ) -> None:
        self.settings = settings
        self.session = session
        self.parser = parser
        self.embeddings = embeddings
        self.vector_store = vector_store

    async def ensure_demo_data_loaded(self) -> bool:
        existing_count = await self.session.scalar(select(func.count(LogFile.id)))
        if existing_count or not self.settings.auto_load_demo_data:
            return False
        demo_files = sorted(self.settings.resolved_demo_data_dir.glob("*"))
        for path in demo_files:
            if path.is_file() and path.suffix.lower() in self.settings.allowed_log_extensions:
                await self.ingest_local_file(path, copy_to_uploads=False)
        await self.index_unindexed_chunks()
        return bool(demo_files)

    async def ingest_uploads(self, files: list[UploadFile]) -> list[LogFile]:
        uploaded: list[LogFile] = []
        for file in files:
            suffix = Path(file.filename or "").suffix.lower()
            if suffix not in self.settings.allowed_log_extensions:
                raise ValueError(
                    f"Unsupported log extension '{suffix}'. Allowed: {sorted(self.settings.allowed_log_extensions)}"
                )
            destination = self.settings.resolved_upload_dir / f"{uuid4()}_{Path(file.filename or 'upload.log').name}"
            size = 0
            with destination.open("wb") as handle:
                while chunk := await file.read(1024 * 1024):
                    size += len(chunk)
                    if size > self.settings.max_upload_size_bytes:
                        destination.unlink(missing_ok=True)
                        raise ValueError(f"{file.filename} exceeds {self.settings.max_upload_size_mb} MB upload limit")
                    handle.write(chunk)
            uploaded.append(
                await self.ingest_local_file(destination, original_filename=file.filename or destination.name)
            )
        await self.index_unindexed_chunks()
        return uploaded

    async def ingest_docker_logs(self, container: str) -> LogFile:
        if not self.settings.enable_docker_log_collection:
            raise ValueError("Docker log collection is disabled by configuration")
        if not container.replace("_", "").replace("-", "").replace(".", "").isalnum():
            raise ValueError("Container name contains unsupported characters")

        command = ["docker", "logs", "--tail", str(self.settings.docker_log_tail_lines), container]
        try:
            completed = await asyncio.to_thread(
                subprocess.run,
                command,
                capture_output=True,
                text=True,
                timeout=self.settings.request_timeout_seconds,
                check=False,
            )
        except FileNotFoundError as exc:
            raise ValueError("Docker CLI is not installed or not available on PATH") from exc
        except subprocess.TimeoutExpired as exc:
            raise ValueError(f"Timed out collecting logs for container '{container}'") from exc

        combined = "\n".join(part for part in (completed.stdout, completed.stderr) if part.strip())
        if completed.returncode != 0 and not combined.strip():
            raise ValueError(f"Docker returned exit code {completed.returncode} without log output")
        if not combined.strip():
            raise ValueError(f"Container '{container}' did not return any logs")

        destination = self.settings.resolved_upload_dir / f"{uuid4()}_docker_{container}.log"
        destination.write_text(combined, encoding="utf-8")
        log_file = await self.ingest_local_file(
            destination, original_filename=f"docker:{container}", copy_to_uploads=False
        )
        await self.index_unindexed_chunks()
        return log_file

    async def ingest_local_file(
        self,
        path: Path,
        original_filename: str | None = None,
        copy_to_uploads: bool = True,
    ) -> LogFile:
        source_path = path
        if copy_to_uploads:
            destination = self.settings.resolved_upload_dir / f"{uuid4()}_{path.name}"
            shutil.copy2(path, destination)
            source_path = destination

        source_type, parsed_lines, chunks = self.parser.parse_file(source_path)
        log_file = LogFile(
            filename=original_filename or path.name,
            storage_path=str(source_path),
            source_type=source_type,
            size_bytes=source_path.stat().st_size,
            line_count=len(parsed_lines),
        )
        self.session.add(log_file)
        await self.session.flush()
        for chunk in chunks:
            self.session.add(
                LogChunk(
                    file_id=log_file.id,
                    chunk_index=chunk.chunk_index,
                    start_line=chunk.start_line,
                    end_line=chunk.end_line,
                    text=chunk.text,
                    severity=chunk.severity,
                    source_type=chunk.source_type,
                    error_count=chunk.error_count,
                    warning_count=chunk.warning_count,
                    metadata_json=chunk.metadata,
                )
            )
        await self.session.commit()
        await self.session.refresh(log_file)
        return log_file

    async def index_unindexed_chunks(self) -> int:
        result = await self.session.execute(select(LogChunk).order_by(LogChunk.created_at, LogChunk.chunk_index))
        chunks = list(result.scalars().all())
        known_ids = set(self.vector_store.mapping)
        pending = [chunk for chunk in chunks if chunk.id not in known_ids]
        if not pending:
            return 0
        embeddings = await asyncio.to_thread(self.embeddings.embed_texts, [chunk.text for chunk in pending])
        indexed = self.vector_store.add([chunk.id for chunk in pending], embeddings)
        logger.info("Indexed %s log chunks", indexed)
        return indexed

    async def search(self, query: str, limit: int, file_id: str | None = None) -> list[SearchResult]:
        await self.ensure_demo_data_loaded()
        query_embedding = await asyncio.to_thread(self.embeddings.embed_texts, [query])
        vector_results = self.vector_store.search(query_embedding[0], max(limit, 50))
        if not vector_results:
            return []
        chunk_ids = [chunk_id for chunk_id, _score in vector_results]
        result = await self.session.execute(select(LogChunk).where(LogChunk.id.in_(chunk_ids)))
        chunks_by_id = {chunk.id: chunk for chunk in result.scalars().all()}
        filtered = []
        for chunk_id, score in vector_results:
            chunk = chunks_by_id.get(chunk_id)
            if chunk is None:
                continue
            if file_id is not None and chunk.file_id != file_id:
                continue
            filtered.append(SearchResult(chunk=LogChunkRead.model_validate(chunk), score=score))
            if len(filtered) >= limit:
                break
        return filtered

    async def ask(self, question: str, file_id: str | None = None) -> Investigation:
        await self.ensure_demo_data_loaded()
        started = time.perf_counter()
        investigation = Investigation(question=question, status=InvestigationStatus.running)
        self.session.add(investigation)
        await self.session.commit()
        await self.session.refresh(investigation)

        async def scoped_search(query: str, limit: int) -> list[SearchResult]:
            return await self.search(query, limit, file_id)

        graph = build_investigation_graph(scoped_search)
        try:
            state = await graph.ainvoke({"question": question, "events": []})
            summary: IncidentSummary = state["summary"]
            investigation.status = InvestigationStatus.completed
            investigation.strategy = state["strategy"]
            investigation.matched_chunk_ids = summary.evidence_chunk_ids
            investigation.answer = summary.model_dump()
            investigation.confidence = summary.confidence
            investigation.response_time_ms = int((time.perf_counter() - started) * 1000)
            for event in state["events"]:
                self.session.add(
                    InvestigationEvent(
                        investigation_id=investigation.id,
                        step=event["step"],
                        message=event["message"],
                        payload=event.get("payload", {}),
                    )
                )
        except Exception as exc:
            logger.exception("Investigation failed")
            investigation.status = InvestigationStatus.failed
            investigation.answer = {
                "incident_summary": "The investigation failed before completion.",
                "root_cause": str(exc),
                "recommendations": ["Review backend logs and retry the investigation."],
                "confidence": 0.0,
                "evidence_chunk_ids": [],
                "reasoning": [],
            }
        await self.session.commit()
        await self.session.refresh(investigation)
        return investigation

    async def ask_stream(self, question: str, file_id: str | None = None) -> AsyncIterator[dict]:
        await self.ensure_demo_data_loaded()
        started = time.perf_counter()
        investigation = Investigation(question=question, status=InvestigationStatus.running)
        self.session.add(investigation)
        await self.session.commit()
        await self.session.refresh(investigation)

        async def scoped_search(query: str, limit: int) -> list[SearchResult]:
            return await self.search(query, limit, file_id)

        graph = build_investigation_graph(scoped_search)
        final_state = None
        try:
            async for update in graph.astream({"question": question, "events": []}):
                node_state = next(iter(update.values()))
                final_state = node_state
                event = node_state.get("events", [{}])[-1]
                yield {
                    "type": event.get("step", "progress"),
                    "investigation_id": investigation.id,
                    "message": event.get("message", "Investigation progressed."),
                    "payload": event.get("payload", {}),
                }

            if final_state is None:
                raise RuntimeError("Investigation graph completed without state")

            summary: IncidentSummary = final_state["summary"]
            investigation.status = InvestigationStatus.completed
            investigation.strategy = final_state["strategy"]
            investigation.matched_chunk_ids = summary.evidence_chunk_ids
            investigation.answer = summary.model_dump()
            investigation.confidence = summary.confidence
            investigation.response_time_ms = int((time.perf_counter() - started) * 1000)
            for event in final_state["events"]:
                self.session.add(
                    InvestigationEvent(
                        investigation_id=investigation.id,
                        step=event["step"],
                        message=event["message"],
                        payload=event.get("payload", {}),
                    )
                )
            await self.session.commit()
            await self.session.refresh(investigation)
            yield {
                "type": "completed",
                "investigation": investigation,
            }
        except Exception as exc:
            logger.exception("Streaming investigation failed")
            investigation.status = InvestigationStatus.failed
            investigation.answer = {
                "incident_summary": "The streaming investigation failed before completion.",
                "root_cause": str(exc),
                "recommendations": ["Review backend logs and retry the investigation."],
                "confidence": 0.0,
                "evidence_chunk_ids": [],
                "reasoning": [],
            }
            await self.session.commit()
            yield {
                "type": "failed",
                "investigation": investigation,
                "message": str(exc),
            }

    async def history(self) -> list[Investigation]:
        result = await self.session.execute(select(Investigation).order_by(Investigation.created_at.desc()).limit(50))
        return list(result.scalars().all())

    async def files(self) -> list[LogFileRead]:
        await self.ensure_demo_data_loaded()
        result = await self.session.execute(select(LogFile).order_by(LogFile.created_at.desc()))
        return [LogFileRead.model_validate(file) for file in result.scalars().all()]

    async def metrics(self) -> MetricsRead:
        await self.ensure_demo_data_loaded()
        files_uploaded = await self.session.scalar(select(func.count(LogFile.id))) or 0
        chunks = await self.session.scalar(select(func.count(LogChunk.id))) or 0
        avg_response = await self.session.scalar(select(func.avg(Investigation.response_time_ms))) or 0.0
        avg_confidence = await self.session.scalar(select(func.avg(Investigation.confidence))) or 0.0
        return MetricsRead(
            files_uploaded=files_uploaded,
            chunks=chunks,
            embedding_count=self.vector_store.count,
            average_response_time_ms=round(float(avg_response), 2),
            average_confidence=round(float(avg_confidence), 2),
        )
