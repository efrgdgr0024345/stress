import { useState } from "react";
import { ArrowDownToLine, RotateCcw, Search } from "lucide-react";
import { api, type Project } from "./types";
import { Dialog } from "./ui";
type Diff = {
  from: number;
  to: number;
  changes: Record<string, { added: number; removed: number; modified: number }>;
};
export function RevisionActions({
  project,
  revision,
  mutation,
  notify,
}: {
  project: Project;
  revision: number;
  mutation: (
    path: string,
    body: unknown,
    method?: string,
  ) => Promise<Project | undefined>;
  notify: (m: string, e?: boolean) => void;
}) {
  const [diff, setDiff] = useState<Diff | null>(null),
    [reason, setReason] = useState(""),
    [busy, setBusy] = useState(false);
  const inspect = async () => {
    try {
      setDiff(await api(`/projects/${project.id}/revisions/${revision}/diff`));
    } catch (e) {
      notify((e as Error).message, true);
    }
  };
  const download = async () => {
    try {
      const snapshot = await api<Project>(
          `/projects/${project.id}/revisions/${revision}`,
        ),
        url = URL.createObjectURL(
          new Blob([JSON.stringify(snapshot, null, 2)], {
            type: "application/json",
          }),
        );
      const a = document.createElement("a");
      a.href = url;
      a.download = `caesar-revision-${revision}.json`;
      a.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (e) {
      notify((e as Error).message, true);
    }
  };
  const restore = async () => {
    setBusy(true);
    try {
      if (
        await mutation(`/revisions/${revision}/restore`, {
          version: project.version,
          reason,
        })
      ) {
        setDiff(null);
        notify(
          `Revision ${revision} restored as a new draft. All earlier snapshots remain intact.`,
        );
      }
    } finally {
      setBusy(false);
    }
  };
  return (
    <>
      <button className="text-button" onClick={inspect}>
        <Search size={13} />
        Inspect
      </button>
      {diff && (
        <Dialog
          title={`Revision ${revision} · comparison`}
          subtitle={`Compared with current revision ${project.version}. Recovery creates a new draft and never overwrites history.`}
          onClose={() => setDiff(null)}
        >
          <div className="responsive-table">
            <table>
              <thead>
                <tr>
                  <th>OBJECTS</th>
                  <th>ADDED</th>
                  <th>REMOVED</th>
                  <th>CHANGED</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(diff.changes).map(([kind, c]) => (
                  <tr key={kind}>
                    <td>{kind}</td>
                    <td>{c.added}</td>
                    <td>{c.removed}</td>
                    <td>{c.modified}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <button
            className="button secondary full"
            style={{ marginTop: 18 }}
            onClick={download}
          >
            <ArrowDownToLine size={15} />
            Download revision snapshot
          </button>
          {revision !== project.version && (
            <>
              <label className="form-field" style={{ marginTop: 22 }}>
                Recovery reason
                <textarea
                  value={reason}
                  onChange={(e) => setReason(e.target.value)}
                  placeholder="Explain why this earlier model should become the new working draft…"
                  minLength={10}
                />
              </label>
              <button
                className="button primary full"
                disabled={busy || reason.trim().length < 10}
                onClick={restore}
              >
                <RotateCcw size={15} />
                Restore as a new draft
              </button>
              <p className="fine-print" style={{ marginTop: 12 }}>
                Material and layout approvals are reset so the restored drawing
                is reviewed again.
              </p>
            </>
          )}
        </Dialog>
      )}
    </>
  );
}
