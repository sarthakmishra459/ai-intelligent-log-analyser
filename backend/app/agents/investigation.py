import time
from dataclasses import dataclass, field
from typing import TypedDict

from langgraph.graph import END, StateGraph

from app.domain.enums import LogSeverity
from app.domain.schemas import IncidentSummary, SearchResult


class InvestigationState(TypedDict, total=False):
    question: str
    strategy: dict
    search_queries: list[str]
    matches: list[SearchResult]
    root_cause: dict
    summary: IncidentSummary
    events: list[dict]


@dataclass
class PlannerAgent:
    def plan(self, question: str) -> dict:
        normalized = question.lower()
        focus: list[str] = []
        if any(token in normalized for token in ("502", "gateway", "users", "nginx")):
            focus.extend(["http_5xx", "upstream", "dependency"])
        if any(token in normalized for token in ("memory", "oom", "heap", "killed")):
            focus.extend(["memory", "resource_exhaustion"])
        if any(token in normalized for token in ("postgres", "database", "slow", "query")):
            focus.extend(["database", "latency", "connections"])
        if any(token in normalized for token in ("crash", "restart", "pod", "container")):
            focus.extend(["crash", "kubernetes", "container"])
        if not focus:
            focus = ["errors", "warnings", "dependency", "resource_exhaustion"]
        return {
            "objective": "Find the most likely root cause from high-signal log evidence.",
            "focus": sorted(set(focus)),
            "severity_priority": ["critical", "error", "warning", "info"],
        }

    def queries(self, question: str, strategy: dict) -> list[str]:
        focus = " ".join(strategy.get("focus", []))
        return [
            question,
            f"{question} {focus} errors warnings failures",
            f"root cause {focus} timeout exception crash resource exhaustion dependency failure",
        ]


@dataclass
class RootCauseAgent:
    def analyze(self, question: str, matches: list[SearchResult]) -> dict:
        if not matches:
            return {
                "category": "insufficient_evidence",
                "root_cause": "No indexed log chunks matched the question.",
                "confidence": 0.2,
                "reasoning": ["The vector index returned no evidence for the investigation question."],
            }

        signal_scores: dict[str, float] = {
            "memory pressure or OOM termination": 0.0,
            "upstream or dependency failure": 0.0,
            "database latency or connection saturation": 0.0,
            "application exception or crash": 0.0,
            "infrastructure resource exhaustion": 0.0,
        }
        reasoning: list[str] = []
        for result in matches:
            chunk = result.chunk
            text = chunk.text.lower()
            severity_weight = self._severity_weight(chunk.severity)
            score = max(result.score, 0.05) * severity_weight
            memory_tokens = ("oom", "out of memory", "memory pressure", "heap", "killed process")
            dependency_tokens = ("upstream", "connection refused", "service unavailable", "502", "timeout")
            database_tokens = ("deadlock", "slow query", "checkpoint", "too many connections", "connection pool")
            crash_tokens = ("exception", "traceback", "fatal", "panic", "crash", "unhandledrejection")
            resource_tokens = ("cpu", "disk full", "no space left", "i/o error", "throttl")
            if any(token in text for token in memory_tokens):
                signal_scores["memory pressure or OOM termination"] += score
            if any(token in text for token in dependency_tokens):
                signal_scores["upstream or dependency failure"] += score
            if any(token in text for token in database_tokens):
                signal_scores["database latency or connection saturation"] += score
            if any(token in text for token in crash_tokens):
                signal_scores["application exception or crash"] += score
            if any(token in text for token in resource_tokens):
                signal_scores["infrastructure resource exhaustion"] += score
            if chunk.error_count or chunk.warning_count:
                reasoning.append(
                    f"{chunk.source_type.value} lines {chunk.start_line}-{chunk.end_line} contain "
                    f"{chunk.error_count} errors and {chunk.warning_count} warnings."
                )

        category, score = max(signal_scores.items(), key=lambda item: item[1])
        if score <= 0:
            category = "general error cluster"
            score = sum(max(result.score, 0.0) for result in matches[:3]) / max(len(matches[:3]), 1)

        confidence = min(0.95, max(0.35, score / max(len(matches), 1) + 0.35))
        return {
            "category": category,
            "root_cause": self._root_cause_sentence(category, question),
            "confidence": round(confidence, 2),
            "reasoning": reasoning[:6] or ["Relevant chunks were found, but explicit error signatures were limited."],
        }

    def _severity_weight(self, severity: LogSeverity) -> float:
        return {
            LogSeverity.critical: 1.4,
            LogSeverity.error: 1.2,
            LogSeverity.warning: 0.9,
            LogSeverity.info: 0.6,
            LogSeverity.debug: 0.4,
            LogSeverity.unknown: 0.5,
        }[severity]

    def _root_cause_sentence(self, category: str, question: str) -> str:
        return f"The evidence most strongly points to {category} as the cause related to: " f"{question.strip()}"


