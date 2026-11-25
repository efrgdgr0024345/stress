import { useEffect, useState } from "react";
import { ClipboardCheck, Loader2, Wrench } from "lucide-react";
import { api, label, pointLabel, type Project } from "./types";
import { Dialog } from "./ui";

type Kind = "BEND" | "TEE" | "RIGID" | "RESTRAINT";
type Value = string | number | boolean | null;
type Field = {
  key: string;
  label: string;
  type: string;
  unit?: string;
  required?: boolean;
  options?: (string | { value: string; label: string })[];
};
type RecordRow = {
  id: string;
  kind: Kind;
  component_id?: string | null;
  point_id?: string | null;
  element_id?: string | null;
  review_state: "DRAFT" | "REVIEWED";
  values: Record<string, Value>;
  source_sheet_id?: string | null;
  evidence: string;
  current: boolean;
  stale: boolean;
  issues: string[];
};
type Requirement = {
  id: string;
  component_id?: string | null;
  point_id?: string | null;
  element_id?: string | null;
  kind: Kind | "UNSUPPORTED";
  material_id?: string;
  sheet_id?: string;
  missing: string[];
  record?: RecordRow | null;
  label?: string;
};
type Report = {
  revision: number;
  can_edit: boolean;
  profile: string;
  requirements: Requirement[];
  records: RecordRow[];
  issues: ({ code: string; message: string } | string)[];
  field_schema: Record<Kind, Field[]>;
  elements?: { id: string; from_point_id: string; to_point_id: string }[];
};

const optionLabel = (key: string, value: string) => {
  const names: Record<string, Record<string, string>> = {
    rigid_type: { "1": "1 · Valve", "2": "2 · Flange" },
    type_code: {
      "2": "2 · X",
      "3": "3 · Y",
      "4": "4 · Z",
      "13": "13 · +X",
      "14": "14 · +Y",
      "15": "15 · +Z",
      "16": "16 · −X",
      "17": "17 · −Y",
      "18": "18 · −Z",
    },
    tee_type: { "3": "3 · B31J welding tee" },
    weight_scope: {
      COMPONENT_TOTAL_EXCLUDES_FLUID_INSULATION:
        "Component total, excluding fluid and insulation",
    },
  };
  return names[key]?.[value] || label(value);
};

