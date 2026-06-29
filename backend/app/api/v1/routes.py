import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from app.api.dependencies import get_log_analysis_service
from app.application.log_analysis_service import LogAnalysisService
from app.domain.schemas import (
    IndexResponse,
    InvestigationRead,
    MetricsRead,
    QuestionRequest,
    SearchRequest,
    SearchResult,
    UploadResponse,
)

router = APIRouter()


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/upload", response_model=UploadResponse)
async def upload_logs(
    files: list[UploadFile] = File(...),
    service: LogAnalysisService = Depends(get_log_analysis_service),
) -> UploadResponse:
    try:
        uploaded = await service.ingest_uploads(files)
        auto_loaded = await service.ensure_demo_data_loaded()
        return UploadResponse(files=uploaded, auto_loaded_demo_data=auto_loaded)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/index", response_model=IndexResponse)
async def index_logs(service: LogAnalysisService = Depends(get_log_analysis_service)) -> IndexResponse:
    await service.ensure_demo_data_loaded()
    before = service.vector_store.count
    indexed = await service.index_unindexed_chunks()
    return IndexResponse(files_indexed=0, chunks_created=indexed, embeddings_stored=service.vector_store.count - before)


@router.post("/docker/{container}", response_model=UploadResponse)
async def collect_docker_logs(
    container: str,
    service: LogAnalysisService = Depends(get_log_analysis_service),
) -> UploadResponse:
    try:
        log_file = await service.ingest_docker_logs(container)
        return UploadResponse(files=[log_file], auto_loaded_demo_data=False)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/search", response_model=list[SearchResult])
async def search_logs(
    request: SearchRequest,
    service: LogAnalysisService = Depends(get_log_analysis_service),
) -> list[SearchResult]:
    return await service.search(request.query, request.limit)


@router.post("/questions", response_model=InvestigationRead)
async def ask_question(
    request: QuestionRequest,
    service: LogAnalysisService = Depends(get_log_analysis_service),
) -> InvestigationRead:
    investigation = await service.ask(request.question)
    return InvestigationRead.model_validate(investigation, from_attributes=True)


@router.post("/questions/stream")
async def stream_question(
    request: QuestionRequest,
    service: LogAnalysisService = Depends(get_log_analysis_service),
) -> StreamingResponse:
    async def event_stream() -> AsyncIterator[str]:
        async for event in service.ask_stream(request.question):
            if "investigation" in event:
                event = {
                    **event,
                    "investigation": InvestigationRead.model_validate(
                        event["investigation"], from_attributes=True
                    ).model_dump(mode="json"),
                }
            yield _sse(event["type"], event)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.get("/history", response_model=list[InvestigationRead])
async def history(service: LogAnalysisService = Depends(get_log_analysis_service)) -> list[InvestigationRead]:
    return [InvestigationRead.model_validate(item, from_attributes=True) for item in await service.history()]


@router.get("/files")
async def files(service: LogAnalysisService = Depends(get_log_analysis_service)):
    return await service.files()


@router.get("/metrics", response_model=MetricsRead)
async def metrics(service: LogAnalysisService = Depends(get_log_analysis_service)) -> MetricsRead:
    return await service.metrics()


def _sse(event: str, payload: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(payload)}\n\n"
