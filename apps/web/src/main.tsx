import { APP_BASE, appPath } from "./paths";
import { Updates } from "./updates";
import { SystemLogs } from "./logs";
import { ProjectPipeline, type PipelineIssue } from "./pipeline";
import { EngineeringResults } from "./results";
import {
  startDiagnostics,
  navigation,
  browserEvent,
  flushDiagnostics,
} from "./diagnostics";
import React, { useState, useEffect, useRef } from "react";
import { createRoot } from "react-dom/client";
import {
  Activity,
  ArrowDownToLine,
  ArrowLeft,
  ArrowRight,
  ArrowUpRight,
  Bell,
  Box,
  Check,
  CheckCheck,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  CircleHelp,
  ClipboardCheck,
  Database,
  FileText,
  Folder,
  GitBranch,
  Grip,
  LayoutDashboard,
  Layers,
  Loader2,
  Maximize2,
  MousePointer2,
  Plus,
  Search,
  Settings2,
  ShieldCheck,
  SlidersHorizontal,
  Trash2,
  Upload,
  X,
  ZoomIn,
  ZoomOut,
} from "lucide-react";
import {
  api,
  label,
  type Project,
  type Sheet,
  type PipeNode,
  type Material,
  type User,
  type History,
  type Artifact,
  type Point,
} from "./types";
import { DrawingEditor } from "./viewer";
import { CatalogManager, MatchDialog } from "./catalogs";
import { RevisionActions } from "./revisions";
import { PDFPreview } from "./pdf-preview";
import "./style.css";
import "./macos.css";
startDiagnostics();

type Page =
  | "projects"
  | "workspace"
  | "sheets"
  | "materials"
  | "validation"
  | "activity"
  | "logs"
  | "processing"
  | "results"
  | "catalogs";
type Toast = { message: string; error: boolean };
const workspaceTimeZone =
  import.meta.env.VITE_WORKSPACE_TIMEZONE || "Australia/Perth";
const date = (v: string) =>
  new Date(v).toLocaleDateString(undefined, {
    day: "numeric",
    month: "short",
    year: "numeric",
    timeZone: workspaceTimeZone,
  });
const Icon = ({
  name,
  ...props
}: {
  name: typeof Folder;
  size?: number;
  className?: string;
}) => React.createElement(name, { size: 18, strokeWidth: 1.7, ...props });
function Badge({
  children,
  tone = "neutral",
}: {
  children: React.ReactNode;
  tone?: string;
}) {
  return (
    <span className={`badge ${tone}`}>
      <i />
      {children}
    </span>
  );
}
function Empty({
  title,
  text,
  action,
}: {
  title: string;
  text: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="empty">
      <div className="empty-icon">
        <Layers size={28} />
      </div>
      <h3>{title}</h3>
      <p>{text}</p>
      {action}
    </div>
  );
}

