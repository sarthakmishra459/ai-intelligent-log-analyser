from enum import StrEnum


class LogSeverity(StrEnum):
    debug = "debug"
    info = "info"
    warning = "warning"
    error = "error"
    critical = "critical"
    unknown = "unknown"


class LogSourceType(StrEnum):
    system = "system"
    nginx = "nginx"
    apache = "apache"
    postgresql = "postgresql"
    redis = "redis"
    docker = "docker"
    application = "application"
    kubernetes = "kubernetes"
    spring_boot = "spring_boot"
    nodejs = "nodejs"
    unknown = "unknown"


class InvestigationStatus(StrEnum):
    queued = "queued"
    running = "running"
    completed = "completed"
    failed = "failed"
