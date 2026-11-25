import { useEffect, useRef, useState } from "react";
import {
  Database,
  FileSpreadsheet,
  History,
  Loader2,
  ShieldCheck,
} from "lucide-react";
import { api, label, type Project } from "./types";
import { Dialog } from "./ui";

type Decision = "ACCEPT_EXACT_MATCH" | "DECLARE_NA" | "REOPEN";
type Review = {
  id: string;
  material_id: string;
  decision: string;
  reason_code?: string;
  evidence: string;
  reviewed_by?: string;
  reviewed_at?: string;
  current?: boolean;
  stale?: boolean;
  effective_status?: string;
  vendor?: string;
  model?: string;
};
type Candidate = {
  catalog_version_id: string;
  record_id: string;
  quality: string;
  dataset_approved: boolean;
  integrity_current: boolean;
  record: Record<string, string | number | null>;
};
type CatalogRow = {
  material_id: string;
  sheet_id: string;
  item_no: string;
  family: string;
  description: string;
  size: string;
  quantity: number | null;
  occurrence_count: number;
  source_sha256: string;
  source_context_sha256: string;
  status: string;
  proposal_status: string;
  reason_codes: string[];
  exact_candidates: Candidate[];
  partial_candidates?: Candidate[];
  values: {
    weight_n: string | null;
    half_weight_n: string | null;
    full_weight_n: string | null;
    length_mm: string | null;
  };
  catalog_source_quality: string | null;
  project_manufacturer: {
    status: string;
    vendor?: string;
    model?: string;
    latest_review?: Review;
  };
  latest_review?: Review | null;
  current?: boolean;
};
type CatalogReport = {
  revision: number;
  can_edit: boolean;
  prepared: boolean;
  catalog_manifest: {
    catalog_version_id: string;
    source_sha256: string;
    status: string;
    record_count: number;
    source_filename: string;
    sheet: string;
    integrity_current: boolean;
    units: Record<string, string>;
  }[];
  reason_codes?: string[];
  rows: CatalogRow[];
  classification_rows?: CatalogRow[];
  sheets: {
    sheet_id: string;
    rows: CatalogRow[];
    review_complete: boolean;
    numeric_complete: boolean;
  }[];
  reviews: Review[];
  manufacturer_reviews: Review[];
};
const reasons = [
  "SPECIFICATION_UNCONFIRMED",
  "NO_EXACT_CATALOG_MATCH",
  "CATALOG_FACING_UNSPECIFIED",
  "CATALOG_COMPONENT_TYPE_UNSUPPORTED",
  "API_BORE_UNCONFIRMED",
  "VALVE_MANUFACTURER_DATA_UNAVAILABLE",
  "CATALOG_DATASET_UNAPPROVED",
  "COMPONENT_CLASSIFICATION_UNCONFIRMED",
  "CATALOG_RECORD_INCOMPLETE",
];
const decisionReason = (decision: Decision) =>
  decision === "ACCEPT_EXACT_MATCH"
    ? "SOURCE_SPECIFICATION_AND_DATASET_REVIEWED"
    : decision === "REOPEN"
      ? "REVIEW_REOPENED"
      : reasons[0];
const dispositionLabels: Record<string, string> = {
  DECLARED_NA: "Reviewed N/A",
  DECLARE_NA: "Declare N/A",
  MATCHED_REFERENCE: "Catalog reference matched",
};
const dispositionLabel = (value: string) =>
  dispositionLabels[value] || label(value);
const number = (value: string | number | null | undefined) =>
  value == null ? "N/A" : String(value);

