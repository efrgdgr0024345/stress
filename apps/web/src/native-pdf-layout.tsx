import { useCallback, useEffect, useState } from "react";
import {
  CheckCircle2,
  Download,
  FileCheck2,
  Loader2,
  ScanEye,
} from "lucide-react";
import { api, label, pointLabel, type Project } from "./types";
import { appPath } from "./paths";
import { PDFPages } from "./pdf-preview";
import { Dialog } from "./ui";

type LayoutIssue = {
  code: string;
  message: string;
  sheet_id?: string;
  physical_point_id?: string;
  point_id?: string;
  object_key?: string;
};
type Placement = {
  group: string;
  role: string;
  type: string;
  rect?: number[];
  text?: string;
  physical_point_id?: string | null;
  material_id?: string | null;
};
type LayoutSheet = {
  sheet_id: string;
  page_index: number;
  source_sha256: string;
  protected_regions: unknown[];
  north_regions: unknown[];
  placements: Placement[];
  point_positions: {
    physical_point_id: string;
    anchor: number[];
    bubble: number[];
    requested_bubble: number[];
    leader_vertices: number[][];
  }[];
  axis: { origin: number[] } | null;
  schedule: { position: number[]; rect: number[] } | null;
  issues: LayoutIssue[];
};
type Accepted = {
  current: boolean;
  stale?: boolean;
  reviewed_by?: string;
  reviewed_at?: string;
  reason?: string;
  proposal_sha256?: string;
};
type LayoutReport = {
  revision: number;
  can_edit: boolean;
  accepted: Accepted | null;
  can_export?: boolean;
  proposal_sha256?: string;
  input_sha256?: string;
  sheets?: LayoutSheet[];
  issues?: LayoutIssue[];
  summary?: {
    point_instances: number;
    generated_objects: number;
    layout_exceptions: number;
    protected_regions: number;
  };
};

