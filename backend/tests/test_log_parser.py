from app.core.config import Settings
from app.domain.enums import LogSeverity, LogSourceType
from app.services.log_parser import LogParser


def test_parser_detects_nginx_errors(tmp_path):
    path = tmp_path / "nginx.log"
    path.write_text(
        "2026/06/29 [error] connect() failed (111: Connection refused) while connecting to upstream\n"
        '10.0.0.1 - - "GET /api HTTP/1.1" 502 157\n',
        encoding="utf-8",
    )
    settings = Settings(project_root=tmp_path, chunk_target_lines=20, chunk_overlap_lines=0)
    source_type, lines, chunks = LogParser(settings).parse_file(path)
    assert source_type == LogSourceType.nginx
    assert len(lines) == 2
    assert chunks[0].severity == LogSeverity.error
    assert chunks[0].error_count == 1
    assert "http_5xx" in chunks[0].metadata["signals"]
