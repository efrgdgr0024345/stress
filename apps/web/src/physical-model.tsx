import { useEffect, useState } from "react";
import { GitBranch, Ruler, CheckCircle2, Loader2 } from "lucide-react";
import { api, label, pointLabel, type Project } from "./types";
import { Dialog } from "./ui";
import { SourceCoordinates } from "./source-coordinates";
import { SourceExceptions } from "./source-exceptions";

type Port = {
  point_id: string;
  proof: {
    sheet_id: string;
    evidence: string;
    dimension_convention?: string;
    dimension_convention_kind?: string;
  };
};
type Component = {
  id: string;
  kind: string;
  family: string;
  item_no: string;
  occurrence: number;
  line_id: string;
  sheet_id: string;
  ports: Record<string, Port | null>;
  evidence: string;
};
type Dimension = {
  id: string;
  kind: string;
  axis: string;
  from_point_id: string;
  to_point_id: string | null;
  source_text: string;
  source_format?: string;
  tolerance_text: string;
  sheet_id: string;
  evidence: string;
};
type Model = {
  components: Component[];
  dimensions: Dimension[];
  can_edit: boolean;
  cod_proposals: {
    component_id: string;
    point_id: string | null;
    status: string;
    coordinates_mm: Record<string, string> | null;
    leg_point_ids?: string[];
  }[];
  policies: Record<string, { ports: string[]; proof: string[] }>;
  solution: {
    issues: { code: string }[];
    elements: { delta_mm: Record<string, string | null> }[];
  };
};
export type ModelSelection = {
  type: "component" | "dimension" | "cod";
  id: string;
} | null;

