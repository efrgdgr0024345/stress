"""Real Chromium test against the built application, with disposable storage."""

import io
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
from urllib.request import urlopen
import zipfile

import fitz
from playwright.sync_api import sync_playwright, expect
from catalog_workflow import exercise_catalogs

ROOT = Path(__file__).resolve().parents[2]
Path("/tmp/caesar-screens").mkdir(exist_ok=True)


def run():
    with tempfile.TemporaryDirectory(prefix="caesar-e2e-") as tmp:
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
        prefix = os.environ.get("CAESAR_TEST_MOUNT", "")
        origin = f"http://127.0.0.1:{port}"
        base = origin + prefix
        with open(Path(tmp) / "server.log", "w") as log:
            process = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "uvicorn",
                    "tests.e2e.hosted_app:app",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(port),
                ],
                cwd=ROOT,
                env={
                    **os.environ,
                    "CAESAR_DATA_DIR": str(Path(tmp) / "data"),
                    "CAESAR_LOCAL_DEMO": "1",
                },
                stdout=log,
                stderr=log,
            )
            try:
                for _ in range(100):
                    try:
                        if urlopen(base + "/api/v1/health").status == 200:
                            break
                    except Exception:
                        time.sleep(0.1)
                else:
                    raise RuntimeError("Test server did not become ready.")
                with sync_playwright() as playwright:
                    browser = playwright.chromium.launch(
                        executable_path=os.environ.get(
                            "CHROMIUM_PATH", "/usr/bin/chromium"
                        ),
                        args=["--no-sandbox"],
                    )
                    context = browser.new_context(
                        viewport={"width": 1440, "height": 1000}, accept_downloads=True
                    )
                    page = context.new_page()
                    errors = []
                    page.on("pageerror", lambda e: errors.append(str(e)))
                    page.goto(base + "/")
                    page.get_by_role("button", name="Enter local workspace").click()
                    expect(
                        page.get_by_role("heading", name="Projects.")
                    ).to_be_visible()
                    page.get_by_label("Search projects").fill("does-not-exist")
                    expect(
                        page.get_by_role("heading", name="No matching projects")
                    ).to_be_visible()
                    page.get_by_label("Search projects").fill("")
                    page.get_by_role("button",name="System updates",exact=True).click()
                    expect(page.get_by_role("dialog",name="System updates",exact=True)).to_be_visible()
                    expect(page.get_by_role("button",name="Check GitHub",exact=True)).to_be_visible()
                    expect(page.get_by_role("button",name="Install update",exact=True)).to_be_disabled()
                    page.get_by_role("button",name="Close dialog",exact=True).click()
                    page.get_by_role("link", name="Load project", exact=True).click()
                    lessons = context.request.get(base + "/api/v1/lessons").json()[
                        "lessons"
                    ]
                    assert len(lessons) >= 8
                    expect(page.locator(".lesson")).to_have_count(len(lessons))
                    expect(page.locator(".lesson-icon")).to_have_count(len(lessons))
                    assert page.url.startswith(base + "/loader.php")
                    expect(page.get_by_role("link", name="Download cPanel ZIP")).to_be_visible()
                    install = page.get_by_role("button", name="Install on cPanel")
                    install.click()
                    expect(page.get_by_role("heading", name="cPanel installation guide")).to_be_visible()
                    expect(install).to_have_attribute("aria-expanded", "true")
                    with page.expect_download() as download_info:
                        page.get_by_role("link", name="Download cPanel ZIP").click()
                    download = download_info.value
                    assert download.suggested_filename == "caesar-cpanel.zip"
                    with zipfile.ZipFile(download.path()) as package:
                        assert "caesar-system/passenger_wsgi.py" in package.namelist()
                        assert "caesar-system/scripts/check_host.py" in package.namelist()
                    install.click()
                    expect(page.locator("#cpanel-guide")).to_be_hidden()
                    expect(
                        page.get_by_role("button", name="Load project", exact=True)
                    ).to_be_enabled()
                    page.screenshot(
                        path="/tmp/caesar-screens/loader.png", full_page=True
                    )
                    page.get_by_role("button", name="Load project", exact=True).click()
                    assert page.url.startswith(base + "/?project=")
                    expect(page.locator(".node-glyph").first).to_be_visible()
                    page.wait_for_function(
                        "document.querySelector('canvas')?.width > 100"
                    )
                    page.get_by_label("Drawing annotations", exact=True).click()
                    page.get_by_label("Note text", exact=True).fill(
                        "Browser-reviewed drawing note"
                    )
                    page.get_by_role(
                        "button", name="Add annotation", exact=True
                    ).click()
                    expect(page.locator(".free-annotation")).to_have_count(1)
                    page.locator(".free-annotation").click()
                    page.get_by_label("Left / start X (PDF points)", exact=True).fill(
                        "50"
                    )
                    page.get_by_role(
                        "button", name="Save annotation", exact=True
                    ).click()
                    expect(page.get_by_role("dialog")).to_have_count(0)
                    page.get_by_label(
                        "Toggle model route connections", exact=True
                    ).click()
                    expect(page.locator(".route-connection").first).to_be_visible()
                    projects = context.request.get(base + "/api/v1/projects").json()
                    sample = projects[0]
                    support = next(
                        n for n in sample["nodes"] if n.get("support_gap_mm")
                    )
                    page.locator(".node-list button").filter(
                        has=page.get_by_text(str(support["number"]), exact=True)
                    ).click()
                    expect(
                        page.get_by_text("Support within 6 in", exact=False).first
                    ).to_be_visible()
                    page.get_by_label("bubble X", exact=True).fill("480")
                    page.get_by_role("button", name="Save point", exact=True).click()
                    expect(
                        page.get_by_role("button", name="Save point", exact=True)
                    ).to_be_disabled()
                    updated = context.request.get(
                        base + f"/api/v1/projects/{sample['id']}"
                    ).json()
                    saved = next(
                        n for n in updated["nodes"] if n["id"] == support["id"]
                    )
                    assert saved["station_mm"] == support["station_mm"]
                    assert saved["instances"][0]["bubble"][0] == 480
                    assert "SUPPORT_WITHIN_6_IN" in saved["reasons"]
                    page.get_by_role("button", name="All sheet points").click()
                    page.get_by_role("button", name="Add point", exact=True).click()
                    overlay = page.locator(".drawing-overlay")
                    overlay.click(position={"x": 180, "y": 170})
                    expect(
                        page.get_by_role("heading", name="New physical point")
                    ).to_be_visible()
                    page.get_by_role("button", name="Save point", exact=True).click()
                    expect(
                        page.get_by_role("button", name="Save point", exact=True)
                    ).to_be_disabled()
                    updated = context.request.get(
                        base + f"/api/v1/projects/{sample['id']}"
                    ).json()
                    assert len(updated["nodes"]) == len(sample["nodes"]) + 1
                    assert updated["nodes"][-1]["station_mm"] is None
                    old_width = page.locator("canvas").evaluate("(e)=>e.width")
                    page.get_by_label("Zoom in", exact=True).click()
                    expect(page.locator("canvas")).not_to_have_js_property(
                        "width", old_width
                    )
                    page.get_by_label("Fit drawing", exact=True).click()
                    page.get_by_label("Next sheet", exact=True).click()
                    expect(page.get_by_label("Active sheet")).to_have_value("1")
                    page.get_by_role("button", name="Source text", exact=True).click()
                    expect(page.locator(".source-text")).to_contain_text("Synthetic")
                    page.get_by_role("button", name="Materials", exact=True).click()
                    page.locator("tbody .text-button").first.click()
                    expect(
                        page.get_by_role("dialog", name="Review material")
                    ).to_be_visible()
                    page.get_by_label("Located instances", exact=True).fill("2")
                    page.get_by_role("button", name="Save review", exact=True).click()
                    expect(page.get_by_role("dialog")).to_have_count(0)
                    exercise_catalogs(page, context, base, tmp)
                    page.get_by_role("button", name="Validation", exact=False).filter(
                        has_text="Validation"
                    ).last.click()
                    expect(
                        page.get_by_role("heading", name="Evidence before release.")
                    ).to_be_visible()
                    page.get_by_role("button", name="Export review", exact=True).click()
                    page.get_by_role("button", name="Generate review bundle").click()
                    expect(
                        page.get_by_role("button", name="Download review bundle (.zip)")
                    ).to_be_visible(timeout=15000)
                    with page.expect_download() as download:
                        page.get_by_role(
                            "button", name="Download review bundle (.zip)"
                        ).click()
                    bundle = Path(tmp) / "review.zip"
                    download.value.save_as(bundle)
                    with zipfile.ZipFile(bundle) as archive:
                        qa = json.loads(archive.read("qa.json"))
                        assert qa["structural_check"] == "passed"
                        assert qa["native_annotations"] > 75
                        assert qa["desktop_editor_roundtrip"] == "not tested"
                    page.get_by_role(
                        "button", name="Preview generated PDF", exact=True
                    ).click()
                    expect(page.locator(".pdf-preview canvas")).to_be_visible(
                        timeout=15000
                    )
                    expect(
                        page.get_by_label("Next preview page", exact=True)
                    ).to_be_enabled()
                    page.get_by_label("Next preview page", exact=True).click()
                    expect(page.locator(".pdf-preview canvas")).to_be_visible(
                        timeout=15000
                    )
                    page.screenshot(
                        path="/tmp/caesar-screens/export-preview.png", full_page=True
                    )
                    page.get_by_label("Close dialog", exact=True).click()
                    page.get_by_role("button", name="All projects", exact=True).click()
                    page.get_by_role("button", name="New project", exact=True).click()
                    page.get_by_label("Project name", exact=True).fill(
                        "Browser upload verification"
                    )
                    page.get_by_label("Full line ID", exact=False).fill(
                        "E2E-ROTATED-001"
                    )
                    doc = fitz.open()
                    p = doc.new_page(width=600, height=500)
                    p.insert_text((90, 100), "Rotated source fixture")
                    p.set_cropbox(fitz.Rect(40, 30, 560, 470))
                    p.set_rotation(90)
                    pdf_path = Path(tmp) / "rotated.pdf"
                    doc.save(pdf_path)
                    doc.close()
                    page.locator(".upload-zone input").set_input_files(pdf_path)
                    page.get_by_role(
                        "button", name="Create project", exact=True
                    ).click()
                    try:
                        expect(page.locator(".drawing-overlay")).to_be_visible(
                            timeout=15000
                        )
                    except Exception:
                        print("Browser errors during new project upload:", errors)
                        raise
                    expect(page.get_by_label("Active sheet")).to_have_count(1)
                    page.get_by_role("button", name="Add point", exact=True).click()
                    page.locator(".drawing-overlay").click(
                        position={"x": 180, "y": 190}
                    )
                    page.get_by_label("Along-route station", exact=False).fill(
                        "2 1/8 in"
                    )
                    page.get_by_label("Dimension source / evidence", exact=True).fill(
                        "E2E synthetic dimension; not engineering input"
                    )
                    page.get_by_role("button", name="Save point", exact=True).click()
                    expect(
                        page.get_by_role("button", name="Save point", exact=True)
                    ).to_be_disabled()
                    project = next(
                        p
                        for p in context.request.get(base + "/api/v1/projects").json()
                        if p["line_id"] == "E2E-ROTATED-001"
                    )
                    from decimal import Decimal

                    assert Decimal(project["nodes"][0]["station_mm"]) == Decimal(
                        "53.975"
                    )
                    anchor = project["nodes"][0]["instances"][0]["anchor"]
                    visible = page.locator(".anchor-handle").first
                    assert (
                        abs(float(visible.get_attribute("cx")) - (440 - anchor[1]))
                        < 0.01
                    )
                    assert abs(float(visible.get_attribute("cy")) - anchor[0]) < 0.01
                    page.reload()
                    expect(page.locator(".node-glyph")).to_have_count(1)
                    # A mobile viewport must not introduce document-level horizontal scrolling.
                    page.set_viewport_size({"width": 390, "height": 844})
                    page.goto(base + "/")
                    expect(
                        page.get_by_role("heading", name="Projects.")
                    ).to_be_visible()
                    assert page.evaluate(
                        "document.documentElement.scrollWidth<=window.innerWidth"
                    )
                    page.locator(".mobile-menu").click()
                    expect(page.locator(".sidebar")).to_be_visible()
                    screenshot = Path("/tmp/caesar-screens")
                    screenshot.mkdir(exist_ok=True)
                    page.screenshot(path=str(screenshot / "mobile.png"), full_page=True)
                    assert not errors, errors
                    browser.close()
                    print(
                        "PASS: project loader and all lessons, in-browser drawing/notes, node editing, catalog mapping/approval/exact matching, native PDF preview/download, rotated CropBox upload, persistence, and mobile layout; no browser errors."
                    )
            finally:
                process.terminate()
                process.wait(timeout=10)


if __name__ == "__main__":
    run()