@dataclass
class SummaryAgent:
    recommendations_by_category: dict[str, list[str]] = field(
        default_factory=lambda: {
            "memory pressure or OOM termination": [
                "Inspect process memory limits and recent traffic or batch spikes.",
                "Capture heap/profile data and raise memory limits only after leak analysis.",
                "Add alerts for sustained memory pressure before the OOM killer intervenes.",
            ],
            "upstream or dependency failure": [
                "Check health, latency, and recent deploys for upstream services.",
                "Tune retry, timeout, and circuit breaker settings to avoid request pileups.",
                "Add synthetic checks for the failing dependency path.",
            ],
            "database latency or connection saturation": [
                "Review slow queries, locks, checkpoints, and connection pool limits.",
                "Correlate PostgreSQL latency with application request spikes.",
                "Add query-level metrics and alerts for connection exhaustion.",
            ],
            "application exception or crash": [
                "Trace the top exception stack to the owning deployment or code path.",
                "Add regression tests for the failing request or background job.",
                "Improve crash-loop alerting with release metadata.",
            ],
            "infrastructure resource exhaustion": [
                "Inspect CPU, disk, and IO saturation on the affected nodes.",
                "Move noisy workloads or adjust resource requests and limits.",
                "Add capacity alerts with enough lead time for remediation.",
            ],
        }
    )

    def summarize(self, question: str, matches: list[SearchResult], root_cause: dict) -> IncidentSummary:
        evidence_ids = [result.chunk.id for result in matches[:8]]
        category = root_cause["category"]
        source_summary = ", ".join(sorted({match.chunk.source_type.value for match in matches[:5]})) or "indexed logs"
        return IncidentSummary(
            incident_summary=(
                f"Investigated '{question.strip()}' across {len(matches)} relevant log chunks. "
                f"The strongest evidence is concentrated in {source_summary}."
            ),
            root_cause=root_cause["root_cause"],
            recommendations=self.recommendations_by_category.get(
                category,
                [
                    "Collect more logs around the incident window.",
                    "Correlate application, infrastructure, and dependency metrics.",
                    "Add structured error fields to improve future investigations.",
                ],
            ),
            confidence=root_cause["confidence"],
            evidence_chunk_ids=evidence_ids,
            reasoning=root_cause["reasoning"],
        )


def build_investigation_graph(search_callable):
    planner = PlannerAgent()
    root_cause_agent = RootCauseAgent()
    summary_agent = SummaryAgent()

    def plan(state: InvestigationState) -> InvestigationState:
        strategy = planner.plan(state["question"])
        return {
            **state,
            "strategy": strategy,
            "search_queries": planner.queries(state["question"], strategy),
            "events": state.get("events", [])
            + [{"step": "planner", "message": "Planner selected investigation focus.", "payload": strategy}],
        }

    async def search(state: InvestigationState) -> InvestigationState:
        started = time.perf_counter()
        matches: list[SearchResult] = []
        seen: set[str] = set()
        for query in state["search_queries"]:
            for result in await search_callable(query, 8):
                if result.chunk.id not in seen:
                    seen.add(result.chunk.id)
                    matches.append(result)
        matches.sort(key=lambda result: result.score, reverse=True)
        return {
            **state,
            "matches": matches[:12],
            "events": state.get("events", [])
            + [
                {
                    "step": "searching",
                    "message": f"Semantic search returned {len(matches[:12])} unique chunks.",
                    "payload": {"elapsed_ms": round((time.perf_counter() - started) * 1000, 2)},
                }
            ],
        }

    def analyze(state: InvestigationState) -> InvestigationState:
        root_cause = root_cause_agent.analyze(state["question"], state.get("matches", []))
        return {
            **state,
            "root_cause": root_cause,
            "events": state.get("events", [])
            + [{"step": "reasoning", "message": "Root cause agent evaluated matched evidence.", "payload": root_cause}],
        }

    def summarize(state: InvestigationState) -> InvestigationState:
        summary = summary_agent.summarize(state["question"], state.get("matches", []), state["root_cause"])
        return {
            **state,
            "summary": summary,
            "events": state.get("events", [])
            + [
                {
                    "step": "summary",
                    "message": "Summary agent produced incident report.",
                    "payload": summary.model_dump(),
                }
            ],
        }

    graph = StateGraph(InvestigationState)
    graph.add_node("planner", plan)
    graph.add_node("search", search)
    graph.add_node("root_cause_analysis", analyze)
    graph.add_node("incident_summary", summarize)
    graph.set_entry_point("planner")
    graph.add_edge("planner", "search")
    graph.add_edge("search", "root_cause_analysis")
    graph.add_edge("root_cause_analysis", "incident_summary")
    graph.add_edge("incident_summary", END)
    return graph.compile()
