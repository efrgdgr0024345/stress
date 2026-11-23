import { appPath } from "./paths";
import { useEffect, useRef, useState } from "react";
import * as pdfjs from "pdfjs-dist";
import workerUrl from "pdfjs-dist/build/pdf.worker.min.mjs?url";
import {
  ArrowDownToLine,
  ArrowLeft,
  Check,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  CircleHelp,
  Crosshair,
  FileText,
  GitBranch,
  Hand,
  Link2,
  List,
  Loader2,
  Maximize2,
  MousePointer2,
  Move,
  Plus,
  RotateCcw,
  Route,
  Save,
  Settings2,
  StickyNote,
  Trash2,
  X,
  ZoomIn,
  ZoomOut,
} from "lucide-react";
import {
  type Project,
  type Sheet,
  type PipeNode,
  type NodeInstance,
  type Point,
  label,
  api,
  type DrawingNote,
} from "./types";
import { DrawingNotes } from "./drawing-notes";
import type { SourceFeature } from "./pipeline";

pdfjs.GlobalWorkerOptions.workerSrc = workerUrl;
type Mutation = (
  path: string,
  body: unknown,
  method?: string,
) => Promise<Project | undefined>;
type Draft = Omit<PipeNode, "id" | "number" | "reasons" | "support_gap_mm"> & {
  id?: string;
  number?: number;
  dimension: string;
  _version?: number;
};
type Mode = "select" | "pan" | "add" | "link" | "axis" | "table" | "route";
export function DrawingEditor({
  project,
  sheet,
  activeSheet,
  onSheet,
  selected,
  onSelect,
  mutation,
  busy,
  notify,
  evidenceRegion,
}: {
  project: Project;
  sheet: Sheet;
  activeSheet: number;
  onSheet: (i: number) => void;
  selected: string | null;
  onSelect: (id: string | null) => void;
  mutation: Mutation;
  busy: boolean;
  notify: (m: string, e?: boolean) => void;
  evidenceRegion?: number[] | null;
}) {
  const [pdfPage, setPdfPage] = useState<pdfjs.PDFPageProxy | null>(null),
    [error, setError] = useState(""),
    [loading, setLoading] = useState(true);
  const [zoom, setZoom] = useState(1),
    [fitWidth, setFitWidth] = useState(800),
    [mode, setMode] = useState<Mode>("select"),
    [draft, setDraft] = useState<Draft | null>(null),
    [dirty, setDirty] = useState(false);
  const [showLabels, setShowLabels] = useState(true),
    [showRoutes, setShowRoutes] = useState(false),
    [showFeatures, setShowFeatures] = useState(true),
    [nodeQuery, setNodeQuery] = useState(""),
    [inspectorTab, setInspectorTab] = useState<"point" | "source" | "features">(
      "point",
    ),
    [linkId, setLinkId] = useState("");
  const [routeStart, setRouteStart] = useState<number | null>(null);
  const previousSelection = useRef(selected);
  useEffect(() => {
    setRouteStart(null);
    setMode("select");
  }, [sheet.id]);
  const sourceGraph = project.automation?.graph_proposals?.find(
    (g) => g.sheet_id === sheet.id,
  );
  const sourceFeatures = (project.automation?.feature_proposals || []).filter(
    (feature) => feature.sheet_id === sheet.id,
  );
  const [notesOpen, setNotesOpen] = useState(false),
    [editingNote, setEditingNote] = useState<DrawingNote | undefined>();
  const [scheduleLines, setScheduleLines] = useState<string[]>([]);
  useEffect(() => {
    api<Record<string, string[]>>(`/projects/${project.id}/schedules`)
      .then((v) => setScheduleLines(v[sheet.id] || []))
      .catch((e) => notify(e.message, true));
  }, [project.version, sheet.id]);
  const canvas = useRef<HTMLCanvasElement>(null),
    scroller = useRef<HTMLDivElement>(null),
    svg = useRef<SVGSVGElement>(null);
  const drag = useRef<{ what: "anchor" | "bubble"; pointer: number } | null>(
      null,
    ),
    pan = useRef<{ x: number; y: number; sx: number; sy: number } | null>(null);
  useEffect(() => {
    let alive = true;
    setLoading(true);
    setError("");
    setPdfPage(null);
    const task = pdfjs.getDocument({
      url: appPath(`api/v1/projects/${project.id}/sources/${sheet.source_id}`),
      withCredentials: true,
      isEvalSupported: false,
    });
    task.promise
      .then((doc) => doc.getPage(sheet.page_index + 1))
      .then((p) => {
        if (alive) {
          setPdfPage(p);
          setLoading(false);
        }
      })
      .catch((e) => {
        if (alive) {
          setError(`PDF preview could not load: ${e.message}`);
          setLoading(false);
        }
      });
    return () => {
      alive = false;
      task.destroy();
    };
  }, [project.id, sheet.id]);
  useEffect(() => {
    if (!scroller.current) return;
    const observer = new ResizeObserver((entries) =>
      setFitWidth(Math.max(250, entries[0].contentRect.width - 56)),
    );
    observer.observe(scroller.current);
    return () => observer.disconnect();
  }, []);
  const viewport = pdfPage?.getViewport({ scale: 1 });
  const width = viewport?.width || sheet.width,
    height = viewport?.height || sheet.height;
  const scale = (fitWidth / width) * zoom;
  useEffect(() => {
    if (!pdfPage || !canvas.current) return;
    const ratio = Math.min(window.devicePixelRatio || 1, 2);
    const renderViewport = pdfPage.getViewport({ scale: scale * ratio });
    const c = canvas.current;
    c.width = renderViewport.width;
    c.height = renderViewport.height;
    const task = pdfPage.render({
      canvasContext: c.getContext("2d")!,
      viewport: renderViewport,
    });
    task.promise.catch((e) => {
      if (e.name !== "RenderingCancelledException") setError(e.message);
    });
    return () => task.cancel();
  }, [pdfPage, scale]);
  useEffect(() => {
    if (dirty && previousSelection.current === selected) return;
    previousSelection.current = selected;
    const node = project.nodes.find((n) => n.id === selected);
    if (node) {
      setDraft({
        ...structuredClone(node),
        _version: project.version,
        dimension:
          node.dimension_input ||
          (node.station_mm === null ? "" : `${node.station_mm} mm`),
      });
      setInspectorTab("point");
    } else {
      setDraft(null);
    }
    setDirty(false);
  }, [selected, project.version]);
  const map = ([x, y]: Point): Point => {
    if (!pdfPage || !viewport) return [x, y];
    return viewport.convertToViewportPoint(
      pdfPage.view[0] + x,
      pdfPage.view[3] - y,
    ) as Point;
  };
  const unmap = (x: number, y: number): Point => {
    if (!pdfPage || !viewport) return [x, y];
    const p = viewport.convertToPdfPoint(x, y);
    return [p[0] - pdfPage.view[0], pdfPage.view[3] - p[1]];
  };
  const eventPoint = (e: React.PointerEvent): Point => {
    const rect = svg.current!.getBoundingClientRect();
    return unmap(
      ((e.clientX - rect.left) / rect.width) * width,
      ((e.clientY - rect.top) / rect.height) * height,
    );
  };
  const clamp = ([x, y]: Point): Point => [
    Math.max(14, Math.min(sheet.width - 14, x)),
    Math.max(14, Math.min(sheet.height - 14, y)),
  ];
  const current = project.nodes.find((n) => n.id === selected);
  useEffect(() => {
    if (!dirty) return;
    const warn = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);
  const nodes = project.nodes.filter((n) =>
    n.instances.some((v) => v.sheet_id === sheet.id),
  );
  const scheduleRows = project.materials.filter(
    (m) => m.sheet_id === sheet.id && ["valve", "flange"].includes(m.family),
  );
  const patch = (changes: Partial<Draft>) => {
    setDraft((d) => (d ? { ...d, ...changes } : null));
    setDirty(true);
  };
  const proposeFeature = (
    feature: SourceFeature,
    role: "flange_face" | "opposite_pipe_dot",
  ) => {
    if (busy) return;
    if (dirty && !confirm("Discard unsaved point changes?")) return;
    const reference = `Source feature ${feature.id}/${role}`;
    const existing = project.nodes.find(
      (n) =>
        (n.source_feature_id === feature.id &&
          n.source_feature_role === role) ||
        n.source_feature_links?.some(
          (r) => r.id === feature.id && r.role === role,
        ),
    );
    if (existing) {
      onSelect(existing.id);
      setInspectorTab("point");
      return;
    }
    const anchor = feature[role];
    previousSelection.current = null;
    onSelect(null);
    setDraft({
      _version: project.version,
      line_id: sheet.line_id,
      route: "main",
      order:
        Math.max(
          0,
          ...project.nodes
            .filter((n) => n.line_id === sheet.line_id && n.route === "main")
            .map((n) => n.order),
        ) + 1,
      kind: "flange",
      station_mm: null,
      dimension: "",
      evidence: `${reference}. Unreviewed graphical ${role.replaceAll("_", " ")} proposal (${feature.profile}); source ${feature.source_sha256}. Confirm material identity, route/order and dimensional evidence.`,
      source_feature_id: feature.id,
      source_feature_role: role,
      instances: [
        {
          sheet_id: sheet.id,
          anchor: [...anchor],
          bubble: clamp([anchor[0] + 35, anchor[1] - 35]),
        },
      ],
    });
    setDirty(true);
    setMode("select");
    setShowLabels(true);
    setInspectorTab("point");
    notify(
      "Source location prepared. Check the route and order before saving; physical station is unknown.",
    );
  };
  const clickDrawing = async (e: React.PointerEvent) => {
    if (drag.current || mode === "pan" || mode === "route") return;
    const anchor = clamp(eventPoint(e));
    if (mode === "add") {
      onSelect(null);
      setDraft({
        _version: project.version,
        line_id: sheet.line_id,
        route: "main",
        order:
          Math.max(
            0,
            ...project.nodes
              .filter((n) => n.route === "main")
              .map((n) => n.order),
          ) + 1,
        kind: "endpoint",
        station_mm: null,
        evidence: "",
        dimension: "",
        instances: [
          {
            sheet_id: sheet.id,
            anchor,
            bubble: clamp([anchor[0] + 30, anchor[1] - 30]),
          },
        ],
      });
      setDirty(true);
      setMode("select");
      setInspectorTab("point");
    } else if (mode === "link") {
      const n = project.nodes.find((n) => n.id === linkId);
      if (!n) {
        notify("Choose an existing physical point to link.", true);
        return;
      }
      if (n.instances.some((v) => v.sheet_id === sheet.id)) {
        notify("This point already appears on this sheet.", true);
        return;
      }
      onSelect(n.id);
      setTimeout(() => {
        setDraft({
          ...structuredClone(n),
          dimension:
            n.dimension_input ||
            (n.station_mm === null ? "" : `${n.station_mm} mm`),
          instances: [
            ...structuredClone(n.instances),
            {
              sheet_id: sheet.id,
              anchor,
              bubble: clamp([anchor[0] + 30, anchor[1] - 30]),
            },
          ],
        });
        setDirty(true);
      }, 0);
      setMode("select");
    } else if (mode === "axis" || mode === "table") {
      const pos: Point = [
        Math.max(
          50,
          Math.min(sheet.width - (mode === "table" ? 390 : 80), anchor[0]),
        ),
        Math.max(60, Math.min(sheet.height - 130, anchor[1])),
      ];
      const p = await mutation(
        `/sheets/${sheet.id}`,
        {
          version: project.version,
          printed_id: sheet.printed_id,
          line_id: sheet.line_id,
          axis: mode === "axis" ? pos : sheet.axis,
          table: mode === "table" ? pos : sheet.table,
        },
        "PATCH",
      );
      if (p)
        notify(
          `${mode === "axis" ? "Local axis triad" : "Component schedule"} placed. Inspect clearance before export.`,
        );
      setMode("select");
    } else if (e.target === svg.current) {
      onSelect(null);
      setDraft(null);
      setDirty(false);
    }
  };
  const startDrag = (
    e: React.PointerEvent,
    node: PipeNode,
    what: "anchor" | "bubble",
  ) => {
    if (mode !== "select") return;
    e.stopPropagation();
    onSelect(node.id);
    if (selected !== node.id)
      setDraft({
        ...structuredClone(node),
        dimension:
          node.dimension_input ||
          (node.station_mm === null ? "" : `${node.station_mm} mm`),
      });
    drag.current = { what, pointer: e.pointerId };
    svg.current?.setPointerCapture(e.pointerId);
  };
  const pointerMove = (e: React.PointerEvent) => {
    if (!drag.current) return;
    const point = clamp(eventPoint(e));
    setDraft((d) =>
      d
        ? {
            ...d,
            instances: d.instances.map((v) =>
              v.sheet_id === sheet.id
                ? { ...v, [drag.current!.what]: point }
                : v,
            ),
          }
        : d,
    );
    setDirty(true);
  };
  const save = async () => {
    if (!draft) return;
    const body = {
      version: draft._version ?? project.version,
      line_id: draft.line_id,
      route: draft.route,
      takeoff_id: draft.takeoff_id || null,
      order: draft.order,
      kind: draft.kind,
      dimension: draft.dimension,
      evidence: draft.evidence,
      source_feature_id: draft.source_feature_id,
      source_feature_role: draft.source_feature_role,
      instances: draft.instances,
    };
    const p = await mutation(
      `/nodes${draft.id ? "/" + draft.id : ""}`,
      body,
      draft.id ? "PATCH" : "POST",
    );
    if (p) {
      const id = draft.id || p.nodes[p.nodes.length - 1].id;
      onSelect(id);
      setDirty(false);
      notify("Point saved. Engineering reasons and route numbering updated.");
    }
  };
  const deletePoint = async () => {
    if (!draft?.id) return;
    if (
      !window.confirm(
        `Delete physical point ${draft.number} and all its sheet representations?`,
      )
    )
      return;
    const p = await mutation(
      `/nodes/${draft.id}?version=${project.version}`,
      undefined,
      "DELETE",
    );
    if (p) {
      onSelect(null);
      setDraft(null);
      notify("Physical point deleted and routes renumbered.");
    }
  };
  const displayNodes = [
    ...nodes.filter((n) => n.id !== draft?.id),
    ...(draft
      ? ([
          {
            ...draft,
            id: draft.id || "new",
            number: draft.number || "?",
            reasons:
              draft.dimension && draft.evidence
                ? current?.reasons || []
                : ["UNVERIFIED_DIMENSION"],
          },
        ] as unknown as PipeNode[])
      : []),
  ].filter((n) => n.instances.some((v) => v.sheet_id === sheet.id));
  const glyph = (n: PipeNode) => {
    const inst = n.instances.find((v) => v.sheet_id === sheet.id)!;
    const a = map(inst.anchor),
      b = map(inst.bubble),
      color = n.reasons.length ? "#3264c9" : "#cb4242";
    const isSelected = n.id === selected || n.id === "new";
    return (
      <g
        key={n.id}
        className={`node-glyph ${isSelected ? "is-selected" : ""}`}
        style={{ color }}
      >
        <line
          x1={a[0]}
          y1={a[1]}
          x2={b[0]}
          y2={b[1]}
          stroke={color}
          strokeWidth={1.2}
        />
        <circle
          cx={a[0]}
          cy={a[1]}
          r={isSelected ? 5 : 2.5}
          fill={color}
          stroke="white"
          strokeWidth={1}
          className="anchor-handle"
          onPointerDown={(e) => startDrag(e, n, "anchor")}
        />
        <g
          className="bubble-handle"
          onPointerDown={(e) => startDrag(e, n, "bubble")}
          onClick={(e) => e.stopPropagation()}
        >
          <circle
            cx={b[0]}
            cy={b[1]}
            r={isSelected ? 16 : 12}
            fill={isSelected ? "#f0f7f1" : "#fff"}
            stroke={color}
            strokeWidth={isSelected ? 2 : 1}
          />
          <text
            x={b[0]}
            y={b[1] + 3}
            transform={`rotate(${sheet.rotation},${b[0]},${b[1]})`}
            textAnchor="middle"
            fill={color}
            fontSize={8}
            fontFamily="Arial, sans-serif"
          >
            {n.number}
          </text>
        </g>
        {isSelected && (
          <circle
            cx={b[0]}
            cy={b[1]}
            r={21}
            fill="none"
            stroke={color}
            strokeWidth={0.6}
            strokeDasharray="2 3"
            pointerEvents="none"
          />
        )}
      </g>
    );
  };
  return (
    <div className="drawing-workspace">
      <div className="drawing-main">
        <div className="drawing-toolbar">
          <div className="sheet-picker">
            <FileText size={16} />
            <select
              aria-label="Active sheet"
              value={activeSheet}
              onChange={(e) => {
                if (dirty && !confirm("Discard unsaved point changes?")) return;
                onSheet(+e.target.value);
                onSelect(null);
                setDraft(null);
                setDirty(false);
              }}
            >
              {project.sheets.map((s, i) => (
                <option key={s.id} value={i}>
                  {s.printed_id || `Sheet ${i + 1}`} · Page {s.page_index + 1}
                </option>
              ))}
            </select>
            <ChevronDown size={13} />
          </div>
          <div className="toolbar-actions">
            <button
              className={`tool ${showLabels ? "chosen" : ""}`}
              title="Toggle node overlay"
              aria-label="Toggle node overlay"
              onClick={() => setShowLabels(!showLabels)}
            >
              <GitBranch size={17} />
            </button>
            <button
              className={`tool ${showRoutes ? "chosen" : ""}`}
              aria-label="Toggle model route connections"
              title="Show entered route order (presentation only)"
              onClick={() => setShowRoutes(!showRoutes)}
            >
              <Route size={17} />
            </button>
            {!!sourceFeatures.length && (
              <button
                className={`tool ${showFeatures ? "chosen" : ""}`}
                aria-label="Toggle detected flange locations"
                title="Show proposed flange faces and separate pipe dots"
                onClick={() => setShowFeatures(!showFeatures)}
              >
                <Crosshair size={17} />
              </button>
            )}
            <span className="toolbar-divider" />
            <button
              className={`tool ${mode === "select" ? "chosen" : ""}`}
              title="Select and edit"
              aria-label="Select and edit"
              onClick={() => setMode("select")}
            >
              <MousePointer2 size={17} />
            </button>
            <button
              className={`tool ${mode === "pan" ? "chosen" : ""}`}
              title="Pan drawing"
              aria-label="Pan drawing"
              onClick={() => setMode("pan")}
            >
              <Hand size={17} />
            </button>
            <span className="toolbar-divider" />
            {!!sourceGraph?.vertices.length && (
              <button
                className={`tool ${mode === "route" ? "chosen" : ""}`}
                aria-label="Choose source route"
                title="Select main route start and end from source linework"
                disabled={busy || dirty}
                onClick={() => {
                  setMode(mode === "route" ? "select" : "route");
                  setRouteStart(null);
                  notify(
                    "Choose the main route start, then its end. Proposed stations remain unverified.",
                  );
                }}
              >
                <Route size={17} />
              </button>
            )}
            <button
              className={`button compact ${mode === "add" ? "primary" : "secondary"}`}
              disabled={busy}
              onClick={() => {
                if (dirty && !confirm("Discard unsaved point changes?")) return;
                onSelect(null);
                setDraft(null);
                setDirty(false);
                setMode(mode === "add" ? "select" : "add");
                setShowLabels(true);
              }}
            >
              <Plus size={15} />
              Add point
            </button>
            <div className="layout-menu">
              <button
                className="tool"
                aria-label="Drawing annotations"
                disabled={busy}
                title="Edit drawing notes and graphic objects"
                onClick={() => {
                  setEditingNote(undefined);
                  setNotesOpen(true);
                }}
              >
                <StickyNote size={17} />
              </button>
              <button
                className="tool"
                aria-label="Layout tools"
                disabled={busy}
                title="Place axis or schedule"
                onClick={() => setMode(mode === "axis" ? "table" : "axis")}
              >
                <Settings2 size={17} />
              </button>
            </div>
          </div>
        </div>
        {(mode === "add" ||
          mode === "axis" ||
          mode === "table" ||
          mode === "link") && (
          <div className="placement-banner">
            <Crosshair size={16} />
            <span>
              {mode === "add"
                ? "Click a drawing feature to place a provisional physical point."
                : mode === "axis"
                  ? "Click a clear area to place the editable local axis triad."
                  : mode === "table"
                    ? "Click a clear area to place the editable component schedule."
                    : "Select a physical point, then click its depiction on this sheet."}
            </span>
            {mode === "axis" && (
              <button onClick={() => setMode("table")}>
                Place schedule instead
              </button>
            )}
            {mode === "link" && (
              <select
                aria-label="Point to link"
                value={linkId}
                onChange={(e) => setLinkId(e.target.value)}
              >
                <option value="">Choose point</option>
                {project.nodes
                  .filter(
                    (n) => !n.instances.some((v) => v.sheet_id === sheet.id),
                  )
                  .map((n) => (
                    <option value={n.id} key={n.id}>
                      Node {n.number} · {n.kind}
                    </option>
                  ))}
              </select>
            )}
            <button
              className="icon-button"
              aria-label="Cancel placement"
              onClick={() => setMode("select")}
            >
              <X size={15} />
            </button>
          </div>
        )}
        <div
          className={`drawing-scroller ${mode === "pan" ? "pan-mode" : ""}`}
          ref={scroller}
          onPointerDown={(e) => {
            if (mode === "pan" && scroller.current) {
              pan.current = {
                x: e.clientX,
                y: e.clientY,
                sx: scroller.current.scrollLeft,
                sy: scroller.current.scrollTop,
              };
              e.currentTarget.setPointerCapture(e.pointerId);
            }
          }}
          onPointerMove={(e) => {
            if (pan.current && scroller.current) {
              scroller.current.scrollLeft =
                pan.current.sx - e.clientX + pan.current.x;
              scroller.current.scrollTop =
                pan.current.sy - e.clientY + pan.current.y;
            }
          }}
          onPointerUp={() => (pan.current = null)}
        >
          {loading && (
            <div className="drawing-loading">
              <Loader2 className="spin" size={22} />
              <span>Rendering original PDF…</span>
            </div>
          )}
          {error && <div className="notice amber">{error}</div>}
          <div
            className="paper"
            style={{
              width: width * scale,
              height: height * scale,
              visibility: loading ? "hidden" : "visible",
            }}
          >
            <canvas ref={canvas} style={{ width: "100%", height: "100%" }} />
            <svg
              ref={svg}
              viewBox={`0 0 ${width} ${height}`}
              className={`drawing-overlay mode-${mode}`}
              onPointerDown={clickDrawing}
              onPointerMove={pointerMove}
              onPointerUp={(e) => {
                drag.current = null;
                if (svg.current?.hasPointerCapture(e.pointerId))
                  svg.current.releasePointerCapture(e.pointerId);
              }}
              onPointerCancel={() => (drag.current = null)}
            >
              {showFeatures &&
                sourceFeatures.map((feature, index) => {
                  const a = map(feature.flange_face),
                    b = map(feature.opposite_pipe_dot);
                  return (
                    <g
                      key={feature.id}
                      className="source-feature"
                      data-feature={feature.id}
                    >
                      <line
                        x1={a[0]}
                        y1={a[1]}
                        x2={b[0]}
                        y2={b[1]}
                        stroke="#007aff"
                        strokeWidth={1.5}
                        strokeDasharray="3 3"
                        pointerEvents="none"
                      />
                      {(["flange_face", "opposite_pipe_dot"] as const).map(
                        (role) => {
                          const [x, y] = map(feature[role]);
                          return (
                            <circle
                              key={role}
                              data-feature-role={role}
                              cx={x}
                              cy={y}
                              r={5}
                              fill={
                                role === "flange_face" ? "#fff" : "#007aff55"
                              }
                              stroke="#007aff"
                              strokeWidth={1.5}
                              role="button"
                              tabIndex={busy ? -1 : 0}
                              style={{ cursor: "pointer" }}
                              aria-label={`Flange proposal ${index + 1} ${role.replaceAll("_", " ")}`}
                              onPointerDown={(e) => {
                                e.stopPropagation();
                                proposeFeature(feature, role);
                              }}
                              onKeyDown={(e) => {
                                if (e.key === "Enter" || e.key === " ") {
                                  e.preventDefault();
                                  proposeFeature(feature, role);
                                }
                              }}
                            >
                              <title>{`Proposed ${role.replaceAll("_", " ")} · inspect source before use`}</title>
                            </circle>
                          );
                        },
                      )}
                    </g>
                  );
                })}
              {mode === "route" && sourceGraph && (
                <g className="source-route-candidates">
                  {sourceGraph.edges.map(([a, b], i) => {
                    const p = map(sourceGraph.vertices[a]),
                      q = map(sourceGraph.vertices[b]);
                    return (
                      <line
                        key={i}
                        x1={p[0]}
                        y1={p[1]}
                        x2={q[0]}
                        y2={q[1]}
                        stroke="#35a1d8"
                        strokeWidth={3}
                        strokeDasharray="6 4"
                        pointerEvents="none"
                      />
                    );
                  })}
                  {sourceGraph.vertices.map((vertex, i) => {
                    const [x, y] = map(vertex);
                    return (
                      <circle
                        key={i}
                        className="source-route-vertex"
                        data-vertex={i}
                        cx={x}
                        cy={y}
                        r={7}
                        fill={routeStart === i ? "#ffc14f" : "#fff"}
                        stroke="#198bdd"
                        strokeWidth={2}
                        style={{ cursor: "pointer" }}
                        onPointerDown={async (e) => {
                          e.stopPropagation();
                          if (routeStart === null) {
                            setRouteStart(i);
                            notify("Start chosen. Select the main route end.");
                          } else {
                            const p = await mutation("/pipeline/route", {
                              version: project.version,
                              sheet_id: sheet.id,
                              start: routeStart,
                              end: i,
                            });
                            if (p) {
                              setMode("select");
                              setRouteStart(null);
                              notify(
                                "Main and simple branches proposed. Review physical evidence; the draft refreshes automatically.",
                              );
                            }
                          }
                        }}
                      >
                        <title>
                          {routeStart === null
                            ? "Choose main route start"
                            : "Choose main route end"}
                        </title>
                      </circle>
                    );
                  })}
                </g>
              )}
              {evidenceRegion && evidenceRegion.length === 4 && (
                <polygon
                  points={[
                    [evidenceRegion[0], evidenceRegion[1]],
                    [evidenceRegion[2], evidenceRegion[1]],
                    [evidenceRegion[2], evidenceRegion[3]],
                    [evidenceRegion[0], evidenceRegion[3]],
                  ]
                    .map((p) => map(p as Point).join(","))
                    .join(" ")}
                  fill="#ffc35522"
                  stroke="#d9992d"
                  strokeWidth={2}
                  strokeDasharray="6 4"
                  pointerEvents="none"
                >
                  <title>Selected source evidence</title>
                </polygon>
              )}
              {showRoutes &&
                project.graph?.edges.map((edge) => {
                  const a = displayNodes
                    .find((n) => n.id === edge.from)
                    ?.instances.find((i) => i.sheet_id === sheet.id);
                  const b = displayNodes
                    .find((n) => n.id === edge.to)
                    ?.instances.find((i) => i.sheet_id === sheet.id);
                  if (!a || !b) return null;
                  const aa = map(a.anchor),
                    bb = map(b.anchor);
                  return (
                    <line
                      key={`${edge.from}-${edge.to}`}
                      className="route-connection"
                      x1={aa[0]}
                      y1={aa[1]}
                      x2={bb[0]}
                      y2={bb[1]}
                      stroke={edge.route === "main" ? "#74916b" : "#ae976c"}
                      strokeWidth={2}
                      strokeDasharray="5 4"
                      opacity={0.7}
                      pointerEvents="none"
                    />
                  );
                })}
              {showLabels && displayNodes.map(glyph)}
              {(project.annotations || [])
                .filter((n) => n.sheet_id === sheet.id)
                .map((note) => {
                  const [x1, y1, x2, y2] = note.rect,
                    a = map([x1, y1]),
                    b = map([x2, y2]);
                  return (
                    <g
                      className="free-annotation"
                      key={note.id}
                      onClick={(e) => {
                        e.stopPropagation();
                        setEditingNote(note);
                        setNotesOpen(true);
                      }}
                      style={{ cursor: "pointer" }}
                    >
                      {note.kind === "Line" ? (
                        <line
                          x1={a[0]}
                          y1={a[1]}
                          x2={b[0]}
                          y2={b[1]}
                          stroke={note.color}
                          strokeWidth={2}
                        />
                      ) : (
                        <g
                          transform={`translate(${a.join(",")}) rotate(${sheet.rotation})`}
                        >
                          {note.kind === "Circle" ? (
                            <ellipse
                              cx={(x2 - x1) / 2}
                              cy={(y2 - y1) / 2}
                              rx={(x2 - x1) / 2}
                              ry={(y2 - y1) / 2}
                              fill="transparent"
                              stroke={note.color}
                            />
                          ) : note.kind === "Square" ? (
                            <rect
                              width={x2 - x1}
                              height={y2 - y1}
                              fill="transparent"
                              stroke={note.color}
                            />
                          ) : (
                            <foreignObject width={x2 - x1} height={y2 - y1}>
                              <div
                                style={{
                                  font: "10px/1.2 Arial",
                                  whiteSpace: "pre-wrap",
                                  overflowWrap: "anywhere",
                                  padding: 2,
                                  color: note.color,
                                  lineHeight: "12px",
                                  border: `1px dashed ${note.color}44`,
                                  height: "100%",
                                }}
                              >
                                {note.text}
                              </div>
                            </foreignObject>
                          )}
                        </g>
                      )}
                    </g>
                  );
                })}
              {sheet.axis && showLabels && (
                <g className="axis-overlay" pointerEvents="none">
                  {[
                    ["X / +Mx", 36, 20],
                    ["Y / +My", -30, 20],
                    ["Z / +Mz", 0, -35],
                  ].map(([text, dx, dy]) => {
                    const a = map(sheet.axis!),
                      b = map([
                        sheet.axis![0] + Number(dx),
                        sheet.axis![1] + Number(dy),
                      ]),
                      t = map([
                        sheet.axis![0] + Number(dx) - 10,
                        sheet.axis![1] + Number(dy) - 4,
                      ]);
                    return (
                      <g key={String(text)}>
                        <line
                          x1={a[0]}
                          y1={a[1]}
                          x2={b[0]}
                          y2={b[1]}
                          stroke="#cb4242"
                          strokeWidth={1}
                        />
                        <text
                          x={t[0]}
                          y={t[1]}
                          transform={`rotate(${sheet.rotation},${t[0]},${t[1]})`}
                          fontSize={7}
                          fill="#cb4242"
                        >
                          {text}
                        </text>
                      </g>
                    );
                  })}
                </g>
              )}
              {sheet.table && showLabels && scheduleRows.length > 0 && (
                <g
                  transform={`translate(${map(sheet.table).join(",")}) rotate(${sheet.rotation})`}
                  pointerEvents="none"
                >
                  <rect
                    width={Math.min(370, sheet.width - sheet.table[0] - 8)}
                    height={scheduleLines.length * 15 + 8}
                    fill="#fff"
                    fillOpacity={0.94}
                    stroke="#cb4242"
                    strokeWidth={0.6}
                  />
                  {scheduleLines.map((text, i) => (
                    <text
                      key={i}
                      x={5}
                      y={12 + i * 15}
                      fontSize={6.5}
                      fill="#cb4242"
                    >
                      {text}
                    </text>
                  ))}
                </g>
              )}
            </svg>
          </div>
        </div>
        <div className="drawing-bottom">
          <div className="drawing-legend">
            <span>
              <i className="red" />
              Evidence recorded
            </span>
            <span>
              <i className="blue" />
              Engineering review
            </span>
          </div>
          <div className="zoom-tools">
            <button
              className="tool"
              aria-label="Zoom out"
              onClick={() => setZoom((z) => Math.max(0.4, z - 0.2))}
            >
              <ZoomOut size={16} />
            </button>
            <span>{Math.round(scale * 100)}%</span>
            <button
              className="tool"
              aria-label="Zoom in"
              onClick={() => setZoom((z) => Math.min(3, z + 0.2))}
            >
              <ZoomIn size={16} />
            </button>
            <button
              className="tool"
              aria-label="Fit drawing"
              onClick={() => setZoom(1)}
            >
              <Maximize2 size={15} />
            </button>
            <span className="toolbar-divider" />
            <button
              className="tool"
              aria-label="Previous sheet"
              disabled={!activeSheet}
              onClick={() => onSheet(activeSheet - 1)}
            >
              <ChevronLeft size={16} />
            </button>
            <span>
              {activeSheet + 1} / {project.sheets.length}
            </span>
            <button
              className="tool"
              aria-label="Next sheet"
              disabled={activeSheet === project.sheets.length - 1}
              onClick={() => onSheet(activeSheet + 1)}
            >
              <ChevronRight size={16} />
            </button>
          </div>
        </div>
        <div className="coordinate-notice">
          <ShieldIcon />
          <span>
            Graphic coordinates are presentation only. Physical stations require
            independent dimensional evidence.
          </span>
          {project.sample && <b>SYNTHETIC SOURCE</b>}
        </div>
      </div>
      <aside className="inspector">
        {dirty &&
          draft?._version !== undefined &&
          draft._version !== project.version && (
            <div className="notice amber">
              <span>
                The project updated. Your unsaved values are retained.
                <button
                  className="text-button"
                  onClick={() => {
                    if (current)
                      setDraft({
                        ...structuredClone(current),
                        _version: project.version,
                        dimension:
                          current.dimension_input ||
                          (current.station_mm === null
                            ? ""
                            : `${current.station_mm} mm`),
                      });
                    else setDraft(null);
                    setDirty(false);
                  }}
                >
                  Discard edits and reload
                </button>
              </span>
            </div>
          )}
        <div className="inspector-tabs">
          <button
            className={inspectorTab === "point" ? "selected" : ""}
            onClick={() => setInspectorTab("point")}
          >
            Point inspector
          </button>
          <button
            className={inspectorTab === "source" ? "selected" : ""}
            onClick={() => setInspectorTab("source")}
          >
            Source text
          </button>
          <button
            className={inspectorTab === "features" ? "selected" : ""}
            onClick={() => setInspectorTab("features")}
          >
            Detected features
          </button>
        </div>
        {inspectorTab === "features" ? (
          <div className="inspector-content source-features-panel">
            <span className="eyebrow">
              {sourceFeatures.length} FLANGE LOCATION PROPOSALS
            </span>
            <p className="fine-print">
              Blue marks show proposed faces and separate pipe dots. Inspect
              each symbol and set its route before saving a point. Physical
              dimensions and material matches remain unknown.
            </p>
            {!sourceFeatures.length && (
              <p className="fine-print">
                No supported flange symbols were recognized on this sheet. Other
                drawing conventions require review.
              </p>
            )}
            {sourceFeatures.map((feature, index) => (
              <div className="source-feature-card" key={feature.id}>
                <strong>
                  <Crosshair size={15} /> Flange proposal {index + 1}
                </strong>
                <span className="fine-print">
                  Unreviewed · face and pipe dot
                </span>
                <div className="source-feature-actions">
                  <button
                    className="button secondary compact"
                    disabled={busy}
                    onClick={() => proposeFeature(feature, "flange_face")}
                  >
                    Inspect face
                  </button>
                  <button
                    className="button secondary compact"
                    disabled={busy}
                    onClick={() => proposeFeature(feature, "opposite_pipe_dot")}
                  >
                    Inspect pipe dot
                  </button>
                </div>
              </div>
            ))}
          </div>
        ) : inspectorTab === "source" ? (
          <div className="inspector-content">
            <span className="eyebrow">EXTRACTED PDF TEXT</span>
            <p className="fine-print">
              Text extraction is a proposal source, not an engineering
              verification. Stroke lettering and raster content may not appear.
            </p>
            <pre className="source-text">
              {sheet.ocr_text ||
                sheet.text ||
                "No searchable text was found. Review the original page manually."}
            </pre>
            <a
              className="button secondary full compact"
              href={appPath(
                `api/v1/projects/${project.id}/sources/${sheet.source_id}`,
              )}
            >
              <ArrowDownToLine size={14} />
              Download original
            </a>
          </div>
        ) : draft ? (
          <div className="inspector-content">
            <button
              className="back-link"
              onClick={() => {
                if (!dirty || confirm("Discard unsaved changes?")) {
                  onSelect(null);
                  setDraft(null);
                  setDirty(false);
                }
              }}
            >
              <ArrowLeft size={13} />
              All sheet points
            </button>
            <div className="node-heading">
              <span
                className={`node-big ${current?.reasons.length || !draft.id ? "blue" : "red"}`}
              >
                {draft.number || "+"}
              </span>
              <div>
                <h3>{draft.id ? "Physical point" : "New physical point"}</h3>
                <span>
                  {label(draft.kind)} · {draft.route}
                </span>
              </div>
            </div>
            <div
              className={`point-status ${current?.reasons.length || !draft.id ? "flagged" : ""}`}
            >
              <span className="online-dot" />
              {current?.reasons.length || !draft.id
                ? "Engineering review required"
                : "Dimensional evidence recorded"}
            </div>
            {current?.reasons.map((reason) => (
              <div className="reason" key={reason}>
                <CircleHelp size={13} />
                <span>
                  {label(reason)}
                  {reason === "SUPPORT_WITHIN_6_IN" &&
                    ` · ${current.support_gap_mm} mm`}
                </span>
              </div>
            ))}
            <div className="field-section">
              <span className="eyebrow">PHYSICAL MODEL</span>
              <label className="form-field">
                Component
                <select
                  value={draft.kind}
                  onChange={(e) => patch({ kind: e.target.value })}
                >
                  {[
                    "endpoint",
                    "flange",
                    "tee",
                    "elbow",
                    "support",
                    "valve",
                    "instrument",
                    "continuation",
                  ].map((k) => (
                    <option key={k} value={k}>
                      {label(k)}
                    </option>
                  ))}
                </select>
              </label>
              <label className="form-field">
                Full line ID
                <input
                  value={draft.line_id}
                  onChange={(e) => patch({ line_id: e.target.value })}
                />
              </label>
              <div className="form-grid">
                <label className="form-field">
                  Route
                  <select
                    value={draft.route}
                    onChange={(e) =>
                      patch({ route: e.target.value, takeoff_id: null })
                    }
                  >
                    <option value="main">Main run</option>
                    {Array.from(
                      { length: 9 },
                      (_, i) => `branch-0${i + 1}`,
                    ).map((b) => (
                      <option key={b} value={b}>
                        {b}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="form-field">
                  Route order
                  <input
                    type="number"
                    min={0}
                    value={draft.order}
                    onChange={(e) => patch({ order: +e.target.value })}
                  />
                </label>
              </div>
              {draft.route !== "main" && (
                <label className="form-field">
                  Shared main-run tee
                  <select
                    value={draft.takeoff_id || ""}
                    onChange={(e) =>
                      patch({ takeoff_id: e.target.value || null })
                    }
                  >
                    <option value="">Unconfirmed takeoff</option>
                    {project.nodes
                      .filter(
                        (n) =>
                          n.kind === "tee" &&
                          n.route === "main" &&
                          n.line_id === draft.line_id,
                      )
                      .map((n) => (
                        <option key={n.id} value={n.id}>
                          Node {n.number} · Order {n.order}
                        </option>
                      ))}
                  </select>
                  <small>The tee keeps its main-run node identity.</small>
                </label>
              )}
              <label className="form-field">
                Along-route station
                <input
                  placeholder="e.g. 1200 mm or 3' 2 in"
                  value={draft.dimension}
                  onChange={(e) => patch({ dimension: e.target.value })}
                />
                <small>Explicit units required. Blank = unverified.</small>
              </label>
              {draft.proposed_station_mm !== undefined &&
                draft.proposed_station_mm !== null && (
                  <div className="notice">
                    <span>
                      Extracted source proposal: {draft.proposed_station_mm} mm.
                      Confirm its dimension chain before using it.
                      <button
                        className="text-button"
                        disabled={busy}
                        onClick={() =>
                          patch({
                            dimension:
                              draft.proposed_dimension_input ||
                              `${draft.proposed_station_mm} mm`,
                          })
                        }
                      >
                        Use source proposal
                      </button>
                    </span>
                  </div>
                )}
              <label className="form-field">
                Dimension source / evidence
                <textarea
                  aria-label="Dimension source / evidence"
                  rows={3}
                  placeholder="Drawing dimension chain, CAD coordinates, or engineering evidence…"
                  value={draft.evidence}
                  onChange={(e) => patch({ evidence: e.target.value })}
                />
              </label>
            </div>
            <div className="field-section">
              <span className="eyebrow">GRAPHIC PRESENTATION</span>
              <p className="fine-print">
                Drag the bubble or anchor on the drawing. This never changes the
                physical station.
              </p>
              {draft.instances
                .filter((i) => i.sheet_id === sheet.id)
                .map((inst) => (
                  <div key={inst.sheet_id}>
                    {(["anchor", "bubble"] as const).map((what) => (
                      <div key={what} className="coordinate-row">
                        <span>{label(what)}</span>
                        {inst[what].map((v, index) => (
                          <label key={index}>
                            <small>{index ? "Y" : "X"}</small>
                            <input
                              aria-label={`${what} ${index ? "Y" : "X"}`}
                              type="number"
                              step="0.1"
                              value={Number(v.toFixed(1))}
                              onChange={(e) => {
                                const point = [...inst[what]] as Point;
                                point[index] = +e.target.value;
                                patch({
                                  instances: draft.instances.map((i) =>
                                    i.sheet_id === sheet.id
                                      ? { ...i, [what]: point }
                                      : i,
                                  ),
                                });
                              }}
                            />
                          </label>
                        ))}
                      </div>
                    ))}
                  </div>
                ))}
              <div className="shared-point">
                <Link2 size={14} />
                {draft.instances.length} sheet representation
                {draft.instances.length > 1 ? "s" : ""} · One physical identity
              </div>
            </div>
            <div className="inspector-save">
              {dirty && (
                <span className="unsaved-dot">Unsaved point changes</span>
              )}
              <button
                className="button primary full"
                disabled={busy || !dirty}
                onClick={save}
              >
                {busy ? (
                  <Loader2 size={16} className="spin" />
                ) : (
                  <Save size={16} />
                )}
                Save point
              </button>
              {draft.id && (
                <button
                  className="button danger full compact"
                  disabled={busy}
                  onClick={deletePoint}
                >
                  <Trash2 size={14} />
                  Delete physical point
                </button>
              )}
            </div>
          </div>
        ) : (
          <div className="inspector-content">
            <div className="panel-title">
              <h3>Sheet points</h3>
              <span className="count-pill">{nodes.length}</span>
            </div>
            <p className="fine-print">
              Select a node to review its evidence, model order, and graphic
              position.
            </p>
            <div className="node-search">
              <List size={15} />
              <input
                value={nodeQuery}
                onChange={(e) => setNodeQuery(e.target.value)}
                aria-label="Search sheet nodes"
                placeholder="Find a node or component…"
              />
            </div>
            <div className="node-list">
              {nodes
                .filter((n) =>
                  `${n.number} ${n.kind} ${n.route}`.includes(
                    nodeQuery.toLowerCase(),
                  ),
                )
                .map((n) => (
                  <button key={n.id} onClick={() => onSelect(n.id)}>
                    <span
                      className={`node-mini ${n.reasons.length ? "blue" : "red"}`}
                    >
                      {n.number}
                    </span>
                    <span>
                      <b>{label(n.kind)}</b>
                      <small>
                        {n.route === "main" ? "Main run" : n.route} ·{" "}
                        {n.station_mm === null
                          ? "Unverified station"
                          : `${n.station_mm} mm`}
                      </small>
                    </span>
                    <ChevronRight size={14} />
                  </button>
                ))}
            </div>
            <div className="inspector-tools">
              <button
                className="button secondary full compact"
                onClick={() => {
                  setMode("link");
                  setShowLabels(true);
                }}
              >
                <Link2 size={14} />
                Link an existing point
              </button>
              <button
                className="button secondary full compact"
                onClick={() => setMode("axis")}
              >
                <Move size={14} />
                Place local axis
              </button>
              <button
                className="button secondary full compact"
                onClick={() => setMode("table")}
              >
                <FileText size={14} />
                Place component schedule
              </button>
              <button
                className="text-button"
                disabled={busy}
                onClick={async () => {
                  if (
                    await mutation("/nodes/renumber", {
                      version: project.version,
                    })
                  )
                    notify(
                      "Numbering regenerated from explicit route order; physical identities retained.",
                    );
                }}
              >
                <RotateCcw size={14} />
                Regenerate numbering
              </button>
            </div>
            <div className="inspector-note">
              <CircleHelp size={17} />
              <p>
                A new sheet does not start a new node series. Link a confirmed
                continuation to its existing physical point.
              </p>
            </div>
          </div>
        )}
      </aside>
      {notesOpen && (
        <DrawingNotes
          project={project}
          sheet={sheet}
          initial={editingNote}
          onClose={() => setNotesOpen(false)}
          mutation={mutation}
          busy={busy}
        />
      )}
    </div>
  );
}
function ShieldIcon() {
  return <Crosshair size={13} />;
}