export function ProjectCatalogReviewControls({
  project,
  onUpdate,
}: {
  project: Project;
  onUpdate: (project: Project) => void;
}) {
  const path = `/projects/${project.id}/catalog-review`;
  const reviewRef = useRef<HTMLFormElement>(null);
  const [data, setData] = useState<CatalogReport | null>(null);
  const [open, setOpen] = useState(false),
    [version, setVersion] = useState(project.version);
  const [sheetId, setSheetId] = useState(""),
    [materialId, setMaterialId] = useState("");
  const [decision, setDecision] = useState<Decision>("DECLARE_NA"),
    [reason, setReason] = useState(reasons[0]);
  const [evidence, setEvidence] = useState(""),
    [confirmed, setConfirmed] = useState(false),
    [candidateId, setCandidateId] = useState("");
  const [mode, setMode] = useState<"catalog" | "manufacturer">("catalog");
  const [makerDecision, setMakerDecision] = useState<"CONFIRM" | "REOPEN">(
    "REOPEN",
  );
  const [vendor, setVendor] = useState(""),
    [model, setModel] = useState("");
  const [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    api<CatalogReport>(path)
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
  const sheetName = (id: string) => {
    const sheet = project.sheets.find((s) => s.id === id);
    return sheet?.printed_id || `PDF page ${(sheet?.page_index ?? -1) + 1}`;
  };
  const row = data?.rows.find((r) => r.material_id === materialId);
  const rows =
    data?.rows.filter((r) => !sheetId || r.sheet_id === sheetId) || [];
  const current = data?.revision === version && project.version === version;
  const editable = Boolean(data?.can_edit && current && !busy);
  const approvedCandidates =
    row?.exact_candidates.filter(
      (candidate) => candidate.dataset_approved && candidate.integrity_current,
    ) || [];
  const candidate = approvedCandidates.find(
    (c) => `${c.catalog_version_id}:${c.record_id}` === candidateId,
  );
  const reset = (id: string) => {
    setMaterialId(id);
    setDecision("DECLARE_NA");
    setReason(reasons[0]);
    setEvidence("");
    setConfirmed(false);
    setCandidateId("");
    setMakerDecision("REOPEN");
    setVendor("");
    setModel("");
    setError("");
    setMode("catalog");
  };
  const close = () => {
    if (!busy) {
      setOpen(false);
      setError("");
    }
  };
  const save = async (body: Record<string, unknown>, suffix: string) => {
    setBusy(true);
    setError("");
    try {
      const updated = await api<Project>(`${path}/${suffix}`, {
        method: "POST",
        body: JSON.stringify({ version, ...body, confirmed: true }),
      });
      const next = await api<CatalogReport>(path);
      onUpdate(updated);
      setData(next);
      setVersion(updated.version);
      setEvidence("");
      setConfirmed(false);
      setCandidateId("");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  const history =
    data?.reviews.filter((r) => r.material_id === materialId) || [];
  const makerHistory =
    data?.manufacturer_reviews.filter((r) => r.material_id === materialId) ||
    [];
  return (
    <div className="physical-controls">
      <div className="review-actions">
        <button
          className="button secondary"
          disabled={
            !data ||
            !project.materials.some((m) =>
              ["flange", "valve"].includes(m.family),
            )
          }
          onClick={() => {
            setVersion(project.version);
            setSheetId("");
            reset(data?.rows[0]?.material_id || "");
            setOpen(true);
          }}
        >
          <Database size={16} /> Review catalogs and schedules
        </button>
        <span className="fine-print">
          {data?.rows.length ?? 0} flange / valve source items · catalog quality
          and project manufacturer are separate
        </span>
      </div>
      {error && !open && (
        <p className="error-text" role="alert">
          {error}
        </p>
      )}
      {open && data && (
        <Dialog
          wide
          title="Project catalogs and schedules"
          subtitle={`Revision ${version} · Per-sheet source inventory and evidence-linked values`}
          onClose={close}
        >
          <div
            className="notice"
            style={{ display: "block", color: "#37577d" }}
          >
            <b>Unknowns stay N/A and blue.</b> Exact catalog matches require the
            complete drawing specification and an approved dataset. An explicit
            N/A records an unresolved data gap; it does not waive manufacturer
            evidence or approve engineering use.{" "}
            <p className="fine-print">
              W_flange, W_half and W_full are alternative bare / half bolting /
              full bolting weights in N. Do not add the assembly weights
              together. Catalog source quality does not confirm the installed
              manufacturer.
            </p>
          </div>
          {!current && (
            <div className="notice amber" role="alert">
              The project changed. Close this dialog and reopen it before saving
              a decision.
            </div>
          )}
          {error && (
            <div className="notice amber" role="alert">
              {error}
            </div>
          )}
          <div className="review-actions">
            <button
              className="button secondary"
              disabled={!editable}
              onClick={() => save({}, "prepare")}
            >
              <Database size={15} />{" "}
              {data.prepared
                ? "Refresh catalog proposals"
                : "Prepare catalog proposals"}
            </button>
            <span className="fine-print">
              Source proposals never accept values or confirm manufacturers.
            </span>
          </div>
          <details aria-label="Registered catalog sources">
            <summary>
              Registered catalog sources (
              {data.catalog_manifest.reduce(
                (sum, source) => sum + source.record_count,
                0,
              )}{" "}
              records)
            </summary>
            {!data.catalog_manifest.length ? (
              <p>
                No catalog dataset is registered in this account. Unknown values
                remain N/A.
              </p>
            ) : (
              <div className="results-table-scroll">
                <table
                  className="results-grid"
                  aria-label="Registered catalog dataset inventory"
                >
                  <thead>
                    <tr>
                      <th>Source workbook / sheet</th>
                      <th>Records</th>
                      <th>Dataset approval</th>
                      <th>Source integrity</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.catalog_manifest.map((source) => (
                      <tr key={source.catalog_version_id}>
                        <td>
                          {source.source_filename}
                          <br />
                          <small>{source.sheet}</small>
                          <details>
                            <summary>Source identity</summary>
                            <small style={{ overflowWrap: "anywhere" }}>
                              {source.source_sha256}
                            </small>
                          </details>
                        </td>
                        <td>{source.record_count}</td>
                        <td>{label(source.status)}</td>
                        <td>
                          {source.integrity_current
                            ? "Current"
                            : "Review required"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            <p className="fine-print">
              Review and approve datasets in Component catalogs before exact
              matching. Project manufacturer evidence remains separate.
            </p>
          </details>
          <label className="form-field">
            Schedule drawing sheet
            <select
              aria-label="Schedule drawing sheet"
              value={sheetId}
              onChange={(e) => setSheetId(e.target.value)}
            >
              <option value="">Whole project · every sheet</option>
              {project.sheets.map((sheet) => (
                <option key={sheet.id} value={sheet.id}>
                  {sheetName(sheet.id)}
                </option>
              ))}
            </select>
          </label>
          {project.sheets
            .filter((s) => !sheetId || s.id === sheetId)
            .map((sheet) => {
              const summary = data.sheets.find((s) => s.sheet_id === sheet.id);
              const schedule = rows.filter((r) => r.sheet_id === sheet.id);
              if (!schedule.length) return null;
              return (
                <section
                  key={sheet.id}
                  aria-label={`Component schedule ${sheetName(sheet.id)}`}
                >
                  <h3>
                    <FileSpreadsheet size={16} /> {sheetName(sheet.id)} ·
                    Component schedule
                  </h3>
                  <p className="fine-print">
                    {summary?.review_complete
                      ? "Catalog dispositions reviewed"
                      : "Catalog review required"}{" "}
                    ·{" "}
                    {summary?.numeric_complete
                      ? "Catalog numeric values available"
                      : "Numeric data incomplete — N/A retained"}{" "}
                    · Engineering review draft
                  </p>
                  <div className="results-table-scroll">
                    <table
                      className="results-grid"
                      aria-label={`Schedule table ${sheetName(sheet.id)}`}
                    >
                      <thead>
                        <tr>
                          <th>Source item</th>
                          <th>Specification</th>
                          <th>Qty</th>
                          <th>Review</th>
                          <th>W_flange / valve W (N)</th>
                          <th>W_half (N)</th>
                          <th>W_full (N)</th>
                          <th>Valve L (mm)</th>
                          <th>Manufacturer</th>
                        </tr>
                      </thead>
                      <tbody>
                        {schedule.map((r) => (
                          <tr
                            key={r.material_id}
                            data-material-id={r.material_id}
                          >
                            <td>
                              <button
                                type="button"
                                className="button secondary"
                                onClick={() => {
                                  reset(r.material_id);
                                  reviewRef.current?.scrollIntoView({
                                    behavior: "smooth",
                                    block: "start",
                                  });
                                }}
                                aria-label={`Review ${sheetName(r.sheet_id)} item ${r.item_no}`}
                              >
                                Item {r.item_no} · {label(r.family)}
                              </button>
                              <br />
                              <small>
                                {r.occurrence_count} source occurrences
                              </small>
                            </td>
                            <td style={{ minWidth: 240, whiteSpace: "normal" }}>
                              {r.description}
                              <br />
                              <small>Size {r.size}</small>
                            </td>
                            <td>{number(r.quantity)}</td>
                            <td>
                              <span className="badge blue">
                                {dispositionLabel(r.status)}
                              </span>
                              <br />
                              <small>{label(r.proposal_status)}</small>
                            </td>
                            <td>{number(r.values.weight_n)}</td>
                            <td>
                              {r.family === "flange"
                                ? number(r.values.half_weight_n)
                                : "N/A"}
                            </td>
                            <td>
                              {r.family === "flange"
                                ? number(r.values.full_weight_n)
                                : "N/A"}
                            </td>
                            <td>
                              {r.family === "valve"
                                ? number(r.values.length_mm)
                                : "N/A"}
                            </td>
                            <td>
                              <span
                                className={`badge ${r.project_manufacturer.status === "CONFIRMED" ? "green" : "blue"}`}
                              >
                                {label(r.project_manufacturer.status)}
                              </span>
                              <br />
                              <small>
                                {r.catalog_source_quality
                                  ? label(r.catalog_source_quality)
                                  : "No accepted catalog quality"}
                              </small>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </section>
              );
            })}
          {Boolean(data.classification_rows?.length) && (
            <div
              className="notice"
              aria-label="Components requiring classification"
              style={{ display: "block", color: "#37577d" }}
            >
              <b>Classification still requires review</b>
              {data.classification_rows?.map((component) => (
                <p key={component.material_id}>
                  <span className="badge blue">
                    Component classification unconfirmed
                  </span>{" "}
                  {sheetName(component.sheet_id)} · Item {component.item_no} ·{" "}
                  {component.description}
                  <br />
                  <small>
                    Visible process ends remain source proposals. This component
                    is not counted as a valve or given a catalog weight. Correct
                    the material family only after reviewing its actual source.
                  </small>
                </p>
              ))}
            </div>
          )}
          <form
            ref={reviewRef}
            onSubmit={async (event) => {
              event.preventDefault();
              if (!row) return;
              if (mode === "manufacturer")
                await save(
                  {
                    material_id: row.material_id,
                    source_context_sha256: row.source_context_sha256,
                    decision: makerDecision,
                    evidence,
                    ...(makerDecision === "CONFIRM" ? { vendor, model } : {}),
                  },
                  "manufacturer",
                );
              else
                await save(
                  {
                    material_id: row.material_id,
                    source_context_sha256: row.source_context_sha256,
                    decision,
                    reason_code: reason,
                    evidence,
                    ...(candidate && decision === "ACCEPT_EXACT_MATCH"
                      ? {
                          catalog_version_id: candidate.catalog_version_id,
                          record_id: candidate.record_id,
                        }
                      : {}),
                  },
                  "decision",
                );
            }}
          >
            <label className="form-field">
              Source component for review
              <select
                aria-label="Source component for review"
                value={materialId}
                onChange={(e) => reset(e.target.value)}
              >
                {data.rows.map((r) => (
                  <option key={r.material_id} value={r.material_id}>
                    {sheetName(r.sheet_id)} · Item {r.item_no} · {r.family} ·{" "}
                    {r.size}
                  </option>
                ))}
              </select>
            </label>
            {row && (
              <>
                <div
                  className="notice"
                  style={{ display: "block", color: "#37577d" }}
                >
                  <b>Actual source description</b>
                  <p>{row.description}</p>
                  <p className="fine-print">
                    {sheetName(row.sheet_id)} · Item {row.item_no} ·{" "}
                    {row.reason_codes.map(label).join(" · ")}
                  </p>
                  <details>
                    <summary>Source identity and provenance</summary>
                    <p
                      className="fine-print"
                      style={{ overflowWrap: "anywhere" }}
                    >
                      PDF SHA256: {row.source_sha256}
                      <br />
                      Current source context: {row.source_context_sha256}
                      <br />
                      Material: {row.material_id}
                    </p>
                  </details>
                </div>
                <label className="form-field">
                  Review evidence type
                  <select
                    aria-label="Review evidence type"
                    value={mode}
                    onChange={(e) => {
                      setMode(e.target.value as typeof mode);
                      setEvidence("");
                      setConfirmed(false);
                    }}
                  >
                    <option value="catalog">
                      Catalog match or explicit N/A
                    </option>
                    <option value="manufacturer">
                      Independent project manufacturer evidence
                    </option>
                  </select>
                </label>
                {mode === "catalog" ? (
                  <>
                    <label className="form-field">
                      Catalog disposition
                      <select
                        aria-label="Catalog disposition"
                        disabled={!editable}
                        value={decision}
                        onChange={(e) => {
                          setDecision(e.target.value as Decision);
                          setReason(decisionReason(e.target.value as Decision));
                          setConfirmed(false);
                        }}
                      >
                        <option value="DECLARE_NA">
                          Explicit N/A — unresolved data
                        </option>
                        <option
                          value="ACCEPT_EXACT_MATCH"
                          disabled={approvedCandidates.length !== 1}
                        >
                          Accept an exact source-specification match
                        </option>
                        <option value="REOPEN">Reopen catalog review</option>
                      </select>
                    </label>
                    <label className="form-field">
                      Catalog decision reason
                      <select
                        aria-label="Catalog decision reason"
                        disabled={!editable}
                        value={reason}
                        onChange={(e) => {
                          setReason(e.target.value);
                          setConfirmed(false);
                        }}
                      >
                        {(decision === "DECLARE_NA"
                          ? reasons
                          : [decisionReason(decision)]
                        ).map((r) => (
                          <option key={r} value={r}>
                            {label(r)}
                          </option>
                        ))}
                      </select>
                    </label>
                    {decision === "ACCEPT_EXACT_MATCH" ? (
                      <>
                        <label className="form-field">
                          Exact approved catalog record
                          <select
                            aria-label="Exact approved catalog record"
                            value={candidateId}
                            required
                            disabled={!editable}
                            onChange={(e) => {
                              setCandidateId(e.target.value);
                              setConfirmed(false);
                            }}
                          >
                            <option value="">
                              Select a proved exact match
                            </option>
                            {approvedCandidates.map((c) => (
                              <option
                                key={`${c.catalog_version_id}:${c.record_id}`}
                                value={`${c.catalog_version_id}:${c.record_id}`}
                              >
                                {String(c.record.standard)} ·{" "}
                                {String(c.record.rating)} ·{" "}
                                {String(c.record.component_type)} · {c.quality}{" "}
                                · row {String(c.record.source_row)}
                              </option>
                            ))}
                          </select>
                        </label>
                        {candidate && (
                          <div className="notice" style={{ display: "block" }}>
                            W {number(candidate.record.weight_n)} N · W_half{" "}
                            {number(candidate.record.half_weight_n)} N · W_full{" "}
                            {number(candidate.record.full_weight_n)} N · L{" "}
                            {number(candidate.record.length_mm)} mm. Catalog
                            quality {label(candidate.quality)}; project
                            manufacturer remains independently reviewed.
                          </div>
                        )}
                      </>
                    ) : (
                      <p className="fine-print">
                        {approvedCandidates.length} exact approved candidates.
                        Partial candidates are diagnostic only; missing facing,
                        bore, class or valve data cannot become accepted values.
                      </p>
                    )}
                  </>
                ) : (
                  <>
                    <div
                      className="notice"
                      style={{ display: "block", color: "#37577d" }}
                    >
                      <ShieldCheck size={16} /> Current project manufacturer:{" "}
                      <b>{label(row.project_manufacturer.status)}</b>. Catalog
                      quality is{" "}
                      {row.catalog_source_quality
                        ? label(row.catalog_source_quality)
                        : "N/A"}
                      . Confirm only with independent evidence identifying the
                      actual supplied component.
                    </div>
                    <label className="form-field">
                      Manufacturer evidence decision
                      <select
                        aria-label="Manufacturer evidence decision"
                        value={makerDecision}
                        disabled={!editable}
                        onChange={(e) => {
                          setMakerDecision(
                            e.target.value as typeof makerDecision,
                          );
                          setConfirmed(false);
                        }}
                      >
                        <option value="REOPEN">
                          Reopen — manufacturer remains unconfirmed
                        </option>
                        <option value="CONFIRM">
                          Confirm actual manufacturer from independent evidence
                        </option>
                      </select>
                    </label>
                    {makerDecision === "CONFIRM" && (
                      <div className="form-grid">
                        <label className="form-field">
                          Actual manufacturer
                          <input
                            aria-label="Actual manufacturer"
                            required
                            maxLength={150}
                            disabled={!editable}
                            value={vendor}
                            onChange={(e) => {
                              setVendor(e.target.value);
                              setConfirmed(false);
                            }}
                          />
                        </label>
                        <label className="form-field">
                          Actual component model
                          <input
                            aria-label="Actual component model"
                            required
                            maxLength={150}
                            disabled={!editable}
                            value={model}
                            onChange={(e) => {
                              setModel(e.target.value);
                              setConfirmed(false);
                            }}
                          />
                        </label>
                      </div>
                    )}
                  </>
                )}
                <label className="form-field">
                  {mode === "catalog"
                    ? "Catalog source evidence"
                    : "Independent manufacturer source evidence"}
                  <textarea
                    aria-label={
                      mode === "catalog"
                        ? "Catalog source evidence"
                        : "Independent manufacturer source evidence"
                    }
                    required
                    minLength={mode === "manufacturer" ? 20 : 10}
                    maxLength={3000}
                    disabled={!editable}
                    value={evidence}
                    onChange={(e) => {
                      setEvidence(e.target.value);
                      setConfirmed(false);
                    }}
                    placeholder="Identify the source facts, missing fields or independently obtained manufacturer document. Unknown technical values stay N/A."
                  />
                </label>
                <label>
                  <input
                    type="checkbox"
                    aria-label={
                      mode === "catalog"
                        ? "Confirm catalog source decision"
                        : "Confirm independent manufacturer evidence"
                    }
                    required
                    checked={confirmed}
                    disabled={!editable}
                    onChange={(e) => setConfirmed(e.target.checked)}
                  />{" "}
                  {mode === "catalog"
                    ? "I reviewed the source specification and this catalog disposition. N/A remains unresolved; manufacturer confirmation is separate."
                    : "I reviewed independent evidence for this actual component. Catalog source quality alone is insufficient."}
                </label>
                <div className="modal-actions">
                  <button
                    type="button"
                    className="button secondary"
                    disabled={busy}
                    onClick={close}
                  >
                    Close
                  </button>
                  <button
                    className="button primary"
                    disabled={
                      !editable ||
                      !confirmed ||
                      !data.prepared ||
                      (mode === "catalog" &&
                        decision === "ACCEPT_EXACT_MATCH" &&
                        !candidate)
                    }
                  >
                    {busy ? (
                      <Loader2 size={15} className="spin" />
                    ) : (
                      <ShieldCheck size={15} />
                    )}{" "}
                    {mode === "catalog"
                      ? "Save catalog decision"
                      : "Save manufacturer evidence"}
                  </button>
                </div>
                <details aria-label="Catalog decision history">
                  <summary>
                    <History size={14} /> Catalog decision history (
                    {history.length})
                  </summary>
                  {!history.length && <p>No catalog decisions recorded.</p>}
                  {history
                    .slice()
                    .reverse()
                    .map((review) => (
                      <div
                        className="notice"
                        style={{ display: "block", color: "#37577d" }}
                        key={review.id}
                      >
                        <b>
                          {dispositionLabel(review.decision)} ·{" "}
                          {review.stale
                            ? "Stale source"
                            : review.current
                              ? "Current source"
                              : "History"}
                        </b>
                        <p>
                          {review.reason_code && label(review.reason_code)} ·{" "}
                          {review.evidence}
                        </p>
                        <small>
                          {review.reviewed_at} · {review.reviewed_by}
                        </small>
                      </div>
                    ))}
                </details>
                <details aria-label="Manufacturer evidence history">
                  <summary>
                    <History size={14} /> Independent manufacturer evidence (
                    {makerHistory.length})
                  </summary>
                  {!makerHistory.length && (
                    <p>No independent manufacturer confirmation recorded.</p>
                  )}
                  {makerHistory
                    .slice()
                    .reverse()
                    .map((review) => (
                      <div
                        className="notice"
                        style={{ display: "block", color: "#37577d" }}
                        key={review.id}
                      >
                        <b>
                          {dispositionLabel(review.decision)} ·{" "}
                          {review.stale
                            ? "Stale source"
                            : review.current
                              ? "Current source"
                              : "History"}
                        </b>
                        <p>
                          {review.vendor} {review.model} · {review.evidence}
                        </p>
                        <small>
                          {review.reviewed_at} · {review.reviewed_by}
                        </small>
                      </div>
                    ))}
                </details>
              </>
            )}
          </form>
        </Dialog>
      )}
    </div>
  );
}
