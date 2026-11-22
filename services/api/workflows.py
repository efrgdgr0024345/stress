"""Catalog review, immutable matches, drawing notes and revision recovery."""

from copy import deepcopy
import hashlib
import json
import re
import zipfile
from typing import Annotated

from fastapi import Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from openpyxl import load_workbook

from packages.pdf import wrapped_schedule

from packages.catalogs import (
    FIELDS,
    MATCH_FIELDS,
    REQUIRED,
    QUALITY,
    exact_match,
    map_rows,
    schedule_lines,
)


class MappingInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sheet: str = Field(min_length=1, max_length=150)
    header_row: int = Field(default=1, ge=1, le=1000)
    first_data_row: int | None = Field(default=None, ge=2, le=100000)
    last_data_row: int | None = Field(default=None, ge=2, le=100000)
    columns: dict[str, Annotated[int, Field(ge=0, le=199)]]
    constants: dict[str, str] = Field(default_factory=dict)
    weight_unit: str = Field(default="N", pattern=r"^(N|kg|lbf)$")
    length_unit: str = Field(default="mm", pattern=r"^(mm|in)$")


class Reason(BaseModel):
    reason: str = Field(min_length=10, max_length=2000)


class MatchInput(Reason):
    version: int = Field(ge=1)
    catalog_version_id: str
    spec: dict[str, str]


class RestoreInput(Reason):
    version: int = Field(ge=1)


class NoteInput(BaseModel):
    version: int = Field(ge=1)
    sheet_id: str
    kind: str = Field(pattern=r"^(FreeText|Square|Circle|Line)$")
    rect: tuple[float, float, float, float]
    text: str = Field(default="", max_length=1000)
    color: str = Field(default="#cc4444", pattern=r"^#[0-9a-fA-F]{6}$")


