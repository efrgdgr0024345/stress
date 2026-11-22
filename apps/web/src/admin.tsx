import { useEffect, useState } from "react";
import {
  Cloud,
  KeyRound,
  ShieldCheck,
  Play,
  CheckCircle2,
  Loader2,
  Download,
  Unplug,
  ArrowUpRight,
} from "lucide-react";
import { api, type Project } from "./types";
import { appPath } from "./paths";
import { WorkspaceResetCard } from "./workspace-reset";
import "./admin.css";

type Demo = {
  id?: string;
  state?: string;
  stage?: string;
  error?: string;
  page?: number;
  page_count?: number;
  project_title?: string;
  updated?: number;
  events?: { stage: string; state: string; at: number; error?: string }[];
  report?: {
    material_proposals: number;
    pages: {
      page: number;
      words: number;
      ocr_used: boolean;
      elapsed_ms: number;
    }[];
  };
  preview?: {
    item_no: string;
    description: string;
    size: string;
    quantity: number | null;
    family: string;
  }[];
};
type Status = {
  configured: boolean;
  verified_at?: number;
  demo: Demo;
  runner_ready: boolean;
  processing?: {
    policy: {
      enabled: boolean;
      concurrency: number;
      daily_limit: number;
      monthly_limit: number;
    };
    worker: { state?: string; stage?: string; error?: string };
  };
};
const stages: Record<string, string> = {
  build: "Preparing the verified OCR package",
  namespace: "Connecting the private Functions workspace",
  deploy: "Deploying the private worker",
  invoke: "Sending a drawing page",
  submitting: "Submitting the page",
  poll: "Waiting for DigitalOcean extraction / OCR",
  report: "Preparing Excel and website results",
  complete: "Worker test complete",
};
function explain(code: string) {
  if (code.includes("HTTP_401"))
    return "DigitalOcean rejected this token. Check that it is valid and has not expired.";
  if (code.includes("HTTP_403"))
    return "The token lacks permission. Enable Functions read, create and admin permissions.";
  if (code.includes("HTTP_429"))
    return "DigitalOcean is limiting requests. Wait before trying again.";
  if (code === "TOKEN_FORMAT_INVALID")
    return "Enter the full DigitalOcean personal access token.";
  if (code === "PROVIDER_CONNECTION_FAILED")
    return "The hosting server could not reach DigitalOcean. Check outbound HTTPS access.";
  if (code === "PROVIDER_RESPONSE_INVALID" || code === "PROVIDER_JSON_INVALID")
    return "DigitalOcean returned an unexpected response. Open Logs and search provider.http for the HTTP status, response structure and provider request ID.";
  if (code === "FUNCTION_PROCESSING_FAILED")
    return "The provider function finished without usable extraction evidence. Check the private function activation in DigitalOcean.";
  if (code === "SUBMISSION_INTERRUPTED_CHECK_PROVIDER")
    return "The connection stopped during submission. Check the provider activation before retrying; it may have run.";
  return code.replaceAll("_", " ");
}

