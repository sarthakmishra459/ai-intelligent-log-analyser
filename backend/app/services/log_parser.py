import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

from app.core.config import Settings
from app.domain.enums import LogSeverity, LogSourceType

ERROR_PATTERNS = re.compile(
    r"\b(error|err|exception|fatal|panic|segfault|traceback|crash|oom|killed|failed|timeout|refused|unavailable)\b",
    re.IGNORECASE,
)
WARNING_PATTERNS = re.compile(r"\b(warn|warning|retry|slow|degraded|throttle|backoff)\b", re.IGNORECASE)


@dataclass(frozen=True)
class ParsedLine:
    line_number: int
    text: str
    severity: LogSeverity
    source_type: LogSourceType


@dataclass(frozen=True)
class ParsedChunk:
    chunk_index: int
    start_line: int
    end_line: int
    text: str
    severity: LogSeverity
    source_type: LogSourceType
    error_count: int
    warning_count: int
    metadata: dict


class LogParser:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def detect_source_type(self, filename: str, sample: str) -> LogSourceType:
        haystack = f"{filename}\n{sample[:5000]}".lower()
        checks: list[tuple[LogSourceType, tuple[str, ...]]] = [
            (LogSourceType.nginx, ("nginx", "upstream", "client:", "server:", "502", "gateway")),
            (LogSourceType.apache, ("apache", "httpd", "mod_", "[client ")),
            (LogSourceType.postgresql, ("postgres", "postgresql", "statement:", "checkpoint", "deadlock")),
            (LogSourceType.redis, ("redis", "redis-server", "rdb", "aof", "oom command")),
            (LogSourceType.kubernetes, ("kubernetes", "kubelet", "pod/", "containerstatus", "crashloopbackoff")),
            (LogSourceType.docker, ("docker", "container", "dockerd", "containerd")),
            (LogSourceType.spring_boot, ("spring", "tomcat", "hikari", "org.springframework")),
            (LogSourceType.nodejs, ("node", "npm", "express", "javascript", "unhandledrejection")),
            (LogSourceType.system, ("kernel", "systemd", "oom-killer", "sshd", "cron")),
        ]
        for source_type, needles in checks:
            if any(needle in haystack for needle in needles):
                return source_type
        return LogSourceType.application

    def parse_file(self, path: Path) -> tuple[LogSourceType, list[ParsedLine], list[ParsedChunk]]:
        raw_text = path.read_text(encoding="utf-8", errors="replace")
        source_type = self.detect_source_type(path.name, raw_text)
        parsed_lines = [
            ParsedLine(
                line_number=index,
                text=line.rstrip("\n"),
                severity=self._detect_severity(line),
                source_type=source_type,
            )
            for index, line in enumerate(raw_text.splitlines(), start=1)
            if line.strip()
        ]
        chunks = self._chunk_lines(parsed_lines, source_type, path.name)
        return source_type, parsed_lines, chunks

    def _chunk_lines(
        self,
        lines: list[ParsedLine],
        source_type: LogSourceType,
        filename: str,
    ) -> list[ParsedChunk]:
        if not lines:
            return []

        chunks: list[ParsedChunk] = []
        target = self.settings.chunk_target_lines
        overlap = min(self.settings.chunk_overlap_lines, target - 1)
        cursor = 0
        chunk_index = 0
        while cursor < len(lines):
            window = lines[cursor : cursor + target]
            text = "\n".join(line.text for line in window)
            error_count = sum(1 for line in window if line.severity in {LogSeverity.error, LogSeverity.critical})
            warning_count = sum(1 for line in window if line.severity == LogSeverity.warning)
            severity = self._rollup_severity(window)
            digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
            chunks.append(
                ParsedChunk(
                    chunk_index=chunk_index,
                    start_line=window[0].line_number,
                    end_line=window[-1].line_number,
                    text=text,
                    severity=severity,
                    source_type=source_type,
                    error_count=error_count,
                    warning_count=warning_count,
                    metadata={
                        "filename": filename,
                        "sha256": digest,
                        "line_count": len(window),
                        "signals": self._extract_signals(text),
                    },
                )
            )
            chunk_index += 1
            cursor += target - overlap
        return chunks

    def _detect_severity(self, text: str) -> LogSeverity:
        normalized = text.lower()
        if re.search(r"\b(fatal|critical|panic|segfault|oom-killer|crashloopbackoff)\b", normalized):
            return LogSeverity.critical
        if ERROR_PATTERNS.search(text):
            return LogSeverity.error
        if WARNING_PATTERNS.search(text):
            return LogSeverity.warning
        if re.search(r"\b(debug|trace)\b", normalized):
            return LogSeverity.debug
        if normalized.strip():
            return LogSeverity.info
        return LogSeverity.unknown

    def _rollup_severity(self, lines: list[ParsedLine]) -> LogSeverity:
        severities = [line.severity for line in lines]
        for severity in (LogSeverity.critical, LogSeverity.error, LogSeverity.warning, LogSeverity.info):
            if severity in severities:
                return severity
        return LogSeverity.unknown

    def _extract_signals(self, text: str) -> list[str]:
        signals: list[str] = []
        signal_patterns = {
            "http_5xx": r"\b5\d\d\b",
            "timeout": r"\b(timeout|timed out|deadline exceeded)\b",
            "memory": r"\b(oom|out of memory|memory pressure|heap)\b",
            "database": r"\b(deadlock|checkpoint|vacuum|connection pool|slow query)\b",
            "dependency": r"\b(connection refused|dns|upstream|dependency|service unavailable)\b",
            "disk": r"\b(no space left|disk full|i/o error)\b",
            "cpu": r"\b(cpu|load average|throttl)\b",
        }
        for signal, pattern in signal_patterns.items():
            if re.search(pattern, text, re.IGNORECASE):
                signals.append(signal)
        return signals
