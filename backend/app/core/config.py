import json
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


def determine_project_root() -> Path:
    current_file = Path(__file__).resolve()
    for candidate in (current_file.parent, *current_file.parents):
        if (candidate / "data").exists() or (candidate / "pyproject.toml").exists():
            return candidate
    return current_file.parents[2]


class Settings(BaseSettings):
    """Runtime configuration loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "Intelligent Log Analysis Platform"
    app_environment: Literal["local", "test", "staging", "production"] = "local"
    api_prefix: str = "/api/v1"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"

    cors_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: [
            "http://localhost:5173",
            "http://127.0.0.1:5173",
        ]
    )

    database_url: str = "sqlite+aiosqlite:///./data/log_analysis.db"
    database_pool_size: int = Field(default=10, ge=1, le=100)
    database_max_overflow: int = Field(default=20, ge=0, le=100)

    project_root: Path = Field(default_factory=determine_project_root)
    data_dir: Path = Path("data")
    upload_dir: Path = Path("data/uploads")
    demo_data_dir: Path = Path("data/demo_logs")
    faiss_index_dir: Path = Path("data/faiss")

    max_upload_size_mb: int = Field(default=100, ge=1, le=1024)
    allowed_log_extensions: set[str] = Field(
        default_factory=lambda: {".log", ".txt", ".out", ".err", ".json", ".ndjson"}
    )

    chunk_target_lines: int = Field(default=80, ge=10, le=1000)
    chunk_overlap_lines: int = Field(default=10, ge=0, le=250)
    max_search_results: int = Field(default=12, ge=1, le=100)

    embedding_provider: Literal["local", "openai", "deterministic"] = "local"
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    embedding_dimension: int = Field(default=384, ge=64, le=4096)
    openai_api_key: str | None = None
    openai_embedding_model: str = "text-embedding-3-small"

    llm_provider: Literal["openai", "rule_based"] = "rule_based"
    openai_chat_model: str = "gpt-4.1-mini"
    investigation_timeout_seconds: int = Field(default=120, ge=10, le=600)

    auto_load_demo_data: bool = True
    enable_docker_log_collection: bool = True
    docker_log_tail_lines: int = Field(default=5000, ge=100, le=100000)

    request_timeout_seconds: int = Field(default=30, ge=1, le=300)
    stream_heartbeat_seconds: int = Field(default=15, ge=1, le=60)

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: str | list[str]) -> list[str]:
        if isinstance(value, str):
            stripped_value = value.strip()
            if not stripped_value:
                return []
            if stripped_value.startswith("["):
                parsed_value = json.loads(stripped_value)
                if not isinstance(parsed_value, list):
                    raise ValueError("cors_origins JSON value must be a list")
                return [str(origin).strip() for origin in parsed_value if str(origin).strip()]
            return [origin.strip() for origin in stripped_value.split(",") if origin.strip()]
        return value

    @field_validator(
        "data_dir",
        "upload_dir",
        "demo_data_dir",
        "faiss_index_dir",
        mode="after",
    )
    @classmethod
    def ensure_relative_paths(cls, value: Path) -> Path:
        if value.is_absolute():
            return value
        return Path(value)

    @property
    def resolved_data_dir(self) -> Path:
        return self._resolve(self.data_dir)

    @property
    def resolved_database_url(self) -> str:
        return self._resolve_database_url(self.database_url)

    @property
    def resolved_upload_dir(self) -> Path:
        return self._resolve(self.upload_dir)

    @property
    def resolved_demo_data_dir(self) -> Path:
        return self._resolve(self.demo_data_dir)

    @property
    def resolved_faiss_index_dir(self) -> Path:
        return self._resolve(self.faiss_index_dir)

    @property
    def max_upload_size_bytes(self) -> int:
        return self.max_upload_size_mb * 1024 * 1024

    @property
    def should_use_openai_embeddings(self) -> bool:
        return self.embedding_provider == "openai" and bool(self.openai_api_key)

    @property
    def should_use_openai_llm(self) -> bool:
        return self.llm_provider == "openai" and bool(self.openai_api_key)

    def create_runtime_directories(self) -> None:
        for directory in (
            self.resolved_data_dir,
            self.resolved_upload_dir,
            self.resolved_demo_data_dir,
            self.resolved_faiss_index_dir,
        ):
            directory.mkdir(parents=True, exist_ok=True)

        if self.database_url.startswith("sqlite") and ":memory:" not in self.database_url:
            resolved_database_path = self._resolve_database_path(self.database_url)
            if resolved_database_path is not None:
                resolved_database_path.parent.mkdir(parents=True, exist_ok=True)

    def _resolve(self, path: Path) -> Path:
        if path.is_absolute():
            return path
        return self.project_root / path

    def _resolve_database_path(self, database_url: str) -> Path | None:
        for prefix in ("sqlite+aiosqlite:///", "sqlite:///"):
            if database_url.startswith(prefix):
                relative_path = database_url[len(prefix):]
                if not relative_path or relative_path in {":memory:", "file::memory:?cache=shared"}:
                    return None
                if relative_path.startswith("/") or relative_path.startswith("\\"):
                    return Path(relative_path)
                return self.project_root / relative_path
        return None

    def _resolve_database_url(self, database_url: str) -> str:
        if not database_url.startswith("sqlite") or ":memory:" in database_url:
            return database_url

        for prefix in ("sqlite+aiosqlite:///", "sqlite:///"):
            if database_url.startswith(prefix):
                relative_path = database_url[len(prefix):]
                if not relative_path or relative_path in {":memory:", "file::memory:?cache=shared"}:
                    return database_url
                if relative_path.startswith("/") or relative_path.startswith("\\"):
                    return database_url
                resolved_path = (self.project_root / relative_path).resolve()
                return f"{prefix}{resolved_path.as_posix()}"
        return database_url


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.create_runtime_directories()
    return settings