function App() {
  const [updatesOpen, setUpdatesOpen] = useState(false);
  const [user, setUser] = useState<User | null>(null),
    [starting, setStarting] = useState(true),
    [local, setLocal] = useState(false);
  const [projects, setProjects] = useState<Project[]>([]),
    [project, setProject] = useState<Project | null>(null),
    [page, setPage] = useState<Page>("projects");
  const [evidenceRegion, setEvidenceRegion] = useState<number[] | null>(null),
    [revisionOpen, setRevisionOpen] = useState(false);
  const [processingActive, setProcessingActive] = useState(false);
  useEffect(() => {
    navigation(user ? page : "login");
    if (user) void flushDiagnostics();
  }, [page, user?.id]);
  const [query, setQuery] = useState(""),
    [filter, setFilter] = useState("all"),
    [newOpen, setNewOpen] = useState(false),
    [help, setHelp] = useState(false);
  const [toast, setToast] = useState<Toast | null>(null),
    [busy, setBusy] = useState(false),
    [exportOpen, setExportOpen] = useState(false),
    [exported, setExported] = useState<Artifact | null>(null);
  const [previewArtifact, setPreviewArtifact] = useState<Artifact | null>(null);
  const [history, setHistory] = useState<History | null>(null),
    [activeSheet, setActiveSheet] = useState(0),
    [selected, setSelected] = useState<string | null>(null),
    [mobileNav, setMobileNav] = useState(false);
  const notify = (message: string, error = false) =>
    setToast({ message, error });
  useEffect(() => {
    if (toast) {
      const id = setTimeout(() => setToast(null), 6500);
      return () => clearTimeout(id);
    }
  }, [toast]);
  const loadProjects = async () => {
    const data = await api<Project[]>("/projects");
    setProjects(data);
    return data;
  };
  useEffect(() => {
    Promise.all([
      api<User>("/auth/me")
        .then(setUser)
        .catch(() => {}),
      api<{ mode: string }>("/health").then((v) =>
        setLocal(v.mode === "local-development"),
      ),
    ]).finally(() => setStarting(false));
  }, []);
  useEffect(() => {
    if (user) {
      const params = new URLSearchParams(window.location.search);
      if (params.get("returnTo") === "loader") {
        window.location.replace(appPath("loader.php"));
        return;
      }
      loadProjects()
        .then(() => {
          const id = params.get("project");
          const view = params.get("view");
          if (id)
            openProject(
              id,
              ([
                "workspace",
                "sheets",
                "materials",
                "validation",
                "activity",
                "processing",
                "results",
              ].includes(view || "")
                ? view
                : "workspace") as Page,
            );
          else if (view === "catalogs") setPage("catalogs");
          else if (
            view === "logs" &&
            user.role === "admin" &&
            (local || user.id === "admin")
          )
            setPage("logs");
        })
        .catch((e) => notify(e.message, true));
    }
  }, [user]);
  const openProject = async (id: string, target: Page = "workspace") => {
    browserEvent({ kind: "action", action: "load_project" });
    try {
      const p = await api<Project>(`/projects/${id}`);
      setProject(p);
      setPage(target);
      setSelected(null);
      setActiveSheet(0);
      setMobileNav(false);
      window.history.replaceState(
        null,
        "",
        `${APP_BASE}?project=${encodeURIComponent(id)}&view=${target}`,
      );
    } catch (e) {
      notify((e as Error).message, true);
    }
  };
  const update = (p: Project) => {
    setProject(p);
    setProjects((old) => old.map((v) => (v.id === p.id ? p : v)));
  };
  const refreshHistory = async () => {
    if (project)
      setHistory(await api<History>(`/projects/${project.id}/audit`));
  };
  useEffect(() => {
    if (project && (page === "activity" || exportOpen))
      refreshHistory().catch((e) => notify(e.message, true));
  }, [page, project?.version, exportOpen]);
  const navigate = (next: Page) => {
    setPage(next);
    setMobileNav(false);
    window.history.replaceState(
      null,
      "",
      next === "projects"
        ? APP_BASE
        : next === "catalogs" || next === "logs"
          ? `${APP_BASE}?view=${next}`
          : project
            ? `${APP_BASE}?project=${encodeURIComponent(project.id)}&view=${next}`
            : APP_BASE,
    );
  };
  const upload = async (file: File, p = project, replaceSource?: string) => {
    browserEvent({ kind: "action", action: "upload_pdf" });
    if (!p) return;
    setBusy(true);
    try {
      await api(
        `/projects/${p.id}/intake?version=${p.version}${replaceSource ? `&replace_source_id=${encodeURIComponent(replaceSource)}` : ""}`,
        {
          method: "POST",
          body: file,
          headers: {
            "Content-Type": "application/pdf",
            "X-Filename": encodeURIComponent(file.name),
          },
        },
      );
      setActiveSheet(0);
      notify(
        "Drawing queued. Processing continues if you close this page; the review draft appears automatically.",
      );
    } catch (e) {
      notify((e as Error).message, true);
    } finally {
      setBusy(false);
    }
  };
  const exportProject = async () => {
    browserEvent({ kind: "action", action: "export_bundle" });
    if (!project) return;
    setBusy(true);
    try {
      const v = await api<Artifact>(`/projects/${project.id}/exports`, {
        method: "POST",
        body: JSON.stringify({ version: project.version }),
      });
      setExported(v);
      refreshHistory();
      notify(
        "Review bundle generated. Native annotation integrity checks passed.",
      );
    } catch (e) {
      notify((e as Error).message, true);
    } finally {
      setBusy(false);
    }
  };
  const download = (artifact: Artifact) => {
    if (project)
      window.location.href = appPath(
        `api/v1/projects/${project.id}/artifacts/${artifact.id}/download`,
      );
  };
  const mutation = async (path: string, body: unknown, method = "POST") => {
    if (path.startsWith("/nodes"))
      browserEvent({ kind: "action", action: "save_node" });
    if (path.startsWith("/annotations"))
      browserEvent({ kind: "action", action: "save_annotation" });
    if (!project) return;
    setBusy(true);
    try {
      const p = await api<Project>(`/projects/${project.id}${path}`, {
        method,
        body: JSON.stringify(body),
      });
      update(p);
      return p;
    } catch (e) {
      notify((e as Error).message, true);
      if ((e as Error).message.includes("Reload")) {
        const p = await api<Project>(`/projects/${project.id}`);
        update(p);
      }
      return undefined;
    } finally {
      setBusy(false);
    }
  };
  if (starting)
    return (
      <div className="loading-screen">
        <Loader2 className="spin" />
        <span>Opening your workspace…</span>
      </div>
    );
  if (!user) return <Login local={local} onLogin={setUser} />;
  const sheet =
    project?.sheets[Math.min(activeSheet, (project?.sheets.length || 1) - 1)];
  const allIssues = projects.reduce((n, p) => n + p.issues.length, 0);
  return (
    <div className="app-shell">
      <aside className={`sidebar ${mobileNav ? "mobile-open" : ""}`}>
        <button
          className="brand"
          onClick={() => navigate("projects")}
          aria-label="CAESAR home"
        >
          <span className="brand-mark">
            <Layers size={22} />
          </span>
          <span>
            CAESAR<span className="brand-sub">ISOMETRIC WORKSPACE</span>
          </span>
        </button>
        <div className="workspace-picker">
          <span className="company-logo">N</span>
          <span>
            Engineering workspace
            <small>
              {local ? "Local development" : "Authenticated workspace"}
            </small>
          </span>
          <ChevronDown size={15} />
        </div>
        <div className="nav-caption">WORKSPACE</div>
        <nav>
          <button
            aria-label="Projects"
            className={page === "projects" ? "active" : ""}
            onClick={() => navigate("projects")}
          >
            <LayoutDashboard />
            Projects<span className="nav-count">{projects.length}</span>
          </button>
          <button
            className={page === "catalogs" ? "active" : ""}
            onClick={() => navigate("catalogs")}
          >
            <Database />
            Component catalogs
          </button>
          {user.role === "admin" && (local || user.id === "admin") && (
            <button
              className={page === "logs" ? "active" : ""}
              onClick={() => navigate("logs")}
            >
              <Activity size={18} />
              Logs
            </button>
          )}
        </nav>
        {project && (
          <>
            <div className="nav-caption project-caption">CURRENT PROJECT</div>
            <div className="nav-project">
              <span className="online-dot" />
              {project.title}
            </div>
            <nav>
              {(
                [
                  ["workspace", "Drawing workspace", GitBranch],
                  ["processing", "Project flow", Activity],
                  ["results", "Excel results", FileText],
                  ["sheets", "Drawing register", FilesIcon],
                  ["materials", "Materials review", Box],
                  ["validation", "Validation & release", ShieldCheck],
                  ["activity", "Revision history", Activity],
                ] as const
              ).map(([id, title, ic]) => (
                <button
                  key={id}
                  className={page === id ? "active" : ""}
                  onClick={() => navigate(id)}
                >
                  <Icon name={ic} />
                  {title}
                  {id === "validation" && (
                    <span className="nav-count">{project.issues.length}</span>
                  )}
                </button>
              ))}
            </nav>
          </>
        )}
        <div className="sidebar-bottom">
          {user.role === "admin" && (local || user.id === "admin") && (
            <button className="help-link" onClick={() => setUpdatesOpen(true)}>
              <Settings2 size={17} />
              System updates
            </button>
          )}
          <div className="review-card">
            <div>
              <ShieldCheck size={17} />
              <b>Engineering, with evidence.</b>
            </div>
            <p>
              Every point has a source.
              <br />
              Every decision has a record.
            </p>
            <button onClick={() => setHelp(true)}>
              Workspace guide <ArrowUpRight size={14} />
            </button>
          </div>
          <button className="help-link" onClick={() => setHelp(true)}>
            <CircleHelp size={17} />
            Help & documentation
            <ArrowUpRight size={14} />
          </button>
          <div className="profile">
            <span className="avatar">AM</span>
            <div>
              <b>{user.name}</b>
              <small>
                {label(user.role)} ·{" "}
                {local ? "Local workspace" : "Hosted workspace"}
              </small>
            </div>
            <button
              className="icon-button"
              title="Sign out"
              onClick={async () => {
                await api("/auth/logout", { method: "POST" });
                setUser(null);
              }}
            >
              <ArrowRight size={17} />
            </button>
          </div>
        </div>
      </aside>
      <main className="main">
        <header className="topbar">
          <div className="breadcrumbs">
            <button
              className="icon-button mobile-menu"
              onClick={() => setMobileNav(!mobileNav)}
            >
              <Grip />
            </button>
            <span>Workspace</span>
            <ChevronRight size={13} />
            <strong>
              {page === "projects"
                ? "Projects"
                : page === "catalogs"
                  ? "Component catalogs"
                  : page === "logs"
                    ? "Logs"
                    : project?.title}
            </strong>
            {project &&
              page !== "projects" &&
              page !== "catalogs" &&
              page !== "logs" && (
                <>
                  <ChevronRight size={13} />
                  <span>{label(page)}</span>
                </>
              )}
          </div>
          <div className="top-actions">
            <span className="environment-label">
              <span className="online-dot" />
              {local ? "Local development" : "Authenticated workspace"}
            </span>
            <button
              className="icon-button"
              aria-label="Workspace guide"
              onClick={() => setHelp(true)}
            >
              <CircleHelp size={18} />
            </button>
            <span className="avatar small">AM</span>
          </div>
        </header>
        {page === "logs" && <SystemLogs />}
        {page === "projects" && (
          <div className="page-content">
            <div className="page-heading">
              <div>
                <div className="eyebrow">YOUR ENGINEERING WORKSPACE</div>
                <h1>
                  Projects<span className="heading-dot">.</span>
                </h1>
                <p>From isometric drawings to engineering-ready decisions.</p>
              </div>
              <div className="heading-actions">
                <a className="button secondary" href={appPath("loader.php")}>
                  <Folder size={16} />
                  Load project
                </a>
                <button
                  className="button primary"
                  onClick={() => setNewOpen(true)}
                >
                  <Plus size={17} />
                  New project
                </button>
              </div>
            </div>
            <div className="stats-grid">
              <Stat
                label="Total projects"
                value={projects.length}
                detail="In your workspace"
                icon={Folder}
              />
              <Stat
                label="Drawings registered"
                value={projects.reduce((n, p) => n + p.sheets.length, 0)}
                detail="Source pages preserved"
                icon={Layers}
              />
              <Stat
                label="Awaiting review"
                value={projects.filter((p) => p.issues.length).length}
                detail={`${allIssues} open review items`}
                icon={ClipboardCheck}
                accent
              />
              <Stat
                label="Physical points"
                value={projects.reduce((n, p) => n + p.nodes.length, 0)}
                detail="Stable, traceable identities"
                icon={GitBranch}
              />
            </div>
            <div className="section-title">
              <div>
                <h2>
                  Project register <span>{projects.length}</span>
                </h2>
                <p>
                  Keep your drawings, review decisions, and revisions in one
                  place.
                </p>
              </div>
              <span className="subtle-label">
                <span className="online-dot" />
                All changes saved locally
              </span>
            </div>
            <div className="project-panel">
              <div className="table-toolbar">
                <div className="tabs">
                  {[
                    ["all", "All projects"],
                    ["review", "Needs review"],
                    ["draft", "Drafts"],
                  ].map(([id, text]) => (
                    <button
                      key={id}
                      className={filter === id ? "selected" : ""}
                      onClick={() => setFilter(id)}
                    >
                      {text}
                      {id === "all" && <span>{projects.length}</span>}
                    </button>
                  ))}
                </div>
                <div className="search-field">
                  <Search size={16} />
                  <input
                    aria-label="Search projects"
                    placeholder="Search projects or line IDs…"
                    value={query}
                    onChange={(e) => setQuery(e.target.value)}
                  />
                  <kbd>/</kbd>
                </div>
              </div>
              <div className="responsive-table">
                <table className="project-table">
                  <thead>
                    <tr>
                      <th>PROJECT / LINE ID</th>
                      <th>STATUS</th>
                      <th>DRAWINGS</th>
                      <th>REVIEW ITEMS</th>
                      <th>LAST UPDATED</th>
                      <th />
                    </tr>
                  </thead>
                  <tbody>
                    {projects
                      .filter(
                        (p) =>
                          (p.title + " " + p.line_id)
                            .toLowerCase()
                            .includes(query.toLowerCase()) &&
                          (filter === "all" ||
                            (filter === "review" && p.issues.length > 0) ||
                            (filter === "draft" && p.status === "DRAFT")),
                      )
                      .map((p) => (
                        <tr
                          key={p.id}
                          onClick={() => openProject(p.id)}
                          tabIndex={0}
                          onKeyDown={(e) =>
                            e.key === "Enter" && openProject(p.id)
                          }
                        >
                          <td>
                            <div className="project-name">
                              <div className="file-tile">
                                <GitBranch size={21} />
                              </div>
                              <div>
                                <strong>{p.title}</strong>
                                <span>
                                  {p.line_id}
                                  {p.sample && <em>EXAMPLE</em>}
                                </span>
                              </div>
                            </div>
                          </td>
                          <td>
                            <Badge
                              tone={p.status === "DRAFT" ? "neutral" : "amber"}
                            >
                              {label(p.status)}
                            </Badge>
                          </td>
                          <td>
                            <span className="inline-icon">
                              <FileText size={15} />
                              {p.sheets.length} sheets
                            </span>
                          </td>
                          <td>
                            <span
                              className={
                                p.issues.length ? "review-count" : "muted"
                              }
                            >
                              {p.issues.length ? (
                                <>
                                  <span className="amber-dot" />
                                  {p.issues.length} to review
                                </>
                              ) : (
                                "—"
                              )}
                            </span>
                          </td>
                          <td>
                            <span className="date-cell">
                              {date(p.updated)}
                              <small>
                                Revision {String(p.version).padStart(2, "0")}
                              </small>
                            </span>
                          </td>
                          <td>
                            <ArrowUpRight size={18} />
                          </td>
                        </tr>
                      ))}
                  </tbody>
                </table>
              </div>
              {!projects.length && (
                <Empty
                  title="Your first project starts here"
                  text="Create a project and upload an isometric PDF to start an evidence-led review."
                  action={
                    <button
                      className="button primary"
                      onClick={() => setNewOpen(true)}
                    >
                      <Plus size={16} />
                      Create project
                    </button>
                  }
                />
              )}
              {projects.length > 0 &&
                !projects.some(
                  (p) =>
                    (p.title + " " + p.line_id)
                      .toLowerCase()
                      .includes(query.toLowerCase()) &&
                    (filter === "all" ||
                      (filter === "review" && p.issues.length > 0) ||
                      (filter === "draft" && p.status === "DRAFT")),
                ) && (
                  <Empty
                    title="No matching projects"
                    text="Try a different name, line ID, or status filter."
                  />
                )}
              <div className="table-footer">
                <span>
                  {projects.length} project{projects.length !== 1 ? "s" : ""} in
                  this workspace
                </span>
                <span>
                  Private by default <ShieldCheck size={13} />
                </span>
              </div>
            </div>
            <div className="getting-started">
              <div className="guide-art">
                <GitBranch size={34} />
                <span className="art-node n1">10</span>
                <span className="art-node n2">20</span>
              </div>
              <div>
                <span className="eyebrow">BUILT FOR ENGINEERING JUDGEMENT</span>
                <h3>A clear route from drawing to review.</h3>
                <p>
                  Upload your sheets. Define physical points. Review the
                  evidence.
                  <br className="desktop-break" /> Export individually editable
                  annotations and a complete audit trail.
                </p>
              </div>
              <button
                className="button secondary"
                onClick={() => setHelp(true)}
              >
                Explore the workflow <ArrowUpRight size={16} />
              </button>
            </div>
            <div className="page-foot">
              <span>
                <ShieldCheck size={14} />
                Graphic placement never determines physical dimensions.
              </span>
              <span>CAESAR ISO · Manual review MVP</span>
            </div>
          </div>
        )}
        {project &&
          page !== "projects" &&
          page !== "catalogs" &&
          page !== "logs" && (
            <>
              <div className="project-top">
                <div>
                  <button
                    className="back-link"
                    onClick={() => navigate("projects")}
                  >
                    <ArrowLeft size={13} />
                    All projects
                  </button>
                  <h1>
                    {project.title}{" "}
                    {project.sample && (
                      <span className="sample-tag">SYNTHETIC EXAMPLE</span>
                    )}
                  </h1>
                  <div className="project-meta">
                    <span>{project.line_id}</span>
                    <span>
                      Revision {String(project.version).padStart(2, "0")}
                    </span>
                    <Badge tone="amber">{label(project.status)}</Badge>
                  </div>
                </div>
                <div className="heading-actions">
                  <button
                    className="button secondary"
                    onClick={() => navigate("results")}
                  >
                    <FileText size={16} />
                    Excel results
                  </button>
                  {!!project.sheets.length && (
                    <button
                      className="button secondary"
                      disabled={busy || processingActive}
                      onClick={() => setRevisionOpen(true)}
                    >
                      Upload revision
                    </button>
                  )}
                  <label
                    className={`button secondary ${busy ? "disabled" : ""}`}
                  >
                    <Upload size={16} />
                    Add drawings
                    <input
                      type="file"
                      accept="application/pdf"
                      hidden
                      disabled={busy}
                      onChange={(e) => {
                        if (e.target.files?.[0]) upload(e.target.files[0]);
                        e.target.value = "";
                      }}
                    />
                  </label>
                  <button
                    className="button primary"
                    onClick={() => {
                      setExported(null);
                      setExportOpen(true);
                    }}
                  >
                    <ArrowDownToLine size={16} />
                    Export review
                  </button>
                </div>
              </div>
              <div className="project-tabs">
                {(
                  [
                    ["workspace", "Drawing workspace"],
                    ["processing", "Project flow"],
                    ["results", "Excel results"],
                    ["sheets", "Drawing register"],
                    ["materials", "Materials"],
                    ["validation", "Validation"],
                    ["activity", "History"],
                  ] as const
                ).map(([id, title]) => (
                  <button
                    key={id}
                    className={page === id ? "selected" : ""}
                    onClick={() => navigate(id)}
                  >
                    {title}
                    {id === "validation" && (
                      <span>{project.issues.length}</span>
                    )}
                  </button>
                ))}
                <span className="saved-label">
                  <CheckCheck size={14} />
                  Saved · v{project.version}
                </span>
              </div>
              <ProjectPipeline
                project={project}
                expanded={page === "processing"}
                onRefresh={update}
                onOpen={() => navigate("processing")}
                onPreview={setPreviewArtifact}
                onActive={setProcessingActive}
                administrator={
                  user.role === "admin" && (local || user.id === "admin")
                }
                onReview={(issue: PipelineIssue) => {
                  const index = project.sheets.findIndex(
                    (s) => s.id === issue.sheet_id,
                  );
                  if (index >= 0) setActiveSheet(index);
                  setEvidenceRegion(issue.bbox || null);
                  if (issue.point_id) setSelected(issue.point_id);
                  navigate(
                    issue.code === "DRAWING_IDENTITY_REVIEW_REQUIRED"
                      ? "sheets"
                      : issue.material_id && !issue.bbox
                        ? "materials"
                        : "workspace",
                  );
                }}
              />
              {page === "results" && (
                <EngineeringResults
                  project={project}
                  onUpdate={update}
                  onReview={(id, kind) => {
                    if (kind === "node") {
                      setSelected(id);
                      const node = project.nodes.find((n) => n.id === id);
                      const index = project.sheets.findIndex(
                        (s) => s.id === node?.instances[0]?.sheet_id,
                      );
                      if (index >= 0) setActiveSheet(index);
                      navigate("workspace");
                    } else navigate("materials");
                  }}
                />
              )}
              {page === "workspace" &&
                (sheet ? (
                  <DrawingEditor
                    project={project}
                    sheet={sheet}
                    activeSheet={activeSheet}
                    onSheet={setActiveSheet}
                    selected={selected}
                    onSelect={setSelected}
                    mutation={mutation}
                    busy={busy || processingActive}
                    notify={notify}
                    evidenceRegion={evidenceRegion}
                  />
                ) : (
                  <Empty
                    title="Bring your drawing into view"
                    text="Upload a PDF to register its pages. Every sheet and its original source are preserved."
                    action={
                      <label className="button primary">
                        <Upload size={16} />
                        Upload PDF
                        <input
                          type="file"
                          accept=".pdf"
                          hidden
                          onChange={(e) =>
                            e.target.files?.[0] && upload(e.target.files[0])
                          }
                        />
                      </label>
                    }
                  />
                ))}
              {page === "sheets" && (
                <div className="inner-content">
                  <div className="section-title">
                    <div>
                      <h2>Drawing register</h2>
                      <p>
                        Physical pages are registered automatically. Confirm the
                        printed sheet and full line identity.
                      </p>
                    </div>
                    <Badge>{project.sheets.length} source pages</Badge>
                  </div>
                  {project.sheets.length ? (
                    <div className="sheet-cards">
                      {project.sheets.map((s, i) => (
                        <SheetCard
                          key={s.id}
                          sheet={s}
                          index={i}
                          project={project}
                          onOpen={() => {
                            setActiveSheet(i);
                            navigate("workspace");
                          }}
                          mutation={mutation}
                        />
                      ))}
                    </div>
                  ) : (
                    <Empty
                      title="No drawings registered"
                      text="Use Add drawings to upload a multipage PDF."
                    />
                  )}
                </div>
              )}
              {page === "materials" && (
                <Materials
                  project={project}
                  mutation={mutation}
                  busy={busy}
                  notify={notify}
                  onDrawing={(id) => {
                    setActiveSheet(
                      project.sheets.findIndex((s) => s.id === id),
                    );
                    navigate("workspace");
                  }}
                />
              )}
              {page === "validation" && (
                <div className="inner-content">
                  <div className="section-title">
                    <div>
                      <h2>Evidence before release.</h2>
                      <p>
                        Review every exception. Blue indicates a reason to
                        investigate, not an inferred dimension.
                      </p>
                    </div>
                    <Badge tone="amber">Review draft only</Badge>
                  </div>
                  <div className="validation-grid">
                    <div className="panel">
                      <div className="panel-title">
                        <ClipboardCheck size={18} />
                        <h3>Review checklist</h3>
                      </div>
                      <p className="muted">
                        Confirm these reviews after inspecting every source
                        page.
                      </p>
                      <label className="check-row">
                        <input
                          type="checkbox"
                          checked={project.materials_reviewed}
                          disabled={busy}
                          onChange={(e) =>
                            mutation("/review", {
                              version: project.version,
                              materials_reviewed: e.target.checked,
                              layout_reviewed: project.layout_reviewed,
                            })
                          }
                        />
                        <div>
                          <b>Materials reconciliation reviewed</b>
                          <small>
                            Source quantities, component instances, and
                            unresolved items accounted for.
                          </small>
                        </div>
                      </label>
                      <label className="check-row">
                        <input
                          type="checkbox"
                          checked={project.layout_reviewed}
                          disabled={busy}
                          onChange={(e) =>
                            mutation("/review", {
                              version: project.version,
                              materials_reviewed: project.materials_reviewed,
                              layout_reviewed: e.target.checked,
                            })
                          }
                        />
                        <div>
                          <b>Annotation layout reviewed</b>
                          <small>
                            All pages checked for collisions, dimensions,
                            north-arrow and title clearance.
                          </small>
                        </div>
                      </label>
                      <div className="notice amber">
                        <ShieldCheck size={18} />
                        <span>
                          Verified-for-modelling release is disabled until
                          catalog matching, lead approval, and target-editor
                          checks are implemented and validated.
                        </span>
                      </div>
                    </div>
                    <div className="panel release-summary">
                      <span className="eyebrow">CURRENT REVISION</span>
                      <h3>
                        {project.nodes.length}
                        <small>unique physical points</small>
                      </h3>
                      <div>
                        <span>Displayed node labels</span>
                        <b>
                          {project.nodes.reduce(
                            (n, p) => n + p.instances.length,
                            0,
                          )}
                        </b>
                      </div>
                      <div>
                        <span>Blue / flagged points</span>
                        <b>
                          {project.nodes.filter((n) => n.reasons.length).length}
                        </b>
                      </div>
                      <div>
                        <span>Open exceptions</span>
                        <b>{project.issues.length}</b>
                      </div>
                      <button
                        className="button primary"
                        onClick={() => setExportOpen(true)}
                      >
                        <ArrowDownToLine size={16} />
                        Export review draft
                      </button>
                    </div>
                  </div>
                  <div className="panel issues-panel">
                    <div className="panel-title">
                      <h3>Exception queue</h3>
                      <Badge tone="amber">{project.issues.length} open</Badge>
                    </div>
                    {project.issues.map((issue, i) => (
                      <button
                        key={i}
                        className="issue-row"
                        onClick={() => {
                          if (issue.point_id) {
                            setSelected(issue.point_id);
                            const n = project.nodes.find(
                              (n) => n.id === issue.point_id,
                            );
                            if (n)
                              setActiveSheet(
                                project.sheets.findIndex(
                                  (s) => s.id === n.instances[0].sheet_id,
                                ),
                              );
                            navigate("workspace");
                          } else if (issue.material_id) navigate("materials");
                          else setHelp(true);
                        }}
                      >
                        <span className={`issue-dot ${issue.severity}`} />
                        <div>
                          <b>{label(issue.code)}</b>
                          <p>{issue.message}</p>
                        </div>
                        <span className="issue-level">{issue.severity}</span>
                        <ChevronRight size={16} />
                      </button>
                    ))}
                  </div>
                </div>
              )}
              {page === "activity" && (
                <div className="inner-content">
                  <div className="section-title">
                    <div>
                      <h2>Revision history</h2>
                      <p>
                        Immutable revision snapshots and an attributable record
                        of engineering changes.
                      </p>
                    </div>
                    <Badge>Revision {project.version}</Badge>
                  </div>
                  <div className="history-grid">
                    <div className="panel">
                      <div className="panel-title">
                        <Activity size={18} />
                        <h3>Project activity</h3>
                      </div>
                      {history?.events.map((e) => (
                        <div className="timeline" key={e.id}>
                          <span className="timeline-dot" />
                          <div>
                            <b>{e.action}</b>
                            <p>{e.detail || e.actor}</p>
                            <small>
                              {new Date(e.created).toLocaleString(undefined, {
                                timeZone: workspaceTimeZone,
                              })}
                            </small>
                          </div>
                        </div>
                      ))}
                    </div>
                    <div>
                      <div className="panel">
                        <div className="panel-title">
                          <ArrowDownToLine size={18} />
                          <h3>Exported review bundles</h3>
                        </div>
                        {history?.artifacts.length ? (
                          history.artifacts.map((a) => (
                            <button
                              className="artifact-row"
                              key={a.id}
                              onClick={() => download(a)}
                            >
                              <FileText size={20} />
                              <span>
                                <b>Review · Revision {a.revision}</b>
                                <small>
                                  {a.count} editable objects · {date(a.created)}
                                </small>
                              </span>
                              <ArrowDownToLine size={16} />
                            </button>
                          ))
                        ) : (
                          <p className="muted">
                            No exports yet. Export a review draft to generate an
                            editable PDF and its schedules.
                          </p>
                        )}
                      </div>
                      <div className="panel revision-list">
                        <h3>Saved revisions</h3>
                        {history?.revisions.map((r) => (
                          <div key={r.version}>
                            <b>Revision {String(r.version).padStart(2, "0")}</b>
                            <span>{date(r.updated)}</span>
                            <RevisionActions
                              project={project}
                              revision={r.version}
                              mutation={mutation}
                              notify={notify}
                            />
                          </div>
                        ))}
                      </div>
                    </div>
                  </div>
                </div>
              )}
            </>
          )}
        {page === "catalogs" && (
          <CatalogManager busy={busy} setBusy={setBusy} notify={notify} />
        )}
      </main>
      {toast && (
        <div role="status" className={`toast ${toast.error ? "error" : ""}`}>
          {toast.error ? <CircleHelp size={18} /> : <Check size={18} />}
          <span>{toast.message}</span>
          <button
            className="icon-button"
            aria-label="Dismiss notification"
            onClick={() => setToast(null)}
          >
            <X size={16} />
          </button>
        </div>
      )}
      {newOpen && (
        <Modal
          title="Create a new project"
          subtitle="Give your drawing set a home."
          onClose={() => setNewOpen(false)}
        >
          <NewProject
            onCreate={async (name, line, description, file) => {
              setBusy(true);
              try {
                const p = await api<Project>("/projects", {
                  method: "POST",
                  body: JSON.stringify({
                    title: name,
                    line_id: line,
                    description,
                  }),
                });
                setProjects((old) => [p, ...old]);
                setProject(p);
                setSelected(null);
                setPage("workspace");
                setActiveSheet(0);
                setNewOpen(false);
                window.history.replaceState(
                  null,
                  "",
                  `${APP_BASE}?project=${encodeURIComponent(p.id)}&view=workspace`,
                );
                if (file) await upload(file, p);
                else {
                  await openProject(p.id);
                  notify(
                    "Project created. Upload drawings to start your review.",
                  );
                }
              } catch (e) {
                notify((e as Error).message, true);
              } finally {
                setBusy(false);
              }
            }}
            busy={busy}
          />
        </Modal>
      )}
      {revisionOpen && project && (
        <Modal
          title="Upload a drawing revision"
          subtitle="Replace one active document. Other documents remain active; previous sources and edits are archived."
          onClose={() => setRevisionOpen(false)}
        >
          <form
            onSubmit={(e) => {
              e.preventDefault();
              const fields = new FormData(e.currentTarget);
              const file = fields.get("revision_pdf");
              if (file instanceof File && file.size) {
                setRevisionOpen(false);
                void upload(file, project, String(fields.get("source_id")));
              }
            }}
          >
            <label className="form-field">
              Document being replaced
              <select name="source_id">
                {Array.from(
                  new Map(project.sheets.map((s) => [s.source_id, s])).values(),
                ).map((s) => (
                  <option value={s.source_id} key={s.source_id}>
                    {s.filename}
                  </option>
                ))}
              </select>
            </label>
            <label className="form-field">
              Revised PDF
              <input
                type="file"
                name="revision_pdf"
                accept="application/pdf"
                required
              />
            </label>
            <div className="notice amber">
              Changed pages require engineering reconciliation. Previous node
              stations and review notes will not be copied onto unproved new
              locations.
            </div>
            <button className="button primary" disabled={busy}>
              Process revision
            </button>
          </form>
        </Modal>
      )}
      {exportOpen && project && (
        <Modal
          title="Export engineering review"
          subtitle={`Revision ${project.version} · ${project.title}`}
          onClose={() => setExportOpen(false)}
        >
          <div className="notice amber">
            <ShieldCheck size={20} />
            <span>
              {project.issues.length} open review items. This bundle is labelled{" "}
              <b>engineering review draft</b> and is not verified for modelling.
            </span>
          </div>
          <div className="export-contents">
            {[
              [
                "Formatted Excel workbook",
                "Editable node, element, component and exception tables with source evidence",
              ],
              [
                "Individually editable PDF",
                "Native circle, text, leader, axis and table objects",
              ],
              [
                "Node schedules & project model",
                "CSV + JSON with physical identities and evidence",
              ],
              [
                "Traceability & QA reports",
                "Annotation manifest, exceptions, materials and numbering map",
              ],
            ].map(([a, b]) => (
              <div key={a}>
                <Check size={17} />
                <span>
                  <b>{a}</b>
                  <small>{b}</small>
                </span>
              </div>
            ))}
          </div>
          <p className="fine-print">
            Source content streams are checked after export. Desktop PDF editor
            compatibility still requires a manual round trip. Unknown catalog
            values remain N/A.
          </p>
          {exported ? (
            <>
              <button
                className="button secondary full"
                style={{ marginBottom: 10 }}
                onClick={() => {
                  setExportOpen(false);
                  setPreviewArtifact(exported);
                }}
              >
                <FileText size={16} />
                Preview generated PDF
              </button>
              <button
                className="button primary full"
                onClick={() => download(exported)}
              >
                <ArrowDownToLine size={17} />
                Download review bundle (.zip)
              </button>
            </>
          ) : (
            <button
              className="button primary full"
              disabled={busy || !project.sheets.length}
              onClick={exportProject}
            >
              {busy ? (
                <Loader2 size={17} className="spin" />
              ) : (
                <ArrowDownToLine size={17} />
              )}
              Generate review bundle
            </button>
          )}
        </Modal>
      )}
      {previewArtifact && project && (
        <PDFPreview
          project={project}
          artifact={previewArtifact}
          onClose={() => setPreviewArtifact(null)}
        />
      )}
      {updatesOpen && <Updates onClose={() => setUpdatesOpen(false)} />}
      {help && (
        <Modal
          title="A clear route to review"
          subtitle="CAESAR ISO · Manual review MVP"
          onClose={() => setHelp(false)}
        >
          <div className="workflow-steps">
            {[
              [
                "01",
                "Register the source",
                "Create a project, upload a PDF, and confirm the printed identity of each sheet. Original bytes and source hashes are retained.",
              ],
              [
                "02",
                "Define physical points",
                "Click Add point in the drawing workspace. Enter main/branch order explicitly. Move bubbles separately from physical anchors.",
              ],
              [
                "03",
                "Attach engineering evidence",
                "Enter stations with explicit units and source evidence. Blank stations stay blue. Drawing pixels never become physical dimensions.",
              ],
              [
                "04",
                "Review and export",
                "Reconcile materials, review layout and exceptions, then download the native annotated PDF and its traceability bundle.",
              ],
            ].map(([n, t, d]) => (
              <div key={n}>
                <span>{n}</span>
                <div>
                  <h3>{t}</h3>
                  <p>{d}</p>
                </div>
              </div>
            ))}
          </div>
          <div className="notice">
            This local MVP is not a stress solver or a production hosted
            service. The original 1010 fixtures and canonical workbooks were not
            provided. Synthetic examples are explicitly labelled.
          </div>
        </Modal>
      )}
    </div>
  );
}
const FilesIcon = FileText;
function Stat({
  label: caption,
  value,
  detail,
  icon,
  accent,
}: {
  label: string;
  value: number;
  detail: string;
  icon: typeof Folder;
  accent?: boolean;
}) {
  return (
    <div className={`stat-card ${accent ? "accent" : ""}`}>
      <div>
        <span>{caption}</span>
        <Icon name={icon} />
      </div>
      <strong>{String(value).padStart(2, "0")}</strong>
      <small>
        {accent && <span className="amber-dot" />}
        {detail}
      </small>
    </div>
  );
}

