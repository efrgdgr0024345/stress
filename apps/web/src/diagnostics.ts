import { appPath } from "./paths";
type View =
  | "projects"
  | "workspace"
  | "sheets"
  | "materials"
  | "validation"
  | "activity"
  | "catalogs"
  | "logs"
  | "admin"
  | "processing"
  | "results"
  | "login"
  | "unknown";
type BrowserEvent = {
  kind:
    | "navigation"
    | "api"
    | "error"
    | "rejection"
    | "console"
    | "resource"
    | "action";
  view: View;
  client_at: number;
  action?:
    | "load_project"
    | "upload_pdf"
    | "export_bundle"
    | "save_node"
    | "save_annotation"
    | "form_invalid"
    | "check_updates"
    | "install_update"
    | "rollback_update";
  request_id?: string;
  status?: number;
  duration_ms?: number;
  error_type?: string;
  frame?: string;
};
const queue: BrowserEvent[] = [];
let currentView: View = "login",
  started = false,
  sending = false,
  dropped = 0;
export function browserEvent(event: Omit<BrowserEvent, "view" | "client_at">) {
  queue.push({ ...event, view: currentView, client_at: Date.now() });
  if (queue.length > 200) {
    queue.shift();
    dropped++;
  }
}
export function navigation(view: View) {
  currentView = view;
  browserEvent({ kind: "navigation" });
}
function errorFields(value: unknown) {
  const names = [
    "Error",
    "TypeError",
    "ReferenceError",
    "SyntaxError",
    "RangeError",
    "URIError",
    "EvalError",
    "AggregateError",
    "DOMException",
  ];
  const error = value instanceof Error ? value : undefined;
  const match = error?.stack?.match(
    /(?:\/assets\/|\/src\/)(?:[\w-]+\/)*([\w.-]+\.(?:m?js|tsx?)):(\d+):(\d+)/,
  );
  return {
    error_type:
      error && names.includes(error.name) ? error.name : "UnknownError",
    frame: match ? `${match[1]}:${match[2]}:${match[3]}` : "",
  };
}
export function browserSnapshot() {
  return { pending: [...queue], dropped_in_this_tab: dropped };
}
export async function flushDiagnostics() {
  if (sending || !queue.length) return;
  sending = true;
  const batch = queue.splice(0, 20);
  try {
    const response = await fetch(appPath("api/v1/system/logs/client"), {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ events: batch }),
    });
    if (!response.ok) {
      queue.unshift(...batch);
      while (queue.length > 200) {
        queue.shift();
        dropped++;
      }
    }
  } catch {
    queue.unshift(...batch);
    while (queue.length > 200) {
      queue.shift();
      dropped++;
    }
  } finally {
    sending = false;
  }
}
export function startDiagnostics() {
  if (started) return;
  started = true;
  window.addEventListener(
    "error",
    (event) =>
      browserEvent({
        kind: event.error ? "error" : "resource",
        ...errorFields(event.error),
      }),
    true,
  );
  window.addEventListener("unhandledrejection", (event) =>
    browserEvent({ kind: "rejection", ...errorFields(event.reason) }),
  );
  document.addEventListener(
    "invalid",
    () => browserEvent({ kind: "action", action: "form_invalid" }),
    true,
  );
  const original = console.error.bind(console);
  console.error = (...args: unknown[]) => {
    browserEvent({
      kind: "console",
      ...errorFields(args.find((arg) => arg instanceof Error)),
    });
    original(...args);
  };
  setInterval(() => {
    if (document.visibilityState === "visible") void flushDiagnostics();
  }, 10000);
}
