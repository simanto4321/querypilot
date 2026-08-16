// Typed client for the QueryPilot API.

export interface TraceStep {
  name: string;
  status: "ok" | "fail" | "skip" | "pending";
  duration_ms: number;
  detail: string;
}

export interface ChartPoint {
  label: string;
  value: number;
}

export interface Chart {
  type: "bar";
  x_label: string;
  y_label: string;
  points: ChartPoint[];
}

export interface QueryState {
  id: string;
  question: string;
  provider: string;
  rationale: string;
  confidence: number;
  sql: string;
  safe_sql: string;
  status: "completed" | "needs_approval" | "rejected" | "error" | "pending";
  tables: string[];
  estimated_rows: number;
  columns: string[];
  rows: (string | number | null)[][];
  chart: Chart | null;
  trace: TraceStep[];
  created_at: string;
}

export interface ColumnMeta {
  name: string;
  type: string;
  description: string;
  synonyms: string[];
}

export interface TableMeta {
  table: string;
  description: string;
  synonyms: string[];
  columns: ColumnMeta[];
}

async function json<T>(res: Response): Promise<T> {
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return (await res.json()) as T;
}

export const api = {
  schema: () => fetch("/api/schema").then(json<TableMeta[]>),
  ask: (question: string) =>
    fetch("/api/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question }),
    }).then(json<QueryState>),
  approve: (id: string) => fetch(`/api/approve/${id}`, { method: "POST" }).then(json<QueryState>),
  reject: (id: string) => fetch(`/api/reject/${id}`, { method: "POST" }).then(json<QueryState>),
  history: () => fetch("/api/history").then(json<QueryState[]>),
};
