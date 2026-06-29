from pathlib import Path

from app.core.config import Settings


def test_relative_sqlite_database_url_is_resolved_from_project_root(tmp_path: Path) -> None:
    settings = Settings(project_root=tmp_path, database_url="sqlite+aiosqlite:///./data/test.db")

    assert settings.resolved_database_url == f"sqlite+aiosqlite:///{(tmp_path / 'data' / 'test.db').resolve().as_posix()}"
