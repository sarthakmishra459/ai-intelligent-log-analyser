from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.domain.enums import InvestigationStatus, LogSeverity, LogSourceType


class LogFileRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    filename: str
    source_type: LogSourceType
    size_bytes: int
    line_count: int
    created_at: datetime


class LogChunkRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    file_id: str
    chunk_index: int
    start_line: int
    end_line: int
    text: str
    severity: LogSeverity
    source_type: LogSourceType
    error_count: int
    warning_count: int
    metadata_json: dict[str, Any]


class UploadResponse(BaseModel):
    files: list[LogFileRead]
    auto_loaded_demo_data: bool


class IndexResponse(BaseModel):
    files_indexed: int
    chunks_created: int
    embeddings_stored: int


class SearchRequest(BaseModel):
    query: str = Field(min_length=2, max_length=1000)
    limit: int = Field(default=10, ge=1, le=50)


class SearchResult(BaseModel):
    chunk: LogChunkRead
    score: float


class QuestionRequest(BaseModel):
    question: str = Field(min_length=3, max_length=2000)


class IncidentSummary(BaseModel):
    incident_summary: str
    root_cause: str
    recommendations: list[str]
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_chunk_ids: list[str]
    reasoning: list[str]


class InvestigationRead(BaseModel):
    id: str
    question: str
    status: InvestigationStatus
    strategy: dict[str, Any]
    matched_chunk_ids: list[str]
    answer: dict[str, Any]
    confidence: float
    response_time_ms: int
    created_at: datetime
    updated_at: datetime


class MetricsRead(BaseModel):
    files_uploaded: int
    chunks: int
    embedding_count: int
    average_response_time_ms: float
    average_confidence: float
