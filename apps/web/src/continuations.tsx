import { useEffect, useState } from "react";
import { FileText, Link2, Loader2 } from "lucide-react";
import { api, label, pointLabel, type Project } from "./types";
import { Dialog } from "./ui";

type Link = {
  id: string;
  status: string;
  evidence: string;
  left_point_id: string;
  right_point_id: string;
  point_id?: string;
  delta_mm: Record<string, string | null>;
};
type Report = {
  revision: number;
  links: Link[];
  candidates: {
    id: string;
    sheet_id: string;
    source_text: string;
    point_id?: string | null;
    source_label?: string;
  }[];
  source_reviews?: {
    id: string;
    candidate_id: string;
    decision: string;
    reason_code: string;
    evidence: string;
    status: string;
    effective_status?: string;
    current?: boolean;
    stale?: boolean;
    is_latest?: boolean;
    reviewed_at?: string;
    engineering_approved: false;
  }[];
  candidate_pairs: unknown[];
  can_edit: boolean;
};

export function ContinuationControls({
  project,
  onUpdate,
  selection,
  sourceSelection,
  onClear,
}: {
  project: Project;
  onUpdate: (p: Project) => void;
  selection: string | null;
  sourceSelection?: string | null;
  onClear: () => void;
}) {
  const [data, setData] = useState<Report | null>(null),
    [open, setOpen] = useState(false),
    [version, setVersion] = useState(project.version);
  const [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  const [decision, setDecision] = useState("PROPOSE");
  const [sourceOpen, setSourceOpen] = useState(false),
    [sourceId, setSourceId] = useState(""),
    [sourceVersion, setSourceVersion] = useState(project.version),
    [sourceError, setSourceError] = useState("");
  const path = `/projects/${project.id}/continuations`;
  useEffect(() => {
    let active = true;
    api<Report>(path)
      .then((v) => {
        if (active) setData(v);
      })
      .catch((e) => {
        if (active) setError(e.message);
      });
    return () => {
      active = false;
    };
  }, [project.id, project.version]);
  useEffect(() => {
    if (selection) {
      setSourceOpen(false);
      setVersion(project.version);
      setOpen(true);
      setError("");
    }
  }, [selection]);
  const openSource = (id: string) => {
    setOpen(false);
    setSourceId(id);
    setSourceVersion(project.version);
    setSourceError("");
    setSourceOpen(true);
  };
  useEffect(() => {
    if (sourceSelection) openSource(sourceSelection);
  }, [sourceSelection]);
  const link = data?.links.find((l) => l.id === selection);
  const source = data?.candidates.find((c) => c.id === sourceId);
  const sourcePoint = project.nodes.find((n) => n.id === source?.point_id);
  const sourceHistory = (data?.source_reviews || []).filter(
    (r) => r.candidate_id === sourceId,
  );
  const sourceReview =
    sourceHistory.find((r) => r.is_latest) || sourceHistory.at(-1);
  const closeSource = () => {
    if (!busy) {
      setSourceOpen(false);
      setSourceError("");
      onClear();
    }
  };
  const close = () => {
    if (!busy) {
      setOpen(false);
      setError("");
      onClear();
    }
  };
  const name = (n: Project["nodes"][number]) =>
    `${pointLabel(n)} · ${n.line_id} · ${n.instances.map((i) => project.sheets.find((s) => s.id === i.sheet_id)?.printed_id || "Unverified sheet").join(" / ")}`;
  return (
    <div className="physical-controls">
      <div className="review-actions">
        <button
          className="button secondary"
          disabled={!data}
          onClick={() => {
            onClear();
            setSourceOpen(false);
            setDecision("PROPOSE");
            setVersion(project.version);
            setOpen(true);
            setError("");
          }}
        >
          <Link2 size={16} /> Review continuation
        </button>
        <button
          className="button secondary"
          disabled={!data?.candidates.length}
          onClick={() => {
            onClear();
            openSource(data?.candidates[0]?.id || "");
          }}
        >
          <FileText size={16} /> Review source reference
        </button>
        <span className="fine-print">
          {data?.candidates.length || 0} printed reference proposals ·{" "}
          {data?.candidate_pairs.length || 0} reciprocal sheet candidates
        </span>
      </div>
      {error && !open && !sourceOpen && (
        <p className="error-text" role="alert">
          {error}
        </p>
      )}
      {sourceOpen && data && (
        <Dialog
          wide
          title="Review source reference"
          subtitle={`Revision ${sourceVersion} · Source-reference decision; engineering coordinates remain independent`}
          onClose={closeSource}
        >
          <form
            key={`source:${sourceId}`}
            onSubmit={async (e) => {
              e.preventDefault();
              setBusy(true);
              setSourceError("");
              const form = new FormData(e.currentTarget);
              try {
                const updated = await api<Project>(
                  `${path}/sources/${sourceId}/decision`,
                  {
                    method: "POST",
                    body: JSON.stringify({
                      version: sourceVersion,
                      decision: form.get("source_decision"),
                      reason_code: form.get("source_reason"),
                      evidence: form.get("source_evidence"),
                      confirmed: true,
                    }),
                  },
                );
                onUpdate(updated);
                setSourceOpen(false);
                onClear();
              } catch (e) {
                setSourceError((e as Error).message);
              } finally {
                setBusy(false);
              }
            }}
          >
            {sourceError && (
              <p className="error-text" role="alert">
                {sourceError}
              </p>
            )}
            {data.revision !== sourceVersion && (
              <p className="notice amber" role="status">
                Source review details are refreshing for this revision. If the
                project changed while this dialog was open, close and reopen it
                to inspect the current source decisions.
              </p>
            )}
            <label className="form-field">
              Source continuation reference
              <select
                aria-label="Source continuation reference"
                value={sourceId}
                onChange={(e) => setSourceId(e.target.value)}
                required
                disabled={busy}
              >
                {data.candidates.map((c) => {
                  const point = project.nodes.find((n) => n.id === c.point_id);
                  return (
                    <option key={c.id} value={c.id}>
                      {point ? pointLabel(point) : c.source_label || "Source"} ·{" "}
                      {c.source_text.slice(0, 120)}
                    </option>
                  );
                })}
              </select>
            </label>
            {source && (
              <div className="notice">
                <FileText size={20} />
                <div>
                  <strong>
                    {source.source_label || "Printed continuation reference"}
                  </strong>
                  <p>{source.source_text}</p>
                  <p className="fine-print">
                    Source point:{" "}
                    {sourcePoint
                      ? pointLabel(sourcePoint)
                      : "Unlocated — source interface requires review"}{" "}
                    · Sheet:{" "}
                    {project.sheets.find((s) => s.id === source.sheet_id)
                      ?.printed_id || "Unverified printed identity"}
                  </p>
                </div>
              </div>
            )}
            <p aria-live="polite">
              <span className="badge">Source review</span>{" "}
              <strong>
                {label(
                  sourceReview?.effective_status ||
                    sourceReview?.status ||
                    "REVIEW_REQUIRED",
                )}
              </strong>
              {sourceReview?.reason_code && (
                <> · {label(sourceReview.reason_code)}</>
              )}
            </p>
            {sourceReview?.stale && (
              <p className="notice amber">
                The source binding changed. Inspect the current reference before
                recording a fresh decision.
              </p>
            )}
            {sourceReview?.evidence && (
              <p className="fine-print">
                Recorded source evidence: {sourceReview.evidence}
              </p>
            )}
            <p className="fine-print">
              Record an external boundary or reject an unsupported in-pack match
              with its source reason. Reopen preserves the decision history and
              returns the reference to review. Physical identity, accepted XYZ,
              stations and connectivity require their separate engineering
              evidence and review.
            </p>
            <div className="form-grid">
              <label className="form-field">
                Source reference decision
                <select
                  name="source_decision"
                  aria-label="Source reference decision"
                  defaultValue=""
                  required
                  disabled={!data.can_edit || busy}
                >
                  <option value="" disabled>
                    Choose a source-only decision
                  </option>
                  <option value="REJECT_MATCH">
                    Reject a proposed in-pack match
                  </option>
                  <option value="DECLARE_EXTERNAL_BOUNDARY">
                    Record an external drawing / equipment boundary
                  </option>
                  <option value="REOPEN">Reopen this source reference</option>
                </select>
              </label>
              <label className="form-field">
                Source decision reason
                <select
                  name="source_reason"
                  aria-label="Source decision reason"
                  defaultValue=""
                  required
                  disabled={!data.can_edit || busy}
                >
                  <option value="" disabled>
                    Choose the source reason
                  </option>
                  <option value="MISSING_PEER_IN_PACK">
                    Referenced drawing / peer is absent
                  </option>
                  <option value="EQUIPMENT_BOUNDARY">
                    Source shows an equipment boundary
                  </option>
                  <option value="ACCEPTED_XYZ_REQUIRED">
                    Independent accepted XYZ is missing
                  </option>
                  <option value="SOURCE_INTERFACE_UNCONFIRMED">
                    Physical interface needs source confirmation
                  </option>
                  <option value="LINE_OR_SIZE_MISMATCH">
                    Full line ID or nominal size differs
                  </option>
                </select>
              </label>
            </div>
            <label className="form-field">
              Source reference evidence
              <textarea
                name="source_evidence"
                aria-label="Source reference evidence"
                required
                minLength={10}
                maxLength={3000}
                disabled={!data.can_edit || busy}
                placeholder="Record the observed source reference, available peer/equipment evidence and the reason for this decision."
              />
            </label>
            <label className="check-field">
              <input
                type="checkbox"
                aria-label="Confirm source reference decision and evidence"
                required
                disabled={!data.can_edit || busy}
              />{" "}
              I inspected this source reference and recorded the decision
              reason.
            </label>
            {!!sourceHistory.length && (
              <details>
                <summary>Source decision history</summary>
                <ol>
                  {sourceHistory.map((review) => (
                    <li key={review.id}>
                      <strong>
                        {label(review.effective_status || review.status)}
                      </strong>{" "}
                      ·{" "}
                      {label(
                        review.reason_code || "SOURCE_INTERFACE_UNCONFIRMED",
                      )}
                      <p className="fine-print">{review.evidence}</p>
                    </li>
                  ))}
                </ol>
              </details>
            )}
            <div className="modal-actions">
              <button
                type="button"
                className="button secondary"
                onClick={closeSource}
                disabled={busy}
              >
                Cancel
              </button>
              {data.can_edit && (
                <button
                  className="button primary"
                  disabled={busy || !source || data.revision !== sourceVersion}
                >
                  {busy ? (
                    <Loader2 className="spin" size={16} />
                  ) : (
                    <FileText size={16} />
                  )}{" "}
                  Save source reference decision
                </button>
              )}
            </div>
          </form>
        </Dialog>
      )}
      {open && data && (
        <Dialog
          wide
          title={
            link
              ? "Review saved continuation"
              : "Compare continuation depictions"
          }
          subtitle={`Revision ${version} · Independent engineering coordinates required`}
          onClose={close}
        >
          <form
            key={selection || "new"}
            onSubmit={async (e) => {
              e.preventDefault();
              setBusy(true);
              setError("");
              const form = new FormData(e.currentTarget);
              try {
                const body = link
                  ? {
                      version,
                      decision: form.get("saved_decision"),
                      topology_confirmed: form.has("topology_confirmed"),
                      evidence: form.get("evidence"),
                      confirmed: true,
                    }
                  : {
                      version,
                      decision,
                      left_point_id: form.get("left_point_id"),
                      right_point_id: form.get("right_point_id"),
                      left_size: form.get("left_size"),
                      right_size: form.get("right_size"),
                      left_candidate_id: form.get("left_candidate_id") || null,
                      right_candidate_id:
                        form.get("right_candidate_id") || null,
                      tolerance_text: form.get("tolerance_text"),
                      topology_confirmed: form.has("topology_confirmed"),
                      evidence: form.get("evidence"),
                      confirmed: true,
                    };
                const p = await api<Project>(
                  path + (link ? "/" + link.id : ""),
                  {
                    method: link ? "PATCH" : "POST",
                    body: JSON.stringify(body),
                  },
                );
                onUpdate(p);
                setOpen(false);
                onClear();
              } catch (e) {
                setError((e as Error).message);
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
            <p className="fine-print">
              Compare the actual continuation interfaces, nominal pipe sizes and
              accepted E/N/EL coordinates. A difference of 25.4 mm or more on
              any axis flags both depictions blue. Drawing distance does not
              prove a connection.
            </p>
            {link ? (
              <>
                <p>
                  <strong>{link.status.replaceAll("_", " ")}</strong>
                </p>
                <p className="fine-print">
                  Recorded deltas:{" "}
                  {Object.entries(link.delta_mm)
                    .map(
                      ([a, v]) => `${a}: ${v === null ? "unknown" : v + " mm"}`,
                    )
                    .join(" · ")}
                </p>
                <label className="form-field">
                  Saved connection decision
                  <select
                    name="saved_decision"
                    aria-label="Saved connection decision"
                    disabled={!data.can_edit}
                  >
                    <option value="WITHDRAW">
                      Withdraw acceptance / require source review
                    </option>
                    {link.point_id && (
                      <option value="REVALIDATE">
                        Revalidate independent source coordinates
                      </option>
                    )}
                  </select>
                </label>
                <p className="fine-print">
                  Withdrawal preserves the point identity and history and flags
                  it for review. Revalidation requires complete, identical
                  independent XYZ coordinates on every depicting source sheet. A
                  previous revision can be restored as a new draft when
                  identities need to be separated.
                </p>
              </>
            ) : (
              <>
                <div className="form-grid">
                  {(
                    [
                      ["left_point_id", "Source point"],
                      ["right_point_id", "Other sheet point"],
                    ] as const
                  ).map(([key, title], index) => (
                    <label className="form-field" key={key}>
                      {title}
                      <select
                        name={key}
                        aria-label={title}
                        required
                        defaultValue={project.nodes[index]?.id}
                        disabled={!data.can_edit}
                      >
                        <option value="">Choose point</option>
                        {project.nodes.map((n) => (
                          <option key={n.id} value={n.id}>
                            {name(n)}
                          </option>
                        ))}
                      </select>
                    </label>
                  ))}
                </div>
                <div className="form-grid">
                  {(
                    [
                      ["left_size", "Source nominal pipe size"],
                      ["right_size", "Other nominal pipe size"],
                    ] as const
                  ).map(([key, title]) => (
                    <label className="form-field" key={key}>
                      {title}
                      <input
                        name={key}
                        aria-label={title}
                        required
                        maxLength={40}
                        placeholder="e.g. 8 in"
                        disabled={!data.can_edit}
                      />
                    </label>
                  ))}
                </div>
                <div className="form-grid">
                  {(
                    [
                      [
                        "left_candidate_id",
                        "Printed reference for source point",
                      ],
                      [
                        "right_candidate_id",
                        "Printed reference for other point",
                      ],
                    ] as const
                  ).map(([key, title]) => (
                    <label className="form-field" key={key}>
                      {title}
                      <select
                        name={key}
                        aria-label={title}
                        disabled={!data.can_edit}
                      >
                        <option value="">Explicit manual source proof</option>
                        {data.candidates.map((c) => (
                          <option key={c.id} value={c.id}>
                            {project.sheets.find((s) => s.id === c.sheet_id)
                              ?.printed_id || "Sheet"}{" "}
                            · {c.source_text.slice(0, 100)}
                          </option>
                        ))}
                      </select>
                    </label>
                  ))}
                </div>
                <label className="form-field">
                  Coordinate comparison tolerance
                  <input
                    name="tolerance_text"
                    aria-label="Coordinate comparison tolerance"
                    defaultValue="0.01 mm"
                    required
                    maxLength={100}
                    disabled={!data.can_edit}
                  />
                </label>
                <label className="form-field">
                  Connection decision
                  <select
                    aria-label="Connection decision"
                    value={decision}
                    onChange={(e) => setDecision(e.target.value)}
                    disabled={!data.can_edit}
                  >
                    <option value="PROPOSE">
                      Save comparison and retain both points
                    </option>
                    <option value="ACCEPT_IDENTITY">
                      Confirm identical interface and share one point ID
                    </option>
                    <option value="REJECT">
                      Reject this proposed connection
                    </option>
                  </select>
                </label>
              </>
            )}
            <label className="form-field">
              Continuation engineering evidence
              <textarea
                name="evidence"
                aria-label="Continuation engineering evidence"
                defaultValue={link?.evidence || ""}
                required
                minLength={10}
                maxLength={3000}
                disabled={!data.can_edit}
              />
            </label>
            <label className="check-field">
              <input
                type="checkbox"
                name="topology_confirmed"
                aria-label="Confirm continuation interface identity and topology"
                required={!link && decision === "ACCEPT_IDENTITY"}
                disabled={!data.can_edit}
              />{" "}
              I inspected the source symbols and confirm the same physical
              interface, component identity and topology.
            </label>
            <div className="modal-actions">
              <button
                type="button"
                className="button secondary"
                onClick={close}
              >
                Cancel
              </button>
              {data.can_edit && (
                <button
                  className="button primary"
                  disabled={busy || (!link && project.nodes.length < 2)}
                >
                  {busy ? (
                    <Loader2 className="spin" size={16} />
                  ) : (
                    <Link2 size={16} />
                  )}{" "}
                  Save continuation review
                </button>
              )}
            </div>
          </form>
        </Dialog>
      )}
    </div>
  );
}
