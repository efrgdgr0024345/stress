import { useEffect, useState } from "react";
import { Link2, Loader2 } from "lucide-react";
import { api, type Project } from "./types";
import { Dialog } from "./ui";

type Link = {
  id: string;
  status: string;
  evidence: string;
  left_point_id: string;
  right_point_id: string;
  point_id?: string;
  delta_mm: Record<string, string | null>;
};
type Report = {
  revision: number;
  links: Link[];
  candidates: { id: string; sheet_id: string; source_text: string }[];
  candidate_pairs: unknown[];
  can_edit: boolean;
};

export function ContinuationControls({
  project,
  onUpdate,
  selection,
  onClear,
}: {
  project: Project;
  onUpdate: (p: Project) => void;
  selection: string | null;
  onClear: () => void;
}) {
  const [data, setData] = useState<Report | null>(null),
    [open, setOpen] = useState(false),
    [version, setVersion] = useState(project.version);
  const [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  const [decision, setDecision] = useState("PROPOSE");
  const path = `/projects/${project.id}/continuations`;
  useEffect(() => {
    let active = true;
    api<Report>(path)
      .then((v) => {
        if (active) setData(v);
      })
      .catch((e) => {
        if (active) setError(e.message);
      });
    return () => {
      active = false;
    };
  }, [project.id, project.version]);
  useEffect(() => {
    if (selection) {
      setVersion(project.version);
      setOpen(true);
      setError("");
    }
  }, [selection]);
  const link = data?.links.find((l) => l.id === selection);
  const close = () => {
    if (!busy) {
      setOpen(false);
      setError("");
      onClear();
    }
  };
  const name = (n: Project["nodes"][number]) =>
    `Node ${n.number} · ${n.line_id} · ${n.instances.map((i) => project.sheets.find((s) => s.id === i.sheet_id)?.printed_id || "Unverified sheet").join(" / ")}`;
  return (
    <div className="physical-controls">
      <div className="review-actions">
        <button
          className="button secondary"
          disabled={!data}
          onClick={() => {
            onClear();
            setDecision("PROPOSE");
            setVersion(project.version);
            setOpen(true);
            setError("");
          }}
        >
          <Link2 size={16} /> Review continuation
        </button>
        <span className="fine-print">
          {data?.candidates.length || 0} printed reference proposals ·{" "}
          {data?.candidate_pairs.length || 0} reciprocal sheet candidates
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
          title={
            link
              ? "Review saved continuation"
              : "Compare continuation depictions"
          }
          subtitle={`Revision ${version} · Independent engineering coordinates required`}
          onClose={close}
        >
          <form
            key={selection || "new"}
            onSubmit={async (e) => {
              e.preventDefault();
              setBusy(true);
              setError("");
              const form = new FormData(e.currentTarget);
              try {
                const body = link
                  ? {
                      version,
                      decision: form.get("saved_decision"),
                      topology_confirmed: form.has("topology_confirmed"),
                      evidence: form.get("evidence"),
                      confirmed: true,
                    }
                  : {
                      version,
                      decision,
                      left_point_id: form.get("left_point_id"),
                      right_point_id: form.get("right_point_id"),
                      left_size: form.get("left_size"),
                      right_size: form.get("right_size"),
                      left_candidate_id: form.get("left_candidate_id") || null,
                      right_candidate_id:
                        form.get("right_candidate_id") || null,
                      tolerance_text: form.get("tolerance_text"),
                      topology_confirmed: form.has("topology_confirmed"),
                      evidence: form.get("evidence"),
                      confirmed: true,
                    };
                const p = await api<Project>(
                  path + (link ? "/" + link.id : ""),
                  {
                    method: link ? "PATCH" : "POST",
                    body: JSON.stringify(body),
                  },
                );
                onUpdate(p);
                setOpen(false);
                onClear();
              } catch (e) {
                setError((e as Error).message);
              } finally {
                setBusy(false);
              }
            }}
          >
            {error && (
              <p className="error-text" role="alert">
                {error}
              </p>
            )}
            <p className="fine-print">
              Compare the actual continuation interfaces, nominal pipe sizes and
              accepted E/N/EL coordinates. A difference of 25.4 mm or more on
              any axis flags both depictions blue. Drawing distance does not
              prove a connection.
            </p>
            {link ? (
              <>
                <p>
                  <strong>{link.status.replaceAll("_", " ")}</strong>
                </p>
                <p className="fine-print">
                  Recorded deltas:{" "}
                  {Object.entries(link.delta_mm)
                    .map(
                      ([a, v]) => `${a}: ${v === null ? "unknown" : v + " mm"}`,
                    )
                    .join(" · ")}
                </p>
                <label className="form-field">
                  Saved connection decision
                  <select
                    name="saved_decision"
                    aria-label="Saved connection decision"
                    disabled={!data.can_edit}
                  >
                    <option value="WITHDRAW">
                      Withdraw acceptance / require source review
                    </option>
                    {link.point_id && (
                      <option value="REVALIDATE">
                        Revalidate independent source coordinates
                      </option>
                    )}
                  </select>
                </label>
                <p className="fine-print">
                  Withdrawal preserves the point identity and history and flags
                  it for review. Revalidation requires complete, identical
                  independent XYZ coordinates on every depicting source sheet. A
                  previous revision can be restored as a new draft when
                  identities need to be separated.
                </p>
              </>
            ) : (
              <>
                <div className="form-grid">
                  {(
                    [
                      ["left_point_id", "Source point"],
                      ["right_point_id", "Other sheet point"],
                    ] as const
                  ).map(([key, title], index) => (
                    <label className="form-field" key={key}>
                      {title}
                      <select
                        name={key}
                        aria-label={title}
                        required
                        defaultValue={project.nodes[index]?.id}
                        disabled={!data.can_edit}
                      >
                        <option value="">Choose point</option>
                        {project.nodes.map((n) => (
                          <option key={n.id} value={n.id}>
                            {name(n)}
                          </option>
                        ))}
                      </select>
                    </label>
                  ))}
                </div>
                <div className="form-grid">
                  {(
                    [
                      ["left_size", "Source nominal pipe size"],
                      ["right_size", "Other nominal pipe size"],
                    ] as const
                  ).map(([key, title]) => (
                    <label className="form-field" key={key}>
                      {title}
                      <input
                        name={key}
                        aria-label={title}
                        required
                        maxLength={40}
                        placeholder="e.g. 8 in"
                        disabled={!data.can_edit}
                      />
                    </label>
                  ))}
                </div>
                <div className="form-grid">
                  {(
                    [
                      [
                        "left_candidate_id",
                        "Printed reference for source point",
                      ],
                      [
                        "right_candidate_id",
                        "Printed reference for other point",
                      ],
                    ] as const
                  ).map(([key, title]) => (
                    <label className="form-field" key={key}>
                      {title}
                      <select
                        name={key}
                        aria-label={title}
                        disabled={!data.can_edit}
                      >
                        <option value="">Explicit manual source proof</option>
                        {data.candidates.map((c) => (
                          <option key={c.id} value={c.id}>
                            {project.sheets.find((s) => s.id === c.sheet_id)
                              ?.printed_id || "Sheet"}{" "}
                            · {c.source_text.slice(0, 100)}
                          </option>
                        ))}
                      </select>
                    </label>
                  ))}
                </div>
                <label className="form-field">
                  Coordinate comparison tolerance
                  <input
                    name="tolerance_text"
                    aria-label="Coordinate comparison tolerance"
                    defaultValue="0.01 mm"
                    required
                    maxLength={100}
                    disabled={!data.can_edit}
                  />
                </label>
                <label className="form-field">
                  Connection decision
                  <select
                    aria-label="Connection decision"
                    value={decision}
                    onChange={(e) => setDecision(e.target.value)}
                    disabled={!data.can_edit}
                  >
                    <option value="PROPOSE">
                      Save comparison and retain both points
                    </option>
                    <option value="ACCEPT_IDENTITY">
                      Confirm identical interface and share one point ID
                    </option>
                    <option value="REJECT">
                      Reject this proposed connection
                    </option>
                  </select>
                </label>
              </>
            )}
            <label className="form-field">
              Continuation engineering evidence
              <textarea
                name="evidence"
                aria-label="Continuation engineering evidence"
                defaultValue={link?.evidence || ""}
                required
                minLength={10}
                maxLength={3000}
                disabled={!data.can_edit}
              />
            </label>
            <label className="check-field">
              <input
                type="checkbox"
                name="topology_confirmed"
                aria-label="Confirm continuation interface identity and topology"
                required={!link && decision === "ACCEPT_IDENTITY"}
                disabled={!data.can_edit}
              />{" "}
              I inspected the source symbols and confirm the same physical
              interface, component identity and topology.
            </label>
            <div className="modal-actions">
              <button
                type="button"
                className="button secondary"
                onClick={close}
              >
                Cancel
              </button>
              {data.can_edit && (
                <button
                  className="button primary"
                  disabled={busy || (!link && project.nodes.length < 2)}
                >
                  {busy ? (
                    <Loader2 className="spin" size={16} />
                  ) : (
                    <Link2 size={16} />
                  )}{" "}
                  Save continuation review
                </button>
              )}
            </div>
          </form>
        </Dialog>
      )}
    </div>
  );
}
