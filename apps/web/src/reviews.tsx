import { useEffect, useState } from "react";
import {
  CheckCircle2,
  ClipboardCheck,
  Download,
  Fingerprint,
  Layers,
  Loader2,
  RefreshCw,
  ShieldCheck,
} from "lucide-react";
import { api, label, type Project, type Issue, type Artifact } from "./types";
import { appPath } from "./paths";
import { Dialog } from "./ui";
import type { AccountSecurity } from "./account";
import "./review.css";

type Receipt = {
  id: string;
  revision: number;
  actor_name: string;
  created: string;
  level?: string;
  signature: string;
};
type Scope = {
  key: string;
  kind: string;
  title: string;
  sha256: string;
  ready: boolean;
  state: string;
  blocking: string[];
  review: (Receipt & { actor_id: string }) | null;
};
type Review = {
  revision: number;
  scopes: Scope[];
  issues: (Issue & { id: string })[];
  processing: boolean;
  approvals: Receipt[];
  qualifications: (Receipt & {
    kind: string;
    application: string;
    application_version: string;
  })[];
  can_review: boolean;
  can_lead: boolean;
  independent: boolean;
  mfa: AccountSecurity;
  model_import_qualified: boolean;
};
const categories = [
  { kind: "identity", title: "Drawing register", icon: Fingerprint },
  {
    kind: "materials",
    title: "Materials & reference data",
    icon: ClipboardCheck,
  },
  { kind: "geometry", title: "Physical model & dimensions", icon: Layers },
  { kind: "layout", title: "Drawing presentation", icon: Layers },
];