export function PhysicalModelControls({
  project,
  onUpdate,
  selection,
  onClear,
}: {
  project: Project;
  onUpdate: (p: Project) => void;
  selection: ModelSelection;
  onClear: () => void;
}) {
  const [data, setData] = useState<Model | null>(null),
    [error, setError] = useState("");
  const [mode, setMode] = useState<
      "component" | "dimension" | "apply" | "cod" | null
    >(null),
    [busy, setBusy] = useState(false);
  const [componentId, setComponentId] = useState(""),
    [dimensionId, setDimensionId] = useState("");
  const [kind, setKind] = useState(""),
    [ports, setPorts] = useState<Record<string, string>>({});
  const [proofSheets, setProofSheets] = useState<Record<string, string>>({});
  const path = `/projects/${project.id}/physical-model`;
  useEffect(() => {
    let active = true;
    api<Model>(path)
      .then((value) => {
        if (active) setData(value);
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
      setMode(selection.type);
      if (selection.type === "component" || selection.type === "cod")
        setComponentId(selection.id);
      else setDimensionId(selection.id);
    }
  }, [selection]);
  const component = data?.components.find((c) => c.id === componentId);
  const dimension = data?.dimensions.find((d) => d.id === dimensionId);
  const cod = data?.cod_proposals?.find((c) => c.component_id === componentId);
  useEffect(() => {
    if (component) {
      setKind(component.kind);
      setPorts(
        Object.fromEntries(
          Object.entries(component.ports).map(([key, value]) => [
            key,
            value?.point_id || "",
          ]),
        ),
      );
      setProofSheets(
        Object.fromEntries(
          Object.entries(component.ports).map(([key, value]) => [
            key,
            value?.proof.sheet_id || "",
          ]),
        ),
      );
    }
  }, [component]);
  const close = () => {
    if (!busy) {
      setMode(null);
      setError("");
      onClear();
    }
  };
  const pointName = (id: string) => {
    const n = project.nodes.find((p) => p.id === id);
    return n
      ? `${n.line_id} · ${pointLabel(n)} · ${n.route ?? "unassigned topology"} · station ${n.station_mm ?? "unknown"} mm`
      : "";
  };
  const complete = data?.solution.elements.some((e) =>
    Object.values(e.delta_mm).every((v) => v !== null),
  );
  return (
    <div className="physical-controls">
      <SourceCoordinates project={project} onUpdate={onUpdate} />
      <SourceExceptions project={project} onUpdate={onUpdate} />
      <button
        className="button secondary"
        disabled={busy || !data?.can_edit}
        onClick={async () => {
          setBusy(true);
          setError("");
          try {
            onUpdate(
              await api<Project>(path + "/source-points", {
                method: "POST",
                body: JSON.stringify({
                  version: project.version,
                  confirmed: true,
                }),
              }),
            );
          } catch (e) {
            setError((e as Error).message);
          } finally {
            setBusy(false);
          }
        }}
      >
        <GitBranch size={15} />{" "}
        {project.source_review?.prepared
          ? "Refresh source review"
          : "Locate source interfaces"}
      </button>
      <div className="review-actions">
        <button
          className="button secondary"
          disabled={!data?.components.length}
          onClick={() => {
            setComponentId(data?.components[0]?.id || "");
            setMode("component");
          }}
        >
          <GitBranch size={16} /> Component connections
        </button>
        {data?.can_edit && (
          <>
            <button
              className="button secondary"
              disabled={!project.nodes.length}
              onClick={() => {
                setDimensionId("");
                setMode("dimension");
              }}
            >
              <Ruler size={16} /> Add source dimension
            </button>
            <button
              className="button secondary"
              disabled={
                !complete ||
                data.solution.issues.some(
                  (i) => i.code !== "DIMENSION_SOLUTION_STALE",
                )
              }
              onClick={() => setMode("apply")}
            >
              <CheckCircle2 size={16} /> Accept solved XYZ
            </button>
            <button
              className="button secondary"
              disabled={!data?.cod_proposals?.length}
              onClick={() => {
                setComponentId(data?.cod_proposals?.[0]?.component_id || "");
                setDimensionId("");
                setMode("cod");
              }}
            >
              <Ruler size={16} /> Review bend COD
            </button>
          </>
        )}
      </div>
      <p className="fine-print">
        Physical interfaces reuse the same point IDs. Source dimensions solve
        signed engineering axes; unknown axes remain blank. Relative coordinates
        show their own basis.
      </p>
      {error && !mode && (
        <p className="error-text" role="alert">
          {error}
        </p>
      )}
      {mode && data && (
        <Dialog
          wide={mode === "component"}
          title={
            mode === "component"
              ? "Component connections"
              : mode === "dimension"
                ? dimension
                  ? "Review source dimension"
                  : "Add source dimension"
                : mode === "cod"
                  ? "Review theoretical bend COD"
                  : "Accept solved engineering vectors"
          }
          subtitle={`Project revision ${project.version} · ${data.can_edit ? "Engineering evidence required" : "Read only"}`}
          onClose={close}
        >
          <form
            key={mode + componentId + dimensionId}
            onSubmit={async (event) => {
              event.preventDefault();
              const form = new FormData(event.currentTarget);
              setBusy(true);
              setError("");
              try {
                let suffix = "",
                  method = "POST",
                  body: Record<string, unknown> = {};
                const evidence = String(form.get("evidence") || "");
                if (mode === "component" && component) {
                  suffix = "/components/" + component.id;
                  method = "PATCH";
                  const mapped: Record<string, unknown> = {};
                  for (const key of data.policies[kind].ports) {
                    const node = project.nodes.find((n) => n.id === ports[key]);
                    if (!node) {
                      mapped[key] = null;
                      continue;
                    }
                    const sheetId =
                      proofSheets[key] || node.instances[0]?.sheet_id;
                    const instance = node.instances.find(
                      (v) => v.sheet_id === sheetId,
                    );
                    if (!instance)
                      throw new Error(
                        "Choose a source page showing this physical point.",
                      );
                    const [x, y] = instance.anchor;
                    mapped[key] = {
                      point_id: node.id,
                      sheet_id: sheetId,
                      bbox: [x - 8, y - 8, x + 8, y + 8],
                      evidence,
                      dimension_convention: String(
                        form.get("dimension_convention") || "",
                      ),
                    };
                  }
                  body = {
                    kind,
                    ports: mapped,
                    evidence,
                    confirmed: true,
                    cod_convention_confirmed: form.has(
                      "cod_convention_confirmed",
                    ),
                  };
                } else if (mode === "dimension") {
                  const type = String(form.get("kind"));
                  suffix =
                    "/dimensions" + (dimension ? "/" + dimension.id : "");
                  method = dimension ? "PATCH" : "POST";
                  body = {
                    kind: type,
                    axis: form.get("axis"),
                    from_point_id: form.get("from_point_id"),
                    to_point_id:
                      type === "DELTA" ? form.get("to_point_id") : null,
                    source_text: form.get("source_text"),
                    source_format: form.get("source_format"),
                    tolerance_text: form.get("tolerance_text"),
                    sheet_id: form.get("sheet_id"),
                    evidence,
                    confirmed: true,
                  };
                } else if (mode === "cod") {
                  suffix = "/components/" + componentId + "/accept-cod";
                  body = { reason: evidence, confirmed: true };
                } else {
                  suffix = "/apply-vectors";
                  body = { reason: evidence, confirmed: true };
                }
                const result = await api<Project>(path + suffix, {
                  method,
                  body: JSON.stringify({ version: project.version, ...body }),
                });
                onUpdate(result);
                setMode(null);
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
            {mode === "component" && (
              <>
                <label className="form-field">
                  Source occurrence
                  <select
                    aria-label="Source occurrence"
                    value={componentId}
                    onChange={(e) => setComponentId(e.target.value)}
                  >
                    {data.components.map((c) => (
                      <option key={c.id} value={c.id}>
                        {c.line_id} · Item {c.item_no} / occurrence{" "}
                        {c.occurrence} · {label(c.kind)}
                      </option>
                    ))}
                  </select>
                </label>
                {component && (
                  <>
                    <label className="form-field">
                      Physical connection type
                      <select
                        aria-label="Physical connection type"
                        value={kind}
                        disabled={
                          !data.can_edit || component.family !== "instrument"
                        }
                        onChange={(e) => {
                          setKind(e.target.value);
                          setPorts({});
                          setProofSheets({});
                        }}
                      >
                        {(component.family === "instrument"
                          ? [
                              "instrument_unclassified",
                              "single_instrument",
                              "inline_instrument",
                            ]
                          : [component.kind]
                        ).map((value) => (
                          <option key={value} value={value}>
                            {label(value)}
                          </option>
                        ))}
                      </select>
                    </label>
                    <div className="notice">
                      <GitBranch size={18} />
                      <span>
                        Choose the existing node at each source feature. A valve
                        and adjacent flange share their interface node. Opposite
                        flange ends use separate nodes at the face and pipe
                        black dot.
                      </span>
                    </div>
                    {(data.policies[kind]?.ports || []).map((key) => {
                      const node = project.nodes.find(
                        (n) => n.id === ports[key],
                      );
                      return (
                        <div className="physical-port-field" key={key}>
                          <label className="form-field">
                            {label(key)}
                            <select
                              aria-label={label(key)}
                              disabled={!data.can_edit}
                              value={ports[key] || ""}
                              onChange={(e) => {
                                setPorts({ ...ports, [key]: e.target.value });
                                setProofSheets({ ...proofSheets, [key]: "" });
                              }}
                            >
                              <option value="">
                                Unlocated — retain an explicit exception
                              </option>
                              {project.nodes
                                .filter((n) => n.line_id === component.line_id)
                                .map((n) => (
                                  <option key={n.id} value={n.id}>
                                    {pointName(n.id)}
                                  </option>
                                ))}
                            </select>
                          </label>
                          {node && (
                            <label className="form-field">
                              Source page for {label(key)}
                              <select
                                aria-label={`Source page for ${label(key)}`}
                                disabled={!data.can_edit}
                                value={
                                  proofSheets[key] ||
                                  node.instances[0]?.sheet_id
                                }
                                onChange={(e) =>
                                  setProofSheets({
                                    ...proofSheets,
                                    [key]: e.target.value,
                                  })
                                }
                              >
                                {node.instances.map((v) => {
                                  const s = project.sheets.find(
                                    (p) => p.id === v.sheet_id,
                                  );
                                  return (
                                    <option key={v.sheet_id} value={v.sheet_id}>
                                      {s?.printed_id || s?.filename} · page{" "}
                                      {(s?.page_index || 0) + 1}
                                    </option>
                                  );
                                })}
                              </select>
                            </label>
                          )}
                        </div>
                      );
                    })}
                    {kind === "elbow" && (
                      <>
                        <label className="form-field">
                          Engineering dimension convention proving theoretical
                          COD
                          <textarea
                            name="dimension_convention"
                            required
                            minLength={10}
                            maxLength={1000}
                            disabled={!data.can_edit}
                            defaultValue={
                              component.ports.theoretical_cod?.proof
                                .dimension_convention || ""
                            }
                          />
                        </label>
                        <label className="check-row">
                          <input
                            type="checkbox"
                            name="cod_convention_confirmed"
                            aria-label="Source convention proves theoretical centreline intersection"
                            defaultChecked={
                              component.ports.theoretical_cod?.proof
                                .dimension_convention_kind ===
                              "THEORETICAL_CENTRELINE_INTERSECTION"
                            }
                            disabled={!data.can_edit}
                          />{" "}
                          The source convention proves COD at the intersection
                          of its two adjacent straight centreline legs.
                        </label>
                      </>
                    )}
                  </>
                )}
              </>
            )}
            {mode === "dimension" && (
              <>
                <label className="form-field">
                  Printed source number convention
                  <select
                    name="source_format"
                    aria-label="Printed source number convention"
                    defaultValue={dimension?.source_format || "STANDARD"}
                  >
                    <option value="STANDARD">
                      Standard explicit mm / inch / feet and fractions
                    </option>
                    <option value="ISO_IN_DOT_FRACTION">
                      ISO inches dot fraction (2.1/8&quot;)
                    </option>
                    <option value="ISO_FT_IN_DOT_FRACTION">
                      Printed ISO feet/inch fraction (for example 3'10.3/8")
                    </option>
                  </select>
                </label>
                <div className="form-grid">
                  <label className="form-field">
                    Constraint type
                    <select
                      name="kind"
                      aria-label="Constraint type"
                      defaultValue={dimension?.kind || "DELTA"}
                    >
                      <option value="DELTA">
                        Signed difference between two points
                      </option>
                      <option value="COORDINATE">
                        Engineering coordinate at one point
                      </option>
                    </select>
                  </label>
                  <label className="form-field">
                    Engineering axis
                    <select
                      name="axis"
                      aria-label="Engineering axis"
                      defaultValue={dimension?.axis || "X"}
                    >
                      <option value="X">X / East</option>
                      <option value="Y">Y / North</option>
                      <option value="Z">Z / Elevation</option>
                    </select>
                  </label>
                </div>
                <label className="form-field">
                  From point / coordinate point
                  <select
                    name="from_point_id"
                    aria-label="From point / coordinate point"
                    defaultValue={
                      dimension?.from_point_id || project.nodes[0]?.id
                    }
                  >
                    {project.nodes.map((n) => (
                      <option key={n.id} value={n.id}>
                        {pointName(n.id)}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="form-field">
                  To point for signed difference
                  <select
                    name="to_point_id"
                    aria-label="To point for signed difference"
                    defaultValue={
                      dimension?.to_point_id ||
                      project.nodes[1]?.id ||
                      project.nodes[0]?.id
                    }
                  >
                    {project.nodes.map((n) => (
                      <option key={n.id} value={n.id}>
                        {pointName(n.id)}
                      </option>
                    ))}
                  </select>
                  <small>
                    Ignored for a single-point engineering coordinate.
                  </small>
                </label>
                <div className="form-grid">
                  <label className="form-field">
                    Original signed source dimension
                    <input
                      name="source_text"
                      required
                      maxLength={100}
                      defaultValue={dimension?.source_text || ""}
                      placeholder={"e.g. -2 1/8 in, S 500 mm or EL 3' 2\""}
                    />
                  </label>
                  <label className="form-field">
                    Declared tolerance
                    <input
                      name="tolerance_text"
                      required
                      maxLength={100}
                      defaultValue={dimension?.tolerance_text || "0 mm"}
                    />
                  </label>
                </div>
                <label className="form-field">
                  Source drawing page
                  <select
                    name="sheet_id"
                    aria-label="Source drawing page"
                    defaultValue={dimension?.sheet_id || project.sheets[0]?.id}
                  >
                    {project.sheets.map((s) => (
                      <option key={s.id} value={s.id}>
                        {s.printed_id || s.filename} · page {s.page_index + 1}
                      </option>
                    ))}
                  </select>
                </label>
              </>
            )}
            {mode === "apply" && (
              <p>
                Accept complete signed XYZ vectors from the reviewed
                constraints. Existing pipe properties and accepted physical
                stations remain recorded. Conflicting or incomplete axes cannot
                be accepted as exact geometry.
              </p>
            )}
            {mode === "cod" && (
              <>
                <label className="form-field">
                  Elbow occurrence
                  <select
                    aria-label="Elbow occurrence"
                    value={componentId}
                    onChange={(e) => setComponentId(e.target.value)}
                  >
                    {data.cod_proposals.map((c) => (
                      <option key={c.component_id} value={c.component_id}>
                        Item{" "}
                        {
                          data.components.find((v) => v.id === c.component_id)
                            ?.item_no
                        }{" "}
                        · {c.status.replaceAll("_", " ")}
                      </option>
                    ))}
                  </select>
                </label>
                <p>
                  <strong>{cod?.status.replaceAll("_", " ")}</strong>
                </p>
                <p className="fine-print">
                  COD uses only fully constrained engineering XYZ points on the
                  two straight legs and the confirmed source convention. Unknown
                  leg coordinates, parallel/skew lines or incompatible source
                  facts remain unresolved. Stations and bend radius are not
                  inferred.
                </p>
                {cod?.coordinates_mm && (
                  <p>
                    {Object.entries(cod.coordinates_mm)
                      .map(([axis, value]) => `${axis}: ${value} mm`)
                      .join(" · ")}
                  </p>
                )}
                {!!cod?.leg_point_ids?.length && (
                  <p className="fine-print">
                    Source leg points:{" "}
                    {cod.leg_point_ids.map(pointName).join(" → ")}
                  </p>
                )}
              </>
            )}
            {data.can_edit && (
              <>
                <label className="form-field">
                  Engineering source and decision
                  <textarea
                    name="evidence"
                    required
                    minLength={10}
                    maxLength={3000}
                    rows={3}
                    defaultValue={
                      mode === "cod"
                        ? ""
                        : mode === "component"
                          ? component?.evidence || ""
                          : dimension?.evidence || ""
                    }
                  />
                </label>
                <label className="check-row">
                  <input
                    type="checkbox"
                    aria-label="Confirm engineering source evidence"
                    required
                  />
                  I inspected the source engineering evidence. Graphic pixel
                  distances are not physical dimensions.
                </label>
                <div className="modal-footer">
                  <button
                    type="button"
                    className="button secondary"
                    disabled={busy}
                    onClick={close}
                  >
                    Cancel
                  </button>
                  <button
                    className="button primary"
                    disabled={
                      busy || (mode === "cod" && cod?.status !== "COD_PROPOSED")
                    }
                  >
                    {busy && <Loader2 size={16} className="spin" />}
                    {mode === "component"
                      ? "Save source connections"
                      : mode === "dimension"
                        ? "Save source dimension"
                        : mode === "cod"
                          ? "Accept proved COD coordinates"
                          : "Accept engineering vectors"}
                  </button>
                </div>
              </>
            )}
          </form>
        </Dialog>
      )}
    </div>
  );
}
