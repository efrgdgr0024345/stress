import { useEffect, useState } from "react";
import {
  Activity,
  AlertCircle,
  Download,
  Pause,
  Play,
  RefreshCw,
  Search,
  Copy,
  ChevronRight,
} from "lucide-react";
import { api } from "./types";
import { appPath } from "./paths";
import { browserSnapshot, flushDiagnostics } from "./diagnostics";
import "./logs.css";
type Entry = {
  id: number;
  timestamp: string;
  level: string;
  source: string;
  event: string;
  request_id: string | null;
  actor_id: string | null;
  tenant: string | null;
  project_id: string | null;
  release: string;
  pid: number;
  details: Record<string, unknown>;
};
type Report = {
  events: Entry[];
  totals: Record<string, number>;
  stored_events: number;
  next_before: number | null;
  retention_days: number;
  max_events: number;
  dropped_in_this_process: number;
};
const timestamp = (text: string) =>
  new Date(text).toLocaleString("en-AU", {
    timeZone: "Australia/Sydney",
    hour12: false,
  });
export function SystemLogs() {
  const [report, setReport] = useState<Report | null>(null),
    [entries, setEntries] = useState<Entry[]>([]),
    [selected, setSelected] = useState<Entry | null>(null);
  const [search, setSearch] = useState(""),
    [query, setQuery] = useState(""),
    [level, setLevel] = useState(""),
    [source, setSource] = useState(""),
    [hours, setHours] = useState("24"),
    [live, setLive] = useState(true),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [copied, setCopied] = useState(false);
  const params = new URLSearchParams({ q: query, level, source, hours });
  const fetchLogs = async (older = false) => {
    setBusy(true);
    try {
      const parameters = new URLSearchParams(params);
      if (older && report?.next_before)
        parameters.set("before", String(report.next_before));
      const result = await api<Report>(`/system/logs?${parameters}`);
      setReport(result);
      setEntries((previous) =>
        older ? [...previous, ...result.events] : result.events,
      );
      setError("");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  useEffect(() => {
    const timer = setTimeout(() => setQuery(search), 300);
    return () => clearTimeout(timer);
  }, [search]);
  useEffect(() => {
    let active = true;
    const load = async () => {
      try {
        const result = await api<Report>(`/system/logs?${params}`);
        if (active) {
          setReport(result);
          setEntries(result.events);
          setError("");
        }
      } catch (e) {
        if (active) setError((e as Error).message);
      }
    };
    void load();
    return () => {
      active = false;
    };
  }, [query, level, source, hours]);
  useEffect(() => {
    if (!live || busy) return;
    const timer = setInterval(() => {
      if (document.visibilityState === "visible") void fetchLogs();
    }, 5000);
    return () => clearInterval(timer);
  }, [live, busy, query, level, source, hours]);
  const download = async () => {
    setBusy(true);
    try {
      await flushDiagnostics();
      const response = await fetch(
        appPath(`api/v1/system/logs/export?${params}`),
        { credentials: "same-origin" },
      );
      if (!response.ok) throw new Error("Could not download diagnostics");
      const data = {
        ...(await response.json()),
        browser_buffer: browserSnapshot(),
      };
      const url = URL.createObjectURL(
        new Blob([JSON.stringify(data, null, 2)], { type: "application/json" }),
      );
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = "caesar-diagnostics.json";
      anchor.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="page-content diagnostic-page">
      <div className="page-heading">
        <div>
          <div className="eyebrow">SYSTEM DIAGNOSTICS</div>
          <h1>
            Logs<span className="heading-dot">.</span>
          </h1>
          <p>
            Follow requests, drawing operations and updates. Share one
            diagnostic file when you need help.
          </p>
        </div>
        <div className="heading-actions">
          <button
            className="button secondary"
            disabled={busy}
            onClick={() => void fetchLogs()}
          >
            <RefreshCw size={16} />
            Refresh
          </button>
          <button
            className="button primary"
            disabled={busy}
            onClick={() => void download()}
          >
            <Download size={16} />
            Download diagnostics
          </button>
        </div>
      </div>
      {error && (
        <div className="diagnostic-alert" role="alert">
          <AlertCircle size={18} />
          {error}
        </div>
      )}
      {!!report?.dropped_in_this_process && (
        <div className="diagnostic-alert" role="alert">
          Some events could not be stored by this server process. Check private
          storage space and database permissions.
        </div>
      )}
      <div className="diagnostic-summary">
        {[
          ["Events retained", report?.stored_events || 0, "blue"],
          ["Errors", report?.totals.ERROR || 0, "red"],
          ["Warnings", report?.totals.WARNING || 0, "amber"],
          [
            "Info + debug",
            (report?.totals.INFO || 0) + (report?.totals.DEBUG || 0),
            "green",
          ],
        ].map(([title, count, tone]) => (
          <div className={`diagnostic-metric ${tone}`} key={title}>
            <span>
              <Activity size={15} />
              {title}
            </span>
            <strong>{count}</strong>
            <small>
              {title === "Events retained"
                ? "Across retained history"
                : "Within selected time range"}
            </small>
          </div>
        ))}
      </div>
      <div className="diagnostic-toolbar">
        <label className="diagnostic-search">
          <Search size={16} />
          <input
            aria-label="Search logs"
            placeholder="Search event, request ID or project ID…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </label>
        <select
          aria-label="Log level"
          value={level}
          onChange={(e) => setLevel(e.target.value)}
        >
          <option value="">All levels</option>
          {["DEBUG", "INFO", "WARNING", "ERROR"].map((v) => (
            <option key={v}>{v}</option>
          ))}
        </select>
        <select
          aria-label="Log source"
          value={source}
          onChange={(e) => setSource(e.target.value)}
        >
          <option value="">All sources</option>
          {["server", "browser", "updater"].map((v) => (
            <option key={v}>{v}</option>
          ))}
        </select>
        <select
          aria-label="Log time range"
          value={hours}
          onChange={(e) => setHours(e.target.value)}
        >
          <option value="1">Last hour</option>
          <option value="24">Last 24 hours</option>
          <option value="168">Last 7 days</option>
        </select>
        <button
          className={`button secondary diagnostic-live ${live ? "on" : ""}`}
          aria-pressed={live}
          onClick={() => setLive(!live)}
        >
          {live ? <Pause size={14} /> : <Play size={14} />}{" "}
          {live ? "Live" : "Paused"}
        </button>
      </div>
      <div className="diagnostic-layout">
        <div className="diagnostic-list">
          <div className="diagnostic-list-heading">
            Event timeline <small>Times: Australia/Sydney · newest first</small>
          </div>
          {!entries.length && (
            <div className="empty">
              <Activity />
              <h3>No matching events</h3>
              <p>
                Try a different filter or perform an action in the workspace.
              </p>
            </div>
          )}
          {entries.map((entry) => (
            <button
              key={entry.id}
              className={`diagnostic-row ${selected?.id === entry.id ? "selected" : ""}`}
              onClick={() => {
                setSelected(entry);
                setCopied(false);
                setLive(false);
              }}
            >
              <span className={`diagnostic-level ${entry.level.toLowerCase()}`}>
                {entry.level}
              </span>
              <span className="diagnostic-row-main">
                <strong>{entry.event}</strong>
                <small>
                  {entry.source} · {timestamp(entry.timestamp)}
                  {entry.details.status
                    ? ` · HTTP ${entry.details.status}`
                    : ""}
                  {typeof entry.details.duration_ms === "number"
                    ? ` · ${entry.details.duration_ms} ms`
                    : ""}
                </small>
                {entry.request_id && (
                  <code>Request {entry.request_id.slice(0, 12)}…</code>
                )}
              </span>
              <ChevronRight size={15} />
            </button>
          ))}
          {report?.next_before && (
            <button
              className="button secondary"
              disabled={busy}
              onClick={() => {
                setLive(false);
                void fetchLogs(true);
              }}
            >
              Load older events
            </button>
          )}
        </div>
        <aside className="diagnostic-detail">
          {selected ? (
            <>
              <div className="diagnostic-detail-heading">
                <h2>Event details</h2>
                <button
                  className="icon-button"
                  aria-label="Copy log event"
                  onClick={() => {
                    navigator.clipboard
                      .writeText(JSON.stringify(selected, null, 2))
                      .then(() => setCopied(true))
                      .catch(() =>
                        setError(
                          "Clipboard unavailable; use the diagnostic download.",
                        ),
                      );
                  }}
                >
                  <Copy size={16} />
                </button>
              </div>
              {copied && <p role="status">Event copied</p>}
              <p>
                <span
                  className={`diagnostic-level ${selected.level.toLowerCase()}`}
                >
                  {selected.level}
                </span>{" "}
                {selected.event}
              </p>
              <dl>
                <dt>Time (Sydney)</dt>
                <dd>{timestamp(selected.timestamp)}</dd>
                <dt>Time (UTC)</dt>
                <dd>{selected.timestamp}</dd>
                <dt>Request ID</dt>
                <dd>{selected.request_id || "Background operation"}</dd>
                <dt>Project ID</dt>
                <dd>{selected.project_id || "Not project-specific"}</dd>
                <dt>Actor / tenant</dt>
                <dd>
                  {selected.actor_id || "System / unauthenticated"} ·{" "}
                  {selected.tenant || "—"}
                </dd>
                <dt>Release / worker PID</dt>
                <dd>
                  {selected.release} · {selected.pid}
                </dd>
              </dl>
              <h3>Structured details</h3>
              <pre>{JSON.stringify(selected.details, null, 2)}</pre>
              <p>
                Use the request ID to find related browser and server events.
                Client reports are marked untrusted.
              </p>
            </>
          ) : (
            <div className="diagnostic-detail-empty">
              <Activity size={26} />
              <h2>Select an event</h2>
              <p>
                See request timing, safe error frames, operation counts and
                release details here.
              </p>
            </div>
          )}
        </aside>
      </div>
      <p className="diagnostic-note">
        Detailed application events, not raw documents or provider OS logs.
        Passwords, session headers, request bodies, query values, filenames and
        drawing text are excluded. Up to 20,000 events (approximately), 7 days;
        downloads include up to 2,000 matching events plus this tab’s pending
        browser events. Review files before sharing.
      </p>
    </div>
  );
}
