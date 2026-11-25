import { useEffect, useState } from "react";
import { Eye, GitBranch, History, Loader2, Network } from "lucide-react";
import { api, pointLabel, type Project } from "./types";
import { Dialog } from "./ui";

type Assignment = {
  point_id: string;
  topology_state: "ASSIGNED" | "UNASSIGNED";
  line_id: string;
  route: string | null;
  order: number | null;
  takeoff_id: string | null;
  topology_confirmed: boolean;
};
type ReviewPoint = Omit<Assignment, "topology_confirmed"> & {
  point_label: string;
  number: number | null;
  source_location_reviewed: boolean;
  has_source_observations: boolean;
  station_mm: string | null;
  instances: { sheet_id: string }[];
};
type Mapping = { point_id: string; old: number | null; new: number | null };
type GraphIssue = {
  code: string;
  message: string;
  point_ids: string[];
  blocks_apply: boolean;
};
type Report = {
  revision: number;
  can_edit?: boolean;
  can_apply: boolean;
  points: ReviewPoint[];
  summary: {
    points: number;
    assigned: number;
    unassigned: number;
    edges: number;
    lines: number;
    connected_assigned: boolean;
    complete: boolean;
  };
  graph: {
    points: string[];
    edges: { from: string; to: string; line_id: string; route: string }[];
  };
  issues: GraphIssue[];
  numbering_map: Mapping[];
  numbering_history?: {
    revision: number;
    action: string;
    reviewed_by: string;
    reviewed_at: string;
    mapping: Mapping[];
    alias_rows: {
      retired_point_id: string;
      physical_point_id: string;
      old: number | null;
      new: number | null;
    }[];
    point_instances: Record<string, { sheet_id: string }[]>;
  }[];
  preview_sha256?: string;
};
type Request = {
  version: number;
  assignments: Assignment[];
  reason: string;
  confirmed: true;
};

function RouteSchematic({
  report,
  name,
}: {
  report: Report;
  name: (id: string) => string;
}) {
  const assigned = report.points.filter(
    (p) =>
      p.topology_state === "ASSIGNED" && p.route != null && p.order != null,
  );
  const groups = [
    ...new Set(assigned.map((p) => `${p.line_id}\n${p.route}`)),
  ].sort();
  const locations = new Map<string, { x: number; y: number }>();
  let width = 900;
  groups.forEach((group, index) => {
    assigned
      .filter((p) => `${p.line_id}\n${p.route}` === group)
      .sort((a, b) => (a.order ?? 0) - (b.order ?? 0))
      .forEach((p, column) => {
        const x = 130 + column * 150;
        locations.set(p.point_id, { x, y: 75 + index * 105 });
        width = Math.max(width, x + 130);
      });
  });
  return (
    <div
      className="notice"
      aria-label="Explicit route graph"
      style={{ display: "block", color: "#37577d" }}
    >
      <b>Reviewed route schematic</b>
      <p className="fine-print">
        Abstract declared sequence and takeoffs. Spacing is not physical length
        or source geometry. {report.summary.unassigned} unassigned points remain
        outside this graph.
      </p>
      {!assigned.length ? (
        <p>No accepted route/order connections.</p>
      ) : (
        <div style={{ overflowX: "auto" }}>
          <svg
            role="img"
            aria-label="Reviewed route schematic"
            viewBox={`0 0 ${width} ${Math.max(150, groups.length * 105 + 50)}`}
            style={{ minWidth: 700, width: "100%" }}
          >
            {groups.map((group, index) => (
              <text
                key={group}
                x="10"
                y={40 + index * 105}
                fill="currentColor"
                fontSize="12"
              >
                {group.replace("\n", " · ")}
              </text>
            ))}
            {report.graph.edges.map((edge) => {
              const a = locations.get(edge.from),
                b = locations.get(edge.to);
              return a && b ? (
                <line
                  key={`${edge.from}:${edge.to}`}
                  x1={a.x}
                  y1={a.y}
                  x2={b.x}
                  y2={b.y}
                  stroke="#6196d8"
                  strokeWidth="3"
                >
                  <title>
                    {name(edge.from)} → {name(edge.to)} · {edge.route}
                  </title>
                </line>
              ) : null;
            })}
            {assigned.map((point) => {
              const position = locations.get(point.point_id)!;
              return (
                <g
                  key={point.point_id}
                  transform={`translate(${position.x},${position.y})`}
                >
                  <circle
                    r="20"
                    fill="#e5efff"
                    stroke="#4678bc"
                    strokeWidth="2"
                  />
                  <text textAnchor="middle" y="5" fill="#234d86" fontSize="13">
                    {point.number ?? point.point_label}
                  </text>
                  <text
                    textAnchor="middle"
                    y="37"
                    fill="currentColor"
                    fontSize="11"
                  >
                    {name(point.point_id)}
                    {point.instances.length > 1
                      ? ` · ${point.instances.length} sheets`
                      : ""}
                  </text>
                </g>
              );
            })}
          </svg>
        </div>
      )}
    </div>
  );
}

