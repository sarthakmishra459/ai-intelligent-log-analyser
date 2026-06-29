import {
  AlertTriangle,
  Database,
  FileUp,
  Gauge,
  RefreshCcw,
  Search,
  Server,
  Sparkles,
  Upload,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { api } from "./lib/api";
import type {
  Investigation,
  LogFile,
  Metrics,
  SearchResult,
} from "./types/api";

const examples = [
  "Why are users getting 502?",
  "Why did server crash?",
  "Why was memory high?",
  "Why is PostgreSQL slow?",
];

const emptyMetrics: Metrics = {
  files_uploaded: 0,
  chunks: 0,
  embedding_count: 0,
  average_response_time_ms: 0,
  average_confidence: 0,
};

export function App() {
  const [metrics, setMetrics] = useState<Metrics>(emptyMetrics);
  const [files, setFiles] = useState<LogFile[]>([]);
  const [query, setQuery] = useState(examples[0]);
  const [results, setResults] = useState<SearchResult[]>([]);
  const [question, setQuestion] = useState(examples[0]);
  const [investigation, setInvestigation] = useState<Investigation | null>(
    null,
  );
  const [selected, setSelected] = useState<SearchResult | null>(null);
  const [selectedFileId, setSelectedFileId] = useState<string | null>(null);
  const [dockerContainer, setDockerContainer] = useState("");
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState(
    "Demo logs load automatically when the API starts.",
  );
  const [progress, setProgress] = useState<string[]>([]);

  const refresh = async () => {
    const [nextMetrics, nextFiles] = await Promise.all([
      api.metrics(),
      api.files(),
    ]);
    setMetrics(nextMetrics);
    setFiles(nextFiles);
  };

  useEffect(() => {
    refresh().catch((error) => setStatus(error.message));
  }, []);

  const highlightedTerms = useMemo(
    () => query.split(/\s+/).filter((term) => term.length > 3),
    [query],
  );

  async function upload(filesToUpload: FileList | null) {
    if (!filesToUpload?.length) return;
    await run("Uploading and indexing logs", async () => {
      await api.upload(filesToUpload);
      await refresh();
    });
  }

  async function search() {
    await run("Searching indexed log chunks", async () => {
      const nextResults = await api.search(query);
      setResults(nextResults);
      setSelected(nextResults[0] ?? null);
    });
  }

  async function ask() {
    await run("Running AI investigation", async () => {
      setProgress(["Planner selected an investigation strategy"]);
      const answer = await api.ask(question, selectedFileId);
      setInvestigation(answer);
      setProgress([
        "Planner",
        "Semantic search",
        "Root cause reasoning",
        "Summary",
      ]);
      const evidence = await api.search(question);
      setResults(evidence);
      setSelected(evidence[0] ?? null);
      await refresh();
    });
  }

  async function collectDocker() {
    if (!dockerContainer.trim()) return;
    await run("Collecting Docker logs", async () => {
      await api.docker(dockerContainer.trim());
      setDockerContainer("");
      await refresh();
    });
  }

  async function run(label: string, action: () => Promise<void>) {
    setBusy(true);
    setStatus(label);
    try {
      await action();
      setStatus("Ready");
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Request failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="min-h-screen">
      <header className="border-b border-line bg-white">
        <div className="mx-auto flex max-w-7xl flex-col gap-3 px-4 py-4 md:flex-row md:items-center md:justify-between">
          <div>
            <h1 className="text-2xl font-semibold tracking-normal text-ink">
              Intelligent Log Analysis
            </h1>
            <p className="text-sm text-slate-600">{status}</p>
          </div>
          <button
            className="inline-flex h-10 items-center gap-2 rounded-md border border-line bg-white px-3 text-sm font-medium hover:bg-panel disabled:opacity-50"
            disabled={busy}
            onClick={() => refresh().catch((error) => setStatus(error.message))}
            title="Refresh dashboard"
          >
            <RefreshCcw size={16} /> Refresh
          </button>
        </div>
      </header>

      <section className="mx-auto grid max-w-7xl gap-4 px-4 py-5 md:grid-cols-5">
        <Metric
          icon={<FileUp size={18} />}
          label="Files"
          value={metrics.files_uploaded}
        />
        <Metric
          icon={<Database size={18} />}
          label="Chunks"
          value={metrics.chunks}
        />
        <Metric
          icon={<Sparkles size={18} />}
          label="Embeddings"
          value={metrics.embedding_count}
        />
        <Metric
          icon={<Gauge size={18} />}
          label="Avg response"
          value={`${metrics.average_response_time_ms} ms`}
        />
        <Metric
          icon={<AlertTriangle size={18} />}
          label="Confidence"
          value={`${Math.round(metrics.average_confidence * 100)}%`}
        />
      </section>

      <section className="mx-auto grid max-w-7xl gap-4 px-4 pb-6 lg:grid-cols-[360px_1fr]">
        <aside className="space-y-4">
          <Panel title="Inputs">
            <label className="flex min-h-24 cursor-pointer flex-col items-center justify-center rounded-md border border-dashed border-slate-400 bg-white px-4 py-5 text-center hover:bg-panel">
              <Upload size={24} />
              <span className="mt-2 text-sm font-medium">Upload log files</span>
              <span className="text-xs text-slate-500">
                Multiple .log, .txt, .json, .ndjson files
              </span>
              <input
                className="hidden"
                type="file"
                multiple
                onChange={(event) => upload(event.target.files)}
              />
            </label>
            <div className="mt-3 flex gap-2">
              <input
                className="h-10 min-w-0 flex-1 rounded-md border border-line px-3 text-sm"
                placeholder="container name"
                value={dockerContainer}
                onChange={(event) => setDockerContainer(event.target.value)}
              />
              <button
                className="h-10 rounded-md bg-ink px-3 text-sm font-medium text-white disabled:opacity-50"
                disabled={busy}
                onClick={collectDocker}
              >
                <Server size={16} />
              </button>
            </div>
          </Panel>

          <Panel title="Files">
            <div className="max-h-72 overflow-auto">
              {files.map((file) => (
                <div
                  key={file.id}
                  className="border-b border-line py-2 last:border-0"
                >
                  <div className="truncate text-sm font-medium">
                    {file.filename}
                  </div>
                  <div className="text-xs text-slate-500">
                    {file.source_type} · {file.line_count} lines ·{" "}
                    {Math.round(file.size_bytes / 1024)} KB
                  </div>
                </div>
              ))}
            </div>
          </Panel>
        </aside>

        <div className="space-y-4">
          <Panel title="Natural Language Search">
            <div className="flex flex-col gap-2 md:flex-row">
              <input
                className="h-11 flex-1 rounded-md border border-line px-3"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
              />
              <button
                className="inline-flex h-11 items-center justify-center gap-2 rounded-md bg-accent px-4 font-medium text-white disabled:opacity-50"
                disabled={busy}
                onClick={search}
              >
                <Search size={18} /> Search
              </button>
            </div>
          </Panel>

          <Panel title="Live Investigation">
            {/* Single layout container holding all form elements */}
            <div className="flex flex-col gap-3 md:grid md:grid-cols-12 md:items-center">
              {/* Question dropdown (takes 4 columns on desktop) */}
              <div className="md:col-span-4">
                <select
                  className="h-11 w-full rounded-md border border-line px-3"
                  value={question}
                  onChange={(event) => setQuestion(event.target.value)}
                >
                  {examples.map((example) => (
                    <option key={example}>{example}</option>
                  ))}
                </select>
              </div>

              {/* Question input field (takes 8 columns on desktop) */}
              <div className="md:col-span-8">
                <input
                  className="h-11 w-full rounded-md border border-line px-3"
                  value={question}
                  onChange={(event) => setQuestion(event.target.value)}
                />
              </div>

              {/* File select dropdown (takes 4 columns on desktop, lines up with the select above) */}
              <div className="md:col-span-4">
                <select
                  className="h-11 w-full rounded-md border border-line px-3"
                  value={selectedFileId ?? ""}
                  onChange={(event) =>
                    setSelectedFileId(event.target.value || null)
                  }
                >
                  <option value="">All files</option>
                  {files.map((file) => (
                    <option key={file.id} value={file.id}>
                      {file.filename}
                    </option>
                  ))}
                </select>
              </div>

              {/* Investigate Button (takes 2 columns on desktop) */}
              <div className="md:col-span-2">
                <button
                  className="h-11 w-full rounded-md bg-ink px-4 font-medium text-white disabled:opacity-50"
                  disabled={busy}
                  onClick={ask}
                >
                  Investigate
                </button>
              </div>
            </div>

            {/* Status Steps Row */}
            <div className="mt-4 grid grid-cols-2 gap-2 md:grid-cols-4">
              {["Planner", "Searching", "Reasoning", "Summary"].map((step) => (
                <div
                  key={step}
                  className={`rounded-md border px-3 py-2 text-sm text-center md:text-left ${
                    progress
                      .join(" ")
                      .toLowerCase()
                      .includes(step.toLowerCase().replace("ing", ""))
                      ? "border-accent bg-teal-50 text-accent"
                      : "border-line bg-panel text-slate-600"
                  }`}
                >
                  {step}
                </div>
              ))}
            </div>

            {/* Results Panel */}
            {investigation?.answer ? (
              <div className="mt-4 grid gap-3">
                <p className="text-sm text-slate-700">
                  {investigation.answer.incident_summary}
                </p>
                <div className="rounded-md border border-line bg-panel p-3 text-sm">
                  <div className="font-semibold">Root cause</div>
                  <div>{investigation.answer.root_cause}</div>
                </div>
                <div className="grid gap-2 md:grid-cols-2">
                  {investigation.answer.recommendations.map((item) => (
                    <div
                      key={item}
                      className="rounded-md border border-line p-3 text-sm"
                    >
                      {item}
                    </div>
                  ))}
                </div>
              </div>
            ) : null}
          </Panel>

          <Panel title="Matching Logs">
            <div className="grid gap-4 lg:grid-cols-[320px_1fr]">
              <div className="max-h-96 overflow-auto border-r border-line pr-3">
                {results.map((result) => (
                  <button
                    key={result.chunk.id}
                    className={`mb-2 block w-full rounded-md border p-3 text-left text-sm hover:bg-panel ${selected?.chunk.id === result.chunk.id ? "border-accent bg-teal-50" : "border-line bg-white"}`}
                    onClick={() => setSelected(result)}
                  >
                    <div className="font-medium">
                      {result.chunk.source_type} lines {result.chunk.start_line}
                      -{result.chunk.end_line}
                    </div>
                    <div className="text-xs text-slate-500">
                      score {result.score.toFixed(3)} ·{" "}
                      {result.chunk.error_count} errors ·{" "}
                      {result.chunk.warning_count} warnings
                    </div>
                  </button>
                ))}
              </div>
              <LogViewer result={selected} terms={highlightedTerms} />
            </div>
          </Panel>
        </div>
      </section>
    </main>
  );
}

function Metric({
  icon,
  label,
  value,
}: {
  icon: React.ReactNode;
  label: string;
  value: string | number;
}) {
  return (
    <div className="rounded-md border border-line bg-white p-4">
      <div className="flex items-center gap-2 text-sm text-slate-500">
        {icon}
        {label}
      </div>
      <div className="mt-2 text-2xl font-semibold">{value}</div>
    </div>
  );
}

function Panel({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section className="rounded-md border border-line bg-white p-4">
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-normal text-slate-500">
        {title}
      </h2>
      {children}
    </section>
  );
}

function LogViewer({
  result,
  terms,
}: {
  result: SearchResult | null;
  terms: string[];
}) {
  if (!result)
    return (
      <div className="min-h-72 rounded-md bg-panel p-4 text-sm text-slate-500">
        Search or investigate to inspect matching log lines.
      </div>
    );
  const lines = result.chunk.text.split("\n");
  return (
    <pre className="min-h-72 max-h-96 overflow-auto rounded-md bg-[#101820] p-4 text-xs leading-5 text-slate-100">
      {lines.map((line, index) => (
        <div key={`${result.chunk.id}-${index}`} className="log-line">
          <span className="mr-3 inline-block w-10 select-none text-right text-slate-500">
            {result.chunk.start_line + index}
          </span>
          <span dangerouslySetInnerHTML={{ __html: highlight(line, terms) }} />
        </div>
      ))}
    </pre>
  );
}

function highlight(line: string, terms: string[]) {
  const escaped = line.replace(
    /[&<>"']/g,
    (char) =>
      ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#039;",
      })[char] ?? char,
  );
  return terms.reduce(
    (value, term) =>
      value.replace(
        new RegExp(`(${escapeRegExp(term)})`, "ig"),
        "<mark>$1</mark>",
      ),
    escaped,
  );
}

function escapeRegExp(value: string) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}