def install(api):
    def admin(actor=Depends(api.user)):
        if actor["role"] != "admin":
            raise HTTPException(403, "Administrator permission required.")
        return actor

    def catalog(catalog_id, actor):
        with api.db() as conn:
            row = conn.execute(
                "SELECT * FROM catalogs WHERE id=? AND tenant=?",
                (catalog_id, actor["tenant"]),
            ).fetchone()
        if not row:
            raise HTTPException(404, "Catalog not found.")
        record = {**dict(row), "data": json.loads(row["data"])}
        path = api.DATA / "catalogs" / f"{catalog_id}.xlsx"
        if (
            not path.exists()
            or hashlib.sha256(path.read_bytes()).hexdigest() != record["sha256"]
        ):
            raise HTTPException(
                409,
                "Catalog source integrity check failed. Re-register the original workbook.",
            )
        return record, path

    def dataset(version_id, actor):
        with api.db() as conn:
            row = conn.execute(
                "SELECT * FROM catalog_versions WHERE id=? AND tenant=?",
                (version_id, actor["tenant"]),
            ).fetchone()
        if not row:
            raise HTTPException(404, "Catalog version not found.")
        return {**dict(row), "data": json.loads(row["data"])}

    @api.app.get("/api/v1/projects/{project_id}/artifacts/{artifact_id}/pdf")
    def preview_artifact(project_id: str, artifact_id: str, actor=Depends(api.user)):
        with api.db() as conn:
            api.project_read(project_id, actor, conn)
            record = conn.execute(
                "SELECT * FROM artifacts WHERE id=? AND project_id=?",
                (artifact_id, project_id),
            ).fetchone()
        if not record:
            raise HTTPException(404, "Artifact not found.")
        try:
            with zipfile.ZipFile(
                api.DATA / "exports" / f"{artifact_id}.zip"
            ) as archive:
                pdf = archive.read("annotated-review.pdf")
        except (OSError, KeyError, zipfile.BadZipFile):
            raise HTTPException(
                409,
                "The review artifact is unavailable. Regenerate from a new working revision.",
            )
        return api.Response(
            pdf,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'inline; filename="caesar-review-r{record["revision"]}.pdf"'
            },
        )

    @api.app.get("/api/v1/catalog-schema")
    def schema(actor=Depends(api.user)):
        return {
            "fields": FIELDS,
            "required": REQUIRED,
            "match_fields": MATCH_FIELDS,
            "quality": QUALITY,
            "weight_units": ["N", "kg", "lbf"],
            "length_units": ["mm", "in"],
        }

    @api.app.get("/api/v1/catalogs/{catalog_id}/preview")
    def preview(
        catalog_id: str,
        sheet: str | None = None,
        header_row: int = Query(default=1, ge=1, le=1000),
        actor=Depends(api.user),
    ):
        record, path = catalog(catalog_id, actor)
        workbook = load_workbook(path, read_only=True, data_only=True, keep_links=False)
        try:
            name = sheet or workbook.sheetnames[0]
            if name not in workbook.sheetnames:
                raise HTTPException(422, "Worksheet not found.")
            page = workbook[name]
            rows = list(
                page.iter_rows(
                    min_row=header_row,
                    max_row=header_row + 12,
                    max_col=min(page.max_column or 1, 200),
                    values_only=True,
                )
            )
            return {
                "sheet": name,
                "header_row": header_row,
                "headers": [
                    {"index": i, "label": str(v) if v is not None else f"Column {i+1}"}
                    for i, v in enumerate(rows[0] if rows else [])
                ],
                "rows": [
                    [str(v) if v is not None else None for v in r] for r in rows[1:]
                ],
                "total_rows": page.max_row,
                "source_sha256": record["sha256"],
            }
        finally:
            workbook.close()

    @api.app.get("/api/v1/catalogs/{catalog_id}/versions")
    def versions(catalog_id: str, actor=Depends(api.user)):
        catalog(catalog_id, actor)
        with api.db() as conn:
            return [
                {**dict(r), "data": json.loads(r["data"])}
                for r in conn.execute(
                    "SELECT * FROM catalog_versions WHERE catalog_id=? AND tenant=? ORDER BY seq DESC",
                    (catalog_id, actor["tenant"]),
                )
            ]

    @api.app.post("/api/v1/catalogs/{catalog_id}/versions")
    def map_version(catalog_id: str, body: MappingInput, actor=Depends(admin)):
        source, path = catalog(catalog_id, actor)
        start = body.first_data_row or body.header_row + 1
        if start <= body.header_row:
            raise HTTPException(422, "Data must start after the header row.")
        workbook = load_workbook(path, read_only=True, data_only=True, keep_links=False)
        try:
            if body.sheet not in workbook.sheetnames:
                raise HTTPException(422, "Worksheet not found.")
            page = workbook[body.sheet]
            end = body.last_data_row or page.max_row or start
            if end < start or end - start >= 5000:
                raise HTTPException(
                    422,
                    "Select a nonempty range of at most 5,000 source rows per dataset version.",
                )
            rows = enumerate(
                page.iter_rows(
                    min_row=start,
                    max_row=end,
                    max_col=min(page.max_column or 1, 200),
                    values_only=True,
                ),
                start,
            )
            try:
                mapped = map_rows(
                    rows,
                    body.columns,
                    body.constants,
                    body.weight_unit,
                    body.length_unit,
                    source["sha256"] + body.sheet,
                )
            except ValueError as exc:
                raise HTTPException(422, str(exc))
        finally:
            workbook.close()
        data = {
            **mapped,
            "mapping": body.model_dump(),
            "source_sha256": source["sha256"],
            "source_filename": source["filename"],
            "status": (
                "INVALID"
                if mapped["errors"] or not mapped["records"]
                else "PENDING_APPROVAL"
            ),
            "created_by": actor["name"],
            "records_sha256": hashlib.sha256(
                json.dumps(mapped["records"], sort_keys=True).encode()
            ).hexdigest(),
            "approval": None,
        }
        with api.LOCK, api.db() as conn:
            conn.execute("BEGIN IMMEDIATE")
            seq = conn.execute(
                "SELECT COALESCE(MAX(seq),0)+1 FROM catalog_versions WHERE catalog_id=?",
                (catalog_id,),
            ).fetchone()[0]
            record = {
                "id": api.uid(),
                "tenant": actor["tenant"],
                "catalog_id": catalog_id,
                "seq": seq,
                "created": api.now(),
                "data": data,
            }
            conn.execute(
                "INSERT INTO catalog_versions VALUES (?,?,?,?,?,?)",
                (
                    record["id"],
                    record["tenant"],
                    catalog_id,
                    seq,
                    record["created"],
                    json.dumps(data),
                ),
            )
            api.audit(
                conn,
                "catalog:" + catalog_id,
                actor["name"],
                "Mapped catalog dataset",
                f'Version {seq}; {len(mapped["records"])} records; {len(mapped["errors"])} errors',
            )
        api.diag.emit(api.DATA,"catalog.mapping.completed",catalog_id=catalog_id,dataset_id=record["id"],records=len(mapped["records"]),errors=len(mapped["errors"]),state=data["status"])
        return record

    @api.app.post("/api/v1/catalog-versions/{version_id}/approve")
    def approve_dataset(version_id: str, body: Reason, actor=Depends(admin)):
        with api.LOCK, api.db() as conn:
            conn.execute("BEGIN IMMEDIATE")
            record = dataset(version_id, actor)
            if record["data"]["status"] != "PENDING_APPROVAL":
                raise HTTPException(
                    409,
                    "Only an error-free pending dataset may be approved. Approved datasets are immutable.",
                )
            data = record["data"]
            data["status"] = "APPROVED"
            data["approval"] = {
                "actor": actor["name"],
                "user_id": actor["id"],
                "at": api.now(),
                "reason": body.reason,
            }
            conn.execute(
                "UPDATE catalog_versions SET data=? WHERE id=?",
                (json.dumps(data), version_id),
            )
            api.audit(
                conn,
                "catalog:" + record["catalog_id"],
                actor["name"],
                "Approved catalog dataset",
                body.reason,
            )
        api.diag.emit(api.DATA,"catalog.approval.completed",dataset_id=version_id,state="APPROVED")
        return {**record, "data": data}

    @api.app.get("/api/v1/approved-catalogs")
    def approved_catalogs(actor=Depends(api.user)):
        with api.db() as conn:
            values = [
                {**dict(r), "data": json.loads(r["data"])}
                for r in conn.execute(
                    "SELECT * FROM catalog_versions WHERE tenant=? ORDER BY created DESC",
                    (actor["tenant"],),
                )
            ]
        return [v for v in values if v["data"]["status"] == "APPROVED"]

    @api.app.post("/api/v1/projects/{project_id}/materials/{material_id}/catalog-match")
    def match_material(
        project_id: str,
        material_id: str,
        body: MatchInput,
        dry_run: bool = False,
        actor=Depends(api.editor),
    ):
        version = dataset(body.catalog_version_id, actor)
        if version["data"]["status"] != "APPROVED":
            raise HTTPException(
                422, "Approve the dataset before matching engineering components."
            )
        with api.db() as conn:
            p = api.project_read(project_id, actor, conn)
        item = next((m for m in p["materials"] if m["id"] == material_id), None)
        if not item:
            raise HTTPException(404, "Material not found.")
        if item["family"] not in ("flange", "valve"):
            raise HTTPException(
                422, "Catalog matching is for flange and valve inventory."
            )
        if any(k not in MATCH_FIELDS for k in body.spec):
            raise HTTPException(
                422, "Unknown specification key. Use the explicit catalog match fields."
            )
        spec = {**body.spec, "family": item["family"]}
        result = exact_match(version["data"]["records"], spec)
        if dry_run:
            return result
        if result["status"] != "EXACT_MATCH":
            raise HTTPException(
                422,
                f"{result['status']}: {', '.join(result.get('missing',[])) or str(result.get('count',0))+' exact candidates'}. No substitution was applied.",
            )

        def update(p):
            material = next((m for m in p["materials"] if m["id"] == material_id), None)
            if not material:
                raise HTTPException(404, "Material not found.")
            material["catalog_match"] = {
                "catalog_version_id": version["id"],
                "catalog_source_sha256": version["data"]["source_sha256"],
                "catalog_records_sha256": version["data"]["records_sha256"],
                "catalog_approval": version["data"]["approval"],
                "record": deepcopy(result["candidates"][0]),
                "status": (
                    "MANUFACTURER_CONFIRMED"
                    if result["candidates"][0]["quality"] == "MANUFACTURER_CONFIRMED"
                    and spec.get("vendor", "").strip()
                    and spec.get("model", "").strip()
                    else (
                        "ESTIMATED"
                        if result["candidates"][0]["quality"] == "ESTIMATED"
                        else "REFERENCE_ONLY"
                    )
                ),
                "spec": spec,
                "reason": body.reason,
                "matched_by": actor["name"],
                "matched_at": api.now(),
            }
            p["materials_reviewed"] = False
            p["layout_reviewed"] = False

        return api.change(
            project_id,
            body.version,
            actor,
            "Matched component to approved catalog snapshot",
            update,
        )

    @api.app.delete(
        "/api/v1/projects/{project_id}/materials/{material_id}/catalog-match"
    )
    def clear_match(
        project_id: str, material_id: str, version: int, actor=Depends(api.editor)
    ):
        def update(p):
            material = next((m for m in p["materials"] if m["id"] == material_id), None)
            if not material:
                raise HTTPException(404, "Material not found.")
            material.pop("catalog_match", None)
            material["auto_match_disabled"]=True
            p["materials_reviewed"] = False
            p["layout_reviewed"] = False

        return api.change(
            project_id, version, actor, "Removed component catalog match", update
        )

    @api.app.delete("/api/v1/projects/{project_id}/materials/{material_id}")
    def remove_material(
        project_id: str, material_id: str, version: int, actor=Depends(api.editor)
    ):
        def update(p):
            if not any(m["id"] == material_id for m in p["materials"]):
                raise HTTPException(404, "Material not found.")
            p.setdefault("automation_tombstones",{}).setdefault("material_ids",[]).append(material_id)
            p["materials"] = [m for m in p["materials"] if m["id"] != material_id]
            p["materials_reviewed"] = False
            p["layout_reviewed"] = False

        return api.change(project_id, version, actor, "Removed inventory row", update)

    @api.app.get("/api/v1/projects/{project_id}/schedules")
    def schedules(project_id: str, actor=Depends(api.user)):
        with api.db() as conn:
            p = api.project_read(project_id, actor, conn)
        return {
            s["id"]: wrapped_schedule(
                [
                    m
                    for m in p["materials"]
                    if m["sheet_id"] == s["id"] and m["family"] in ("flange", "valve")
                ],
                min(370, s["width"] - (s.get("table") or [50, 50])[0] - 8),
            )
            for s in p["sheets"]
        }

    @api.app.get("/api/v1/projects/{project_id}/revisions/{revision}")
    def revision(project_id: str, revision: int, actor=Depends(api.user)):
        with api.db() as conn:
            api.project_read(project_id, actor, conn)
            row = conn.execute(
                "SELECT data FROM revisions WHERE id=? AND version=?",
                (project_id, revision),
            ).fetchone()
        if not row:
            raise HTTPException(404, "Revision not found.")
        value = json.loads(row["data"])
        value["issues"] = api.validate(value)
        return value

    @api.app.get("/api/v1/projects/{project_id}/revisions/{revision}/diff")
    def revision_diff(project_id: str, revision: int, actor=Depends(api.user)):
        old = revision_endpoint(project_id, revision, actor)
        with api.db() as conn:
            current = api.project_read(project_id, actor, conn)
        changes = {}
        for key in ("nodes", "materials", "sheets", "annotations"):
            before = {v["id"]: v for v in old.get(key, [])}
            after = {v["id"]: v for v in current.get(key, [])}
            changes[key] = {
                "added": len(after.keys() - before.keys()),
                "removed": len(before.keys() - after.keys()),
                "modified": sum(
                    before[k] != after[k] for k in before.keys() & after.keys()
                ),
            }
        return {"from": revision, "to": current["version"], "changes": changes}

    @api.app.post("/api/v1/projects/{project_id}/revisions/{revision}/restore")
    def restore(
        project_id: str, revision: int, body: RestoreInput, actor=Depends(api.editor)
    ):
        saved = revision_endpoint(project_id, revision, actor)

        def update(p):
            for key in ("nodes", "materials", "sheets", "annotations", "numbering_map"):
                p[key] = deepcopy(saved.get(key, []))
            p["materials_reviewed"] = False
            p["layout_reviewed"] = False
            p.pop("review_approval", None)

        return api.change(
            project_id,
            body.version,
            actor,
            f"Restored revision {revision} as a new draft: {body.reason}",
            update,
        )

    # Keep the path argument and the endpoint callable separate for restoration.
    revision_endpoint = revision

    @api.app.post("/api/v1/projects/{project_id}/annotations")
    def add_note(project_id: str, body: NoteInput, actor=Depends(api.editor)):
        def update(p):
            save_note(p, body)

        return api.change(
            project_id, body.version, actor, "Added native drawing annotation", update
        )

    @api.app.patch("/api/v1/projects/{project_id}/annotations/{note_id}")
    def patch_note(
        project_id: str, note_id: str, body: NoteInput, actor=Depends(api.editor)
    ):
        return api.change(
            project_id,
            body.version,
            actor,
            "Edited native drawing annotation",
            lambda p: save_note(p, body, note_id),
        )

    def save_note(p, body, note_id=None):
        sheet = api.sheet_for(p, body.sheet_id)
        x1, y1, x2, y2 = body.rect
        if not all(
            0 <= x <= sheet["width"] and 0 <= y <= sheet["height"]
            for x, y in [(x1, y1), (x2, y2)]
        ) or (body.kind != "Line" and (x2 - x1 < 8 or y2 - y1 < 8)):
            raise HTTPException(
                422, "Keep a nonempty annotation within the unrotated PDF page bounds."
            )
        if body.kind == "FreeText" and not body.text.strip():
            raise HTTPException(422, "A text annotation needs text.")
        notes = p.setdefault("annotations", [])
        if len(notes) >= 500 and not note_id:
            raise HTTPException(422, "A project supports up to 500 free annotations.")
        note = next((n for n in notes if n["id"] == note_id), None) if note_id else None
        if note_id and not note:
            raise HTTPException(404, "Annotation not found.")
        value = body.model_dump(exclude={"version"})
        if note:
            note.update(value)
        else:
            notes.append({**value, "id": api.uid()})
        p["layout_reviewed"] = False

    @api.app.delete("/api/v1/projects/{project_id}/annotations/{note_id}")
    def delete_note(
        project_id: str, note_id: str, version: int, actor=Depends(api.editor)
    ):
        def update(p):
            if not any(n["id"] == note_id for n in p.get("annotations", [])):
                raise HTTPException(404, "Annotation not found.")
            p["annotations"] = [n for n in p["annotations"] if n["id"] != note_id]
            p["layout_reviewed"] = False

        return api.change(
            project_id, version, actor, "Deleted native drawing annotation", update
        )

    @api.app.get("/api/v1/lessons")
    def lessons():
        path = api.ROOT / "LESSONS_LEARNED.md"
        if not path.exists():
            return {"lessons": [], "source": "LESSONS_LEARNED.md"}
        content = path.read_text(encoding="utf-8")
        values = []
        for heading, body in re.findall(
            r"^## (LESSON-\d+[^\n]*)\n(.*?)(?=^## |\Z)", content, re.M | re.S
        ):
            fields = dict(
                re.findall(
                    r"^- (Category|Status|Lesson|Action|Evidence): (.+)$", body, re.M
                )
            )
            values.append(
                {
                    "id": heading.split(" ")[0],
                    "title": heading.split("—", 1)[-1].strip(),
                    **{key.lower(): value for key, value in fields.items()},
                }
            )
        return {
            "lessons": values,
            "source": "LESSONS_LEARNED.md",
            "sha256": hashlib.sha256(content.encode()).hexdigest(),
            "github_url": "https://github.com/efrgdgr0024345/stress/blob/main/LESSONS_LEARNED.md",
        }
