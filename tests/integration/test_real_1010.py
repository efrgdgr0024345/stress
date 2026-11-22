"""Real reviewed drawing software tests, not the unavailable 1010 golden model."""
import hashlib
import io
from pathlib import Path
import unittest
import zipfile
import fitz
from packages.pdf import inspect_pdf,content_hash
from tests.integration import test_api as fixtures

SOURCE=Path(__file__).resolve().parents[2]/"fixtures/1010/1010 Reviewed.pdf"
SHA="7b97d44bef3d544c4c98ed0667c29607ce58fa4a401dd2463f66010a9615bb59"

class RealDrawingTests(unittest.TestCase):
    setUp=fixtures.ApiTests.setUp
    tearDown=fixtures.ApiTests.tearDown
    def test_reviewed_fixture_identity_and_vector_classification(self):
        self.assertEqual(hashlib.sha256(SOURCE.read_bytes()).hexdigest(),SHA)
        pages=inspect_pdf(SOURCE)
        self.assertEqual(len(pages),2)
        self.assertGreater(pages[0]["vector_paths"],4000)
        self.assertGreater(pages[1]["vector_paths"],6000)
        self.assertEqual(pages[1]["native_text_chars"],0)
        self.assertIn("Vector",pages[1]["format"])

    def test_real_upload_revision_native_export_and_diagnostics(self):
        response=self.client.post("/api/v1/projects",json={"title":"1010 Reviewed — software regression only","line_id":"8-PG-JE3LN2-1010-FUTURE"})
        self.assertEqual(response.status_code,201)
        p=response.json()
        response=self.client.post(f"/api/v1/projects/{p['id']}/sources?version={p['version']}",files={"file":(SOURCE.name,SOURCE.read_bytes(),"application/pdf")})
        self.assertEqual(response.status_code,200,response.text)
        p=response.json()
        self.assertEqual(len(p["sheets"]),2)
        self.assertTrue(all(s["sha256"]==SHA for s in p["sheets"]))
        # An explicitly provisional graphical anchor at the visible upper
        # continuation dot, with no claimed physical station or golden model.
        response=self.client.post(f"/api/v1/projects/{p['id']}/nodes",json={"version":p["version"],"line_id":p["line_id"],"route":"main","order":1,"kind":"endpoint","dimension":"","evidence":"SOFTWARE TEST ONLY: provisional visual anchor; engineering location unverified","instances":[{"sheet_id":p["sheets"][0]["id"],"anchor":[900,405],"bubble":[820,370]}]})
        self.assertEqual(response.status_code,200,response.text)
        p=response.json()
        self.assertIsNone(p["nodes"][0]["station_mm"])
        self.assertIn("UNVERIFIED_DIMENSION",p["nodes"][0]["reasons"])
        response=self.client.post(f"/api/v1/projects/{p['id']}/annotations",json={"version":p["version"],"sheet_id":p["sheets"][1]["id"],"kind":"FreeText","rect":[300,130,720,180],"text":"SOFTWARE VALIDATION ONLY — NOT ENGINEERING APPROVAL","color":"#1e57d8"})
        self.assertEqual(response.status_code,200,response.text)
        p=response.json()
        response=self.client.post(f"/api/v1/projects/{p['id']}/exports",json={"version":p["version"]})
        self.assertEqual(response.status_code,200,response.text)
        artifact=response.json()
        bundle=self.client.get(f"/api/v1/projects/{p['id']}/artifacts/{artifact['id']}/download")
        self.assertEqual(bundle.status_code,200)
        with zipfile.ZipFile(io.BytesIO(bundle.content)) as z:
            name=next(n for n in z.namelist() if n.endswith(".pdf"))
            with fitz.open(SOURCE) as original,fitz.open(stream=z.read(name),filetype="pdf") as generated:
                self.assertEqual(len(generated),2)
                for i in range(2):self.assertEqual(content_hash(original[i]),content_hash(generated[i]))
                annotations=list(generated[1].annots() or [])
                self.assertTrue(any("SOFTWARE VALIDATION" in a.info.get("content","") for a in annotations))
        original=self.client.get(f"/api/v1/projects/{p['id']}/sources/{p['sheets'][0]['source_id']}")
        self.assertEqual(hashlib.sha256(original.content).hexdigest(),SHA)
        logs=self.client.get("/api/v1/system/logs/export").json()
        self.assertTrue(any(e["event"]=="pdf.export.published" for e in logs["events"]))
        self.assertNotIn("SOFTWARE VALIDATION",str(logs))

    def test_notes_only_review_export_without_fabricated_nodes(self):
        p=self.client.post("/api/v1/projects",json={"title":"Notes-only real PDF test","line_id":"8-PG-JE3LN2-1010-FUTURE"}).json()
        self.assertEqual(self.client.post(f"/api/v1/projects/{p['id']}/exports",json={"version":p["version"]}).status_code,422)
        p=self.client.post(f"/api/v1/projects/{p['id']}/sources?version={p['version']}",files={"file":(SOURCE.name,SOURCE.read_bytes(),"application/pdf")}).json()
        p=self.client.post(f"/api/v1/projects/{p['id']}/annotations",json={"version":p["version"],"sheet_id":p["sheets"][0]["id"],"kind":"FreeText","rect":[50,50,400,90],"text":"SOFTWARE TEST ONLY","color":"#1e57d8"}).json()
        self.assertEqual(p["nodes"],[])
        response=self.client.post(f"/api/v1/projects/{p['id']}/exports",json={"version":p["version"]})
        self.assertEqual(response.status_code,200,response.text)
        artifact=response.json()
        response=self.client.get(f"/api/v1/projects/{p['id']}/artifacts/{artifact['id']}/download")
        with zipfile.ZipFile(io.BytesIO(response.content)) as z:
            name=next(n for n in z.namelist() if n.endswith(".pdf"))
            with fitz.open(SOURCE) as source,fitz.open(stream=z.read(name),filetype="pdf") as output:
                self.assertEqual(len(output),2)
                self.assertEqual(content_hash(source[0]),content_hash(output[0]))
                self.assertTrue(any("SOFTWARE TEST ONLY" in a.info.get("content","") for a in output[0].annots()))
