import { useEffect, useState } from "react";
import {
  Check,
  Database,
  FileText,
  GitBranch,
  Loader2,
  Search,
  ShieldCheck,
  Upload,
} from "lucide-react";
import { api, label, type Material, type Project } from "./types";
import { Dialog } from "./ui";

type RecordRow = Record<string, string | null | unknown>;
export interface Dataset {
  id: string;
  catalog_id: string;
  seq: number;
  created: string;
  data: {
    status: string;
    source_filename: string;
    source_sha256: string;
    records: RecordRow[];
    errors: { row: number; message: string }[];
    approval?: { actor: string; reason: string };
    mapping: { sheet: string };
    units: { weight_input: string; length_input: string };
  };
}
interface Catalog {
  id: string;
  filename: string;
  sha256: string;
  created: string;
  data: { sheets: { name: string; rows: number; columns: number }[] };
}
interface Preview {
  sheet: string;
  header_row: number;
  headers: { index: number; label: string }[];
  rows: (string | null)[][];
  total_rows: number;
}
type Schema = {
  fields: string[];
  required: string[];
  match_fields: string[];
  quality: string[];
};
type Notify = (message: string, error?: boolean) => void;
type Mutation = (
  path: string,
  body: unknown,
  method?: string,
) => Promise<Project | undefined>;
const numeric = [
  "weight_n",
  "half_weight_n",
  "full_weight_n",
  "studs_weight_n",
  "nut_weight_n",
  "length_mm",
  "stud_length_mm",
  "stud_count",
];
const caption = (key: string) =>
  ({
    nps: "Pipe NPS",
    api_bore: "True API bore",
    component_type: "Component / flange type",
    weight_n: "Bare / reported weight (N)",
    studs_weight_n: "All studs, total weight (N)",
    nut_weight_n: "One nut weight (N)",
    source: "Source / datasheet reference",
    quality: "Source quality",
    rating: "Class / pressure rating",
  })[key] || label(key);

