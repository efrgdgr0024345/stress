import { useEffect, useState } from "react";
import { ClipboardList } from "lucide-react";
import { api, label, type Project } from "./types";
import { Dialog } from "./ui";

type Exception = {
  id: string;
  code: string;
  evidence: string;
  message: string;
  status: string;
  source_context_sha256: string;
  available_decisions: string[];
};
type Report = {
  all: Exception[];
  can_edit: boolean;
  reviews: {
    id: string;
    exception_id: string;
    decision: string;
    evidence: string;
    reviewed_at: string;
    is_latest: boolean;
    current: boolean;
    stale: boolean;
  }[];
  station_constraints: {
    id: string;
    kind: string;
    source_text: string;
    value_mm: string;
  }[];
};
export function SourceExceptions({
  project,
  onUpdate,
}: {
  project: Project;
  onUpdate: (p: Project) => void;
}) {
  const [data, setData] = useState<Report | null>(null);
  const [open, setOpen] = useState(false),
    [exception, setException] = useState("");
  const [decision, setDecision] = useState("RETAIN_UNRESOLVED"),
    [constraint, setConstraint] = useState("");
  const [evidence, setEvidence] = useState(""),
    [confirmed, setConfirmed] = useState(false);
  const [revision, setRevision] = useState(project.version),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  const path = `/projects/${project.id}/physical-model/source-exceptions`;
  useEffect(() => {
    let current = true;
    api<Report>(path)
      .then((v) => {
        if (current) setData(v);
      })
      .catch((e) => {
        if (current) setError(e.message);
      });
    return () => {
      current = false;
    };
  }, [project.id, project.version]);
  const selected = data?.all.find((v) => v.id === exception);
  const close = () => {
    if (!busy) {
      setOpen(false);
      setError("");
    }
  };
  return (
    <>
      <button
        className="button secondary"
        disabled={!data?.all.length}
        onClick={() => {
          setException(data?.all[0]?.id || "");
          setDecision("RETAIN_UNRESOLVED");
          setConstraint("");
          setEvidence("");
          setConfirmed(false);
          setRevision(project.version);
          setError("");
          setOpen(true);
        }}
      >
        <ClipboardList size={15} />
        Review source exceptions
      </button>
      {open && (
        <Dialog
          title="Review source exception"
          subtitle="Source-bound evidence and reversible review history. Missing facts stay blue."
          onClose={close}
          wide
        >
          {error && (
            <div className="notice amber" role="alert">
              {error}
            </div>
          )}
          <label className="form-field">
            Source exception
            <select
              aria-label="Source exception"
              value={exception}
              onChange={(e) => {
                setException(e.target.value);
                setDecision("RETAIN_UNRESOLVED");
                setConfirmed(false);
                setConstraint("");
                setEvidence("");
              }}
            >
              {data?.all.map((v, i) => (
                <option key={v.id} value={v.id}>
                  {i + 1}. {label(v.code)} · {label(v.status)}
                </option>
              ))}
            </select>
          </label>
          <div className="notice">
            <strong>{label(selected?.code || "")}</strong>
            <p>{selected?.evidence || selected?.message}</p>
            <small>
              Current state: {label(selected?.status || "")}. Recording an
              explanation never accepts a coordinate, station, component
              connection or engineering approval.
            </small>
          </div>
          {!!data?.reviews.filter((v) => v.exception_id === exception)
            .length && (
            <div
              className="notice"
              aria-label="Source exception review history"
            >
              <strong>Review history</strong>
              {data.reviews
                .filter((v) => v.exception_id === exception)
                .map((v) => (
                  <div key={v.id}>
                    <p>
                      <b>{label(v.decision)}</b> · {v.reviewed_at}
                    </p>
                    <p>{v.evidence}</p>
                    <small>
                      {v.is_latest
                        ? v.current
                          ? "Current source-bound review"
                          : "Latest review needs current source evidence"
                        : "Earlier review retained"}
                    </small>
                  </div>
                ))}
            </div>
          )}
          <label className="form-field">
            Review decision
            <select
              aria-label="Source exception decision"
              value={decision}
              onChange={(e) => {
                setDecision(e.target.value);
                setConfirmed(false);
              }}
            >
              {(selected?.available_decisions || []).map((v) => (
                <option key={v} value={v}>
                  {label(v)}
                </option>
              ))}
            </select>
          </label>
          {decision === "CONFIRM_WITNESS_MAPPING" && (
            <label className="form-field">
              Accepted source station constraint
              <select
                aria-label="Source witness station constraint"
                value={constraint}
                onChange={(e) => {
                  setConstraint(e.target.value);
                  setConfirmed(false);
                }}
              >
                <option value="">
                  Select the separately accepted along-centreline witness
                  mapping
                </option>
                {data?.station_constraints
                  .filter((c) => c.kind === "DELTA")
                  .map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.source_text} · {c.value_mm} mm · {c.id.slice(0, 8)}
                    </option>
                  ))}
              </select>
              <small>
                The server checks the original printed length, current source
                page and accepted witness evidence. This review cannot create a
                constraint.
              </small>
            </label>
          )}
          <label className="form-field">
            Source exception review evidence
            <textarea
              aria-label="Source exception review evidence"
              value={evidence}
              onChange={(e) => setEvidence(e.target.value)}
              placeholder="Explain the source evidence, chosen witness mapping, or missing information."
            />
          </label>
          <label className="checkbox-field">
            <input
              type="checkbox"
              aria-label="Confirm source exception decision"
              checked={confirmed}
              onChange={(e) => setConfirmed(e.target.checked)}
            />
            I have reviewed this source exception and the stated evidence
          </label>
          <div className="dialog-actions">
            <button
              className="button secondary"
              disabled={busy}
              onClick={close}
            >
              Cancel
            </button>
            <button
              className="button primary"
              disabled={
                busy ||
                !data?.can_edit ||
                !selected ||
                !selected.available_decisions.includes(decision) ||
                !confirmed ||
                evidence.trim().length < 10 ||
                (decision === "CONFIRM_WITNESS_MAPPING" && !constraint)
              }
              onClick={async () => {
                if (!selected) return;
                setBusy(true);
                setError("");
                try {
                  onUpdate(
                    await api<Project>(`${path}/decision`, {
                      method: "POST",
                      body: JSON.stringify({
                        version: revision,
                        exception_id: selected.id,
                        decision,
                        evidence,
                        confirmed: true,
                        constraint_ids:
                          decision === "CONFIRM_WITNESS_MAPPING"
                            ? [constraint]
                            : [],
                        source_context_sha256: selected.source_context_sha256,
                      }),
                    }),
                  );
                  setOpen(false);
                } catch (e) {
                  setError((e as Error).message);
                } finally {
                  setBusy(false);
                }
              }}
            >
              Save source exception review
            </button>
          </div>
        </Dialog>
      )}
    </>
  );
}
