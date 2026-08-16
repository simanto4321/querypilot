import { useEffect, useMemo, useState } from "react";
import { api, type Chart, type QueryState, type TableMeta } from "./api";

const EXAMPLES = [
  "Total revenue",
  "Revenue by month",
  "Revenue by category",
  "Top 5 products",
  "Top customers",
  "Orders by status",
  "Average order value",
  "Customers by country",
  "List customers",
];

function StatusBadge({ status }: { status: QueryState["status"] }) {
  const label = status.replace("_", " ");
  return <span className={`status ${status}`}>{label}</span>;
}

function BarChart({ chart }: { chart: Chart }) {
  const max = Math.max(...chart.points.map((p) => p.value), 1);
  return (
    <div className="chart">
      {chart.points.map((p, i) => (
        <div className="bar-row" key={i}>
          <span className="bar-label" title={p.label}>{p.label}</span>
          <span className="bar-track">
            <span className="bar-fill" style={{ width: `${(p.value / max) * 100}%` }} />
          </span>
          <span className="bar-val mono">{p.value.toLocaleString()}</span>
        </div>
      ))}
    </div>
  );
}

function ResultTable({ columns, rows }: { columns: string[]; rows: (string | number | null)[][] }) {
  return (
    <table>
      <thead>
        <tr>{columns.map((c) => <th key={c}>{c}</th>)}</tr>
      </thead>
      <tbody>
        {rows.slice(0, 50).map((r, i) => (
          <tr key={i}>
            {r.map((v, j) => (
              <td key={j} className={typeof v === "number" ? "mono" : ""}>{v === null ? "∅" : String(v)}</td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function Trace({ result }: { result: QueryState }) {
  return (
    <div className="trace">
      {result.trace.map((s, i) => (
        <div className="trace-step" key={i}>
          <span className={`trace-dot ${s.status}`} />
          <span className="trace-name">{s.name}</span>
          <span className="trace-detail">{s.detail}</span>
          <span className="trace-ms">{s.duration_ms.toFixed(1)}ms</span>
        </div>
      ))}
    </div>
  );
}

export default function App() {
  const [schema, setSchema] = useState<TableMeta[]>([]);
  const [question, setQuestion] = useState("");
  const [result, setResult] = useState<QueryState | null>(null);
  const [history, setHistory] = useState<QueryState[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.schema().then(setSchema).catch((e) => setError(String(e)));
    api.history().then(setHistory).catch(() => {});
  }, []);

  const submit = async (q: string) => {
    const query = q.trim();
    if (!query) return;
    setLoading(true);
    setError(null);
    try {
      const res = await api.ask(query);
      setResult(res);
      setHistory(await api.history());
    } catch (e) {
      setError(e instanceof Error ? e.message : "Request failed");
    } finally {
      setLoading(false);
    }
  };

  const decide = async (approve: boolean) => {
    if (!result) return;
    const res = approve ? await api.approve(result.id) : await api.reject(result.id);
    setResult(res);
    setHistory(await api.history());
  };

  const rowsPreview = useMemo(() => (result?.rows.length ?? 0), [result]);

  return (
    <div className="app">
      <div className="topbar">
        <div className="brand">
          <div className="logo">🧭</div>
          <div>
            <h1>QueryPilot</h1>
            <p>Ask your warehouse in plain English — safely</p>
          </div>
        </div>
        <span className="provider-tag">read-only · human-in-the-loop</span>
      </div>

      <div className="layout">
        <div>
          <div className="card">
            <div className="ask-row">
              <input
                className="ask-input"
                placeholder="e.g. revenue by category, top 5 products, orders by status…"
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && submit(question)}
              />
              <button className="btn" disabled={loading} onClick={() => submit(question)}>
                {loading ? "Thinking…" : "Ask"}
              </button>
            </div>
            <div className="chips">
              {EXAMPLES.map((ex) => (
                <span key={ex} className="chip" onClick={() => { setQuestion(ex); submit(ex); }}>{ex}</span>
              ))}
            </div>
          </div>

          {error && <div className="card error-box">Could not reach API: {error}</div>}

          {result && (
            <div className="card">
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <strong>{result.question}</strong>
                <StatusBadge status={result.status} />
              </div>
              <div className="rationale">{result.rationale}</div>

              {result.sql && (
                <>
                  <div className="sql-label">Generated SQL · provider: {result.provider} · confidence {(result.confidence * 100).toFixed(0)}%</div>
                  <pre className="sql">{result.safe_sql || result.sql}</pre>
                </>
              )}

              {result.status === "needs_approval" && (
                <div className="approval">
                  <div className="title">⚠ Human approval required</div>
                  <div className="muted">
                    This query returns row-level data (≈ {result.estimated_rows.toLocaleString()} rows scanned).
                    Governance policy holds it for review before it runs.
                  </div>
                  <div className="actions">
                    <button className="mini approve" onClick={() => decide(true)}>Approve &amp; run</button>
                    <button className="mini reject" onClick={() => decide(false)}>Reject</button>
                  </div>
                </div>
              )}

              {result.chart && (
                <>
                  <div className="sql-label">Chart</div>
                  <BarChart chart={result.chart} />
                </>
              )}

              {result.status === "completed" && result.columns.length > 0 && (
                <>
                  <div className="sql-label">Results · {rowsPreview} row(s)</div>
                  <ResultTable columns={result.columns} rows={result.rows} />
                </>
              )}

              <div className="sql-label">Execution trace</div>
              <Trace result={result} />
            </div>
          )}
        </div>

        <div>
          <div className="card">
            <h2>Schema</h2>
            {schema.map((t) => (
              <div className="schema-table" key={t.table}>
                <div className="t">{t.table}</div>
                <div className="d">{t.description}</div>
                <div className="schema-col">{t.columns.map((c) => c.name).join(", ")}</div>
              </div>
            ))}
          </div>

          <div className="card">
            <h2>Recent queries</h2>
            {history.length === 0 ? (
              <p className="muted">No queries yet.</p>
            ) : (
              history.map((h) => (
                <div className="hist-item" key={h.id + h.created_at} onClick={() => setResult(h)}>
                  <span>{h.question}</span>
                  <StatusBadge status={h.status} />
                </div>
              ))
            )}
          </div>
        </div>
      </div>

      <div className="footer">
        QueryPilot · built by{" "}
        <a href="https://github.com/simanto4321" target="_blank" rel="noreferrer">Mehedi Ashraf Simanto</a>
      </div>
    </div>
  );
}
