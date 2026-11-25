import { useEffect, useState } from "react";
import {
  Download,
  FileSpreadsheet,
  Search,
  CheckCircle2,
  AlertCircle,
} from "lucide-react";
import { api, type Project } from "./types";
import { appPath } from "./paths";
import { PhysicalModelControls, type ModelSelection } from "./physical-model";
import { ContinuationControls } from "./continuations";
import { StationControls } from "./stations";
import { TopologyReviewControls } from "./topology-review";
import { Dialog } from "./ui";
import "./results.css";

type Cell = string | number | null;
type Table = {
  name: string;
  columns: { key: string; label: string; kind: string }[];
  rows: Record<string, Cell>[];
};
type Results = {
  revision: number;
  format: string;
  tables: Table[];
  caesar: {
    status: string;
    direct_import_ready: boolean;
    gates: { gate: string; passed: boolean; detail: string }[];
  };
  native: {
    available: boolean;
    profile: string;
    target: string;
    missing: string[];
    qualified_application_roundtrip: boolean;
  };
};
const elementFields = [
  ["dx_mm", "dx", "DX (mm)"],
  ["dy_mm", "dy", "DY (mm)"],
  ["dz_mm", "dz", "DZ (mm)"],
  ["od_mm", "od", "Outside diameter (mm)"],
  ["wall_mm", "wall", "Wall thickness (mm)"],
  ["corrosion_mm", "corrosion", "Corrosion allowance (mm)"],
  ["material_code", "material", "CAESAR material code"],
  ["temperature_c", "temperature", "Temperature (°C)"],
  ["pressure_mpa", "pressure", "Pressure (MPa)"],
];
const advancedFields = [
  ["elastic_modulus_mpa", "Cold elastic modulus (MPa)"],
  ["hot_modulus_mpa", "Hot elastic modulus (MPa)"],
  ["poisson_ratio", "Poisson ratio"],
  ["pipe_density_kg_m3", "Pipe density (kg/m³)"],
  ["fluid_density_kg_m3", "Fluid density (kg/m³)"],
  ["insulation_thickness_mm", "Insulation thickness (mm)"],
  ["insulation_density_kg_m3", "Insulation density (kg/m³)"],
  ["cold_allowable_mpa", "Cold allowable stress (MPa)"],
  ["hot_allowable_mpa", "Hot allowable stress (MPa)"],
].map(([key, label]) => [key, key, label]);