export function AdminConnections({ projects }: { projects: Project[] }) {
  const [status, setStatus] = useState<Status | null>(null),
    [token, setToken] = useState("");
  const [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [notice, setNotice] = useState("");
  const [projectId, setProjectId] = useState(""),
    [sourceId, setSourceId] = useState(""),
    [region, setRegion] = useState("syd1");
  const project = projects.find((p) => p.id === projectId);
  const sources =
    project?.sheets.filter(
      (s, i, all) => all.findIndex((v) => v.source_id === s.source_id) === i,
    ) || [];
  const job = status?.demo || {},
    active = ["queued", "running", "waiting"].includes(job.state || "");
  const refresh = async () =>
    setStatus(await api<Status>("/system/digitalocean"));
  useEffect(() => {
    let mounted = true;
    const load = () =>
      api<Status>("/system/digitalocean")
        .then((v) => {
          if (mounted) setStatus(v);
        })
        .catch((e) => {
          if (mounted) setError(e.message);
        });
    load();
    const timer = setInterval(load, 5000);
    return () => {
      mounted = false;
      clearInterval(timer);
    };
  }, []);
  const connect = async (event: React.FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError("");
    setNotice("");
    // Clear the input immediately; the saved credential is never read back.
    const supplied = token;
    setToken("");
    try {
      await api("/system/digitalocean", {
        method: "POST",
        body: JSON.stringify({ token: supplied }),
      });
      await refresh();
      setNotice(
        "DigitalOcean connected. The token is saved privately on the hosting server.",
      );
    } catch (e) {
      setError(explain((e as Error).message));
    } finally {
      setBusy(false);
    }
  };
  const disconnect = async () => {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await api("/system/digitalocean", { method: "DELETE" });
      await refresh();
      setNotice(
        "Saved token removed. Existing DigitalOcean functions remain in your account.",
      );
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  const run = async () => {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await api("/system/digitalocean/demo", {
        method: "POST",
        body: JSON.stringify({
          project_id: projectId,
          source_id: sourceId,
          region,
        }),
      });
      await refresh();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  const download = (format: string) =>
    appPath(`api/v1/system/digitalocean/demo/${job.id}/${format}`);
  return (
    <div className="page-content admin-connections">
      <div className="page-heading">
        <div>
          <div className="eyebrow">HOSTING ADMINISTRATOR</div>
          <h1>
            Connections<span className="heading-dot">.</span>
          </h1>
          <p>Connect the tools that power your drawing workflow.</p>
        </div>
        <span className="connection-badge">
          <ShieldCheck size={16} />
          Admin only
        </span>
      </div>
      {error && (
        <div className="connection-alert" role="alert">
          {error}
        </div>
      )}
      {notice && (
        <div className="connection-notice" role="status">
          <CheckCircle2 size={18} />
          {notice}
        </div>
      )}
      <section className="connection-card" aria-labelledby="do-heading">
        <div className="connection-heading">
          <span className="connection-icon">
            <Cloud size={28} />
          </span>
          <div>
            <h2 id="do-heading">DigitalOcean</h2>
            <p>Pay per use · Private extraction and OCR worker</p>
          </div>
          <span
            className={`connection-badge ${status?.configured ? "connected" : ""}`}
          >
            {status?.configured ? (
              <CheckCircle2 size={15} />
            ) : (
              <KeyRound size={15} />
            )}
            {status?.configured ? "Connected" : "Not connected"}
          </span>
        </div>
        <form onSubmit={connect} className="connection-form">
          <label htmlFor="do-token">
            {status?.configured
              ? "Replace access token"
              : "Personal access token"}
          </label>
          <div className="connection-input-row">
            <input
              id="do-token"
              type="password"
              autoComplete="new-password"
              spellCheck={false}
              value={token}
              onChange={(e) => setToken(e.target.value)}
              placeholder="Paste your DigitalOcean token here"
              maxLength={512}
              disabled={busy || active}
              required
              minLength={20}
            />
            <button
              className="button primary"
              disabled={busy || active || !token}
            >
              {busy ? (
                <Loader2 size={16} className="spin" />
              ) : (
                <KeyRound size={16} />
              )}
              Save & test connection
            </button>
          </div>
          <p className="connection-hint">
            Stored in an owner-only file outside the public website. The saved
            token is never displayed or included in diagnostic logs. Use
            Functions read, create and admin permissions.
          </p>
          <div className="connection-links">
            <a
              href="https://cloud.digitalocean.com/account/api/tokens"
              target="_blank"
              rel="noreferrer"
            >
              Create a token in DigitalOcean <ArrowUpRight size={14} />
            </a>
            {status?.configured && (
              <button
                type="button"
                disabled={busy || active}
                onClick={disconnect}
              >
                <Unplug size={14} />
                Remove saved token
              </button>
            )}
          </div>
        </form>
        {status?.processing && (
          <div className="connection-progress">
            <label className="connection-heading">
              <input
                type="checkbox"
                checked={status.processing.policy.enabled}
                disabled={busy || !status.configured}
                onChange={async (e) => {
                  const enabled = e.target.checked;
                  setBusy(true);
                  setError("");
                  try {
                    await api("/system/digitalocean/processing", {
                      method: "POST",
                      body: JSON.stringify({
                        enabled,
                        concurrency: status.processing!.policy.concurrency,
                        daily_limit: status.processing!.policy.daily_limit,
                        monthly_limit: status.processing!.policy.monthly_limit,
                      }),
                    });
                    await refresh();
                    setNotice(
                      enabled
                        ? "Normal project uploads will use DigitalOcean automatically. Worker setup runs in the background."
                        : "New project uploads will use the hosting worker. Existing jobs keep their selected processor.",
                    );
                  } catch (error) {
                    setError((error as Error).message);
                  } finally {
                    setBusy(false);
                  }
                }}
              />
              <b>Use DigitalOcean for normal project uploads</b>
              <span className="connection-badge">
                {status.processing.worker.state || "Not prepared"}
              </span>
            </label>
            <p className="connection-hint">
              The project workspace stays the same. Backend tasks process up to{" "}
              {status.processing.policy.concurrency} pages concurrently, with{" "}
              {status.processing.policy.daily_limit} submissions/day and{" "}
              {status.processing.policy.monthly_limit}/month including retries.
              At the full time limit, the monthly compute cap is about US$
              {(
                status.processing.policy.monthly_limit *
                240 *
                0.0000185
              ).toFixed(2)}{" "}
              before shared allowance, transfer and tax.
            </p>
            {status.processing.worker.error && (
              <div className="connection-alert" role="alert">
                {explain(status.processing.worker.error)}
              </div>
            )}
          </div>
        )}
      </section>
      <section className="connection-card" aria-labelledby="test-heading">
        <h2 id="test-heading">Test the serverless worker</h2>
        <p className="connection-hint">
          Deploy the tested Python worker, process up to two pages of a PDF up
          to 700 KB, then display the extracted proposals here and in an
          editable Excel workbook. Your project drawing and reviewed data stay
          intact.
        </p>
        <div className="connection-selects">
          <label>
            Project
            <select
              value={projectId}
              disabled={busy || active}
              onChange={(e) => {
                setProjectId(e.target.value);
                setSourceId("");
              }}
            >
              <option value="">Select a project</option>
              {projects
                .filter((p) => p.sheets.length)
                .map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.title}
                  </option>
                ))}
            </select>
          </label>
          <label>
            Drawing
            <select
              value={sourceId}
              disabled={!project || busy || active}
              onChange={(e) => setSourceId(e.target.value)}
            >
              <option value="">Select a drawing</option>
              {sources.map((s) => (
                <option key={s.source_id} value={s.source_id}>
                  {s.filename}
                </option>
              ))}
            </select>
          </label>
          <label>
            Region
            <select
              value={region}
              disabled={busy || active}
              onChange={(e) => setRegion(e.target.value)}
            >
              <option value="syd1">Sydney</option>
              <option value="sgp1">Singapore</option>
              <option value="nyc3">New York</option>
              <option value="fra1">Frankfurt</option>
            </select>
          </label>
        </div>
        <div className="connection-cost">
          <b>No monthly server required.</b> DigitalOcean includes 90,000
          GiB-seconds per month per team, then charges US$0.0000185 per
          GiB-second. At the 1 GiB / 240 second limit, two full-length
          successful invocations cost at most about US$0.009 in compute before
          free allowance and tax. Provider retries can add usage. No paid
          database, bucket or Droplet is created.
        </div>
        {status && !status.runner_ready && (
          <p role="alert" className="connection-alert">
            The separate processing runner has not checked in recently. The test
            will wait until the hosting cron runner starts.
          </p>
        )}
        <button
          className="button primary"
          disabled={
            busy || active || !status?.configured || !projectId || !sourceId
          }
          onClick={run}
        >
          {active ? <Loader2 size={16} className="spin" /> : <Play size={16} />}
          {active ? "Worker test running" : "Deploy & test worker"}
        </button>
        {job.id && (
          <div className="connection-progress" aria-live="polite">
            <div className="connection-heading">
              <div>
                <h3>{stages[job.stage || ""] || job.stage}</h3>
                <p>
                  {job.project_title} · Page{" "}
                  {Math.min((job.page || 0) + 1, job.page_count || 1)} of{" "}
                  {job.page_count}
                </p>
              </div>
              <span
                className={`connection-badge ${job.state === "done" ? "connected" : ""}`}
              >
                {job.state}
              </span>
            </div>
            {job.error && (
              <div className="connection-alert" role="alert">
                {explain(job.error)}{" "}
                <small>
                  Diagnostic code: {job.error}. View the Logs tab for stage
                  details.
                </small>
              </div>
            )}
            <ol className="connection-timeline">
              {job.events?.map((event, index) => (
                <li key={index}>
                  <span className={event.state === "failed" ? "failed" : ""} />
                  <time>{new Date(event.at * 1000).toLocaleTimeString()}</time>
                  <b>{stages[event.stage] || event.stage}</b>
                  <small>{event.state}</small>
                </li>
              ))}
            </ol>
          </div>
        )}
        {job.state === "done" && job.report && (
          <div className="connection-results">
            <h3>
              {job.report.material_proposals} material proposals extracted
            </h3>
            <p className="connection-hint">
              These are unreviewed source proposals. Physical geometry and
              CAESAR model inputs still need engineering review.
            </p>
            <div className="heading-actions">
              <a className="button primary" href={download("xlsx")}>
                <Download size={16} />
                Excel workbook
              </a>
              <a className="button secondary" href={download("csv")}>
                CSV tables
              </a>
              <a className="button secondary" href={download("json")}>
                Diagnostic report
              </a>
            </div>
            <div className="connection-table">
              <table>
                <thead>
                  <tr>
                    <th>Item</th>
                    <th>Description</th>
                    <th>Size</th>
                    <th>Quantity</th>
                    <th>Family</th>
                  </tr>
                </thead>
                <tbody>
                  {job.preview?.map((row, i) => (
                    <tr key={i}>
                      <td>{row.item_no}</td>
                      <td>{row.description}</td>
                      <td>{row.size}</td>
                      <td>{row.quantity ?? "Review"}</td>
                      <td>{row.family}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </section>
      <WorkspaceResetCard />
    </div>
  );
}
