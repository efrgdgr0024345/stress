from decimal import Decimal
import io, json, zipfile
import unittest
from openpyxl import Workbook
import fitz
from tests.integration import test_api as fixtures
from services.api import main


class Workflows(unittest.TestCase):
    setUp = fixtures.ApiTests.setUp
    tearDown = fixtures.ApiTests.tearDown
    create = fixtures.ApiTests.create
    pdf = fixtures.ApiTests.pdf
    upload = fixtures.ApiTests.upload
    node = fixtures.ApiTests.node

    def test_exact_catalog_record_cannot_override_the_current_source_size(self):
        _,dataset,spec=self.dataset()
        response=self.client.post(f"/api/v1/catalog-versions/{dataset['id']}/approve",json={
            'reason':'SOFTWARE ONLY source-size conflict guard; this fixture is not real engineering approval.','confirmed':True})
        self.assertEqual(response.status_code,200,response.text)
        p=self.client.get('/api/v1/projects').json()[0]
        item=next(m for m in p['materials'] if m['family']=='flange')
        body={k:item[k] for k in ('sheet_id','item_no','family','description','quantity','observed')}
        body.update(version=p['version'],size='2 in',evidence='SOFTWARE ONLY explicit source NPS2 conflicts with the available NPS8 catalog record.')
        response=self.client.patch(f"/api/v1/projects/{p['id']}/materials/{item['id']}",json=body)
        self.assertEqual(response.status_code,200,response.text);p=response.json()
        path=f"/api/v1/projects/{p['id']}/materials/{item['id']}/catalog-match"
        request={'version':p['version'],'catalog_version_id':dataset['id'],'spec':spec,
                 'reason':'SOFTWARE ONLY: an exact NPS8 record must never become a mass for a source NPS2 flange.'}
        preview=self.client.post(path+'?dry_run=true',json=request)
        self.assertEqual(preview.status_code,200,preview.text)
        self.assertEqual(preview.json()['status'],'SOURCE_SPEC_CONFLICT')
        response=self.client.post(path,json=request)
        self.assertEqual(response.status_code,422,response.text)
        current=self.client.get(f"/api/v1/projects/{p['id']}").json()
        self.assertEqual(current['version'],p['version'])
        self.assertFalse(next(m for m in current['materials'] if m['id']==item['id']).get('catalog_match'))

    def dataset(self, duplicate=False, invalid=False, confirmed=False):
        values = {
            "family": "flange",
            "standard": "ASME B16.5",
            "rating": "150",
            "nps": "8",
            "component_type": "WN",
            "facing": "RF",
            "source": "Synthetic reviewed source, not actual engineering data",
            "quality": "REFERENCE_ONLY",
            "weight_n": "100" if not invalid else "-4",
            "weight_scope": "BARE_FLANGE",
            "studs_weight_n": "40",
            "nut_weight_n": "5",
            "stud_count": "4",
        }
        if confirmed:
            values.update(
                quality="MANUFACTURER_CONFIRMED",
                vendor="Synthetic manufacturer",
                model="SYN-001",
            )
        book = Workbook()
        book.active.title = "Flanges"
        book.active.append(list(values))
        book.active.append(list(values.values()))
        if duplicate:
            book.active.append(list(values.values()))
        content = io.BytesIO()
        book.save(content)
        book.close()
        r = self.client.post(
            "/api/v1/catalogs/import",
            files={"file": ("engineering-reference.xlsx", content.getvalue())},
        )
        self.assertEqual(r.status_code, 200, r.text)
        catalog = r.json()
        mapped = self.client.post(
            f"/api/v1/catalogs/{catalog['id']}/versions",
            json={
                "sheet": "Flanges",
                "columns": {key: i for i, key in enumerate(values)},
            },
        )
        self.assertEqual(mapped.status_code, 200, mapped.text)
        return (
            catalog,
            mapped.json(),
            {
                k: values[k]
                for k in [
                    "family",
                    "standard",
                    "rating",
                    "nps",
                    "component_type",
                    "facing",
                ]
            },
        )

    def test_dataset_preview_approval_and_immutable_matching(self):
        c, d, spec = self.dataset()
        preview = self.client.get(f"/api/v1/catalogs/{c['id']}/preview").json()
        self.assertEqual(preview["headers"][0]["label"], "family")
        self.assertEqual(d["data"]["status"], "PENDING_APPROVAL")
        p = self.client.get("/api/v1/projects").json()[0]
        m = next(m for m in p["materials"] if m["family"] == "flange")
        body = {
            "version": p["version"],
            "catalog_version_id": d["id"],
            "spec": spec,
            "reason": "Reviewed synthetic source and exact item specifications",
        }
        path = f"/api/v1/projects/{p['id']}/materials/{m['id']}/catalog-match"
        self.assertEqual(self.client.post(path, json=body).status_code, 422)
        r = self.client.post(
            f"/api/v1/catalog-versions/{d['id']}/approve",
            json={"reason": "Source mapping, units and quality independently checked"},
        )
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(
            self.client.post(
                f"/api/v1/catalog-versions/{d['id']}/approve",
                json={"reason": "Attempt to approve the same immutable dataset again"},
            ).status_code,
            409,
        )
        r = self.client.post(path, json=body)
        self.assertEqual(r.status_code, 200, r.text)
        p = r.json()
        saved = next(v for v in p["materials"] if v["id"] == m["id"])["catalog_match"]
        self.assertEqual(Decimal(saved["record"]["half_weight_n"]), Decimal("140"))
        self.assertEqual(saved["catalog_source_sha256"], c["sha256"])
        self.assertIn("MANUFACTURER_UNCONFIRMED", {i["code"] for i in p["issues"]})
        self.assertFalse(
            any(
                i["code"] == "NO_EXACT_MATCH" and i.get("material_id") == m["id"]
                for i in p["issues"]
            )
        )
        schedules = self.client.get(f"/api/v1/projects/{p['id']}/schedules").json()
        self.assertIn("140", json.dumps(schedules))
        export = self.client.post(
            f"/api/v1/projects/{p['id']}/exports", json={"version": p["version"]}
        )
        self.assertEqual(export.status_code, 200, export.text)
        a = export.json()
        preview = self.client.get(f"/api/v1/projects/{p['id']}/artifacts/{a['id']}/pdf")
        self.assertEqual(preview.status_code, 200, preview.text[:100])
        self.assertTrue(preview.content.startswith(b"%PDF-"))
        self.assertEqual(preview.headers["content-type"], "application/pdf")
        bundle = self.client.get(
            f"/api/v1/projects/{p['id']}/artifacts/{a['id']}/download"
        )
        with zipfile.ZipFile(io.BytesIO(bundle.content)) as z:
            self.assertEqual(
                json.loads(z.read("catalog-provenance.json"))[0]["record"]["weight_n"],
                "100",
            )
            with fitz.open(
                stream=z.read("annotated-review.pdf"), filetype="pdf"
            ) as doc:
                texts = " ".join(
                    a.info["content"] for page in doc for a in page.annots()
                )
                self.assertIn("140", texts)
                self.assertIn("REFERENCE_ONLY", texts)
        # Editing specification-bearing inventory data invalidates the old match.
        body = {**m, "id": None, "version": p["version"], "size": "10 in"}
        r = self.client.patch(
            f"/api/v1/projects/{p['id']}/materials/{m['id']}", json=body
        )
        self.assertEqual(r.status_code, 200, r.text)
        self.assertNotIn(
            "catalog_match",
            next(v for v in r.json()["materials"] if v["id"] == m["id"]),
        )

    def test_ambiguous_and_invalid_catalogs_stay_unusable(self):
        c, d, spec = self.dataset(duplicate=True)
        self.client.post(
            f"/api/v1/catalog-versions/{d['id']}/approve",
            json={"reason": "Duplicate source entries retained for explicit review"},
        )
        p = self.client.get("/api/v1/projects").json()[0]
        m = next(m for m in p["materials"] if m["family"] == "flange")
        body = {
            "version": p["version"],
            "catalog_version_id": d["id"],
            "spec": spec,
            "reason": "Do not arbitrarily select an ambiguous source row",
        }
        path = f"/api/v1/projects/{p['id']}/materials/{m['id']}/catalog-match"
        self.assertEqual(
            self.client.post(path + "?dry_run=true", json=body).json()["status"],
            "AMBIGUOUS_MATCH",
        )
        self.assertEqual(self.client.post(path, json=body).status_code, 422)
        c, d, spec = self.dataset(invalid=True)
        self.assertEqual(d["data"]["status"], "INVALID")
        self.assertEqual(
            self.client.post(
                f"/api/v1/catalog-versions/{d['id']}/approve",
                json={"reason": "Invalid records must never be approved for matching"},
            ).status_code,
            409,
        )

    def test_catalog_source_and_tenant_integrity(self):
        c, d, spec = self.dataset()
        with main.db() as conn:
            conn.execute(
                "UPDATE catalogs SET tenant=? WHERE id=?", ("another", c["id"])
            )
        self.assertEqual(
            self.client.get(f"/api/v1/catalogs/{c['id']}/preview").status_code, 404
        )
        with main.db() as conn:
            conn.execute("UPDATE catalogs SET tenant=? WHERE id=?", ("local", c["id"]))
        (main.DATA / "catalogs" / f"{c['id']}.xlsx").write_bytes(b"tampered source")
        self.assertEqual(
            self.client.get(f"/api/v1/catalogs/{c['id']}/preview").status_code, 409
        )

    def test_catalog_manufacturer_does_not_confirm_the_drawing_manufacturer(self):
        c, d, spec = self.dataset(confirmed=True)
        self.client.post(
            f"/api/v1/catalog-versions/{d['id']}/approve",
            json={
                "reason": "Test source documents its own manufacturer, not the project manufacturer"
            },
        )
        p = self.client.get("/api/v1/projects").json()[0]
        item = next(m for m in p["materials"] if m["family"] == "flange")
        path = f"/api/v1/projects/{p['id']}/materials/{item['id']}/catalog-match"
        body = {
            "version": p["version"],
            "catalog_version_id": d["id"],
            "spec": spec,
            "reason": "Use the catalog as a reference until actual manufacturer evidence is supplied",
        }
        r = self.client.post(path, json=body)
        self.assertEqual(r.status_code, 200, r.text)
        p = r.json()
        matched = next(m for m in p["materials"] if m["id"] == item["id"])
        self.assertEqual(matched["catalog_match"]["status"], "REFERENCE_ONLY")
        self.assertTrue(
            any(
                i["code"] == "MANUFACTURER_UNCONFIRMED"
                and i.get("material_id") == item["id"]
                for i in p["issues"]
            )
        )
        body.update(
            version=p["version"],
            spec={**spec, "vendor": "Synthetic manufacturer", "model": "SYN-001"},
            reason="Synthetic drawing manufacturer and model have both been explicitly checked",
        )
        r = self.client.post(path, json=body)
        self.assertEqual(r.status_code, 200, r.text)
        matched = next(m for m in r.json()["materials"] if m["id"] == item["id"])
        self.assertEqual(matched["catalog_match"]["record"]["quality"], "MANUFACTURER_CONFIRMED")
        self.assertEqual(matched["catalog_match"]["status"], "REFERENCE_ONLY")
        self.assertTrue(any(i['code']=='MANUFACTURER_UNCONFIRMED' and i.get('material_id')==item['id'] for i in r.json()['issues']))

    def test_notes_native_export_and_revision_recovery(self):
        p = self.client.get("/api/v1/projects").json()[0]
        original_version = p["version"]
        sid = p["sheets"][0]["id"]
        ids = []
        for index, kind in enumerate(["FreeText", "Square", "Circle", "Line"]):
            r = self.client.post(
                f"/api/v1/projects/{p['id']}/annotations",
                json={
                    "version": p["version"],
                    "sheet_id": sid,
                    "kind": kind,
                    "rect": [40, 200 + index * 35, 250, 225 + index * 35],
                    "text": "Review note",
                    "color": "#007aff",
                },
            )
            self.assertEqual(r.status_code, 200, r.text)
            p = r.json()
            ids.append(p["annotations"][-1]["id"])
        diff = self.client.get(
            f"/api/v1/projects/{p['id']}/revisions/{original_version}/diff"
        )
        self.assertEqual(diff.status_code, 200, diff.text)
        self.assertEqual(diff.json()["changes"]["annotations"]["added"], 4)
        r = self.client.post(
            f"/api/v1/projects/{p['id']}/exports", json={"version": p["version"]}
        )
        self.assertEqual(r.status_code, 200, r.text)
        a = r.json()
        bundle = self.client.get(
            f"/api/v1/projects/{p['id']}/artifacts/{a['id']}/download"
        )
        with zipfile.ZipFile(io.BytesIO(bundle.content)) as archive:
            notes = [
                v
                for v in json.loads(archive.read("annotation-manifest.json"))
                if v["role"] == "drawing-note"
            ]
            self.assertEqual(len(notes), 4)
            self.assertEqual({v["group"] for v in notes}, set(ids))
        current = p["version"]
        r = self.client.post(
            f"/api/v1/projects/{p['id']}/revisions/{original_version}/restore",
            json={
                "version": current,
                "reason": "Recover the original synthetic model after testing annotations",
            },
        )
        self.assertEqual(r.status_code, 200, r.text)
        restored = r.json()
        self.assertEqual(restored["version"], current + 1)
        self.assertEqual(restored["annotations"], [])
        self.assertFalse(restored["layout_reviewed"])
        old = self.client.get(f"/api/v1/projects/{p['id']}/revisions/{current}").json()
        self.assertEqual(len(old["annotations"]), 4)
        self.assertEqual(
            self.client.post(
                f"/api/v1/projects/{p['id']}/revisions/{original_version}/restore",
                json={
                    "version": current,
                    "reason": "Stale restore must not overwrite someone else edits",
                },
            ).status_code,
            409,
        )

    def test_loader_and_lessons_are_real_files_without_private_drawings(self):
        response = self.client.get("/loader.php")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Load project", response.text)
        self.assertIn("lessons-grid", response.text)
        lessons = self.client.get("/api/v1/lessons").json()
        expected = [
            line
            for line in (main.ROOT / "LESSONS_LEARNED.md").read_text().splitlines()
            if line.startswith("## LESSON-")
        ]
        self.assertEqual(len(lessons["lessons"]), len(expected))
        self.assertGreaterEqual(len(expected), 8)
        self.assertTrue(all(v["lesson"] and v["action"] for v in lessons["lessons"]))
        self.assertEqual(self.client.get("/.local/workspace.sqlite3").status_code, 404)