export function Modal({
  title,
  subtitle,
  children,
  onClose,
}: {
  title: string;
  subtitle?: string;
  children: React.ReactNode;
  onClose: () => void;
}) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const previous = document.activeElement as HTMLElement;
    const key = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
      if (e.key === "Tab") {
        const nodes = ref.current?.querySelectorAll<HTMLElement>(
          "button,input,select,textarea,a[href]",
        );
        if (!nodes?.length) return;
        const first = nodes[0],
          last = nodes[nodes.length - 1];
        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault();
          last.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault();
          first.focus();
        }
      }
    };
    document.addEventListener("keydown", key);
    ref.current?.focus();
    return () => {
      document.removeEventListener("keydown", key);
      previous?.focus();
    };
  }, []);
  return (
    <div
      className="modal-backdrop"
      onMouseDown={(e) => e.target === e.currentTarget && onClose()}
    >
      <div
        className="modal"
        role="dialog"
        aria-modal="true"
        aria-label={title}
        tabIndex={-1}
        ref={ref}
      >
        <div className="modal-heading">
          <div>
            <h2>{title}</h2>
            {subtitle && <p>{subtitle}</p>}
          </div>
          <button
            className="icon-button"
            aria-label="Close dialog"
            onClick={onClose}
          >
            <X size={20} />
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}
function NewProject({
  onCreate,
  busy,
}: {
  onCreate: (
    name: string,
    line: string,
    description: string,
    file: File | null,
  ) => void;
  busy: boolean;
}) {
  const [name, setName] = useState(""),
    [line, setLine] = useState(""),
    [description, setDescription] = useState(""),
    [file, setFile] = useState<File | null>(null);
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        onCreate(name, line, description, file);
      }}
    >
      <label className="form-field">
        Project name
        <input
          required
          maxLength={150}
          placeholder="e.g. West process header"
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
      </label>
      <label className="form-field">
        Full line ID
        <input
          required
          maxLength={150}
          placeholder="e.g. 8-PG-JE3LN2-1010-FUTURE"
          value={line}
          onChange={(e) => setLine(e.target.value)}
        />
        <small>Use the drawing's full line identity, not its filename.</small>
      </label>
      <label className="form-field">
        Description <span className="muted">(optional)</span>
        <textarea
          rows={2}
          maxLength={2000}
          placeholder="Scope, system, or engineering context"
          value={description}
          onChange={(e) => setDescription(e.target.value)}
        />
      </label>
      <label
        className="upload-zone"
        onDragOver={(e) => e.preventDefault()}
        onDrop={(e) => {
          e.preventDefault();
          setFile(e.dataTransfer.files[0] || null);
        }}
      >
        <Upload size={25} />
        <b>{file ? file.name : "Drop your isometric PDF here"}</b>
        <span>or browse files · PDF up to 30 MB · optional</span>
        <input
          type="file"
          accept=".pdf"
          hidden
          onChange={(e) => setFile(e.target.files?.[0] || null)}
        />
      </label>
      <div className="modal-footer">
        <span>
          <ShieldCheck size={14} />
          Original sources stay intact
        </span>
        <button className="button primary" disabled={busy} type="submit">
          {busy ? <Loader2 className="spin" size={16} /> : <Plus size={16} />}
          Create project
        </button>
      </div>
    </form>
  );
}
function Login({
  local,
  onLogin,
}: {
  local: boolean;
  onLogin: (u: User) => void;
}) {
  const [email, setEmail] = useState(""),
    [password, setPassword] = useState(""),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  const enter = async (isLocal = false) => {
    setBusy(true);
    try {
      onLogin(
        await api<User>(isLocal ? "/auth/local" : "/auth/login", {
          method: "POST",
          body: JSON.stringify({ email, password }),
        }),
      );
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="login-shell">
      <div className="login-story">
        <div className="brand">
          <span className="brand-mark">
            <Layers />
          </span>
          <span>
            CAESAR<span className="brand-sub">ISOMETRIC WORKSPACE</span>
          </span>
        </div>
        <div>
          <span className="eyebrow">ENGINEERING, WITH EVIDENCE.</span>
          <h1>
            Every point.
            <br />A clear source.
            <br />
            <em>A better review.</em>
          </h1>
          <p>
            Your isometric drawings, physical points, and engineering decisions.
            Connected in one workspace.
          </p>
        </div>
        <small>CAESAR ISO / Engineering review workspace</small>
      </div>
      <div className="login-form">
        <span className="eyebrow">WELCOME TO YOUR WORKSPACE</span>
        <h2>Start with a clear view.</h2>
        <p>Sign in to review your piping isometrics.</p>
        {local ? (
          <>
            <div className="notice">
              <ShieldCheck size={20} />
              <span>
                Local development workspace. Includes a synthetic training
                project; no production credentials required.
              </span>
            </div>
            <button
              className="button primary full"
              disabled={busy}
              onClick={() => enter(true)}
            >
              {busy ? (
                <Loader2 className="spin" size={18} />
              ) : (
                <ArrowRight size={18} />
              )}
              Enter local workspace
            </button>
          </>
        ) : (
          <form
            onSubmit={(e) => {
              e.preventDefault();
              enter();
            }}
          >
            <label className="form-field">
              Email
              <input
                required
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                autoComplete="username"
              />
            </label>
            <label className="form-field">
              Password
              <input
                required
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="current-password"
              />
            </label>
            <button className="button primary full" disabled={busy}>
              Sign in
            </button>
          </form>
        )}
        {error && (
          <p className="error-text" role="alert">
            {error}
          </p>
        )}
        <p className="fine-print">
          Physical dimensions require engineering evidence.
          <br />
          No distances are inferred from the drawing scale.
        </p>
      </div>
    </div>
  );
}
type Mutation = (
  path: string,
  body: unknown,
  method?: string,
) => Promise<Project | undefined>;
function SheetCard({
  sheet,
  index,
  project,
  onOpen,
  mutation,
}: {
  sheet: Sheet;
  index: number;
  project: Project;
  onOpen: () => void;
  mutation: Mutation;
}) {
  const [editing, setEditing] = useState(false),
    [printed, setPrinted] = useState(sheet.printed_id),
    [line, setLine] = useState(sheet.line_id);
  return (
    <div className="sheet-card">
      <div className="sheet-card-top">
        <div className="file-tile">
          <FileText size={22} />
        </div>
        <Badge>{sheet.format}</Badge>
      </div>
      <h3>{sheet.printed_id || `Unconfirmed sheet ${index + 1}`}</h3>
      <p>
        {sheet.filename} · Physical page {sheet.page_index + 1}
      </p>
      <dl>
        <div>
          <dt>Line</dt>
          <dd>{sheet.line_id}</dd>
        </div>
        <div>
          <dt>Page / rotation</dt>
          <dd>
            {Math.round(sheet.width)} × {Math.round(sheet.height)} pt /{" "}
            {sheet.rotation}°
          </dd>
        </div>
        <div>
          <dt>Source SHA-256</dt>
          <dd className="mono" title={sheet.sha256}>
            {sheet.sha256.slice(0, 20)}…
          </dd>
        </div>
      </dl>
      {sheet.line_id_proposal && !sheet.identity_verified && (
        <p className="fine-print">
          Detected line proposal: {sheet.line_id_proposal}. Confirm against the
          printed title.
        </p>
      )}
      {editing && (
        <div className="sheet-edit">
          <label className="form-field">
            Printed drawing / sheet ID
            <input
              value={printed}
              onChange={(e) => setPrinted(e.target.value)}
            />
          </label>
          <label className="form-field">
            Full line ID
            <input value={line} onChange={(e) => setLine(e.target.value)} />
          </label>
          <button
            className="button primary compact"
            onClick={async () => {
              if (
                await mutation(
                  `/sheets/${sheet.id}`,
                  {
                    version: project.version,
                    printed_id: printed,
                    line_id: line,
                    axis: sheet.axis,
                    table: sheet.table,
                    confirm_identity: true,
                  },
                  "PATCH",
                )
              )
                setEditing(false);
            }}
          >
            Save identity
          </button>
        </div>
      )}
      <div className="sheet-actions">
        <button className="text-button" onClick={() => setEditing(!editing)}>
          <Settings2 size={15} />
          {editing ? "Cancel" : "Edit identity"}
        </button>
        <button className="text-button" onClick={onOpen}>
          Open drawing <ArrowUpRight size={15} />
        </button>
      </div>
      <a
        className="source-link"
        href={appPath(
          `api/v1/projects/${project.id}/sources/${sheet.source_id}`,
        )}
      >
        Download original PDF <ArrowDownToLine size={13} />
      </a>
    </div>
  );
}
function Materials({
  project,
  mutation,
  busy,
  onDrawing,
  notify,
}: {
  project: Project;
  mutation: Mutation;
  busy: boolean;
  onDrawing: (id: string) => void;
  notify: (message: string, error?: boolean) => void;
}) {
  const [editing, setEditing] = useState<Partial<Material> | null>(null),
    [filter, setFilter] = useState("all"),
    [search, setSearch] = useState("");
  const [matching, setMatching] = useState<Material | null>(null);
  const matched = project.materials.filter(
    (m) => m.quantity === m.observed,
  ).length;
  return (
    <div className="inner-content">
      <div className="section-title">
        <div>
          <h2>Materials, accounted for.</h2>
          <p>
            Reconcile listed quantities with observed instances. Unknown
            properties remain N/A.
          </p>
        </div>
        <button
          className="button secondary"
          disabled={!project.sheets.length}
          onClick={() =>
            setEditing({
              sheet_id: project.sheets[0]?.id,
              item_no: "",
              family: "pipe",
              description: "",
              size: "",
              quantity: 1,
              observed: 0,
              evidence: "",
            })
          }
        >
          <Plus size={16} />
          Add material
        </button>
      </div>
      <div className="notice">
        <Box size={18} />
        <span>
          {matched} of {project.materials.length} quantities reconciled. Catalog
          matches require authoritative workbooks and engineering approval; no
          numeric values are substituted.
        </span>
      </div>
      <div className="project-panel">
        <div className="table-toolbar">
          <div className="tabs">
            <button
              className={filter === "all" ? "selected" : ""}
              onClick={() => setFilter("all")}
            >
              All materials
            </button>
            <button
              className={filter === "unresolved" ? "selected" : ""}
              onClick={() => setFilter("unresolved")}
            >
              Unreconciled
            </button>
          </div>
          <div className="search-field">
            <Search size={16} />
            <input
              placeholder="Search materials…"
              aria-label="Search materials"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>
        </div>
        <div className="responsive-table">
          <table>
            <thead>
              <tr>
                <th>ITEM / SHEET</th>
                <th>DESCRIPTION</th>
                <th>SIZE</th>
                <th>LISTED / LOCATED</th>
                <th>CATALOG</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {project.materials
                .filter(
                  (m) =>
                    (filter === "all" || m.quantity !== m.observed) &&
                    `${m.description} ${m.item_no} ${m.family}`
                      .toLowerCase()
                      .includes(search.toLowerCase()),
                )
                .map((m) => (
                  <tr key={m.id}>
                    <td>
                      <b>{m.item_no}</b>
                      <small className="block muted">
                        Sheet{" "}
                        {project.sheets.findIndex((s) => s.id === m.sheet_id) +
                          1}
                      </small>
                    </td>
                    <td>
                      <b className="material-desc">{m.description}</b>
                      <small className="block muted">{label(m.family)}</small>
                    </td>
                    <td>{m.size || "N/A"}</td>
                    <td>
                      <span
                        className={
                          m.quantity === m.observed
                            ? "quantity-ok"
                            : "quantity-warning"
                        }
                      >
                        {m.quantity ?? "N/A"} / {m.observed}
                      </span>
                    </td>
                    <td>
                      {["flange", "valve"].includes(m.family) ? (
                        <div>
                          <Badge
                            tone={
                              m.catalog_match?.status ===
                              "MANUFACTURER_CONFIRMED"
                                ? "green"
                                : "amber"
                            }
                          >
                            {m.catalog_match
                              ? label(
                                  m.catalog_match.status || "REFERENCE_ONLY",
                                )
                              : "No exact match"}
                          </Badge>
                          <small className="block muted">
                            {m.catalog_match
                              ? `W ${m.catalog_match.record.weight_n ?? "N/A"} N · L ${m.catalog_match.record.length_mm ?? "N/A"} mm`
                              : ""}
                          </small>
                          <button
                            className="text-button"
                            onClick={() => setMatching(m)}
                          >
                            {m.catalog_match ? "Review match" : "Match catalog"}{" "}
                            <ArrowUpRight size={13} />
                          </button>
                        </div>
                      ) : (
                        <span className="muted">Not applicable</span>
                      )}
                    </td>
                    <td>
                      <button
                        className="text-button"
                        onClick={() => setEditing(m)}
                      >
                        Review <ArrowUpRight size={14} />
                      </button>
                    </td>
                  </tr>
                ))}
            </tbody>
          </table>
        </div>
        {!project.materials.length && (
          <Empty
            title="Build the materials inventory"
            text="Review the original materials list and add each item. Automatic arbitrary-table recognition is not enabled."
          />
        )}
      </div>
      {matching && (
        <MatchDialog
          project={project}
          material={matching}
          mutation={mutation}
          notify={notify}
          onClose={() => setMatching(null)}
        />
      )}
      {editing && (
        <Modal
          title={editing.id ? "Review material" : "Add material"}
          subtitle="Source quantities are evidence, not proof of a physical station."
          onClose={() => setEditing(null)}
        >
          <form
            onSubmit={async (e) => {
              e.preventDefault();
              const p = await mutation(
                `/materials${editing.id ? "/" + editing.id : ""}`,
                { ...editing, id: undefined, version: project.version },
                editing.id ? "PATCH" : "POST",
              );
              if (p) setEditing(null);
            }}
          >
            <div className="form-grid">
              <label className="form-field">
                Sheet
                <select
                  value={editing.sheet_id}
                  onChange={(e) =>
                    setEditing({ ...editing, sheet_id: e.target.value })
                  }
                >
                  {project.sheets.map((s, i) => (
                    <option key={s.id} value={s.id}>
                      {s.printed_id || `Sheet ${i + 1}`}
                    </option>
                  ))}
                </select>
              </label>
              <label className="form-field">
                Item number
                <input
                  required
                  value={editing.item_no}
                  onChange={(e) =>
                    setEditing({ ...editing, item_no: e.target.value })
                  }
                />
              </label>
            </div>
            <label className="form-field">
              Description
              <input
                required
                value={editing.description}
                onChange={(e) =>
                  setEditing({ ...editing, description: e.target.value })
                }
              />
            </label>
            <div className="form-grid">
              <label className="form-field">
                Family
                <select
                  value={editing.family}
                  onChange={(e) =>
                    setEditing({ ...editing, family: e.target.value })
                  }
                >
                  {[
                    "pipe",
                    "elbow",
                    "tee",
                    "support",
                    "flange",
                    "valve",
                    "instrument",
                    "other",
                  ].map((f) => (
                    <option key={f}>{f}</option>
                  ))}
                </select>
              </label>
              <label className="form-field">
                Size
                <input
                  value={editing.size}
                  onChange={(e) =>
                    setEditing({ ...editing, size: e.target.value })
                  }
                />
              </label>
              <label className="form-field">
                Listed quantity
                <input
                  type="number"
                  min={0}
                  placeholder="Unknown"
                  value={editing.quantity ?? ""}
                  onChange={(e) =>
                    setEditing({
                      ...editing,
                      quantity: e.target.value === "" ? null : +e.target.value,
                      quantity_value: e.target.value || null,
                      quantity_unit: e.target.value
                        ? "count"
                        : editing.quantity_unit,
                    })
                  }
                />
              </label>
              <label className="form-field">
                Source quantity value
                <input
                  inputMode="decimal"
                  value={
                    editing.quantity_value ??
                    (editing.quantity === null ? "" : String(editing.quantity))
                  }
                  onChange={(e) =>
                    setEditing({
                      ...editing,
                      quantity_value: e.target.value || null,
                      quantity:
                        editing.quantity_unit === "count" &&
                        /^\d+$/.test(e.target.value)
                          ? Number(e.target.value)
                          : null,
                    })
                  }
                />
              </label>
              <label className="form-field">
                Source quantity unit
                <select
                  value={editing.quantity_unit || "count"}
                  onChange={(e) =>
                    setEditing({
                      ...editing,
                      quantity_unit: e.target.value,
                      quantity:
                        e.target.value === "count" ? editing.quantity : null,
                    })
                  }
                >
                  {["count", "m", "mm", "ft", "in", "unresolved"].map(
                    (unit) => (
                      <option key={unit} value={unit}>
                        {unit === "unresolved"
                          ? "Unknown — source review required"
                          : unit}
                      </option>
                    ),
                  )}
                </select>
              </label>
              {editing.quantity_unit &&
                editing.quantity_unit !== "count" &&
                editing.quantity_unit !== "unresolved" && (
                  <label className="form-field">
                    Reconciled source quantity ({editing.quantity_unit})
                    <input
                      inputMode="decimal"
                      value={editing.observed_quantity_value ?? ""}
                      placeholder="Unknown"
                      onChange={(e) =>
                        setEditing({
                          ...editing,
                          observed_quantity_value: e.target.value || null,
                        })
                      }
                    />
                  </label>
                )}
              <label className="form-field">
                Located instances
                <input
                  type="number"
                  required
                  min={0}
                  value={editing.observed}
                  onChange={(e) =>
                    setEditing({ ...editing, observed: +e.target.value })
                  }
                />
              </label>
            </div>
            <label className="form-field">
              Evidence / source callouts
              <textarea
                value={editing.evidence}
                onChange={(e) =>
                  setEditing({ ...editing, evidence: e.target.value })
                }
              />
            </label>
            <div className="modal-footer">
              <button
                className="text-button"
                type="button"
                onClick={() => {
                  onDrawing(editing.sheet_id!);
                  setEditing(null);
                }}
              >
                View original sheet <ArrowUpRight size={14} />
              </button>
              <button className="button primary" disabled={busy}>
                <Check size={16} />
                Save review
              </button>
            </div>
            {editing.id && (
              <button
                type="button"
                className="button danger full compact"
                disabled={busy}
                onClick={async () => {
                  if (
                    !confirm(
                      "Remove this inventory row? The previous revision will be retained.",
                    )
                  )
                    return;
                  if (
                    await mutation(
                      `/materials/${editing.id}?version=${project.version}`,
                      undefined,
                      "DELETE",
                    )
                  )
                    setEditing(null);
                }}
              >
                <Trash2 size={14} />
                Remove inventory row
              </button>
            )}
          </form>
        </Modal>
      )}
    </div>
  );
}
createRoot(document.getElementById("root")!).render(<App />);
