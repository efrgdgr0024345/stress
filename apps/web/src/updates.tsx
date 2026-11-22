import { useEffect, useState } from "react";
import { api } from "./types";
import { Dialog } from "./ui";
import { browserEvent } from "./diagnostics";
type Status = {
  current: string;
  available: { version?: string };
  state: { status?: string; message?: string };
  configured: boolean;
  runner_ready: boolean;
  automatic: boolean;
  rollback_available: boolean;
  rollback_blocked?: string;
};
export function Updates({ onClose }: { onClose: () => void }) {
  const [status, setStatus] = useState<Status | null>(null),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  const refresh = () =>
    api<Status>("/system/updates")
      .then(setStatus)
      .catch((e) => setError(e.message));
  useEffect(() => {
    refresh();
    const id = setInterval(refresh, 5000);
    return () => clearInterval(id);
  }, []);
  const action = async (name: string) => {
    if (name === "check" || name === "install" || name === "rollback")
      browserEvent({
        kind: "action",
        action:
          name === "check"
            ? "check_updates"
            : name === "install"
              ? "install_update"
              : "rollback_update",
      });
    setBusy(true);
    setError("");
    try {
      await api(`/system/updates/${name}`, { method: "POST" });
      await refresh();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <Dialog
      title="System updates"
      subtitle="Reviewed GitHub releases · Backups and rollback"
      onClose={onClose}
    >
      {error && <p role="alert">{error}</p>}
      {status && (
        <>
          <p>
            Installed: <b>{status.current}</b> · Available:{" "}
            <b>{status.available.version || "Check for updates"}</b>
          </p>
          <p role="status">
            {status.state.status || "Idle"} {status.state.message || ""}
          </p>
          {!status.runner_ready && (
            <p>
              Enable the update cron runner in cPanel Terminal using{" "}
              <code>python scripts/enable_updates.py</code> from the
              application’s Python environment.
            </p>
          )}
          <p>
            Updates use a short maintenance window. Compatible code updates keep
            your drawings and credentials. Dependency or database migrations
            require a manual upgrade.
          </p>
          {status.rollback_blocked && (
            <p role="status">{status.rollback_blocked}</p>
          )}
          <div className="heading-actions">
            <button
              className="button secondary"
              disabled={busy}
              onClick={() => action("check")}
            >
              Check GitHub
            </button>
            <button
              className="button"
              disabled={
                busy ||
                !status.runner_ready ||
                !status.available.version ||
                status.available.version === status.current ||
                ["queued", "running"].includes(status.state.status || "")
              }
              onClick={() => action("install")}
            >
              Install update
            </button>
            <button
              className="button secondary"
              disabled={
                busy || !status.runner_ready || !status.rollback_available
              }
              onClick={() => action("rollback")}
            >
              Roll back
            </button>
          </div>
          <label>
            <input
              type="checkbox"
              checked={status.automatic}
              disabled={busy || !status.runner_ready}
              onChange={(e) =>
                action(e.target.checked ? "enable-auto" : "disable-auto")
              }
            />{" "}
            Automatically install compatible stable releases
          </label>
        </>
      )}
    </Dialog>
  );
}