export function EngineeringResults({
  project,
  onUpdate,
  onReview,
}: {
  project: Project;
  onUpdate: (p: Project) => void;
  onReview: (id: string, kind: "node" | "material") => void;
}) {
  const [data, setData] = useState<Results | null>(null),
    [selected, setSelected] = useState(
      project.nodes.length
        ? "Nodes"
        : project.materials.length
          ? "Components"
          : "Nodes",
    ),
    [query, setQuery] = useState(""),
    [error, setError] = useState(""),
    [editing, setEditing] = useState<Record<string, Cell> | null>(null),
    [busy, setBusy] = useState(false),
    [settingsOpen, setSettingsOpen] = useState(false);
  const [modelSelection, setModelSelection] = useState<ModelSelection>(null);
  const [continuationSelection, setContinuationSelection] = useState<
    string | null
  >(null);
  const [continuationSourceSelection, setContinuationSourceSelection] =
    useState<string | null>(null);
  const firstMain = project.nodes
    .filter((n) => n.route === "main")
    .sort((a, b) => (a.order ?? 0) - (b.order ?? 0))[0];
  useEffect(() => {
    let alive = true;
    api<Results>(`/projects/${project.id}/results`)
      .then((value) => {
        if (alive) {
          setData(value);
          setError("");
        }
      })
      .catch((e) => alive && setError(e.message));
    return () => {
      alive = false;
    };
  }, [project.id, project.version]);
  const table = data?.tables.find((t) => t.name === selected),
    rows = (table?.rows || []).filter(
      (r) =>
        !query ||
        Object.values(r).some((v) =>
          String(v ?? "")
            .toLowerCase()
            .includes(query.toLowerCase()),
        ),
    );
  const rowAction = (row: Record<string, Cell>) => {
    if (selected === "Continuations" && row.continuation_id) {
      setContinuationSourceSelection(null);
      setContinuationSelection(String(row.continuation_id));
    }
    if (
      selected === "Continuation sources" &&
      (row.source_candidate_id || row.id)
    ) {
      setContinuationSelection(null);
      setContinuationSourceSelection(String(row.source_candidate_id || row.id));
    }
    if (selected === "Component ports" && row.component_id)
      setModelSelection({ type: "component", id: String(row.component_id) });
    if (selected === "Bend COD" && row.component_id)
      setModelSelection({ type: "cod", id: String(row.component_id) });
    if (selected === "Dimensions" && row.id)
      setModelSelection({ type: "dimension", id: String(row.id) });
    if (selected === "CAESAR input") setEditing(row);
    if (selected === "Nodes" && row.id) onReview(String(row.id), "node");
    if (selected === "Components" && row.id)
      onReview(String(row.id), "material");
  };
  return (
    <div className="page-content results-page">
      <div className="page-heading">
        <div>
          <div className="eyebrow">ENGINEERING OUTPUT</div>
          <h1>
            Results workbook<span className="heading-dot">.</span>
          </h1>
          <p>
            A formatted working spreadsheet, backed by the project revision and
            source evidence.
          </p>
        </div>
        <div className="heading-actions results-downloads">
          <a
            className="button primary excel-download"
            href={appPath(`api/v1/projects/${project.id}/results/workbook`)}
          >
            <Download size={16} />
            Export Excel (.xlsx)
          </a>
          <a
            className="button secondary"
            href={appPath(`api/v1/projects/${project.id}/results/csv`)}
          >
            CSV tables (.zip)
          </a>
          {data?.native.available ? (
            <a
              className="button secondary"
              href={appPath(
                `api/v1/projects/${project.id}/results/caesar-neutral`,
              )}
            >
              CAESAR neutral (.cii)
            </a>
          ) : (
            <button
              className="button secondary"
              disabled
              title="Complete the native export requirements below"
            >
              CAESAR neutral (.cii)
            </button>
          )}
        </div>
      </div>
      {error && (
        <div className="notice amber" role="alert">
          {error}
        </div>
      )}
      <div className="results-ribbon">
        <div className="results-excel-icon">
          <FileSpreadsheet size={24} />
        </div>
        <div>
          <b>{project.title}</b>
          <small>
            Revision {data?.revision ?? project.version} · mm / N / MPa / °C ·
            editable Excel tables
          </small>
        </div>
        <span className="badge amber">Engineering review</span>
      </div>
      <div className="results-workbook">
        <PhysicalModelControls
          project={project}
          onUpdate={onUpdate}
          selection={modelSelection}
          onClear={() => setModelSelection(null)}
        />
        <ContinuationControls
          project={project}
          onUpdate={onUpdate}
          selection={continuationSelection}
          sourceSelection={continuationSourceSelection}
          onClear={() => {
            setContinuationSelection(null);
            setContinuationSourceSelection(null);
          }}
        />
        <StationControls project={project} onUpdate={onUpdate} />
        <TopologyReviewControls
          project={project}
          onUpdate={onUpdate}
          onInspect={(id) => onReview(id, "node")}
        />
        <div className="results-formula-bar">
          <span>fx</span>
          <span>
            {selected === "CAESAR input"
              ? "Select an element row to enter its verified geometry and properties."
              : selected === "Nodes"
                ? "Select a point to inspect or edit its drawing evidence."
                : selected === "Continuation sources"
                  ? "Select a printed source reference to review its boundary or matching exception."
                  : "Unknown values stay N/A here and blank in numeric Excel cells."}
          </span>
          <label>
            <Search size={14} />
            <input
              aria-label="Search workbook"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Find in sheet"
            />
          </label>
        </div>
        <div className="results-table-scroll">
          <table className="results-grid">
            <thead>
              <tr>
                <th className="results-row-index">#</th>
                {table?.columns.map((c) => (
                  <th key={c.key}>{c.label}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.slice(0, 1000).map((row, i) => (
                <tr
                  key={String(row.id ?? i)}
                  onClick={() => rowAction(row)}
                  tabIndex={
                    [
                      "Nodes",
                      "Components",
                      "CAESAR input",
                      "Component ports",
                      "Dimensions",
                      "Continuations",
                      "Continuation sources",
                      "Bend COD",
                    ].includes(selected)
                      ? 0
                      : undefined
                  }
                  onKeyDown={(e) => e.key === "Enter" && rowAction(row)}
                >
                  <th className="results-row-index">{i + 1}</th>
                  {table?.columns.map((c) => (
                    <td
                      key={c.key}
                      className={`${c.kind !== "text" ? "numeric" : ""} ${row[c.key] === null || row[c.key] === undefined ? "unknown" : ""}`}
                      title={String(row[c.key] ?? "Unknown")}
                    >
                      {row[c.key] === null || row[c.key] === undefined ? (
                        <span>N/A</span>
                      ) : (
                        String(row[c.key])
                      )}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
          {!rows.length && (
            <div className="results-empty">
              {data
                ? "No rows in this sheet yet. Process a drawing or add reviewed engineering data."
                : "Preparing workbook display…"}
            </div>
          )}
        </div>
        <div
          className="results-sheet-tabs"
          role="tablist"
          aria-label="Workbook sheets"
        >
          {data?.tables.map((t) => (
            <button
              key={t.name}
              role="tab"
              aria-selected={selected === t.name}
              className={selected === t.name ? "selected" : ""}
              onClick={() => {
                setSelected(t.name);
                setQuery("");
              }}
            >
              <FileSpreadsheet size={14} />
              {t.name}
            </button>
          ))}
        </div>
        <div className="results-status">
          <span>
            {Math.min(rows.length, 1000)} of {rows.length} matching rows · full
            data included in Excel export
          </span>
          <span>Exact decimal text retained in the workbook</span>
        </div>
      </div>
      <details className="results-readiness" open={selected === "CAESAR input"}>
        <summary>
          <AlertCircle size={17} />
          CAESAR import readiness: engineering review required
        </summary>
        <p>
          Excel and CSV contain the engineering schedules. The native export
          targets CAESAR II 15.1 straight pipe and becomes available when its
          required inputs are complete. An import in CAESAR and engineering
          review are still required before modelling use.
        </p>
        <div>
          {data?.caesar.gates.map((g) => (
            <div
              key={g.gate}
              className={`results-gate ${g.passed ? "passed" : ""}`}
            >
              {g.passed ? (
                <CheckCircle2 size={16} />
              ) : (
                <AlertCircle size={16} />
              )}
              <span>
                <b>{g.gate}</b>
                <small>{g.detail}</small>
              </span>
            </div>
          ))}
        </div>
      </details>
      <div className="results-readiness">
        <div
          className="inline-actions"
          style={{ justifyContent: "space-between" }}
        >
          <h3 style={{ fontSize: 13 }}>Native CAESAR output</h3>
          <button
            className="button secondary compact"
            onClick={() => setSettingsOpen(true)}
          >
            CAESAR export settings
          </button>
        </div>
        <p>
          Target: {data?.native.target || "CAESAR II 15.1"} · straight-pipe
          import candidate. Component-specific auxiliaries need their own
          verified profile. Actual CAESAR import and engineering review remain
          required.
        </p>
        {!data?.native.available && (
          <ul className="fine-print">
            {data?.native.missing.slice(0, 8).map((message, i) => (
              <li key={i}>{message.replaceAll("_", " ")}</li>
            ))}
          </ul>
        )}
      </div>
      {editing && (
        <Dialog
          title={`Element ${editing.from} → ${editing.to}`}
          subtitle="Enter source-backed engineering values. Geometry never comes from drawing pixels."
          onClose={() => setEditing(null)}
          wide
        >
          <form
            onSubmit={async (e) => {
              e.preventDefault();
              setBusy(true);
              try {
                const fields = new FormData(e.currentTarget);
                const payload: Record<string, unknown> = {
                  version: project.version,
                  evidence: String(fields.get("evidence") || ""),
                };
                for (const [key] of [...elementFields, ...advancedFields])
                  payload[key] = fields.get(key) || null;
                const p = await api<Project>(
                  `/projects/${project.id}/results/elements/${editing.id}`,
                  { method: "PATCH", body: JSON.stringify(payload) },
                );
                onUpdate(p);
                setEditing(null);
                setError("");
              } catch (e) {
                setError((e as Error).message);
              } finally {
                setBusy(false);
              }
            }}
          >
            <div className="results-property-grid">
              {elementFields.map(([key, alias, label]) => (
                <label className="form-field" key={key}>
                  {label}
                  <input
                    name={key}
                    defaultValue={String(editing[alias] ?? "")}
                    inputMode={key === "material_code" ? "text" : "decimal"}
                    maxLength={100}
                    placeholder="Unknown"
                  />
                </label>
              ))}
            </div>
            <details className="results-advanced">
              <summary>Advanced CAESAR material / analysis properties</summary>
              <div className="results-property-grid">
                {advancedFields.map(([key, alias, label]) => (
                  <label className="form-field" key={key}>
                    {label}
                    <input
                      name={key}
                      defaultValue={String(editing[alias] ?? "")}
                      inputMode="decimal"
                      maxLength={100}
                      placeholder="Unknown"
                    />
                  </label>
                ))}
              </div>
              <p className="fine-print">
                Zero fluid density declares a dry pipe; zero insulation
                thickness declares an uninsulated pipe. Leave unknown values
                blank.
              </p>
            </details>
            <label className="form-field">
              Engineering source / evidence
              <textarea
                name="evidence"
                defaultValue={String(editing.evidence ?? "")}
                required
                minLength={10}
                maxLength={3000}
              />
            </label>
            <p className="fine-print">
              Blank fields remain unknown. CAESAR material codes must match your
              selected version's material database.
            </p>
            {error && (
              <p className="error-text" role="alert">
                {error}
              </p>
            )}
            <button className="button primary" disabled={busy}>
              Save element
            </button>
          </form>
        </Dialog>
      )}
      {settingsOpen && (
        <Dialog
          title="CAESAR neutral export settings"
          subtitle="Explicit model/code choices for the documented 15.1 interchange profile."
          onClose={() => setSettingsOpen(false)}
        >
          <form
            onSubmit={async (e) => {
              e.preventDefault();
              if (!firstMain) return;
              setBusy(true);
              try {
                const fields = new FormData(e.currentTarget);
                const p = await api<Project>(
                  `/projects/${project.id}/results/settings`,
                  {
                    method: "PATCH",
                    body: JSON.stringify({
                      version: project.version,
                      piping_code_id: Number(fields.get("code")),
                      ambient_temperature_c: String(fields.get("ambient")),
                      vertical_axis: fields.get("axis"),
                      local_origin_confirmed: fields.get("origin") === "on",
                      origin_point_id: firstMain.id,
                    }),
                  },
                );
                onUpdate(p);
                setSettingsOpen(false);
              } catch (e) {
                setError((e as Error).message);
              } finally {
                setBusy(false);
              }
            }}
          >
            <label className="form-field">
              CAESAR piping code ID
              <input
                name="code"
                type="number"
                min={1}
                max={999}
                required
                defaultValue={project.analysis_model?.piping_code_id ?? ""}
              />
              <small>
                Use the numeric ID from the selected CAESAR version; no code is
                guessed.
              </small>
            </label>
            <label className="form-field">
              Ambient temperature (°C)
              <input
                name="ambient"
                inputMode="decimal"
                required
                defaultValue={
                  project.analysis_model?.ambient_temperature_c ?? ""
                }
              />
            </label>
            <label className="form-field">
              Vertical model axis
              <select
                name="axis"
                defaultValue={project.analysis_model?.vertical_axis || "Z"}
              >
                <option value="Z">Z — elevation</option>
                <option value="Y">Y — vertical</option>
              </select>
            </label>
            <label className="fine-print">
              <input
                type="checkbox"
                name="origin"
                required
                defaultChecked={
                  project.analysis_model?.local_origin_confirmed &&
                  project.analysis_model?.origin_point_id === firstMain?.id
                }
              />{" "}
              Declare node {firstMain?.number ?? "—"} as local origin (0, 0, 0).
              This is a model frame, not a claim of surveyed site coordinates.
            </label>
            {!firstMain && (
              <p className="error-text">
                Create/review a main route before choosing its origin.
              </p>
            )}
            {error && (
              <p className="error-text" role="alert">
                {error}
              </p>
            )}
            <div className="modal-footer">
              <button className="button primary" disabled={busy || !firstMain}>
                Save export settings
              </button>
            </div>
          </form>
        </Dialog>
      )}
    </div>
  );
}
