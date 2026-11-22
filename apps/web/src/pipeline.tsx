import { useEffect, useRef, useState } from "react";
import {
  Activity,
  CheckCircle2,
  FileDown,
  Loader2,
  Play,
  RefreshCw,
  XCircle,
  ArrowUpRight,
  ShieldCheck,
} from "lucide-react";
import { api, type Project, type Artifact } from "./types";
import { appPath } from "./paths";
import "./pipeline.css";

export type PipelineIssue = {
  code: string;
  message?: string;
  severity?: string;
  sheet_id?: string;
  material_id?: string;
  point_id?: string;
  bbox?: number[];
};
export type SourceGraph = {
  sheet_id: string;
  vertices: [number, number][];
  edges: [number, number][];
  page_width: number;
  page_height: number;
};
export type Automation = {
  run_id: string;
  state: string;
  coverage?: Record<string, number>;
  issues: PipelineIssue[];
  graph_proposals?: SourceGraph[];
  inventory_ledger?: unknown[];
  evidence_run?: string;
};
type Run = {
  id: string;
  state: string;
  stage: string;
  revision: number | null;
  error: string | null;
  created: number;
  updated: number;
  progress: {
    pages: number;
    page: number;
    coverage?: Record<string, number>;
    exceptions?: number;
    ocr_pages?: number;
    artifact?: Artifact;
    isolation?: string;
  };
};
type Report = {
  runs: Run[];
  worker: { recent: boolean; at: number | null; executor: string };
};
const steps = [
  ["register", "Register every sheet"],
  ["extract", "Extract source evidence"],
  ["compose", "Prepare engineering proposals"],
  ["export", "Generate native review draft"],
];
export function ProjectPipeline({
  project,
  expanded,
  onRefresh,
  onReview,
  onPreview,
  onOpen,
  onActive,
  administrator,
}: {
  project: Project;
  expanded: boolean;
  onRefresh: (p: Project) => void;
  onReview: (issue: PipelineIssue) => void;
  onPreview: (artifact: Artifact) => void;
  onOpen: () => void;
  onActive: (active: boolean) => void;
  administrator: boolean;
}) {
  const [report, setReport] = useState<Report | null>(null),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  const latest = useRef({ project, onRefresh });
  latest.current = { project, onRefresh };
  useEffect(() => {
    let alive = true,
      inflight = false;
    setReport(null);
    setError("");
    const poll = async () => {
      if (inflight || document.visibilityState === "hidden") return;
      inflight = true;
      try {
        const data = await api<Report>(`/projects/${project.id}/pipeline`);
        if (!alive) return;
        setReport(data);
        setError("");
        const version = data.runs[0]?.revision;
        if (version && version !== latest.current.project.version) {
          const p = await api<Project>(`/projects/${project.id}`);
          if (alive && p.version !== latest.current.project.version)
            latest.current.onRefresh(p);
        }
      } catch (e) {
        if (alive) setError((e as Error).message);
      } finally {
        inflight = false;
      }
    };
    void poll();
    const timer = setInterval(() => void poll(), 2000);
    return () => {
      alive = false;
      clearInterval(timer);
    };
  }, [project.id]);
  const run = report?.runs[0],
    active =
      run && !["DONE", "FAILED", "CANCELLED", "SUPERSEDED"].includes(run.state);
  const [mode, setMode] = useState("isolated");
  useEffect(() => {
    onActive(!!active);
    return () => onActive(false);
  }, [active, onActive]);
  const stage = steps.findIndex(([id]) => id === run?.stage),
    artifact = run?.progress.artifact;
  const automation = project.automation;
  const rerun = async () => {
    setBusy(true);
    try {
      await api(`/projects/${project.id}/pipeline/rerun`, {
        method: "POST",
        body: JSON.stringify({ version: project.version }),
      });
      setError("");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  const cancel = async () => {
    if (!run) return;
    setBusy(true);
    try {
      await api(`/projects/${project.id}/pipeline/${run.id}/cancel`, {
        method: "POST",
      });
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  if (!expanded && !run) return null;
  if (!expanded)
    return (
      <div className={`pipeline-banner ${active ? "working" : ""}`}>
        {active ? (
          <Loader2 size={17} className="spin" />
        ) : (
          <Activity size={17} />
        )}
        <span>
          <strong>
            {active
              ? "Preparing your drawing review"
              : run?.state === "DONE"
                ? "Review draft ready"
                : "Drawing processing needs attention"}
          </strong>
          <small>
            {active
              ? steps[stage]?.[1]
              : `${automation?.coverage?.material_rows ?? 0} material proposals · ${automation?.issues.length ?? 0} source review items`}
          </small>
        </span>
        <button className="text-button" onClick={onOpen}>
          View processing <ArrowUpRight size={14} />
        </button>
      </div>
    );
  return (
    <div className="page-content pipeline-page">
      <div className="page-heading">
        <div>
          <div className="eyebrow">DRAWING TO REVIEW DRAFT</div>
          <h1>
            Project flow<span className="heading-dot">.</span>
          </h1>
          <p>
            Every page accounted for. Evidence and unresolved facts stay
            visible.
          </p>
        </div>
        <div className="heading-actions">
          <button
            className="button secondary"
            disabled={busy || active || !run}
            onClick={() => void rerun()}
          >
            <RefreshCw size={15} />
            Refresh draft
          </button>
          {active && (
            <button
              className="button secondary"
              disabled={busy}
              onClick={() => void cancel()}
            >
              <XCircle size={15} />
              Cancel processing
            </button>
          )}
        </div>
      </div>
      {error && (
        <div className="notice amber" role="alert">
          {error}
        </div>
      )}
      {!run ? (
        <div className="empty-state">
          <Activity size={30} />
          <h3>Start with a drawing</h3>
          <p>
            Upload a PDF to register its sheets, extract evidence and prepare a
            review draft automatically.
          </p>
        </div>
      ) : (
        <>
          {active && !report?.worker.recent && (
            <div className="notice amber">
              Processing is queued. The separate worker has not checked in
              recently. Your upload is retained; configure the processing runner
              on the hosting account.
            </div>
          )}
          {administrator &&
            (!report?.worker.recent || run.state === "WAITING_WORKER") && (
              <div className="pipeline-card" style={{ marginBottom: 20 }}>
                <h3>Set up automatic processing</h3>
                <p>
                  Use an isolated worker where available. The bounded hosting
                  option has resource limits and a clean child environment but
                  runs under the hosting account; use it only for the
                  access-restricted pilot. OCR also needs Tesseract or the
                  container worker.
                </p>
                <label className="form-field">
                  Processing mode
                  <select
                    value={mode}
                    onChange={(e) => setMode(e.target.value)}
                  >
                    <option value="isolated">Isolated worker</option>
                    <option value="bounded_pilot">Bounded hosting pilot</option>
                  </select>
                </label>
                <button
                  className="button secondary"
                  disabled={busy}
                  onClick={async () => {
                    setBusy(true);
                    try {
                      await api("/system/pipeline/config", {
                        method: "POST",
                        body: JSON.stringify({ mode }),
                      });
                      setError("");
                    } catch (e) {
                      setError((e as Error).message);
                    } finally {
                      setBusy(false);
                    }
                  }}
                >
                  Enable processing
                </button>
              </div>
            )}
          {run.error && (
            <div className="notice amber" role="alert">
              <span>
                <b>
                  {run.state === "SUPERSEDED"
                    ? "A newer project revision is retained."
                    : "Processing needs attention."}
                </b>{" "}
                {run.error === "PARSER_ISOLATION_UNAVAILABLE"
                  ? "An isolated worker is required. Configure a supported worker, or the explicitly restricted pilot adapter."
                  : run.error.replaceAll("_", " ").toLowerCase()}{" "}
                <small>
                  Job {run.id}. Open Logs and search this ID for the recorded
                  stages.
                </small>
              </span>
            </div>
          )}
          {run && ["FAILED", "WAITING_WORKER"].includes(run.state) && (
            <button
              className="button secondary"
              disabled={busy}
              style={{ marginBottom: 20 }}
              onClick={async () => {
                setBusy(true);
                try {
                  await api(
                    `/projects/${project.id}/pipeline/${run.id}/retry`,
                    { method: "POST" },
                  );
                  setError("");
                } catch (e) {
                  setError((e as Error).message);
                } finally {
                  setBusy(false);
                }
              }}
            >
              Retry processing
            </button>
          )}
          <div className="pipeline-stages">
            {steps.map(([id, title], i) => {
              const complete = run.state === "DONE" || i < stage;
              return (
                <div
                  key={id}
                  className={`pipeline-stage ${complete ? "complete" : i === stage ? "current" : ""}`}
                >
                  <span className="pipeline-step-icon">
                    {complete ? (
                      <CheckCircle2 size={22} />
                    ) : i === stage && active ? (
                      <Loader2 size={22} className="spin" />
                    ) : (
                      <span>{i + 1}</span>
                    )}
                  </span>
                  <div>
                    <h3>{title}</h3>
                    <p>
                      {id === "extract" && active
                        ? `${run.progress.page} of ${run.progress.pages} pages extracted`
                        : complete
                          ? "Completed"
                          : i === stage
                            ? run.state.replaceAll("_", " ").toLowerCase()
                            : "Waiting for previous stage"}
                    </p>
                  </div>
                </div>
              );
            })}
          </div>
          <div className="pipeline-summary">
            <div className="pipeline-card">
              <ShieldCheck size={21} />
              <h3>Review draft, with evidence</h3>
              <p>
                Extraction proposes facts. Unknown stations and properties stay
                unknown. A completed job is not engineering approval.
              </p>
              <dl>
                {Object.entries(
                  automation?.coverage || run.progress.coverage || {},
                ).map(([key, value]) => (
                  <div key={key}>
                    <dt>{key.replaceAll("_", " ")}</dt>
                    <dd>{value}</dd>
                  </div>
                ))}
              </dl>
            </div>
            <div className="pipeline-card">
              <FileDown size={21} />
              <h3>Latest generated draft</h3>
              <p>
                {artifact
                  ? `Revision ${artifact.revision}. Original drawing content and native annotation objects checked.`
                  : "The review PDF and traceability bundle appear here when output checks pass."}
              </p>
              {artifact && (
                <div className="inline-actions">
                  <a
                    className="button primary excel-download"
                    href={appPath(
                      `api/v1/projects/${project.id}/artifacts/${artifact.id}/workbook`,
                    )}
                  >
                    Export Excel
                  </a>
                  <button
                    className="button secondary"
                    onClick={() => onPreview(artifact)}
                  >
                    Preview PDF
                  </button>
                  <a
                    className="button secondary"
                    href={appPath(
                      `api/v1/projects/${project.id}/artifacts/${artifact.id}/download`,
                    )}
                  >
                    Download review bundle
                  </a>
                </div>
              )}
              {!!run.progress.page && (
                <a
                  className="text-button"
                  href={appPath(
                    `api/v1/projects/${project.id}/pipeline/${run.id}/evidence/0`,
                  )}
                  target="_blank"
                  rel="noreferrer"
                >
                  Inspect first-page evidence <ArrowUpRight size={14} />
                </a>
              )}
            </div>
          </div>
          <div className="pipeline-card">
            <div className="pipeline-review-heading">
              <h3>
                Source review queue{" "}
                <span className="badge">{automation?.issues.length || 0}</span>
              </h3>
              <span className="fine-print">
                Resolve against the original drawing; corrections remain in
                revision history.
              </span>
            </div>
            <div className="pipeline-issues">
              {(automation?.issues || []).map((issue, i) => (
                <button
                  key={i}
                  className="pipeline-issue"
                  onClick={() => onReview(issue)}
                >
                  <span className="pipeline-issue-dot" />
                  <span>
                    <b>{issue.code.replaceAll("_", " ")}</b>
                    <small>
                      {issue.message || "Review the linked source evidence."}
                    </small>
                  </span>
                  <ArrowUpRight size={16} />
                </button>
              ))}
            </div>
            {!automation?.issues.length && (
              <p className="fine-print">
                No source-extraction issues have been published yet. Engineering
                and layout validation remain in Validation & release.
              </p>
            )}
          </div>
        </>
      )}
    </div>
  );
}