export function TopologyReviewControls({
  project,
  onUpdate,
  onInspect,
}: {
  project: Project;
  onUpdate: (project: Project) => void;
  onInspect: (pointId: string) => void;
}) {
  const path = `/projects/${project.id}/topology-review`;
  const [report, setReport] = useState<Report | null>(null);
  const [open, setOpen] = useState(false),
    [version, setVersion] = useState(project.version);
  const [drafts, setDrafts] = useState<Record<string, Assignment>>({});
  const [query, setQuery] = useState(""),
    [reason, setReason] = useState("");
  const [confirmed, setConfirmed] = useState(false),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  const [preview, setPreview] = useState<{
    report: Report;
    request: Request;
  } | null>(null);
  useEffect(() => {
    let active = true;
    api<Report>(path)
      .then((value) => {
        if (active) setReport(value);
      })
      .catch((e) => {
        if (active) setError(e.message);
      });
    return () => {
      active = false;
    };
  }, [project.id, project.version]);
  const sourceName = (id: string) => {
    const point = project.nodes.find((p) => p.id === id);
    return (
      point?.review_label ||
      (point ? pointLabel(point) : "Retired source point")
    );
  };
  const displayName = (id: string) => {
    const point = project.nodes.find((p) => p.id === id);
    if (!point) return "Retired source point";
    return `${pointLabel(point)}${point.number != null && point.review_label ? ` (${point.review_label})` : ""}`;
  };
  const invalidate = () => {
    setPreview(null);
    setConfirmed(false);
    setError("");
  };
  const edit = (id: string, change: Partial<Assignment>) => {
    invalidate();
    setDrafts((current) => {
      const next = {
        ...current[id],
        ...change,
        topology_confirmed: change.topology_confirmed ?? false,
      };
      if (change.topology_state === "UNASSIGNED")
        Object.assign(next, { route: null, order: null, takeoff_id: null });
      if (change.route === "main") next.takeoff_id = null;
      if (change.line_id && change.line_id !== current[id].line_id)
        next.takeoff_id = null;
      return { ...current, [id]: next };
    });
  };
  const close = () => {
    if (!busy) {
      setOpen(false);
      setError("");
    }
  };
  const current = report?.revision === version && project.version === version;
  const editable = Boolean(report?.can_edit && current && !busy);
  const shown = (report?.points || []).filter(
    (p) =>
      !query ||
      [
        displayName(p.point_id),
        p.line_id,
        p.route || "unassigned",
        project.nodes.find((n) => n.id === p.point_id)?.kind || "",
      ]
        .join(" ")
        .toLowerCase()
        .includes(query.toLowerCase()),
  );
  const lines = [
    ...new Set([
      project.line_id,
      ...project.sheets.map((s) => s.line_id),
      ...(report?.points.map((p) => p.line_id) || []),
    ]),
  ].filter(Boolean);
  const activeReport = preview?.report || report;
  return (
    <div className="physical-controls">
      <div className="review-actions">
        <button
          className="button secondary"
          disabled={!report || !project.nodes.length}
          onClick={() => {
            setVersion(project.version);
            setDrafts({});
            setQuery("");
            setReason("");
            setConfirmed(false);
            setPreview(null);
            setError("");
            setOpen(true);
          }}
        >
          <Network size={16} /> Review graph and numbering
        </button>
        <span className="fine-print">
          {report?.summary.assigned ?? 0} explicitly assigned ·{" "}
          {report?.summary.unassigned ?? project.nodes.length} unassigned ·
          geometry needs separate evidence
        </span>
      </div>
      {error && !open && (
        <p className="error-text" role="alert">
          {error}
        </p>
      )}
      {open && report && activeReport && (
        <Dialog
          wide
          title="Review ordered topology"
          subtitle={`Revision ${version} · Explicit source-inspected routes and deterministic numbering`}
          onClose={close}
        >
          <form
            onSubmit={async (event) => {
              event.preventDefault();
              setBusy(true);
              setError("");
              const request: Request = {
                version,
                assignments: Object.values(drafts),
                reason,
                confirmed: true,
              };
              try {
                const value = await api<Report>(`${path}/preview`, {
                  method: "POST",
                  body: JSON.stringify(request),
                });
                setPreview({ report: value, request });
              } catch (e) {
                setError((e as Error).message);
                setPreview(null);
              } finally {
                setBusy(false);
              }
            }}
          >
            <div
              className="notice"
              style={{ display: "block", color: "#37577d" }}
            >
              <b>Source inspection comes first.</b> Inspect each current source
              depiction in Drawing workspace, then explicitly declare route,
              sequence and any tee takeoff below. Page positions, nearby
              symbols, XYZ and station gaps never choose a route.
              <p className="fine-print">
                Main numbering: 10, 20, 30… Branches start at the next hundred.
                Additional full lines use the next thousand. Each physical UUID
                has one number across all source sheets. Numbering does not
                accept engineering geometry.
              </p>
            </div>
            {!current && (
              <div className="notice amber" role="alert">
                The project changed. Close this dialog and reopen it before
                previewing or applying.
              </div>
            )}
            {error && (
              <div className="notice amber" role="alert">
                {error}
              </div>
            )}
            <div className="review-actions">
              <label className="form-field">
                Find source point
                <input
                  aria-label="Find topology point"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="P001, full line or kind"
                />
              </label>
              <span>
                {Object.keys(drafts).length} selected for explicit review
              </span>
            </div>
            <div className="results-table-scroll" style={{ maxHeight: 420 }}>
              <table
                className="results-grid"
                aria-label="Topology assignment review"
              >
                <thead>
                  <tr>
                    <th>Include</th>
                    <th>Physical point / source</th>
                    <th>Topology state</th>
                    <th>Full line</th>
                    <th>Route</th>
                    <th>Order</th>
                    <th>Main tee takeoff</th>
                    <th>Explicit confirmation</th>
                  </tr>
                </thead>
                <tbody>
                  {shown.map((point) => {
                    const id = point.point_id,
                      draft = drafts[id],
                      value = draft || point;
                    const enabled =
                      editable &&
                      Boolean(draft) &&
                      point.source_location_reviewed;
                    const assigned = value.topology_state === "ASSIGNED";
                    const tees = report.points.filter((p) => {
                      const effective = drafts[p.point_id] || p;
                      return (
                        effective.topology_state === "ASSIGNED" &&
                        effective.route === "main" &&
                        effective.line_id === value.line_id &&
                        project.nodes.find((n) => n.id === p.point_id)?.kind ===
                          "tee"
                      );
                    });
                    return (
                      <tr key={id} data-point-id={id}>
                        <td>
                          <input
                            type="checkbox"
                            aria-label={`Include point ${sourceName(id)}`}
                            checked={Boolean(draft)}
                            disabled={
                              !editable || !point.source_location_reviewed
                            }
                            onChange={(e) => {
                              invalidate();
                              setDrafts((values) => {
                                const next = { ...values };
                                if (e.target.checked)
                                  next[id] = {
                                    point_id: id,
                                    topology_state: point.topology_state,
                                    line_id: point.line_id,
                                    route: point.route,
                                    order: point.order,
                                    takeoff_id: point.takeoff_id,
                                    topology_confirmed: false,
                                  };
                                else delete next[id];
                                return next;
                              });
                            }}
                          />
                        </td>
                        <td>
                          <b>{displayName(id)}</b>
                          <br />
                          <small>
                            {project.nodes.find((n) => n.id === id)?.kind} ·{" "}
                            {point.instances.length} source depiction
                            {point.instances.length === 1 ? "" : "s"}
                          </small>
                          <br />
                          <span
                            className={`badge ${point.source_location_reviewed ? "green" : "blue"}`}
                          >
                            {point.has_source_observations
                              ? point.source_location_reviewed
                                ? "Source inspected"
                                : "Source inspection required"
                              : "Existing manual point"}
                          </span>
                          <br />
                          <button
                            type="button"
                            className="button secondary"
                            disabled={busy}
                            onClick={() => {
                              close();
                              onInspect(id);
                            }}
                            aria-label={`Inspect source ${sourceName(id)}`}
                          >
                            <Eye size={13} /> Inspect source
                          </button>
                        </td>
                        <td>
                          <select
                            aria-label={`Topology state ${sourceName(id)}`}
                            disabled={!enabled}
                            value={value.topology_state}
                            onChange={(e) =>
                              edit(id, {
                                topology_state: e.target
                                  .value as Assignment["topology_state"],
                              })
                            }
                          >
                            <option value="UNASSIGNED">Unassigned</option>
                            <option value="ASSIGNED">
                              Assigned explicitly
                            </option>
                          </select>
                        </td>
                        <td>
                          <select
                            aria-label={`Full line ${sourceName(id)}`}
                            disabled={!enabled}
                            value={value.line_id}
                            onChange={(e) =>
                              edit(id, { line_id: e.target.value })
                            }
                          >
                            {lines.map((line) => (
                              <option key={line} value={line}>
                                {line}
                              </option>
                            ))}
                          </select>
                        </td>
                        <td>
                          <input
                            aria-label={`Route ${sourceName(id)}`}
                            list="explicit-route-options"
                            disabled={!enabled || !assigned}
                            value={value.route || ""}
                            placeholder="main or branch-01"
                            pattern="main|branch-[0-9]{2}"
                            required={Boolean(draft && assigned)}
                            onChange={(e) =>
                              edit(id, { route: e.target.value || null })
                            }
                            style={{ width: 130 }}
                          />
                        </td>
                        <td>
                          <input
                            type="number"
                            aria-label={`Order ${sourceName(id)}`}
                            disabled={!enabled || !assigned}
                            min="0"
                            max="100000"
                            step="1"
                            required={Boolean(draft && assigned)}
                            value={value.order ?? ""}
                            onChange={(e) =>
                              edit(id, {
                                order:
                                  e.target.value === ""
                                    ? null
                                    : Number(e.target.value),
                              })
                            }
                            style={{ width: 75 }}
                          />
                        </td>
                        <td>
                          <select
                            aria-label={`Takeoff ${sourceName(id)}`}
                            disabled={
                              !enabled || !assigned || value.route === "main"
                            }
                            value={value.takeoff_id || ""}
                            required={Boolean(
                              draft &&
                              assigned &&
                              value.route &&
                              value.route !== "main",
                            )}
                            onChange={(e) =>
                              edit(id, { takeoff_id: e.target.value || null })
                            }
                          >
                            <option value="">No selected takeoff</option>
                            {tees.map((tee) => (
                              <option key={tee.point_id} value={tee.point_id}>
                                {displayName(tee.point_id)} · existing main tee
                              </option>
                            ))}
                          </select>
                        </td>
                        <td>
                          <label>
                            <input
                              type="checkbox"
                              aria-label={`Confirm declared topology ${sourceName(id)}`}
                              disabled={!enabled || !assigned}
                              checked={draft?.topology_confirmed || false}
                              onChange={(e) =>
                                edit(id, {
                                  topology_confirmed: e.target.checked,
                                })
                              }
                            />{" "}
                            Inspected sequence / takeoff
                          </label>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            <datalist id="explicit-route-options">
              <option value="main" />
              {Array.from({ length: 99 }, (_, index) => (
                <option
                  key={index}
                  value={`branch-${String(index + 1).padStart(2, "0")}`}
                />
              ))}
            </datalist>
            <label className="form-field">
              Route review reason
              <textarea
                aria-label="Route review reason"
                required
                minLength={10}
                maxLength={3000}
                disabled={!editable}
                value={reason}
                onChange={(e) => {
                  invalidate();
                  setReason(e.target.value);
                }}
                placeholder="Source evidence for the explicit sequence and takeoffs, or reason for a numbering-only review"
              />
            </label>
            <label>
              <input
                type="checkbox"
                aria-label="Confirm topology review scope"
                checked={confirmed}
                required
                disabled={!editable}
                onChange={(e) => {
                  setConfirmed(e.target.checked);
                  setPreview(null);
                }}
              />{" "}
              I confirm these selected route decisions. An empty selection
              requests numbering of the already declared graph. Unknown geometry
              remains unresolved.
            </label>
            <div className="modal-actions">
              <button
                type="button"
                className="button secondary"
                onClick={close}
                disabled={busy}
              >
                Cancel
              </button>
              <button
                className="button primary"
                disabled={
                  !editable ||
                  !confirmed ||
                  Object.values(drafts).some(
                    (d) =>
                      d.topology_state === "ASSIGNED" && !d.topology_confirmed,
                  )
                }
              >
                {busy ? (
                  <Loader2 size={15} className="spin" />
                ) : (
                  <GitBranch size={15} />
                )}{" "}
                Preview graph and numbering
              </button>
            </div>
            <div aria-label={preview ? "Topology preview" : "Current topology"}>
              <h3>
                {preview ? "Preview — not applied" : "Current declared graph"}
              </h3>
              <p>
                {activeReport.summary.assigned} assigned ·{" "}
                {activeReport.summary.unassigned} unassigned ·{" "}
                {activeReport.summary.edges} declared edges ·{" "}
                {activeReport.summary.connected_assigned
                  ? "Assigned graph connected"
                  : "Assigned graph not connected"}{" "}
                ·{" "}
                {activeReport.summary.complete
                  ? "Graph checks complete"
                  : "Engineering facts remain unresolved"}
              </p>
              <RouteSchematic report={activeReport} name={displayName} />
              {preview && (
                <>
                  <div
                    className={`notice ${preview.report.can_apply ? "" : "amber"}`}
                  >
                    {preview.report.can_apply
                      ? "Structurally valid review. Applying records only the explicit route and numbering decisions; blue geometry issues remain."
                      : "Resolve the structural/source blockers below before applying."}
                  </div>
                  <div
                    className="results-table-scroll"
                    style={{ maxHeight: 220 }}
                  >
                    <table
                      className="results-grid"
                      aria-label="Preview numbering map"
                    >
                      <thead>
                        <tr>
                          <th>Physical source point</th>
                          <th>Previous number</th>
                          <th>Preview number</th>
                          <th>Source depictions</th>
                        </tr>
                      </thead>
                      <tbody>
                        {preview.report.numbering_map
                          .filter((m) => m.old != null || m.new != null)
                          .map((mapping) => (
                            <tr key={mapping.point_id}>
                              <td>{displayName(mapping.point_id)}</td>
                              <td>{mapping.old ?? "Unassigned"}</td>
                              <td>{mapping.new ?? "Unassigned"}</td>
                              <td>
                                {preview.report.points.find(
                                  (p) => p.point_id === mapping.point_id,
                                )?.instances.length ?? 0}
                              </td>
                            </tr>
                          ))}
                      </tbody>
                    </table>
                  </div>
                  <div className="modal-actions">
                    <button
                      type="button"
                      className="button primary"
                      disabled={!editable || !preview.report.can_apply}
                      onClick={async () => {
                        setBusy(true);
                        setError("");
                        try {
                          const updated = await api<Project>(`${path}/apply`, {
                            method: "POST",
                            body: JSON.stringify({
                              ...preview.request,
                              preview_sha256: preview.report.preview_sha256,
                            }),
                          });
                          onUpdate(updated);
                          setOpen(false);
                          setPreview(null);
                        } catch (e) {
                          setError((e as Error).message);
                        } finally {
                          setBusy(false);
                        }
                      }}
                    >
                      Apply previewed graph and numbering
                    </button>
                  </div>
                </>
              )}
              <details>
                <summary>
                  Typed graph issues ({activeReport.issues.length};{" "}
                  {activeReport.issues.filter((i) => i.blocks_apply).length}{" "}
                  block application)
                </summary>
                <div
                  className="results-table-scroll"
                  style={{ maxHeight: 260 }}
                >
                  <table
                    className="results-grid"
                    aria-label="Typed graph issues"
                  >
                    <thead>
                      <tr>
                        <th>Issue</th>
                        <th>Points</th>
                        <th>Review required</th>
                      </tr>
                    </thead>
                    <tbody>
                      {activeReport.issues.map((issue, index) => (
                        <tr key={`${issue.code}:${index}`}>
                          <td>
                            <span className="badge blue">{issue.code}</span>
                          </td>
                          <td>{issue.point_ids.map(displayName).join(", ")}</td>
                          <td>
                            {issue.blocks_apply
                              ? "Blocks application. "
                              : "Unresolved engineering fact. "}
                            {issue.message}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </details>
            </div>
            <details aria-label="Numbering review history">
              <summary>
                <History size={14} /> Numbering review history (
                {report.numbering_history?.length || 0})
              </summary>
              {!report.numbering_history?.length && (
                <p>No applied numbering history.</p>
              )}
              {report.numbering_history
                ?.slice()
                .reverse()
                .map((entry, index) => (
                  <div
                    className="notice"
                    style={{ display: "block", color: "#37577d" }}
                    key={`${entry.revision}:${index}`}
                  >
                    <b>
                      Revision {entry.revision} · {entry.action}
                    </b>
                    <p className="fine-print">
                      {entry.reviewed_at} · reviewer {entry.reviewed_by}. Stable
                      physical UUIDs and every source instance are retained. An
                      unchanged numbering rerun retains the latest meaningful
                      map.
                    </p>
                    <div className="results-table-scroll">
                      <table className="results-grid">
                        <thead>
                          <tr>
                            <th>Point</th>
                            <th>Previous</th>
                            <th>Assigned</th>
                            <th>Depictions</th>
                          </tr>
                        </thead>
                        <tbody>
                          {entry.mapping
                            .filter((m) => m.old != null || m.new != null)
                            .map((m) => (
                              <tr key={m.point_id}>
                                <td>{displayName(m.point_id)}</td>
                                <td>{m.old ?? "Unassigned"}</td>
                                <td>{m.new ?? "Unassigned"}</td>
                                <td>
                                  {entry.point_instances?.[m.point_id]
                                    ?.length ?? 0}
                                </td>
                              </tr>
                            ))}
                        </tbody>
                      </table>
                    </div>
                    {entry.alias_rows?.map((alias) => (
                      <p className="fine-print" key={alias.retired_point_id}>
                        Retired source identity {alias.retired_point_id} →{" "}
                        {displayName(alias.physical_point_id)} ·{" "}
                        {alias.old ?? "Unassigned"} →{" "}
                        {alias.new ?? "Unassigned"}
                      </p>
                    ))}
                  </div>
                ))}
            </details>
          </form>
        </Dialog>
      )}
    </div>
  );
}
