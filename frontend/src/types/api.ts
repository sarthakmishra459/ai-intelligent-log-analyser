export type LogFile = {
  id: string;
  filename: string;
  source_type: string;
  size_bytes: number;
  line_count: number;
  created_at: string;
};

export type LogChunk = {
  id: string;
  file_id: string;
  chunk_index: number;
  start_line: number;
  end_line: number;
  text: string;
  severity: "debug" | "info" | "warning" | "error" | "critical" | "unknown";
  source_type: string;
  error_count: number;
  warning_count: number;
  metadata_json: Record<string, unknown>;
};

export type SearchResult = {
  chunk: LogChunk;
  score: number;
};

export type Metrics = {
  files_uploaded: number;
  chunks: number;
  embedding_count: number;
  average_response_time_ms: number;
  average_confidence: number;
};

export type IncidentSummary = {
  incident_summary: string;
  root_cause: string;
  recommendations: string[];
  confidence: number;
  evidence_chunk_ids: string[];
  reasoning: string[];
};

export type Investigation = {
  id: string;
  question: string;
  status: "queued" | "running" | "completed" | "failed";
  strategy: Record<string, unknown>;
  matched_chunk_ids: string[];
  answer: IncidentSummary;
  confidence: number;
  response_time_ms: number;
  created_at: string;
  updated_at: string;
};