export function CatalogManager({
  busy,
  setBusy,
  notify,
}: {
  busy: boolean;
  setBusy: (v: boolean) => void;
  notify: Notify;
}) {
  const [catalogs, setCatalogs] = useState<Catalog[]>([]),
    [editing, setEditing] = useState<Catalog | null>(null),
    [schema, setSchema] = useState<Schema | null>(null),
    [versions, setVersions] = useState<Record<string, Dataset[]>>({});
  const load = async () => {
    const data = await api<Catalog[]>("/catalogs");
    setCatalogs(data);
    const pairs = await Promise.all(
      data.map(
        async (c) =>
          [c.id, await api<Dataset[]>(`/catalogs/${c.id}/versions`)] as const,
      ),
    );
    setVersions(Object.fromEntries(pairs));
  };
  useEffect(() => {
    load().catch((e) => notify(e.message, true));
    api<Schema>("/catalog-schema")
      .then(setSchema)
      .catch((e) => notify(e.message, true));
  }, []);
  const upload = async (file: File) => {
    setBusy(true);
    try {
      const form = new FormData();
      form.append("file", file);
      const value = await api<Catalog>("/catalogs/import", {
        method: "POST",
        body: form,
      });
      await load();
      setEditing(value);
      notify(
        "Workbook registered. Map its source columns, then review the normalized dataset.",
      );
    } catch (e) {
      notify((e as Error).message, true);
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="page-content">
      <div className="page-heading">
        <div>
          <div className="eyebrow">CONTROLLED ENGINEERING REFERENCES</div>
          <h1>
            Component catalogs<span className="heading-dot">.</span>
          </h1>
          <p>
            Map the source. Approve the dataset. Match exact specifications.
          </p>
        </div>
        <label className="button primary">
          <Upload size={16} />
          Register workbook
          <input
            type="file"
            hidden
            accept=".xlsx"
            disabled={busy}
            onChange={(e) => {
              if (e.target.files?.[0]) upload(e.target.files[0]);
              e.target.value = "";
            }}
          />
        </label>
      </div>
      <div className="notice">
        <ShieldCheck size={20} />
        <span>
          Numeric data comes only from approved workbook mappings. Exact matches
          are copied into immutable project snapshots; later catalog versions do
          not overwrite past decisions. Reference or estimated values retain
          their quality labels.
        </span>
      </div>
      {!catalogs.length ? (
        <div className="empty">
          <Database size={30} />
          <h3>Start with an authoritative workbook.</h3>
          <p>
            Register a flange or valve XLSX. No sample weights are substituted
            for missing source data.
          </p>
        </div>
      ) : (
        <div className="catalog-grid">
          {catalogs.map((c) => (
            <div className="panel" key={c.id}>
              <div className="panel-title">
                <Database size={20} />
                <h3>{c.filename}</h3>
              </div>
              <p className="mono muted" title={c.sha256}>
                SHA-256 {c.sha256.slice(0, 24)}…
              </p>
              {c.data.sheets.map((s) => (
                <div className="catalog-sheet" key={s.name}>
                  <FileText size={15} />
                  <b>{s.name}</b>
                  <span>{s.rows || "?"} rows</span>
                </div>
              ))}
              <button
                className="button secondary compact full"
                onClick={() => setEditing(c)}
              >
                <GitBranch size={14} />
                Map a new dataset version
              </button>
              {versions[c.id]?.map((v) => (
                <DatasetCard
                  key={v.id}
                  dataset={v}
                  notify={notify}
                  onChange={load}
                />
              ))}
            </div>
          ))}
        </div>
      )}
      {editing && schema && (
        <MappingDialog
          catalog={editing}
          schema={schema}
          onClose={() => setEditing(null)}
          onSaved={async () => {
            await load();
            setEditing(null);
          }}
          notify={notify}
        />
      )}
    </div>
  );
}
function DatasetCard({
  dataset: v,
  notify,
  onChange,
}: {
  dataset: Dataset;
  notify: Notify;
  onChange: () => Promise<void>;
}) {
  const [reason, setReason] = useState(""),
    [busy, setBusy] = useState(false),
    [show, setShow] = useState(false);
  const approve = async () => {
    setBusy(true);
    try {
      await api(`/catalog-versions/${v.id}/approve`, {
        method: "POST",
        body: JSON.stringify({ reason }),
      });
      await onChange();
      notify(
        "Dataset approved. Records are immutable and available for exact matching.",
      );
    } catch (e) {
      notify((e as Error).message, true);
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="catalog-version">
      <div className="inline-actions">
        <h4>
          Version {v.seq} · {v.data.mapping.sheet}
        </h4>
        <span
          className={`badge ${v.data.status === "APPROVED" ? "green" : "amber"}`}
        >
          {label(v.data.status)}
        </span>
      </div>
      <p className="muted">
        {v.data.records.length} records · {v.data.errors.length} errors · input{" "}
        {v.data.units.weight_input} / {v.data.units.length_input}
      </p>
      <button className="text-button" onClick={() => setShow(!show)}>
        <Search size={13} />
        {show ? "Hide" : "Inspect"} normalized records
      </button>
      {show && (
        <div className="catalog-preview">
          <table>
            <thead>
              <tr>
                {[
                  "Row",
                  "Family",
                  "Standard",
                  "Rating",
                  "NPS",
                  "Type",
                  "Weight N",
                  "Length mm",
                  "Quality",
                ].map((s) => (
                  <th key={s}>{s}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {v.data.records.slice(0, 100).map((r, i) => (
                <tr key={i}>
                  {[
                    "source_row",
                    "family",
                    "standard",
                    "rating",
                    "nps",
                    "component_type",
                    "weight_n",
                    "length_mm",
                    "quality",
                  ].map((k) => (
                    <td key={k}>{String(r[k] ?? "N/A")}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {v.data.errors.slice(0, 8).map((e, i) => (
        <p className="error-text" key={i}>
          Row {e.row}: {e.message}
        </p>
      ))}
      {v.data.status === "PENDING_APPROVAL" && (
        <>
          <label className="form-field">
            Dataset review evidence
            <input
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="Reviewed source, units, field mapping and quality…"
              minLength={10}
            />
          </label>
          <button
            className="button primary compact full"
            disabled={busy || reason.trim().length < 10}
            onClick={approve}
          >
            {busy ? (
              <Loader2 size={14} className="spin" />
            ) : (
              <Check size={14} />
            )}
            Approve dataset for matching
          </button>
        </>
      )}
      {v.data.approval && (
        <p className="fine-print">
          Approved by {v.data.approval.actor} · {v.data.approval.reason}
        </p>
      )}
    </div>
  );
}
function MappingDialog({
  catalog,
  schema,
  onClose,
  onSaved,
  notify,
}: {
  catalog: Catalog;
  schema: Schema;
  onClose: () => void;
  onSaved: () => Promise<void>;
  notify: Notify;
}) {
  const [sheet, setSheet] = useState(catalog.data.sheets[0]?.name || ""),
    [header, setHeader] = useState(1),
    [preview, setPreview] = useState<Preview | null>(null),
    [columns, setColumns] = useState<Record<string, number>>({}),
    [constants, setConstants] = useState<Record<string, string>>({
      family: "flange",
      quality: "REFERENCE_ONLY",
    }),
    [last, setLast] = useState<number | "">(""),
    [first, setFirst] = useState(2),
    [weightUnit, setWeightUnit] = useState("N"),
    [lengthUnit, setLengthUnit] = useState("mm"),
    [busy, setBusy] = useState(false);
  const inspect = async () => {
    setBusy(true);
    try {
      const p = await api<Preview>(
        `/catalogs/${catalog.id}/preview?sheet=${encodeURIComponent(sheet)}&header_row=${header}`,
      );
      setPreview(p);
      setLast(Math.min(p.total_rows || header + 1, header + 5000));
      setFirst(header + 1);
      const auto: Record<string, number> = {};
      for (const h of p.headers) {
        const exact = h.label.trim().toLowerCase().replaceAll(" ", "_");
        if (schema.fields.includes(exact)) auto[exact] = h.index;
      }
      setColumns(auto);
      setConstants((old) =>
        Object.fromEntries(
          Object.entries(old).filter(([k]) => auto[k] === undefined),
        ),
      );
    } catch (e) {
      notify((e as Error).message, true);
    } finally {
      setBusy(false);
    }
  };
  useEffect(() => {
    inspect();
  }, []);
  const save = async () => {
    setBusy(true);
    try {
      const result = await api<Dataset>(`/catalogs/${catalog.id}/versions`, {
        method: "POST",
        body: JSON.stringify({
          sheet,
          header_row: header,
          first_data_row: first,
          last_data_row: last || undefined,
          columns,
          constants,
          weight_unit: weightUnit,
          length_unit: lengthUnit,
        }),
      });
      await onSaved();
      notify(
        `${result.data.records.length} normalized records, ${result.data.errors.length} errors. ${result.data.errors.length ? "Resolve the source mapping before approval." : "Inspect the records and approve the dataset."}`,
        !!result.data.errors.length,
      );
    } catch (e) {
      notify((e as Error).message, true);
    } finally {
      setBusy(false);
    }
  };
  return (
    <Dialog
      title="Map workbook columns"
      subtitle="Choose explicit source fields and units. Nothing is matched until a dataset is approved."
      onClose={onClose}
      wide
    >
      <div className="form-grid">
        <label className="form-field">
          Worksheet
          <select
            value={sheet}
            onChange={(e) => {
              setSheet(e.target.value);
              setPreview(null);
            }}
          >
            {catalog.data.sheets.map((s) => (
              <option key={s.name}>{s.name}</option>
            ))}
          </select>
        </label>
        <label className="form-field">
          Header row
          <input
            type="number"
            min={1}
            max={1000}
            value={header}
            onChange={(e) => {
              setHeader(+e.target.value);
              setPreview(null);
            }}
          />
        </label>
      </div>
      <button
        className="button secondary compact"
        disabled={busy}
        onClick={inspect}
      >
        <Search size={14} />
        Read source headers
      </button>
      {preview && (
        <>
          <div className="catalog-preview">
            <table>
              <thead>
                <tr>
                  {preview.headers.map((h) => (
                    <th key={h.index}>{h.label}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {preview.rows.slice(0, 5).map((row, i) => (
                  <tr key={i}>
                    {row.map((v, j) => (
                      <td key={j}>{v ?? "—"}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="form-grid">
            <label className="form-field">
              First data row
              <input
                type="number"
                min={header + 1}
                max={Number(last) || 100000}
                value={first}
                onChange={(e) => setFirst(+e.target.value)}
              />
            </label>
            <label className="form-field">
              Last data row
              <input
                type="number"
                min={header + 1}
                max={header + 5000}
                value={last}
                onChange={(e) => setLast(+e.target.value)}
              />
            </label>
            <label className="form-field">
              Weight source units
              <select
                value={weightUnit}
                onChange={(e) => setWeightUnit(e.target.value)}
              >
                <option>N</option>
                <option>kg</option>
                <option>lbf</option>
              </select>
              <small>kg is converted using 9.80665 m/s².</small>
            </label>
            <label className="form-field">
              Length source units
              <select
                value={lengthUnit}
                onChange={(e) => setLengthUnit(e.target.value)}
              >
                <option>mm</option>
                <option>in</option>
              </select>
            </label>
          </div>
          <p className="fine-print">
            Map a source column or supply an explicit constant. * Required for
            every row. API 6A also requires true API bore. Flanges require
            facing; valves require end connection. Manufacturer-confirmed
            records require vendor and model.
          </p>
          <div className="mapping-grid">
            {schema.fields.map((field) => (
              <div className="mapping-field" key={field}>
                <label htmlFor={`map-${field}`}>
                  {caption(field)}
                  {schema.required.includes(field) ? " *" : ""}
                  <small>
                    {numeric.includes(field)
                      ? "Missing stays N/A"
                      : "Exact text; no fuzzy match"}
                  </small>
                </label>
                <div>
                  <select
                    id={`map-${field}`}
                    value={columns[field] ?? ""}
                    onChange={(e) => {
                      const next = { ...columns };
                      if (e.target.value === "") delete next[field];
                      else next[field] = +e.target.value;
                      setColumns(next);
                      setConstants({ ...constants, [field]: "" });
                    }}
                  >
                    <option value="">No source column</option>
                    {preview.headers.map((h) => (
                      <option key={h.index} value={h.index}>
                        {h.label}
                      </option>
                    ))}
                  </select>
                  <input
                    aria-label={`Constant ${field}`}
                    placeholder={
                      field === "quality"
                        ? "REFERENCE_ONLY / ESTIMATED / MANUFACTURER_CONFIRMED"
                        : field === "weight_scope"
                          ? "BARE_FLANGE / ASSEMBLY / UNKNOWN"
                          : "Explicit constant (optional)"
                    }
                    value={constants[field] || ""}
                    onChange={(e) => {
                      setConstants({ ...constants, [field]: e.target.value });
                      const next = { ...columns };
                      delete next[field];
                      setColumns(next);
                    }}
                  />
                </div>
              </div>
            ))}
          </div>
          <div className="modal-footer">
            <span>
              <ShieldCheck size={14} />
              Source workbook is never changed
            </span>
            <button className="button primary" disabled={busy} onClick={save}>
              {busy ? (
                <Loader2 size={15} className="spin" />
              ) : (
                <GitBranch size={15} />
              )}
              Create dataset version
            </button>
          </div>
        </>
      )}
    </Dialog>
  );
}

export function MatchDialog({
  project,
  material,
  onClose,
  mutation,
  notify,
}: {
  project: Project;
  material: Material;
  onClose: () => void;
  mutation: Mutation;
  notify: Notify;
}) {
  const [datasets, setDatasets] = useState<Dataset[]>([]),
    [id, setId] = useState(""),
    [spec, setSpec] = useState<Record<string, string>>({
      ...material.catalog_match?.spec,
      family: material.family,
    }),
    [reason, setReason] = useState(""),
    [result, setResult] = useState<{
      status: string;
      missing: string[];
      candidates: RecordRow[];
    } | null>(null),
    [busy, setBusy] = useState(false);
  useEffect(() => {
    api<Dataset[]>("/approved-catalogs")
      .then((v) => {
        setDatasets(v);
        setId(v[0]?.id || "");
      })
      .catch((e) => notify(e.message, true));
  }, []);
  const body = {
    version: project.version,
    catalog_version_id: id,
    spec,
    reason,
  };
  const preview = async () => {
    setBusy(true);
    try {
      setResult(
        await api(
          `/projects/${project.id}/materials/${material.id}/catalog-match?dry_run=true`,
          { method: "POST", body: JSON.stringify(body) },
        ),
      );
    } catch (e) {
      notify((e as Error).message, true);
    } finally {
      setBusy(false);
    }
  };
  const save = async () => {
    setBusy(true);
    try {
      if (await mutation(`/materials/${material.id}/catalog-match`, body)) {
        notify("Exact match saved as an immutable source snapshot.");
        onClose();
      }
    } finally {
      setBusy(false);
    }
  };
  return (
    <Dialog
      title={`Catalog match · Item ${material.item_no}`}
      subtitle={material.description}
      onClose={onClose}
      wide
    >
      <div className="notice">
        <Database size={18} />
        <span>
          Specify the complete component identity. Pipe NPS and API bore are
          different fields. A reference match does not confirm the actual
          manufacturer.
        </span>
      </div>
      {!datasets.length ? (
        <p className="fine-print">
          No approved datasets yet. Register, map and approve a workbook in
          Component catalogs first.
        </p>
      ) : (
        <>
          <label className="form-field">
            Approved dataset
            <select
              value={id}
              onChange={(e) => {
                setId(e.target.value);
                setResult(null);
              }}
            >
              {datasets.map((d) => (
                <option key={d.id} value={d.id}>
                  {d.data.source_filename} · Version {d.seq} ·{" "}
                  {d.data.mapping.sheet}
                </option>
              ))}
            </select>
          </label>
          <div className="form-grid">
            {[
              "standard",
              "rating",
              "nps",
              "api_bore",
              "component_type",
              "facing",
              "end_connection",
              "code",
              "vendor",
              "model",
            ].map((k) => (
              <label className="form-field" key={k}>
                {caption(k)}
                <input
                  value={spec[k] || ""}
                  onChange={(e) => {
                    setSpec({ ...spec, [k]: e.target.value });
                    setResult(null);
                  }}
                  placeholder={
                    ["vendor", "model", "code"].includes(k)
                      ? "Optional constraint"
                      : "Enter the drawing specification"
                  }
                />
              </label>
            ))}
          </div>
          <label className="form-field">
            Match evidence / review reason
            <textarea
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="Source item, specification and source quality reviewed…"
              minLength={10}
            />
          </label>
          <button
            className="button secondary"
            disabled={busy || reason.trim().length < 10}
            onClick={preview}
          >
            <Search size={15} />
            Find exact matches
          </button>
          {result && (
            <div className="catalog-version">
              <h4>{label(result.status)}</h4>
              {!!result.missing.length && (
                <p className="fine-print">
                  Required fields: {result.missing.map(caption).join(", ")}
                </p>
              )}
              {result.candidates.slice(0, 5).map((r, i) => (
                <div key={i}>
                  <p>
                    <b>
                      {String(r.component_type)} · {String(r.nps)} ·{" "}
                      {String(r.rating)}
                    </b>
                  </p>
                  <p className="fine-print">
                    Weight {String(r.weight_n ?? "N/A")} N · Length{" "}
                    {String(r.length_mm ?? "N/A")} mm · {String(r.quality)}
                    <br />
                    {String(r.source)}
                  </p>
                </div>
              ))}
              {result.status === "EXACT_MATCH" && (
                <button
                  className="button primary full"
                  disabled={busy}
                  onClick={save}
                >
                  <Check size={15} />
                  Save this exact match
                </button>
              )}
            </div>
          )}
        </>
      )}
      {material.catalog_match && (
        <button
          className="button danger full compact"
          onClick={async () => {
            if (
              await mutation(
                `/materials/${material.id}/catalog-match?version=${project.version}`,
                undefined,
                "DELETE",
              )
            )
              onClose();
          }}
        >
          Remove existing match
        </button>
      )}
    </Dialog>
  );
}