export function NativePDFLayoutControls({
  project,
  onUpdate,
  onInspect,
}: {
  project: Project;
  onUpdate: (project: Project) => void;
  onInspect: (pointId: string) => void;
}) {
  const path = `/projects/${project.id}/pdf-layout`;
  const [data, setData] = useState<LayoutReport | null>(null),
    [preview, setPreview] = useState<LayoutReport | null>(null);
  const [open, setOpen] = useState(false),
    [version, setVersion] = useState(project.version);
  const [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  const [reason, setReason] = useState(""),
    [confirmed, setConfirmed] = useState(false);
  const [visited, setVisited] = useState<number[]>([]),
    [pageCount, setPageCount] = useState(0);
  useEffect(() => {
    let active = true;
    api<LayoutReport>(path)
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
  const onPageRendered = useCallback((page: number, total: number) => {
    setVisited((current) =>
      current.includes(page) ? current : [...current, page],
    );
    setPageCount(total);
  }, []);
  const current =
    project.version === version &&
    data?.revision === version &&
    (!preview || preview.revision === version);
  const token = preview?.proposal_sha256;
  const query = `version=${version}${token ? `&proposal_sha256=${encodeURIComponent(token)}` : ""}`;
  const nativePath = appPath(`api/v1${path}/native.pdf?${query}`);
  const manifestPath = appPath(`api/v1${path}/manifest?${query}`);
  const accepted = Boolean(data?.accepted?.current);
  const name = (id: string) => {
    const point = project.nodes.find((n) => n.id === id);
    return point ? pointLabel(point) : "Unlocated source requirement";
  };
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
            setPreview(null);
            setReason("");
            setConfirmed(false);
            setVisited([]);
            setPageCount(0);
            setError("");
            setOpen(true);
          }}
        >
          <ScanEye size={16} /> Review native PDF layout
        </button>
        <span className="fine-print">
          {accepted
            ? "Graphical placement review current"
            : data?.accepted?.stale
              ? "Graphical placement review requires refresh"
              : "Graphical placement review required"}{" "}
          · source dimensions and engineering approval are separate
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
          title="Native PDF layout review"
          subtitle={`Revision ${version} · Whole-project editable annotation preview`}
          onClose={close}
        >
          <div
            className="notice"
            style={{ display: "block", color: "#37577d" }}
          >
            <b>Review the actual native PDF before recording its placement.</b>{" "}
            Source dimensions, materials and NORTH must stay clear. Proposed
            bubble, leader, triad and schedule positions are graphic coordinates
            only; they never supply physical XYZ, length or station.
            <p className="fine-print">
              Every added object remains an individual editable PDF annotation.
              Blue warnings and the engineering review draft notice remain
              visible. Graphical acceptance does not accept engineering facts or
              approve an issue.
            </p>
          </div>
          {!current && (
            <div className="notice amber" role="alert">
              The project changed. Close and reopen this dialog, then generate a
              current preview.
            </div>
          )}
          {error && (
            <div className="notice amber" role="alert">
              {error}
            </div>
          )}
          <div
            className="notice"
            style={{ display: "block", color: "#37577d" }}
            aria-label="Current graphical review state"
          >
            <b>
              {accepted
                ? "Graphical placement accepted for this source context"
                : data.accepted?.stale
                  ? "Previous graphical review is stale"
                  : "Graphical placement has not been accepted"}
            </b>
            {data.accepted?.reason && <p>{data.accepted.reason}</p>}
            {data.accepted?.reviewed_at && (
              <small>
                {data.accepted.reviewed_at} · {data.accepted.reviewed_by}
              </small>
            )}
          </div>
          <div className="review-actions">
            <button
              className="button primary"
              disabled={!data.can_edit || !current || busy}
              onClick={async () => {
                setBusy(true);
                setError("");
                setPreview(null);
                setVisited([]);
                setPageCount(0);
                setConfirmed(false);
                try {
                  const report = await api<LayoutReport>(`${path}/preview`, {
                    method: "POST",
                    body: JSON.stringify({ version, confirmed: true }),
                  });
                  setPreview(report);
                } catch (e) {
                  setError((e as Error).message);
                } finally {
                  setBusy(false);
                }
              }}
            >
              {busy ? (
                <Loader2 size={15} className="spin" />
              ) : (
                <FileCheck2 size={15} />
              )}{" "}
              Generate native layout preview
            </button>
            <span className="fine-print">
              Read-only proposal. The saved project stays unchanged until
              explicit acceptance.
            </span>
          </div>
          {preview && (
            <div aria-label="Native layout proposal">
              <h3>Proposed placement · not yet accepted</h3>
              <p>
                {preview.summary?.point_instances ?? 0} source point depictions
                · {preview.summary?.generated_objects ?? 0} individual additions
                · {preview.summary?.protected_regions ?? 0} protected source
                regions · {preview.summary?.layout_exceptions ?? 0} layout
                exceptions
              </p>
              <div
                className={`notice ${preview.can_export ? "" : "amber"}`}
                style={{ display: "block", color: "#37577d" }}
              >
                {preview.can_export
                  ? "Collision checks permit this draft preview. All engineering unknowns and blue reasons remain unresolved."
                  : "Resolve the typed layout exceptions before accepting or issuing these placements. Source objects were not hidden to force a fit."}
              </div>
              {token && preview.can_export && (
                <>
                  <PDFPages
                    key={`${version}:${token}`}
                    url={nativePath}
                    totalAdditions={preview.summary?.generated_objects}
                    onPageRendered={onPageRendered}
                  />
                  <div className="review-actions" style={{ marginTop: 12 }}>
                    <a
                      className="button secondary"
                      href={nativePath}
                      download="native-layout-review.pdf"
                    >
                      <Download size={15} /> Download native preview PDF
                    </a>
                    <a
                      className="button secondary"
                      href={manifestPath}
                      download="annotation-manifest.json"
                    >
                      Download annotation manifest
                    </a>
                  </div>
                  <p className="fine-print">
                    {visited.length} / {pageCount || project.sheets.length}{" "}
                    source sheets opened in this preview. Zoom in and pan to
                    inspect the individual added objects.
                  </p>
                </>
              )}
              <details aria-label="Native annotation placement inventory">
                <summary>Individual objects by source sheet</summary>
                {preview.sheets?.map((sheet) => (
                  <div key={sheet.sheet_id}>
                    <h4>
                      {project.sheets.find((s) => s.id === sheet.sheet_id)
                        ?.printed_id || `PDF page ${sheet.page_index + 1}`}
                    </h4>
                    <p className="fine-print">
                      {sheet.placements.length} additions ·{" "}
                      {sheet.protected_regions.length} protected regions ·{" "}
                      {sheet.point_positions.length} point depictions ·{" "}
                      {sheet.axis
                        ? "Axis / moments placed"
                        : "Axis placement unresolved"}{" "}
                      ·{" "}
                      {sheet.schedule
                        ? "Schedule placed"
                        : "Schedule placement unresolved"}
                    </p>
                    <div
                      className="results-table-scroll"
                      style={{ maxHeight: 200 }}
                    >
                      <table className="results-grid">
                        <thead>
                          <tr>
                            <th>Native role</th>
                            <th>Object type</th>
                            <th>Physical source point</th>
                            <th>Content</th>
                          </tr>
                        </thead>
                        <tbody>
                          {sheet.placements.map((object, index) => (
                            <tr key={`${object.group}:${object.role}:${index}`}>
                              <td>{label(object.role)}</td>
                              <td>{object.type}</td>
                              <td>
                                {object.physical_point_id
                                  ? name(object.physical_point_id)
                                  : "N/A"}
                              </td>
                              <td>{object.text || "Graphic annotation"}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                ))}
              </details>
              {Boolean(preview.issues?.length) && (
                <div
                  className="notice amber"
                  style={{ display: "block" }}
                  aria-label="Native layout exceptions"
                >
                  <b>Typed layout exceptions</b>
                  {preview.issues?.map((issue, index) => {
                    const id =
                      issue.physical_point_id ||
                      issue.point_id ||
                      issue.object_key?.split(":").pop();
                    const point = project.nodes.find((node) => node.id === id);
                    return (
                      <p key={`${issue.code}:${index}`}>
                        <span className="badge blue">{issue.code}</span>{" "}
                        {issue.message}{" "}
                        {point && (
                          <button
                            type="button"
                            className="button secondary"
                            disabled={busy}
                            onClick={() => {
                              close();
                              onInspect(point.id);
                            }}
                          >
                            Inspect source {name(point.id)}
                          </button>
                        )}
                      </p>
                    );
                  })}
                </div>
              )}
              <form
                onSubmit={async (event) => {
                  event.preventDefault();
                  if (!token) return;
                  setBusy(true);
                  setError("");
                  try {
                    const updated = await api<Project>(`${path}/accept`, {
                      method: "POST",
                      body: JSON.stringify({
                        version,
                        proposal_sha256: token,
                        reason,
                        confirmed: true,
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
                <label className="form-field">
                  Graphical layout review evidence
                  <textarea
                    aria-label="Graphical layout review evidence"
                    required
                    minLength={10}
                    maxLength={3000}
                    disabled={busy || !current || !data.can_edit}
                    value={reason}
                    onChange={(e) => {
                      setReason(e.target.value);
                      setConfirmed(false);
                    }}
                    placeholder="Record clearance review of source dimensions, NORTH, bubbles/leaders, axis/moment labels and both sheet schedules. Physical data stays unchanged."
                  />
                </label>
                <label>
                  <input
                    type="checkbox"
                    aria-label="Confirm graphical placement review only"
                    required
                    disabled={
                      busy ||
                      !current ||
                      !data.can_edit ||
                      !preview.can_export ||
                      !pageCount ||
                      visited.length !== pageCount
                    }
                    checked={confirmed}
                    onChange={(e) => setConfirmed(e.target.checked)}
                  />{" "}
                  I reviewed every source sheet in this native preview. Accept
                  graphic placements only; retain all blue reasons and
                  engineering draft status.
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
                      busy ||
                      !current ||
                      !data.can_edit ||
                      !preview.can_export ||
                      !token ||
                      !confirmed
                    }
                  >
                    <CheckCircle2 size={15} /> Accept graphical placements
                  </button>
                </div>
              </form>
            </div>
          )}
          {!preview && (
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
