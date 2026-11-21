from decimal import Decimal
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
import zipfile

import fitz
from fastapi.testclient import TestClient
from packages.pdf import content_hash
from services.api import main


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.original_data = main.DATA
        main.DATA = Path(self.temp.name)
        self.context = TestClient(main.app)
        self.client = self.context.__enter__()
        self.client.post("/api/v1/auth/local")

    def tearDown(self):
        self.context.__exit__(None, None, None)
        main.DATA = self.original_data
        self.temp.cleanup()

    def create(self):
        r = self.client.post(
            "/api/v1/projects", json={"title": "Test project", "line_id": "TEST-001"}
        )
        self.assertEqual(r.status_code, 201, r.text)
        self.assertIsInstance(r.json()["issues"], list)
        return r.json()

    def pdf(self, rotate=0, crop=False):
        doc = fitz.open()
        page = doc.new_page(width=600, height=500)
        page.insert_text((90, 100), "Test original engineering content")
        if crop:
            page.set_cropbox(fitz.Rect(40, 30, 560, 470))
        page.set_rotation(rotate)
        result = doc.tobytes()
        doc.close()
        return result

    def upload(self, p, content=None):
        r = self.client.post(
            f"/api/v1/projects/{p['id']}/sources?version={p['version']}",
            files={"file": ("drawing.pdf", content or self.pdf(), "application/pdf")},
        )
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()

    def node(self, p, dimension="", evidence=""):
        return {
            "version": p["version"],
            "line_id": p["line_id"],
            "route": "main",
            "order": 1,
            "kind": "support",
            "dimension": dimension,
            "evidence": evidence,
            "instances": [
                {
                    "sheet_id": p["sheets"][0]["id"],
                    "anchor": [100, 120],
                    "bubble": [150, 100],
                }
            ],
        }

    def test_auth_and_tenant_isolation(self):
        self.assertEqual(TestClient(main.app).get("/api/v1/projects").status_code, 401)
        p = self.create()
        with main.db() as conn:
            conn.execute(
                "UPDATE projects SET tenant=? WHERE id=?", ("different-tenant", p["id"])
            )
        self.assertEqual(
            self.client.get(f"/api/v1/projects/{p['id']}").status_code, 404
        )
        self.assertEqual(
            self.client.post(
                "/api/v1/projects", json={"title": " ", "line_id": "X"}
            ).status_code,
            422,
        )

    def test_upload_pages_immutable_hash_and_duplicate_rejection(self):
        raw = self.pdf(90, True)
        p = self.upload(self.create(), raw)
        s = p["sheets"][0]
        self.assertEqual(s["rotation"], 90)
        self.assertEqual(s["width"], 520)
        self.assertEqual(s["height"], 440)
        self.assertEqual(s["sha256"], hashlib.sha256(raw).hexdigest())
        response = self.client.get(
            f"/api/v1/projects/{p['id']}/sources/{s['source_id']}"
        )
        self.assertEqual(response.content, raw)
        response = self.client.post(
            f"/api/v1/projects/{p['id']}/sources?version={p['version']}",
            files={"file": ("duplicate.pdf", raw)},
        )
        self.assertEqual(response.status_code, 409, response.text)
        self.assertEqual(
            len(list((main.DATA / "sources").glob("*.pdf"))), 2
        )  # seed + source

    def test_bad_signatures_active_content_and_missing_evidence_rejected(self):
        p = self.create()
        response = self.client.post(
            f"/api/v1/projects/{p['id']}/sources?version=1",
            files={"file": ("bad.pdf", b"not a pdf")},
        )
        self.assertEqual(response.status_code, 415)
        doc = fitz.open(stream=self.pdf(), filetype="pdf")
        x = doc.get_new_xref()
        doc.update_object(x, "<< /S /JavaScript /JS (app.alert(1)) >>")
        doc.xref_set_key(doc.pdf_catalog(), "OpenAction", f"{x} 0 R")
        response = self.client.post(
            f"/api/v1/projects/{p['id']}/sources?version=1",
            files={"file": ("active.pdf", doc.tobytes())},
        )
        self.assertEqual(response.status_code, 422, response.text)
        doc.close()
        p = self.upload(p)
        response = self.client.post(
            f"/api/v1/projects/{p['id']}/nodes", json=self.node(p, "1200 mm")
        )
        self.assertEqual(response.status_code, 422)

    def test_stale_version_and_viewer_write_denied(self):
        p = self.upload(self.create())
        r = self.client.post(
            f"/api/v1/projects/{p['id']}/nodes",
            json=self.node(p, "2 1/8 in", "Explicit dimension at source callout"),
        )
        self.assertEqual(r.status_code, 200, r.text)
        updated = r.json()
        self.assertEqual(Decimal(updated["nodes"][0]["station_mm"]), Decimal("53.975"))
        self.assertEqual(updated["nodes"][0]["dimension_input"], "2 1/8 in")
        self.assertEqual(updated["nodes"][0]["reasons"], [])
        self.assertEqual(
            self.client.post(
                f"/api/v1/projects/{p['id']}/nodes", json=self.node(p)
            ).status_code,
            409,
        )
        with main.db() as conn:
            conn.execute("UPDATE users SET role='viewer' WHERE id='local-engineer'")
        self.assertEqual(
            self.client.post(
                "/api/v1/projects", json={"title": "bad", "line_id": "bad"}
            ).status_code,
            403,
        )

    def test_export_native_editable_objects_source_integrity_and_idempotency(self):
        p = self.client.get("/api/v1/projects").json()[0]
        r = self.client.post(
            f"/api/v1/projects/{p['id']}/exports", json={"version": p["version"]}
        )
        self.assertEqual(r.status_code, 200, r.text)
        a = r.json()
        self.assertEqual(
            self.client.post(
                f"/api/v1/projects/{p['id']}/exports", json={"version": p["version"]}
            ).json()["id"],
            a["id"],
        )
        bundle = self.client.get(
            f"/api/v1/projects/{p['id']}/artifacts/{a['id']}/download"
        )
        with zipfile.ZipFile(io.BytesIO(bundle.content)) as archive:
            manifest = json.loads(archive.read("annotation-manifest.json"))
            qa = json.loads(archive.read("qa.json"))
            self.assertTrue(qa["source_content_unchanged"])
            self.assertGreater(len(manifest), len(p["nodes"]) * 3)
            self.assertEqual(len({m["name"] for m in manifest}), len(manifest))
            annotated = fitz.open(
                stream=archive.read("annotated-review.pdf"), filetype="pdf"
            )
            for i, page in enumerate(annotated):
                with fitz.open(
                    main.DATA / "sources" / f"{p['sheets'][i]['source_id']}.pdf"
                ) as src:
                    self.assertEqual(
                        content_hash(page),
                        content_hash(src[p["sheets"][i]["page_index"]]),
                    )
                seen = set()
                for annotation in page.annots():
                    if annotation.type[1] not in seen:
                        annotation.set_opacity(0.8)
                        annotation.update()
                        seen.add(annotation.type[1])
                self.assertTrue({"Circle", "FreeText", "Line", "Square"}.issubset(seen))
            result = annotated.tobytes()
            annotated.close()
            with fitz.open(stream=result, filetype="pdf") as reopened:
                self.assertEqual(
                    sum(1 for pg in reopened for _ in pg.annots()), len(manifest)
                )

    def test_rotated_crop_export_and_graphics_do_not_change_station(self):
        for rotation in [0, 90, 180, 270]:
            p = self.upload(self.create(), self.pdf(rotation, True))
            p = self.client.post(
                f"/api/v1/projects/{p['id']}/nodes",
                json=self.node(p, "100 mm", "Source dimension"),
            ).json()
            n = p["nodes"][0]
            payload = self.node(p, "100 mm", "Source dimension")
            payload["instances"][0]["bubble"] = [190, 160]
            p = self.client.patch(
                f"/api/v1/projects/{p['id']}/nodes/{n['id']}", json=payload
            ).json()
            self.assertEqual(p["nodes"][0]["station_mm"], "100")
            r = self.client.post(
                f"/api/v1/projects/{p['id']}/exports", json={"version": p["version"]}
            )
            self.assertEqual(r.status_code, 200, r.text)

    def test_materials_null_catalog_values_and_audit(self):
        p = self.upload(self.create())
        sid = p["sheets"][0]["id"]
        body = {
            "version": p["version"],
            "sheet_id": sid,
            "item_no": "9",
            "family": "valve",
            "description": "Unknown DBB valve",
            "size": "2 in",
            "quantity": 3,
            "observed": 0,
            "evidence": "Source list",
        }
        r = self.client.post(f"/api/v1/projects/{p['id']}/materials", json=body)
        self.assertEqual(r.status_code, 200, r.text)
        p = r.json()
        codes = {i["code"] for i in p["issues"]}
        self.assertTrue({"NO_EXACT_MATCH", "QUANTITY_MISMATCH"}.issubset(codes))
        self.assertNotIn("weight", p["materials"][0])
        history = self.client.get(f"/api/v1/projects/{p['id']}/audit").json()
        self.assertEqual(len(history["revisions"]), 3)
        self.assertEqual(
            history["events"][0]["action"], "Added materials inventory row"
        )

    def test_cross_origin_write_rejected(self):
        response = self.client.post(
            "/api/v1/projects",
            headers={"Origin": "https://other.example"},
            json={"title": "bad", "line_id": "bad"},
        )
        self.assertEqual(response.status_code, 403)

    def test_branch_tee_and_repeated_continuation_identity(self):
        p = self.upload(self.create())
        body = self.node(p, "0 mm", "Synthetic dimension source")
        body["kind"] = "tee"
        p = self.client.post(f"/api/v1/projects/{p['id']}/nodes", json=body).json()
        tee = p["nodes"][0]
        branch = self.node(p, "200 mm", "Synthetic branch dimension")
        branch.update(route="branch-01", takeoff_id=tee["id"])
        response = self.client.post(f"/api/v1/projects/{p['id']}/nodes", json=branch)
        self.assertEqual(response.status_code, 200, response.text)
        p = response.json()
        self.assertEqual(p["nodes"][1]["number"], 100)
        graph = self.client.get(f"/api/v1/projects/{p['id']}/graph").json()
        self.assertEqual(graph["edges"][0]["from"], tee["id"])
        self.assertEqual(
            self.client.delete(
                f"/api/v1/projects/{p['id']}/nodes/{tee['id']}?version={p['version']}"
            ).status_code,
            422,
        )
        # A second source depicts the same already established physical point.
        p = self.upload(p, self.pdf(180))
        body = self.node(p, "0 mm", "Synthetic shared-interface confirmation")
        body["kind"] = "continuation"
        body["instances"].append(
            {
                "sheet_id": p["sheets"][1]["id"],
                "anchor": [100, 150],
                "bubble": [140, 150],
            }
        )
        # The existing tee cannot change type while a branch depends on it.
        self.assertEqual(
            self.client.patch(
                f"/api/v1/projects/{p['id']}/nodes/{tee['id']}", json=body
            ).status_code,
            422,
        )
        body["kind"] = "tee"
        response = self.client.patch(
            f"/api/v1/projects/{p['id']}/nodes/{tee['id']}", json=body
        )
        self.assertEqual(response.status_code, 200, response.text)
        p = response.json()
        self.assertEqual(len(p["nodes"]), 2)
        self.assertEqual(len(p["nodes"][0]["instances"]), 2)
        self.assertEqual(p["nodes"][0]["id"], tee["id"])

    def test_workbook_intake_keeps_schema_review_pending(self):
        from openpyxl import Workbook

        workbook = Workbook()
        workbook.active.title = "API 6A"
        workbook.active.append(["reference", "weight_N"])
        workbook.active.append(["example", None])
        data = io.BytesIO()
        workbook.save(data)
        response = self.client.post(
            "/api/v1/catalogs/import",
            files={"file": ("reference.xlsx", data.getvalue())},
        )
        self.assertEqual(response.status_code, 200, response.text)
        record = response.json()
        self.assertEqual(record["data"]["status"], "PENDING_SCHEMA_REVIEW")
        self.assertEqual(record["sha256"], hashlib.sha256(data.getvalue()).hexdigest())
        self.assertEqual(record["data"]["sheets"][0]["name"], "API 6A")
