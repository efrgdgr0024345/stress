import { useEffect, useState } from "react";
import {
  ArrowLeftRight,
  CheckCircle2,
  Loader2,
  Ruler,
  Trash2,
} from "lucide-react";
import { api, label, pointLabel, type Project } from "./types";
import { Dialog } from "./ui";

type StationKind = "ABSOLUTE" | "DELTA" | "LOCAL_ORIGIN";
type SourceFormat =
  "STANDARD" | "ISO_FT_IN_DOT_FRACTION" | "ISO_IN_DOT_FRACTION";
type Constraint = {
  id: string;
  kind: StationKind;
  from_point_id: string;
  to_point_id: string | null;
  source_text: string;
  source_format?: SourceFormat;
  tolerance_text: string;
  sheet_id: string;
  evidence: string;
  source_proposal_id?: string | null;
};
type GapProposal = {
  id: string;
  source_label: string;
  from_point_id: string | null;
  to_point_id: string | null;
  from_label: string | null;
  to_label: string | null;
  source_text: string;
  source_format: SourceFormat;
  proposed_distance_mm: string | null;
  sheet_id: string;
  evidence: string;
};
type StationPoint = {
  point_id: string;
  line_id: string;
  route: string | null;
  status: string;
  proposed_station_mm: string | null;
  relative_station_mm: string | null;
  basis: "ABSOLUTE" | "LOCAL_ORIGIN" | null;
  basis_point_id: string | null;
  can_apply: boolean;
};
type StationReport = {
  revision?: number;
  constraints: Constraint[];
  proposals?: GapProposal[];
  solution: {
    can_apply: boolean;
    points: StationPoint[];
    issues: { code: string; message: string; point_ids?: string[] }[];
  };
  can_edit: boolean;
};

