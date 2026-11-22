import { useState } from "react";
import { ArchiveRestore, Loader2 } from "lucide-react";
import { api, label } from "./types";
import { APP_BASE } from "./paths";
import { Dialog } from "./ui";
type Preview = {
  plan_sha256: string;
  counts: Record<string, number>;
  processing: boolean;
  mfa: { enabled: boolean };
};
export function WorkspaceResetCard() {
  const [preview, setPreview] = useState<Preview | null>(null),
    [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  return (
    <section className="connection-card">
      <div className="connection-heading">
        <span className="connection-icon">
          <ArchiveRestore size={25} />
        </span>
        <div>
          <h2>Start a clean test workspace</h2>
          <p>
            Clear project data after testing and keep your system ready to use.
          </p>
        </div>
      </div>
      <p className="connection-hint">
        Projects, source drawings, generated exports, review issues and
        temporary software-test accounts are archived privately, then removed
        from the active workspace. Your administrator login, genuine users,
        reference catalogs, connections, updater and paid-use counters are
        retained.
      </p>
      <button
        className="button secondary"
        disabled={busy}
        onClick={async () => {
          setBusy(true);
          setError("");
          try {
            setPreview(await api("/system/workspace-reset"));
          } catch (e) {
            setError((e as Error).message);
          } finally {
            setBusy(false);
          }
        }}
      >
        <ArchiveRestore size={16} /> Preview project-data reset
      </button>
      {error && !preview && (
        <p className="error-text" role="alert">
          {error}
        </p>
      )}
      {preview && (
        <Dialog
          title="Clear project and test data"
          subtitle="A private recovery snapshot is created before the active data is removed."
          onClose={() => {
            if (!busy) setPreview(null);
          }}
        >
          <div className="review-limitations">
            {Object.entries(preview.counts).map(([key, count]) => (
              <p key={key}>
                <b>{count}</b> {label(key).toLowerCase()}
              </p>
            ))}
          </div>
          {preview.processing ? (
            <p>
              Finish or cancel the pending processing jobs before clearing the
              workspace.
            </p>
          ) : (
            <form
              onSubmit={async (event) => {
                event.preventDefault();
                const form = new FormData(event.currentTarget);
                setBusy(true);
                setError("");
                try {
                  await api("/system/workspace-reset", {
                    method: "POST",
                    body: JSON.stringify({
                      plan_sha256: preview.plan_sha256,
                      confirmation: form.get("confirmation"),
                      code: form.get("code") || null,
                    }),
                  });
                  window.location.assign(APP_BASE);
                } catch (e) {
                  setError((e as Error).message);
                } finally {
                  setBusy(false);
                }
              }}
            >
              <label className="form-field">
                Type CLEAR PROJECT DATA to confirm
                <input
                  name="confirmation"
                  autoComplete="off"
                  required
                  pattern="CLEAR PROJECT DATA"
                />
              </label>
              {preview.mfa.enabled && (
                <label className="form-field">
                  Authenticator or recovery code
                  <input
                    name="code"
                    autoComplete="one-time-code"
                    maxLength={80}
                  />
                  <small>
                    A factor check in this session in the last five minutes is
                    accepted.
                  </small>
                </label>
              )}
              {error && (
                <p className="error-text" role="alert">
                  {error}
                </p>
              )}
              <div className="modal-footer">
                <button
                  type="button"
                  className="button secondary"
                  disabled={busy}
                  onClick={() => setPreview(null)}
                >
                  Cancel
                </button>
                <button
                  className="button primary"
                  disabled={busy}
                  style={{ background: "#d4494a", borderColor: "#cf3b3d" }}
                >
                  {busy ? (
                    <Loader2 className="spin" size={16} />
                  ) : (
                    <ArchiveRestore size={16} />
                  )}
                  Archive and clear projects
                </button>
              </div>
            </form>
          )}
        </Dialog>
      )}
    </section>
  );
}
