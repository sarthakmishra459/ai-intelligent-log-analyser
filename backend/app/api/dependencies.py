from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession

from app.application.log_analysis_service import LogAnalysisService
from app.core.config import Settings, get_settings
from app.infrastructure.database import get_session
from app.infrastructure.vector_store import VectorStore
from app.services.embeddings import build_embedding_provider
from app.services.log_parser import LogParser


async def get_log_analysis_service() -> AsyncGenerator[LogAnalysisService, None]:
    settings: Settings = get_settings()
    async for session in get_session():
        yield LogAnalysisService(
            settings=settings,
            session=session,
            parser=LogParser(settings),
            embeddings=build_embedding_provider(settings),
            vector_store=VectorStore(settings),
        )
        if isinstance(session, AsyncSession):
            await session.close()