export function CIIComponentControls({
  project,
  onUpdate,
}: {
  project: Project;
  onUpdate: (project: Project) => void;
}) {
  const path = `/projects/${project.id}/cii-components`;
  const [data, setData] = useState<Report | null>(null),
    [open, setOpen] = useState(false);
  const [version, setVersion] = useState(project.version),
    [requirementId, setRequirementId] = useState("");
  const [elementId, setElementId] = useState("");
  const [recordId, setRecordId] = useState(""),
    [values, setValues] = useState<Record<string, Value>>({});
  const [reviewState, setReviewState] = useState<"DRAFT" | "REVIEWED">("DRAFT"),
    [sheetId, setSheetId] = useState("");
  const [evidence, setEvidence] = useState(""),
    [confirmed, setConfirmed] = useState(false);
  const [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    api<Report>(path)
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
  const requirement = data?.requirements.find(
    (row) => row.id === requirementId,
  );
  const current = data?.revision === version && project.version === version;
  const editable = Boolean(data?.can_edit && current && !busy);
  const supported = requirement && requirement.kind !== "UNSUPPORTED";
  const fields = supported
    ? data?.field_schema[requirement.kind as Kind] || []
    : [];
  const title = (row: Requirement) => {
    if (row.label) return row.label;
    const material = project.materials.find((m) => m.id === row.material_id),
      point = project.nodes.find((n) => n.id === row.point_id);
    return `${label(row.kind)}${material ? ` · Item ${material.item_no} · ${material.size}` : ""}${point ? ` · ${pointLabel(point)}` : ""}`;
  };
  const choose = (id: string, report = data) => {
    const row = report?.requirements.find((r) => r.id === id);
    const saved =
      row?.record ||
      report?.records.find(
        (record) =>
          record.kind === row?.kind &&
          (row?.component_id
            ? record.component_id === row.component_id
            : record.point_id === row?.point_id),
      );
    setRequirementId(id);
    setRecordId(saved?.id || "");
    setElementId(saved?.element_id || row?.element_id || "");
    setValues(saved?.values || {});
    setReviewState(saved?.review_state || "DRAFT");
    setSheetId(saved?.source_sheet_id || row?.sheet_id || "");
    setEvidence(saved?.evidence || "");
    setConfirmed(false);
    setError("");
  };
  const setValue = (key: string, value: Value) => {
    setValues((current) => ({ ...current, [key]: value }));
    setConfirmed(false);
  };
  const pointOptions = project.nodes.map((point) => (
    <option key={point.id} value={point.id}>
      {pointLabel(point)} · {point.kind} · {point.line_id}
    </option>
  ));
  const close = () => {
    if (!busy) {
      setOpen(false);
      setError("");
    }
  };
  return (
    <div className="physical-controls">
      <div className="review-actions">
        <button
          className="button secondary"
          disabled={!data || !project.sheets.length}
          onClick={() => {
            setVersion(project.version);
            choose(data?.requirements[0]?.id || "");
            setOpen(true);
          }}
        >
          <Wrench size={16} /> CAESAR component data
        </button>
        <span className="fine-print">
          Explicit bend, tee, rigid and restraint inputs · blanks stay unknown ·
          native generation remains gated
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
          title="CAESAR component source data"
          subtitle={`Revision ${version} · CAESAR II 15.1 candidate inputs`}
          onClose={close}
        >
          <div
            className="notice"
            style={{ display: "block", color: "#37577d" }}
          >
            <b>Source data first; export gates remain strict.</b> A saved draft
            keeps every blank value unknown. Reviewed component fields do not
            supply missing stations, XYZ, route connections, manufacturer data
            or lead-engineer approval. A generated CII file still requires
            validation in CAESAR II.
            <p className="fine-print">
              A theoretical elbow COD does not automatically identify the native
              bend far end or define its bend representation. Enter only an
              explicitly reviewed mapping. Rigid weight is force in N; confirm
              the actual bare/bolted assembly scope. Restraint type, direction,
              gap and stiffness require their own source evidence.
            </p>
          </div>
          {!current && (
            <div className="notice amber" role="alert">
              The project changed. Close and reopen this dialog before saving.
            </div>
          )}
          {error && (
            <div className="notice amber" role="alert">
              {error}
            </div>
          )}
          <label className="form-field">
            Native component or restraint
            <select
              aria-label="Native component or restraint"
              disabled={busy}
              value={requirementId}
              onChange={(e) => choose(e.target.value)}
            >
              {!data.requirements.length && (
                <option value="">No applicable source components</option>
              )}
              {data.requirements.map((row, index) => (
                <option key={row.id} value={row.id}>
                  {title(row)} · requirement {index + 1}
                </option>
              ))}
            </select>
          </label>
          {requirement && supported && (
            <form
              onSubmit={async (event) => {
                event.preventDefault();
                setBusy(true);
                setError("");
                try {
                  const updated = await api<Project>(
                    `${path}/records${recordId ? "/" + recordId : ""}`,
                    {
                      method: recordId ? "PATCH" : "POST",
                      body: JSON.stringify({
                        version,
                        kind: requirement.kind,
                        component_id: requirement.component_id || null,
                        point_id: requirement.point_id || null,
                        element_id: elementId || null,
                        review_state: reviewState,
                        values: Object.fromEntries(
                          fields.map((field) => [
                            field.key,
                            values[field.key] ?? null,
                          ]),
                        ),
                        source_sheet_id: sheetId || null,
                        evidence,
                        confirmed: true,
                      }),
                    },
                  );
                  onUpdate(updated);
                  setVersion(updated.version);
                  const report = await api<Report>(path);
                  setData(report);
                  choose(requirement.id, report);
                } catch (e) {
                  setError((e as Error).message);
                } finally {
                  setBusy(false);
                }
              }}
            >
              <div
                className="notice"
                style={{ display: "block", color: "#37577d" }}
              >
                <b>{title(requirement)}</b>
                {requirement.material_id && (
                  <p>
                    {
                      project.materials.find(
                        (m) => m.id === requirement.material_id,
                      )?.description
                    }
                  </p>
                )}
                <p className="fine-print">
                  {requirement.record?.stale
                    ? "Stored source review is stale; recheck its evidence."
                    : requirement.record?.current
                      ? "Stored source record is current; remaining model gates still apply."
                      : "No current reviewed source record."}
                </p>
                {Boolean(requirement.missing.length) && (
                  <p className="fine-print">
                    Still required:{" "}
                    {requirement.missing.join("; ").replaceAll("_", " ")}
                  </p>
                )}
              </div>
              <div className="form-grid">
                <label className="form-field">
                  Component data review state
                  <select
                    aria-label="Component data review state"
                    disabled={!editable}
                    value={reviewState}
                    onChange={(e) => {
                      setReviewState(e.target.value as typeof reviewState);
                      setConfirmed(false);
                    }}
                  >
                    <option value="DRAFT">
                      Draft — missing values remain unknown
                    </option>
                    <option value="REVIEWED">
                      Source reviewed — all required fields must be proved
                    </option>
                  </select>
                </label>
                <label className="form-field">
                  Component source sheet
                  <select
                    aria-label="Component source sheet"
                    disabled={!editable}
                    value={sheetId}
                    onChange={(e) => {
                      setSheetId(e.target.value);
                      setConfirmed(false);
                    }}
                  >
                    <option value="">Source not yet confirmed</option>
                    {project.sheets.map((sheet) => (
                      <option key={sheet.id} value={sheet.id}>
                        {sheet.printed_id || `PDF page ${sheet.page_index + 1}`}
                      </option>
                    ))}
                  </select>
                </label>
              </div>
              {
                <label className="form-field">
                  Native element mapping
                  <select
                    aria-label="Native element mapping"
                    disabled={!editable}
                    value={elementId}
                    onChange={(e) => {
                      setElementId(e.target.value);
                      setConfirmed(false);
                    }}
                  >
                    <option value="">No accepted element mapping</option>
                    {data.elements?.map((element) => {
                      const from = project.nodes.find(
                          (point) => point.id === element.from_point_id,
                        ),
                        to = project.nodes.find(
                          (point) => point.id === element.to_point_id,
                        );
                      return (
                        <option key={element.id} value={element.id}>
                          {from ? pointLabel(from) : "Unknown"} →{" "}
                          {to ? pointLabel(to) : "Unknown"}
                        </option>
                      );
                    })}
                  </select>
                </label>
              }
              <div className="form-grid">
                {fields.map((field) => {
                  const value = values[field.key];
                  const caption = `${field.label}${field.unit ? ` (${field.unit})` : ""}`;
                  const inputProps = {
                    "aria-label": caption,
                    disabled: !editable,
                    required:
                      reviewState === "REVIEWED" && Boolean(field.required),
                  };
                  return (
                    <label className="form-field" key={field.key}>
                      {caption}
                      {field.type === "boolean" || field.type === "bool" ? (
                        <select
                          {...inputProps}
                          value={value == null ? "" : String(value)}
                          onChange={(e) =>
                            setValue(
                              field.key,
                              e.target.value === ""
                                ? null
                                : e.target.value === "true",
                            )
                          }
                        >
                          <option value="">Unknown</option>
                          <option value="true">Explicitly confirmed</option>
                          <option value="false">
                            Explicitly not confirmed
                          </option>
                        </select>
                      ) : field.type === "point" ||
                        field.type === "point_id" ? (
                        <select
                          {...inputProps}
                          value={String(value ?? "")}
                          onChange={(e) =>
                            setValue(field.key, e.target.value || null)
                          }
                        >
                          <option value="">No accepted point mapping</option>
                          {pointOptions}
                        </select>
                      ) : field.options?.length ? (
                        <select
                          {...inputProps}
                          value={String(value ?? "")}
                          onChange={(e) =>
                            setValue(field.key, e.target.value || null)
                          }
                        >
                          <option value="">
                            Unknown — select only with evidence
                          </option>
                          {field.options.map((option) => (
                            <option
                              key={
                                typeof option === "string"
                                  ? option
                                  : option.value
                              }
                              value={
                                typeof option === "string"
                                  ? option
                                  : option.value
                              }
                            >
                              {typeof option === "string"
                                ? optionLabel(field.key, option)
                                : option.label}
                            </option>
                          ))}
                        </select>
                      ) : (
                        <input
                          {...inputProps}
                          value={String(value ?? "")}
                          maxLength={1000}
                          placeholder="Unknown — leave blank"
                          onChange={(e) =>
                            setValue(
                              field.key,
                              e.target.value === "" ? null : e.target.value,
                            )
                          }
                        />
                      )}
                    </label>
                  );
                })}
              </div>
              <label className="form-field">
                Component source evidence
                <textarea
                  aria-label="Component source evidence"
                  required
                  minLength={10}
                  maxLength={3000}
                  disabled={!editable}
                  value={evidence}
                  onChange={(e) => {
                    setEvidence(e.target.value);
                    setConfirmed(false);
                  }}
                  placeholder="Identify the actual source data and what remains unknown. A draft does not assert missing engineering facts."
                />
              </label>
              <label>
                <input
                  type="checkbox"
                  aria-label="Confirm component data record"
                  required
                  checked={confirmed}
                  disabled={!editable}
                  onChange={(e) => setConfirmed(e.target.checked)}
                />{" "}
                Save the stated draft or source review. Keep unknown values null
                and retain every independent CII readiness gate.
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
                  disabled={!editable || !confirmed}
                >
                  {busy ? (
                    <Loader2 size={15} className="spin" />
                  ) : (
                    <ClipboardCheck size={15} />
                  )}{" "}
                  Save component data
                </button>
              </div>
            </form>
          )}
          <details aria-label="CII component readiness blockers">
            <summary>
              Current component readiness blockers ({data.issues.length})
            </summary>
            {data.issues.map((issue, index) => (
              <p className="fine-print" key={index}>
                {typeof issue === "string"
                  ? issue
                  : `${issue.code}: ${issue.message}`}
              </p>
            ))}
          </details>
          {requirement && !supported && (
            <div className="notice amber">
              This source component needs a separately documented native
              representation. No native type, weight or geometry is inferred.
            </div>
          )}
          {(!requirement || !supported) && (
            <div className="modal-actions">
              <button className="button secondary" onClick={close}>
                Close
              </button>
            </div>
          )}
        </Dialog>
      )}
    </div>
  );
}
