import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient
from services.api import main, diagnostics as diag, updates
from tests.integration import test_api as fixtures


class DiagnosticTests(unittest.TestCase):
    setUp=fixtures.ApiTests.setUp
    tearDown=fixtures.ApiTests.tearDown
    def report(self,query=""):
        response=self.client.get("/api/v1/system/logs/export"+query)
        self.assertEqual(response.status_code,200,response.text)
        return response.json()

    def test_request_correlation_actor_and_phase_metadata(self):
        project=self.client.get("/api/v1/projects").json()[0]
        response=self.client.get(f"/api/v1/projects/{project['id']}")
        identity=response.headers["x-request-id"]
        self.assertEqual(len(identity),32)
        events=self.report("?q="+identity)["events"]
        complete=next(e for e in events if e["event"]=="http.completed")
        self.assertEqual(complete["actor_id"],"local-engineer")
        self.assertEqual(complete["project_id"],project["id"])
        self.assertEqual(complete["details"]["status"],200)
        self.assertGreaterEqual(complete["details"]["duration_ms"],0)
        self.assertIn("{project_id}",complete["details"]["route"])

    def test_bodies_query_headers_filenames_and_console_text_are_not_logged(self):
        sentinel="PRIVATE_DRAWING_PASSWORD_SENTINEL"
        self.client.get("/api/v1/projects?token="+sentinel,headers={"Authorization":"Bearer "+sentinel})
        self.client.post("/api/v1/projects",json={"title":sentinel,"description":sentinel,"line_id":"TEST"})
        self.client.post("/api/v1/auth/login",json={"email":"person@example.invalid","password":sentinel})
        self.client.post("/api/v1/system/logs/client",json={"events":[{"kind":"console","message":sentinel}]})
        text=json.dumps(self.report())
        self.assertNotIn(sentinel,text)
        self.assertNotIn("person@example.invalid",text)
        with patch.dict(os.environ,{"API_TOKEN":"SENTINEL_ACCESS_SECRET"}):
            diag.emit(main.DATA,"test.redaction",safe_value="SENTINEL_ACCESS_SECRET",password="hidden",nested={"cookie":"private"})
        text=json.dumps(self.report())
        self.assertNotIn("SENTINEL_ACCESS_SECRET",text)
        self.assertIn("[REDACTED]",text)

    def test_unexpected_exception_has_safe_frames_and_matching_request_id(self):
        def fail():raise ValueError("NEVER_LOG_EXCEPTION_CONTENT")
        main.app.add_api_route("/api/v1/diagnostic-test-failure",fail)
        route=main.app.router.routes[-1]
        main.app.router.routes.remove(route)
        main.app.router.routes.insert(0,route)  # Before the static-site catch-all.
        try:
            response=self.client.get("/api/v1/diagnostic-test-failure")
            self.assertEqual(response.status_code,500)
            identity=response.headers["x-request-id"]
            self.assertEqual(response.json()["request_id"],identity)
            report=self.report("?q="+identity)
            failure=next(e for e in report["events"] if e["event"]=="http.exception")
            self.assertEqual(failure["details"]["exception_type"],"ValueError")
            self.assertTrue(failure["details"]["frames"])
            self.assertNotIn("NEVER_LOG_EXCEPTION_CONTENT",json.dumps(report))
        finally:main.app.router.routes.remove(route)

    def test_logs_require_hosting_operator_not_viewer_or_tenant_admin(self):
        unauthenticated=TestClient(main.app)
        self.assertEqual(unauthenticated.get("/api/v1/system/logs").status_code,401)
        with main.db() as conn:conn.execute("UPDATE users SET role='viewer' WHERE id='local-engineer'")
        self.assertEqual(self.client.get("/api/v1/system/logs/export").status_code,403)
        with main.db() as conn:
            conn.execute("INSERT INTO users VALUES (?,?,?,?,?,?)",("tenant-admin","Other","other@example.invalid","","admin","other"))
            conn.execute("UPDATE sessions SET user_id='tenant-admin'")
        previous=main.LOCAL_DEMO
        try:
            main.LOCAL_DEMO=False
            self.assertEqual(self.client.get("/api/v1/system/logs").status_code,403)
        finally:main.LOCAL_DEMO=previous

    def test_browser_events_are_structured_correlated_and_rate_limited(self):
        identity=self.client.get("/api/v1/projects").headers["x-request-id"]
        batch={"events":[{"kind":"error","error_type":"TypeError","view":"workspace","frame":"index-demo.js:1:20","request_id":identity}]*20}
        for _ in range(6):self.assertEqual(self.client.post("/api/v1/system/logs/client",json=batch).status_code,200)
        self.assertEqual(self.client.post("/api/v1/system/logs/client",json=batch).status_code,429)
        report=self.report("?source=browser&level=ERROR&q="+identity)
        self.assertEqual(len(report["events"]),120)
        self.assertTrue(all(e["details"]["untrusted_client"] for e in report["events"]))

    def test_ingestion_body_is_bounded(self):
        response=self.client.post("/api/v1/system/logs/client",content=b"x"*33000)
        self.assertEqual(response.status_code,413)

    def test_logging_failure_does_not_break_projects(self):
        previous=diag.DROPPED
        try:
            with patch.object(diag,"connection",side_effect=OSError("private disk failure")):
                self.assertEqual(self.client.get("/api/v1/projects").status_code,200)
            self.assertGreater(diag.DROPPED,previous)
        finally:diag.DROPPED=previous

    def test_retention_bounds_rows(self):
        with tempfile.TemporaryDirectory() as temporary,patch.object(diag,"MAX_ROWS",2):
            for _ in range(50):diag.emit(Path(temporary),"bounded.test")
            self.assertEqual(diag.query(Path(temporary))["stored_events"],2)

    def test_updater_logs_phases_without_state_messages(self):
        updates.write(main.DATA/"updates/state.json",{"status":"failed","action":"install","message":"PRIVATE_UPDATER_CONTENT"})
        report=self.report("?source=updater")
        self.assertTrue(any(e["event"]=="update.state" for e in report["events"]))
        self.assertNotIn("PRIVATE_UPDATER_CONTENT",json.dumps(report))

    def test_pdf_parser_phases_share_request_and_omit_document_contents(self):
        project=self.client.get("/api/v1/projects").json()[0]
        response=self.client.post(f"/api/v1/projects/{project['id']}/sources?version={project['version']}",files={"file":("PRIVATE_FILENAME.pdf",fixtures.ApiTests.pdf(self),"application/pdf")})
        self.assertEqual(response.status_code,200,response.text)
        report=self.report("?q="+response.headers["x-request-id"])
        names={e["event"] for e in report["events"]}
        self.assertIn("pdf.parse.started",names)
        self.assertIn("pdf.parse.completed",names)
        self.assertIn("project.change.completed",names)
        self.assertNotIn("PRIVATE_FILENAME",json.dumps(report))
