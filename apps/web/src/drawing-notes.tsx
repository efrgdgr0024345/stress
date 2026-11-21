import { useState } from "react";
import { Check, FileText, Plus, Trash2 } from "lucide-react";
import { type DrawingNote, type Project, type Sheet } from "./types";
import { Dialog } from "./ui";
type Mutation = (
  path: string,
  body: unknown,
  method?: string,
) => Promise<Project | undefined>;
export function DrawingNotes({
  project,
  sheet,
  initial,
  onClose,
  mutation,
  busy,
}: {
  project: Project;
  sheet: Sheet;
  initial?: DrawingNote;
  onClose: () => void;
  mutation: Mutation;
  busy: boolean;
}) {
  const blank: Omit<DrawingNote, "id"> = {
    sheet_id: sheet.id,
    kind: "FreeText",
    rect: [
      35,
      80,
      Math.min(sheet.width - 15, 255),
      Math.min(sheet.height - 15, 150),
    ],
    text: "Engineering review note",
    color: "#007aff",
  };
  const [editing, setEditing] = useState<Partial<DrawingNote>>(
    initial || blank,
  );
  const notes = (project.annotations || []).filter(
    (n) => n.sheet_id === sheet.id,
  );
  const save = async () => {
    const p = await mutation(
      `/annotations${editing.id ? "/" + editing.id : ""}`,
      {
        version: project.version,
        sheet_id: sheet.id,
        kind: editing.kind,
        rect: editing.rect,
        text: editing.text,
        color: editing.color,
      },
      editing.id ? "PATCH" : "POST",
    );
    if (p) onClose();
  };
  return (
    <Dialog
      title="Drawing annotations"
      subtitle="These are graphic review notes, not engineering dimensions. Every object remains editable in the exported PDF."
      onClose={onClose}
      wide
    >
      <div className="form-grid">
        <label className="form-field">
          Object type
          <select
            value={editing.kind}
            onChange={(e) =>
              setEditing({
                ...editing,
                kind: e.target.value as DrawingNote["kind"],
              })
            }
          >
            <option value="FreeText">Text note</option>
            <option value="Square">Rectangle</option>
            <option value="Circle">Ellipse / circle</option>
            <option value="Line">Line</option>
          </select>
        </label>
        <label className="form-field">
          Colour
          <input
            aria-label="Annotation colour"
            type="color"
            value={editing.color}
            onChange={(e) => setEditing({ ...editing, color: e.target.value })}
          />
        </label>
      </div>
      {editing.kind === "FreeText" && (
        <label className="form-field">
          Note text
          <textarea
            aria-label="Note text"
            rows={3}
            value={editing.text}
            onChange={(e) => setEditing({ ...editing, text: e.target.value })}
          />
        </label>
      )}
      <div className="form-grid">
        {[
          "Left / start X",
          "Top / start Y",
          "Right / end X",
          "Bottom / end Y",
        ].map((label, index) => (
          <label key={index} className="form-field">
            {label} (PDF points)
            <input
              type="number"
              step="0.1"
              min={0}
              value={editing.rect?.[index] ?? 0}
              onChange={(e) => {
                const rect = [
                  ...(editing.rect || blank.rect),
                ] as DrawingNote["rect"];
                rect[index] = +e.target.value;
                setEditing({ ...editing, rect });
              }}
            />
          </label>
        ))}
      </div>
      <div className="inline-actions">
        <button className="button primary" disabled={busy} onClick={save}>
          <Check size={15} />
          {editing.id ? "Save annotation" : "Add annotation"}
        </button>
        <button className="button secondary" onClick={() => setEditing(blank)}>
          <Plus size={15} />
          New object
        </button>
        {editing.id && (
          <button
            className="button danger compact"
            disabled={busy}
            onClick={async () => {
              if (
                await mutation(
                  `/annotations/${editing.id}?version=${project.version}`,
                  undefined,
                  "DELETE",
                )
              )
                setEditing(blank);
            }}
          >
            <Trash2 size={14} />
            Delete object
          </button>
        )}
      </div>
      <h3 style={{ marginTop: 25, marginBottom: 12 }}>
        Objects on this sheet · {notes.length}
      </h3>
      {notes.map((note) => (
        <button
          className="note-item"
          key={note.id}
          style={{ width: "100%", textAlign: "left" }}
          onClick={() => setEditing(note)}
        >
          <FileText size={16} style={{ color: note.color }} />
          <span>
            {note.kind} ·{" "}
            {note.text || note.rect.map((n) => n.toFixed(1)).join(", ")}
          </span>
          <span style={{ flex: 0, fontSize: 10 }}>Edit</span>
        </button>
      ))}
      {!notes.length && (
        <p className="fine-print">
          No free annotations yet. Point bubbles and leaders are edited in the
          point inspector.
        </p>
      )}
    </Dialog>
  );
}
