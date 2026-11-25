import { useEffect, useState } from "react";
import { MapPin } from "lucide-react";
import { api, label, type Project } from "./types";
import { Dialog } from "./ui";

type Proposal = {
  id: string;
  candidate_id: string;
  source_label: string;
  point_id: string;
  review_label: string | null;
  sheet_id: string;
  axis: string;
  source_text: string;
  source_format: string;
  proposed_value_mm: string | null;
  accepted_value_mm: string | null;
  status: string;
  can_accept: boolean;
};
export function SourceCoordinates({
  project,
  onUpdate,
}: {
  project: Project;
  onUpdate: (p: Project) => void;
}) {
  const [data, setData] = useState<{
    proposals: Proposal[];
    can_edit: boolean;
  } | null>(null);
  const [open, setOpen] = useState(false),
    [candidate, setCandidate] = useState(""),
    [revision, setRevision] = useState(project.version);
  const [evidence, setEvidence] = useState(""),
    [tolerance, setTolerance] = useState(""),
    [confirmed, setConfirmed] = useState(false);
  const [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  const path = `/projects/${project.id}/physical-model/source-coordinates`;
  useEffect(() => {
    let alive = true;
    api<{ proposals: Proposal[]; can_edit: boolean }>(path)
      .then((v) => {
        if (alive) setData(v);
      })
      .catch((e) => {
        if (alive) setError(e.message);
      });
    return () => {
      alive = false;
    };
  }, [project.id, project.version]);
  const groups = [
    ...new Map(
      (data?.proposals || []).map((p) => [p.candidate_id, p]),
    ).values(),
  ];
  const selected = (data?.proposals || []).filter(
    (p) => p.candidate_id === candidate,
  );
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
        disabled={!groups.length}
        onClick={() => {
          setCandidate(groups[0]?.candidate_id || "");
          setRevision(project.version);
          setEvidence("");
          setTolerance("");
          setConfirmed(false);
          setError("");
          setOpen(true);
        }}
      >
        <MapPin size={15} />
        Review printed XYZ
      </button>
      {open && (
        <Dialog
          title="Review printed source coordinates"
          subtitle="Exact printed E / S / EL text, separate from engineering stations and route order."
          onClose={close}
          wide
        >
          {error && (
            <div className="notice amber" role="alert">
              {error}
            </div>
          )}
          <div className="notice">
            Inspect and confirm this point’s source feature in Drawing workspace
            first. Accepting XYZ does not approve a connection, route station or
            engineering model.
          </div>
          <label className="form-field">
            Printed coordinate reference
            <select
              aria-label="Printed coordinate reference"
              value={candidate}
              onChange={(e) => {
                setCandidate(e.target.value);
                setConfirmed(false);
              }}
            >
              {groups.map((p) => (
                <option key={p.candidate_id} value={p.candidate_id}>
                  {p.source_label} · {p.review_label || "Unnumbered point"}
                </option>
              ))}
            </select>
          </label>
          <div className="review-grid">
            {selected.map((p) => (
              <div className="notice" key={p.id}>
                <div>
                  <b>
                    {p.axis}: {p.source_text}
                  </b>
                  <p>
                    Proposed conversion: {p.proposed_value_mm ?? "unknown"} mm
                  </p>
                  <small>
                    {label(p.status)} ·{" "}
                    {p.accepted_value_mm === null
                      ? "No accepted value"
                      : `Accepted: ${p.accepted_value_mm} mm`}
                  </small>
                </div>
              </div>
            ))}
          </div>
          <label className="form-field">
            Declared coordinate tolerance
            <input
              aria-label="Declared coordinate tolerance"
              placeholder="Explicit comparison tolerance, e.g. 0 mm"
              value={tolerance}
              onChange={(e) => setTolerance(e.target.value)}
            />
            <small>
              Declare the numerical constraint allowance. This does not assert
              survey accuracy.
            </small>
          </label>
          <label className="form-field">
            Coordinate source evidence
            <textarea
              aria-label="Coordinate source evidence"
              value={evidence}
              onChange={(e) => setEvidence(e.target.value)}
              placeholder="Record the source coordinate block, physical interface and interpretation."
            />
          </label>
          <label className="checkbox-field">
            <input
              type="checkbox"
              aria-label="Confirm printed XYZ source evidence"
              checked={confirmed}
              onChange={(e) => setConfirmed(e.target.checked)}
            />
            I have inspected the three printed coordinates, source point and
            declared tolerance
          </label>
          <div className="dialog-actions">
            <button
              className="button secondary"
              onClick={close}
              disabled={busy}
            >
              Cancel
            </button>
            <button
              className="button primary"
              disabled={
                busy ||
                !data?.can_edit ||
                !confirmed ||
                !tolerance.trim() ||
                evidence.trim().length < 10 ||
                selected.length !== 3 ||
                selected.some((p) => !p.can_accept)
              }
              onClick={async () => {
                setBusy(true);
                setError("");
                try {
                  onUpdate(
                    await api<Project>(`${path}/${candidate}/accept`, {
                      method: "POST",
                      body: JSON.stringify({
                        version: revision,
                        tolerance_text: tolerance,
                        evidence,
                        confirmed: true,
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
              Accept printed XYZ coordinates
            </button>
          </div>
        </Dialog>
      )}
    </>
  );
}