export function ReviewFlow({
  project,
  onUpdate,
  onSecurity,
  notify,
}: {
  project: Project;
  onUpdate: (p: Project) => void;
  onSecurity: () => void;
  notify: (message: string, error?: boolean) => void;
}) {
  const [data, setData] = useState<Review | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [selected, setSelected] = useState<
    Scope | "final" | "qualification" | null
  >(null);
  const [artifacts, setArtifacts] = useState<Artifact[]>([]);
  const path = `/projects/${project.id}/reviews`;
  const refresh = () => api<Review>(path).then(setData);
  useEffect(() => {
    let active = true;
    api<Review>(path)
      .then((value) => {
        if (active) {
          setData(value);
          setError("");
        }
      })
      .catch((e) => {
        if (active) setError(e.message);
      });
    return () => {
      active = false;
    };
  }, [project.id, project.version, project.status]);
  const reload = async () => {
    const p = await api<Project>(`/projects/${project.id}`);
    onUpdate(p);
    await refresh();
  };
  const signed = data?.scopes.filter((s) => s.review).length || 0;
  const allSigned = !!data?.scopes.length && signed === data.scopes.length;
  return (
    <section
      className="panel review-flow"
      aria-label="Project review and sign-off"
    >
      <div className="panel-title">
        <div>
          <ShieldCheck size={19} />
          <h3>Review & sign-off</h3>
        </div>
        <button
          className="icon-button"
          aria-label="Refresh review status"
          onClick={() => reload().catch((e) => setError(e.message))}
        >
          <RefreshCw size={16} />
        </button>
      </div>
      <p className="muted">
        Review available sections as the project progresses. A changed section
        needs a fresh review; approved issues remain preserved.
      </p>
      {error && (
        <p className="error-text" role="alert">
          {error}
        </p>
      )}
      {!data && !error && (
        <p>
          <Loader2 size={16} className="spin" /> Loading review sections…
        </p>
      )}
      {data && (
        <>
          <div
            className="review-progress"
            role="progressbar"
            aria-label="Sections reviewed"
            aria-valuemin={0}
            aria-valuemax={data.scopes.length}
            aria-valuenow={signed}
          >
            <span
              style={{
                width: `${(100 * signed) / (data.scopes.length || 1)}%`,
              }}
            />
          </div>
          <p className="muted">
            {signed} of {data.scopes.length} sections signed · Revision{" "}
            {data.revision}
          </p>
          {categories.map(({ kind, title, icon: CategoryIcon }) => {
            const items = data.scopes.filter((s) => s.kind === kind);
            if (!items.length) return null;
            return (
              <details
                className="review-group"
                key={kind}
                open={data.scopes.length <= 8}
              >
                <summary>
                  <CategoryIcon size={17} />
                  {title}
                  <span>
                    {items.filter((s) => s.review).length}/{items.length}
                  </span>
                </summary>
                {items.map((scope) => (
                  <div className="review-scope" key={scope.key}>
                    {scope.review ? (
                      <CheckCircle2 className="review-complete" size={17} />
                    ) : (
                      <ClipboardCheck size={17} />
                    )}
                    <div>
                      <b>{scope.title}</b>
                      <small className={!scope.ready ? "review-pending" : ""}>
                        {label(scope.state)}
                        {scope.review && ` · ${scope.review.actor_name}`}
                        {scope.blocking.length > 0 &&
                          ` · ${scope.blocking.length} limitations`}
                      </small>
                    </div>
                    {data.can_review && (
                      <button
                        className="button secondary"
                        disabled={busy || !scope.ready}
                        onClick={() => setSelected(scope)}
                      >
                        {scope.review ? "View sign-off" : "Review section"}
                      </button>
                    )}
                  </div>
                ))}
              </details>
            );
          })}
          <div className="review-final">
            <h3>Independent review issue</h3>
            <p className="muted">
              A second person checks the current signed sections and accepts the
              listed exceptions. This creates a sealed, downloadable snapshot
              for engineering review.
            </p>
            {data.processing && (
              <p className="review-pending">
                Processing or draft refresh is running. Section reviews remain
                available.
              </p>
            )}
            {data.can_lead && !data.independent && (
              <p className="review-pending">
                A different reviewer must approve work you prepared or signed.
              </p>
            )}
            {!data.can_lead && (
              <p className="muted">
                A reviewer or independent administrator can issue the final
                review.
              </p>
            )}
            {!data.mfa.enabled && data.can_lead && (
              <button className="button secondary" onClick={onSecurity}>
                <ShieldCheck size={16} /> Set up approval authenticator
              </button>
            )}
            <div className="review-actions">
              <button
                className="button primary"
                disabled={
                  busy ||
                  !data.can_lead ||
                  !data.independent ||
                  !allSigned ||
                  data.processing ||
                  !data.mfa.enabled ||
                  data.approvals.some((a) => a.revision === data.revision)
                }
                onClick={() => setSelected("final")}
              >
                <ShieldCheck size={16} /> Approve engineering-review issue
              </button>
              {data.can_lead && (
                <button
                  className="button secondary"
                  disabled={busy || data.processing}
                  onClick={async () => {
                    try {
                      const history = await api<{ artifacts: Artifact[] }>(
                        `/projects/${project.id}/audit`,
                      );
                      setArtifacts(
                        history.artifacts.filter(
                          (a) => a.revision === data.revision,
                        ),
                      );
                      setSelected("qualification");
                    } catch (e) {
                      setError((e as Error).message);
                    }
                  }}
                >
                  Record external test
                </button>
              )}
            </div>
            <p className="muted">
              Verified-for-modelling release remains unavailable while the
              CAESAR import profile and desktop round-trip checks are
              unqualified. Review approval does not clear engineering
              exceptions.
            </p>
          </div>
          {data.qualifications.length > 0 && (
            <div className="review-history">
              <h3>Recorded external tests</h3>
              {data.qualifications.map((q) => (
                <div className="review-history-item" key={q.id}>
                  <div>
                    <b>
                      {label(q.kind)} · revision {q.revision}
                    </b>
                    <small>
                      {q.application} {q.application_version} · {q.actor_name}
                    </small>
                  </div>
                </div>
              ))}
            </div>
          )}
          {data.approvals.length > 0 && (
            <div className="review-history">
              <h3>Preserved approved issues</h3>
              {data.approvals.map((approval) => (
                <div className="review-history-item" key={approval.id}>
                  <CheckCircle2 size={17} />
                  <div>
                    <b>
                      Revision {approval.revision} ·{" "}
                      {label(approval.level || "ENGINEERING_REVIEW")}
                    </b>
                    <small>
                      {approval.actor_name} ·{" "}
                      {new Date(approval.created).toLocaleDateString()}
                    </small>
                    <span className="review-hash">
                      Seal {approval.signature.slice(0, 16)}…
                    </span>
                  </div>
                  <a
                    className="button secondary"
                    href={appPath(
                      `api/v1${path}/approvals/${approval.id}/download`,
                    )}
                  >
                    <Download size={15} /> Download
                  </a>
                </div>
              ))}
            </div>
          )}
        </>
      )}
      {selected && data && (
        <Dialog
          title={
            selected === "final"
              ? "Approve engineering-review issue"
              : selected === "qualification"
                ? "Record external application test"
                : selected.title
          }
          subtitle={`Current project revision ${data.revision}`}
          onClose={() => {
            if (!busy) setSelected(null);
          }}
        >
          <form
            className="review-dialog"
            onSubmit={async (event) => {
              event.preventDefault();
              const form = new FormData(event.currentTarget);
              setBusy(true);
              setError("");
              const final = selected === "final",
                qualification = selected === "qualification";
              const limitations = final
                ? data.issues.map((i) => i.id)
                : typeof selected === "object"
                  ? selected.blocking
                  : [];
              try {
                const common = {
                  version: data.revision,
                  code: form.get("code") || null,
                };
                if (qualification) {
                  await api(path + "/qualifications", {
                    method: "POST",
                    body: JSON.stringify({
                      ...common,
                      kind: form.get("kind"),
                      artifact_id: form.get("artifact_id"),
                      application: form.get("application"),
                      application_version: form.get("application_version"),
                      evidence: form.get("reason"),
                      passed: true,
                    }),
                  });
                } else {
                  const body = {
                    version: data.revision,
                    reason: form.get("reason"),
                    confirmed: true,
                    acknowledge:
                      limitations.length && form.get("exceptions")
                        ? limitations
                        : [],
                    ...(final
                      ? {
                          level: "ENGINEERING_REVIEW",
                          code: form.get("code") || null,
                        }
                      : { scope: (selected as Scope).key }),
                  };
                  const result = await api<{ project: Project }>(
                    path + (final ? "/approve" : "/sign"),
                    { method: "POST", body: JSON.stringify(body) },
                  );
                  onUpdate(result.project);
                }
                setSelected(null);
                await refresh();
                notify(
                  qualification
                    ? "External test evidence recorded for this revision."
                    : final
                      ? "Independent engineering-review issue preserved."
                      : "Section review signed. Remaining limitations stay visible.",
                );
              } catch (e) {
                const message = (e as Error).message;
                setError(message);
                notify(message, true);
                await reload().catch(() => {});
              } finally {
                setBusy(false);
              }
            }}
          >
            {error && (
              <p className="error-text" role="alert">
                {error}
              </p>
            )}
            {typeof selected === "object" && selected.review ? (
              <>
                <p>
                  Signed by {selected.review.actor_name} on{" "}
                  {new Date(selected.review.created).toLocaleString()}.
                </p>
                <p className="review-hash">
                  Content SHA256: {selected.sha256}
                  <br />
                  Server seal: {selected.review.signature}
                </p>
                <p>
                  Changes to the section’s reviewed content will require a fresh
                  sign-off.
                </p>
                <button
                  type="button"
                  className="button secondary"
                  onClick={() => setSelected(null)}
                >
                  Close sign-off
                </button>
              </>
            ) : (
              <>
                {selected === "qualification" && (
                  <>
                    <label className="form-field">
                      Test type
                      <select aria-label="Test type" name="kind">
                        <option value="PDF_EDITOR">
                          PDF editor — select, edit, save and reopen native
                          objects
                        </option>
                        <option value="CAESAR_ROUNDTRIP">
                          CAESAR II — import and inspect the native candidate
                        </option>
                      </select>
                    </label>
                    <label className="form-field">
                      Tested export
                      <select
                        aria-label="Tested export"
                        name="artifact_id"
                        required
                        defaultValue=""
                      >
                        <option value="" disabled>
                          Select the exact current-revision export
                        </option>
                        {artifacts.map((a) => (
                          <option key={a.id} value={a.id}>
                            {a.filename} · {a.created}
                          </option>
                        ))}
                      </select>
                      {!artifacts.length && (
                        <small>
                          Generate a review export for this revision first.
                        </small>
                      )}
                    </label>
                    <label className="form-field">
                      Application name
                      <input
                        name="application"
                        required
                        minLength={2}
                        maxLength={100}
                      />
                    </label>
                    <label className="form-field">
                      Application version
                      <input
                        name="application_version"
                        required
                        maxLength={100}
                      />
                    </label>
                  </>
                )}
                {selected !== "qualification" && (
                  <div className="review-limitations">
                    {selected === "final" ? (
                      data.issues.length ? (
                        data.issues.map((issue) => (
                          <p key={issue.id}>
                            <b>{label(issue.code)}</b> — {issue.message}
                          </p>
                        ))
                      ) : (
                        <p>No validation exceptions are currently listed.</p>
                      )
                    ) : (selected as Scope).blocking.length ? (
                      (selected as Scope).blocking.map((code) => (
                        <p key={code}>{label(code)}</p>
                      ))
                    ) : (
                      <p>No section limitations are currently listed.</p>
                    )}
                  </div>
                )}
                {(selected === "final"
                  ? data.issues.length > 0
                  : typeof selected === "object" &&
                    selected.blocking.length > 0) && (
                  <label className="check-row">
                    <input name="exceptions" type="checkbox" required />I have
                    reviewed and explicitly retain every limitation listed above
                    for this engineering-review issue.
                  </label>
                )}
                <label className="form-field">
                  {selected === "qualification"
                    ? "Checks performed and saved evidence reference"
                    : "Review evidence and decision"}
                  <textarea
                    name="reason"
                    rows={4}
                    required
                    minLength={
                      selected === "qualification"
                        ? 30
                        : selected === "final"
                          ? 20
                          : 10
                    }
                    maxLength={selected === "qualification" ? 4000 : 3000}
                    placeholder={
                      selected === "qualification"
                        ? "Record tested file, objects/model values checked, saved/reopened results and the evidence location."
                        : "Describe the source and evidence you inspected, your decision, and any remaining limitations."
                    }
                  />
                </label>
                {(selected === "final" || selected === "qualification") && (
                  <label className="form-field">
                    Authenticator or recovery code
                    <input
                      name="code"
                      autoComplete="one-time-code"
                      maxLength={80}
                    />
                    <small>
                      A factor check made in this session in the last five
                      minutes is accepted.
                    </small>
                  </label>
                )}
                <label className="check-row">
                  <input type="checkbox" required />
                  {selected === "qualification"
                    ? "I personally completed this external test successfully and the evidence above describes the result."
                    : "I personally inspected this work and accept responsibility for this review decision."}
                </label>
                <div className="modal-footer">
                  <button
                    type="button"
                    className="button secondary"
                    disabled={busy}
                    onClick={() => setSelected(null)}
                  >
                    Cancel
                  </button>
                  <button
                    className="button primary"
                    disabled={
                      busy ||
                      (selected === "qualification" && !artifacts.length)
                    }
                  >
                    {busy ? (
                      <Loader2 className="spin" size={16} />
                    ) : (
                      <ShieldCheck size={16} />
                    )}
                    {selected === "final"
                      ? "Seal review issue"
                      : selected === "qualification"
                        ? "Record successful test"
                        : "Sign section review"}
                  </button>
                </div>
              </>
            )}
          </form>
        </Dialog>
      )}
    </section>
  );
}