export function StationControls({
  project,
  onUpdate,
}: {
  project: Project;
  onUpdate: (project: Project) => void;
}) {
  const path = `/projects/${project.id}/physical-model/stations`;
  const [data, setData] = useState<StationReport | null>(null),
    [mode, setMode] = useState<"review" | "apply" | "remove" | null>(null),
    [version, setVersion] = useState(project.version),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  const [constraintId, setConstraintId] = useState(""),
    [kind, setKind] = useState<StationKind>("ABSOLUTE"),
    [from, setFrom] = useState(""),
    [to, setTo] = useState(""),
    [sourceText, setSourceText] = useState(""),
    [sourceFormat, setSourceFormat] = useState<SourceFormat>("STANDARD"),
    [tolerance, setTolerance] = useState("0 mm"),
    [sheet, setSheet] = useState(""),
    [evidence, setEvidence] = useState(""),
    [proposalId, setProposalId] = useState(""),
    [directionConfirmed, setDirectionConfirmed] = useState(false);
  useEffect(() => {
    let active = true;
    api<StationReport>(path)
      .then((value) => {
        if (active) {
          setData(value);
          if (!mode) setError("");
        }
      })
      .catch((e) => {
        if (active) setError(e.message);
      });
    return () => {
      active = false;
    };
  }, [project.id, project.version]);
  const name = (id: string | null) => {
    const point = project.nodes.find((n) => n.id === id);
    return point ? pointLabel(point) : "Unlocated point";
  };
  const choose = (id: string) => {
    const saved = data?.constraints.find((c) => c.id === id);
    setConstraintId(id);
    setKind(saved?.kind || "ABSOLUTE");
    setFrom(saved?.from_point_id || project.nodes[0]?.id || "");
    setTo(saved?.to_point_id || project.nodes[1]?.id || "");
    setSourceText(saved?.source_text || "");
    setSourceFormat(saved?.source_format || "STANDARD");
    setTolerance(saved?.tolerance_text || "0 mm");
    setSheet(
      saved?.sheet_id ||
        project.nodes[0]?.instances[0]?.sheet_id ||
        project.sheets[0]?.id ||
        "",
    );
    setEvidence(saved?.evidence || "");
    setProposalId(saved?.source_proposal_id || "");
    setDirectionConfirmed(false);
  };
  const proposal = data?.proposals?.find((p) => p.id === proposalId);
  const detachProposal = () => {
    setProposalId("");
    setDirectionConfirmed(false);
    if (evidence === proposal?.evidence) setEvidence("");
  };
  const endpoint = (which: "from" | "to", next: string) => {
    const a = which === "from" ? next : from;
    const b = which === "to" ? next : to;
    if (
      proposal &&
      !(
        a !== b &&
        [a, b].includes(proposal.from_point_id || "") &&
        [a, b].includes(proposal.to_point_id || "")
      )
    )
      detachProposal();
    setDirectionConfirmed(false);
    if (which === "from") setFrom(next);
    else setTo(next);
  };
  const open = (next: "review" | "apply") => {
    setVersion(project.version);
    setError("");
    choose("");
    setMode(next);
  };
  const close = () => {
    if (!busy) {
      setMode(null);
      setError("");
    }
  };
  const current = data?.revision === undefined || data.revision === version;
  const qualified = data?.solution.points.filter((p) => p.can_apply) || [];
  const pointOptions = project.nodes.map((n) => (
    <option key={n.id} value={n.id}>
      {pointLabel(n)} · {n.line_id} · {n.route || "Unassigned route"}
    </option>
  ));
  return (
    <div className="physical-controls">
      <div className="review-actions">
        <button
          className="button secondary"
          disabled={!data || !project.nodes.length}
          onClick={() => open("review")}
        >
          <Ruler size={16} /> Along-route stations
        </button>
        <button
          className="button secondary"
          disabled={!data?.can_edit || !data.solution.can_apply}
          onClick={() => open("apply")}
          title="Apply only fully anchored stations from current along-centreline evidence"
        >
          <CheckCircle2 size={16} /> Apply station solution
        </button>
        <span className="fine-print">
          {qualified.length} fully anchored station proposals · coordinates and
          route order require their own evidence
        </span>
      </div>
      {error && !mode && (
        <p className="error-text" role="alert">
          {error}
        </p>
      )}
      {mode && data && (
        <Dialog
          wide
          title={
            mode === "apply"
              ? "Apply along-route station solution"
              : mode === "remove"
                ? "Remove station evidence"
                : "Source along-route stations"
          }
          subtitle={`Revision ${version} · Explicit along-centreline distances and datum`}
          onClose={close}
        >
          <form
            key={`${mode}:${constraintId}`}
            onSubmit={async (event) => {
              event.preventDefault();
              setBusy(true);
              setError("");
              const form = new FormData(event.currentTarget);
              try {
                const body =
                  mode === "apply"
                    ? {
                        version,
                        reason: form.get("decision_evidence"),
                        confirmed: true,
                      }
                    : mode === "remove"
                      ? {
                          version,
                          reason: form.get("decision_evidence"),
                          confirmed: true,
                        }
                      : {
                          version,
                          kind,
                          from_point_id: from,
                          to_point_id: kind === "DELTA" ? to : null,
                          source_text:
                            kind === "LOCAL_ORIGIN" ? "0 mm" : sourceText,
                          source_format:
                            kind === "LOCAL_ORIGIN" ? "STANDARD" : sourceFormat,
                          tolerance_text: tolerance,
                          sheet_id: sheet,
                          evidence,
                          distance_basis: "ALONG_CENTRELINE",
                          source_proposal_id: proposalId || null,
                          confirmed: true,
                        };
                const url =
                  mode === "apply"
                    ? `${path}/apply`
                    : `${path}/constraints${constraintId ? "/" + constraintId : ""}`;
                const updated = await api<Project>(url, {
                  method:
                    mode === "remove"
                      ? "DELETE"
                      : mode === "review" && constraintId
                        ? "PATCH"
                        : "POST",
                  body: JSON.stringify(body),
                });
                onUpdate(updated);
                setMode(null);
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
            {!current && (
              <p className="notice amber" role="status">
                Station evidence is refreshing for this revision. Close and
                reopen the dialog if the project changed while it was open.
              </p>
            )}
            <div className="notice">
              <Ruler size={20} />
              <div>
                <strong>Along-centreline evidence</strong>
                <p>
                  Record the actual source distance along the route, including
                  any documented bend allowance. Signed XYZ, Euclidean point
                  distance and drawing proportions do not establish a route
                  station. Unproved stations remain blank until an anchored
                  solution is explicitly applied.
                </p>
              </div>
            </div>
            {mode === "review" && (
              <>
                <label className="form-field">
                  Saved station constraint
                  <select
                    aria-label="Saved station constraint"
                    value={constraintId}
                    onChange={(event) => choose(event.target.value)}
                    disabled={busy}
                  >
                    <option value="">New source station evidence</option>
                    {data.constraints.map((c) => (
                      <option key={c.id} value={c.id}>
                        {label(c.kind)} · {name(c.from_point_id)}
                        {c.to_point_id
                          ? ` → ${name(c.to_point_id)}`
                          : ""} · {c.source_text}
                      </option>
                    ))}
                  </select>
                </label>
                {!!data.proposals?.length && (
                  <label className="form-field">
                    Printed support-gap proposal
                    <select
                      aria-label="Printed support-gap proposal"
                      value={proposalId}
                      disabled={!data.can_edit || busy}
                      onChange={(event) => {
                        const next = data.proposals?.find(
                          (p) => p.id === event.target.value,
                        );
                        setProposalId(next?.id || "");
                        setDirectionConfirmed(false);
                        if (next) {
                          setConstraintId("");
                          setKind("DELTA");
                          setFrom(next.from_point_id || "");
                          setTo(next.to_point_id || "");
                          setSourceText(next.source_text);
                          setSourceFormat(next.source_format);
                          setSheet(next.sheet_id);
                          setEvidence(next.evidence);
                          setTolerance("0 mm");
                        }
                      }}
                    >
                      <option value="">Enter other source evidence</option>
                      {data.proposals.map((p) => (
                        <option
                          key={p.id}
                          value={p.id}
                          disabled={
                            !p.from_point_id ||
                            !p.to_point_id ||
                            p.from_point_id === p.to_point_id
                          }
                        >
                          {p.source_label} · {p.from_label || "Unlocated"} ↔{" "}
                          {p.to_label || "Unlocated"} · {p.source_text}
                        </option>
                      ))}
                    </select>
                  </label>
                )}
                {proposal && (
                  <div className="notice">
                    <Ruler size={18} />
                    <div>
                      <strong>Printed source support gap</strong>
                      <p>
                        {proposal.source_text} ·{" "}
                        {proposal.proposed_distance_mm ?? "Unproved"} mm ·{" "}
                        {proposal.source_label}
                      </p>
                      <p className="fine-print">
                        The source distance is unsigned. Explicitly choose its
                        positive stationing direction; the route and datum still
                        require review.
                      </p>
                      <button
                        type="button"
                        className="button secondary"
                        disabled={!data.can_edit || busy}
                        onClick={() => {
                          setFrom(to);
                          setTo(from);
                          setDirectionConfirmed(false);
                        }}
                      >
                        <ArrowLeftRight size={15} /> Reverse stationing
                        direction
                      </button>
                    </div>
                  </div>
                )}
                <div className="form-grid">
                  <label className="form-field">
                    Station evidence type
                    <select
                      aria-label="Station evidence type"
                      value={kind}
                      onChange={(event) => {
                        const next = event.target.value as StationKind;
                        if (next !== "DELTA") detachProposal();
                        if (next === "LOCAL_ORIGIN") {
                          setSourceText("0 mm");
                          setSourceFormat("STANDARD");
                        } else if (kind === "LOCAL_ORIGIN") setSourceText("");
                        setKind(next);
                      }}
                      disabled={!data.can_edit || busy}
                    >
                      <option value="ABSOLUTE">
                        Explicit absolute route station
                      </option>
                      <option value="DELTA">
                        Signed along-route difference
                      </option>
                      <option value="LOCAL_ORIGIN">
                        Declare local station datum (0 mm)
                      </option>
                    </select>
                  </label>
                  <label className="form-field">
                    From point / station point
                    <select
                      aria-label="From point / station point"
                      value={from}
                      onChange={(event) => endpoint("from", event.target.value)}
                      required
                      disabled={!data.can_edit || busy}
                    >
                      <option value="">Choose source point</option>
                      {pointOptions}
                    </select>
                  </label>
                  {kind === "DELTA" && (
                    <label className="form-field">
                      To point
                      <select
                        aria-label="To point"
                        value={to}
                        onChange={(event) => endpoint("to", event.target.value)}
                        required
                        disabled={!data.can_edit || busy}
                      >
                        <option value="">Choose other source point</option>
                        {pointOptions}
                      </select>
                    </label>
                  )}
                  <label className="form-field">
                    Source drawing page
                    <select
                      aria-label="Station source drawing page"
                      value={sheet}
                      onChange={(event) => {
                        if (
                          proposal &&
                          event.target.value !== proposal.sheet_id
                        )
                          detachProposal();
                        setSheet(event.target.value);
                      }}
                      required
                      disabled={!data.can_edit || busy}
                    >
                      {project.sheets.map((s) => (
                        <option key={s.id} value={s.id}>
                          {s.printed_id || s.filename} · page {s.page_index + 1}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label className="form-field">
                    Source number convention
                    <select
                      aria-label="Station source number convention"
                      value={sourceFormat}
                      onChange={(event) => {
                        if (
                          proposal &&
                          event.target.value !== proposal.source_format
                        )
                          detachProposal();
                        setSourceFormat(event.target.value as SourceFormat);
                      }}
                      disabled={
                        !data.can_edit || busy || kind === "LOCAL_ORIGIN"
                      }
                    >
                      <option value="STANDARD">
                        Standard explicit units / feet-inch fractions
                      </option>
                      <option value="ISO_FT_IN_DOT_FRACTION">
                        Printed feet/inches dot fraction (verify notation)
                      </option>
                      <option value="ISO_IN_DOT_FRACTION">
                        Printed inch dot fraction, e.g. 2.1/8" (verify notation)
                      </option>
                    </select>
                  </label>
                  <label className="form-field">
                    Original along-route source dimension
                    <input
                      aria-label="Original along-route source dimension"
                      value={sourceText}
                      onChange={(event) => {
                        if (
                          proposal &&
                          event.target.value !== proposal.source_text
                        )
                          detachProposal();
                        setSourceText(event.target.value);
                      }}
                      required
                      maxLength={100}
                      readOnly={kind === "LOCAL_ORIGIN"}
                      disabled={!data.can_edit || busy}
                      placeholder={"e.g. 4' 0 1/2\" or 1231.9 mm"}
                    />
                  </label>
                  <label className="form-field">
                    Declared station tolerance
                    <input
                      aria-label="Declared station tolerance"
                      value={tolerance}
                      onChange={(event) => setTolerance(event.target.value)}
                      required
                      maxLength={100}
                      disabled={!data.can_edit || busy}
                    />
                  </label>
                </div>
                {proposal && (
                  <label className="check-field">
                    <input
                      type="checkbox"
                      aria-label="Confirm stationing direction for the printed gap"
                      checked={directionConfirmed}
                      onChange={(event) =>
                        setDirectionConfirmed(event.target.checked)
                      }
                      required
                      disabled={!data.can_edit || busy}
                    />{" "}
                    I explicitly choose {name(from)} → {name(to)} as positive
                    stationing direction for this unsigned source gap.
                  </label>
                )}
                {kind === "LOCAL_ORIGIN" && (
                  <label className="check-field">
                    <input
                      type="checkbox"
                      aria-label="Explicitly declare local station datum at zero"
                      required
                      disabled={!data.can_edit || busy}
                    />{" "}
                    I explicitly declare this point station 0 for a local route
                    datum. This declaration establishes no surveyed absolute
                    station.
                  </label>
                )}
                <label className="form-field">
                  Along-route source evidence
                  <textarea
                    aria-label="Along-route source evidence"
                    value={evidence}
                    onChange={(event) => setEvidence(event.target.value)}
                    required
                    minLength={10}
                    maxLength={3000}
                    disabled={!data.can_edit || busy}
                  />
                </label>
                <label className="check-field">
                  <input
                    type="checkbox"
                    aria-label="Confirm along-centreline station evidence"
                    required
                    disabled={!data.can_edit || busy}
                  />{" "}
                  I inspected the source and confirm this is an along-centreline
                  station, distance or explicit local datum.
                </label>
              </>
            )}
            {mode === "remove" && (
              <p>
                Remove the selected{" "}
                {name(
                  data.constraints.find((c) => c.id === constraintId)
                    ?.from_point_id || null,
                )}{" "}
                source constraint from the active solution. Dependent station
                proof requires review again.
              </p>
            )}
            {mode !== "remove" && (
              <>
                <h3>Current station solution</h3>
                {data.solution.points.some(
                  (point) => point.status === "TOPOLOGY_REQUIRED",
                ) && (
                  <p className="fine-print">
                    Review source locations and explicit route order in Drawing
                    workspace before applying their stations. Unassigned points
                    retain unknown stations here.
                  </p>
                )}
                {!!data.solution.issues.length && (
                  <div className="notice amber" role="status">
                    <div>
                      {data.solution.issues.map((issue, index) => (
                        <p key={`${issue.code}:${index}`}>
                          <strong>{label(issue.code)}</strong> · {issue.message}
                        </p>
                      ))}
                    </div>
                  </div>
                )}
                <div className="results-table-scroll">
                  <table className="results-grid station-solution-grid">
                    <thead>
                      <tr>
                        <th>Point</th>
                        <th>Route</th>
                        <th>Proposed station (mm)</th>
                        <th>Relative distance (mm)</th>
                        <th>State</th>
                        <th>Datum</th>
                      </tr>
                    </thead>
                    <tbody>
                      {(mode === "apply"
                        ? qualified
                        : data.solution.points
                      ).map((point) => (
                        <tr key={point.point_id}>
                          <th>{name(point.point_id)}</th>
                          <td>{point.route || "Unassigned"}</td>
                          <td>{point.proposed_station_mm ?? "N/A"}</td>
                          <td>{point.relative_station_mm ?? "N/A"}</td>
                          <td>{label(point.status)}</td>
                          <td>
                            {point.basis === "LOCAL_ORIGIN"
                              ? "Declared local datum"
                              : point.basis === "ABSOLUTE"
                                ? "Source absolute datum"
                                : "Unanchored"}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </>
            )}
            {mode === "apply" && (
              <p className="fine-print">
                {qualified.length} fully anchored point
                {qualified.length === 1 ? "" : "s"} will receive the displayed
                station proof. Other points remain unresolved. This action does
                not assign route order or accept XYZ.
              </p>
            )}
            {mode !== "review" && (
              <>
                <label className="form-field">
                  Station decision evidence
                  <textarea
                    name="decision_evidence"
                    aria-label="Station decision evidence"
                    required
                    minLength={10}
                    maxLength={3000}
                    disabled={busy}
                  />
                </label>
                <label className="check-field">
                  <input
                    type="checkbox"
                    aria-label="Confirm station solution decision"
                    required
                    disabled={busy}
                  />{" "}
                  I inspected the displayed evidence and confirm this station
                  decision.
                </label>
              </>
            )}
            <div className="modal-actions">
              <button
                type="button"
                className="button secondary"
                onClick={close}
                disabled={busy}
              >
                Cancel
              </button>
              {mode === "review" && constraintId && data.can_edit && (
                <button
                  type="button"
                  className="button secondary"
                  onClick={() => {
                    setError("");
                    setMode("remove");
                  }}
                  disabled={busy || !current}
                >
                  <Trash2 size={16} /> Remove station evidence
                </button>
              )}
              {data.can_edit && (
                <button
                  className="button primary"
                  disabled={
                    busy ||
                    !current ||
                    (mode === "apply" && !data.solution.can_apply)
                  }
                >
                  {busy ? (
                    <Loader2 className="spin" size={16} />
                  ) : mode === "apply" ? (
                    <CheckCircle2 size={16} />
                  ) : (
                    <Ruler size={16} />
                  )}{" "}
                  {mode === "apply"
                    ? "Accept proved route stations"
                    : mode === "remove"
                      ? "Remove selected station evidence"
                      : "Save station evidence"}
                </button>
              )}
            </div>
          </form>
        </Dialog>
      )}
    </div>
  );
}
