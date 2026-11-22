"""Browser regression using the user's reviewed PDF, with temporary projects."""
import hashlib
from collections import Counter
from pathlib import Path
import zipfile

import fitz
from playwright.sync_api import expect
from packages.pdf import content_hash

SOURCE = Path(__file__).resolve().parents[2] / "fixtures/1010/1010 Reviewed.pdf"
PIXELS = """(selector) => {
  const c=document.querySelector(selector);
  if(!c?.offsetWidth || c.width<100 || getComputedStyle(c).visibility==='hidden')return null;
  const d=c.getContext('2d').getImageData(0,0,c.width,c.height).data;
  let hash=2166136261,dark=0;
  for(let i=0;i<d.length;i+=64){
    hash=Math.imul(hash^d[i],16777619);
    if(d[i]<150&&d[i+3]>0)dark++;
  }
  return dark>100 ? hash>>>0 : null;
}"""


def wait_for_drawing(page, selector, previous=None):
    page.wait_for_function(
        "(args) => {const hash=("+PIXELS+")(args.selector); return hash!==null && hash!==args.previous;}",
        arg={"selector":selector,"previous":previous},timeout=20000)
    return page.evaluate(PIXELS, selector)


def exercise_real_drawing(page, context, base, directory):
    page.get_by_role("button", name="All projects", exact=True).click()
    page.get_by_role("button", name="New project", exact=True).click()
    page.get_by_label("Project name", exact=True).fill("1010 real drawing software test")
    page.get_by_label("Full line ID", exact=False).fill("8-PG-JE3LN2-1010-FUTURE")
    page.locator(".upload-zone input").set_input_files(SOURCE)
    page.get_by_role("button", name="Create project", exact=True).click()
    expect(page.locator(".drawing-overlay")).to_be_visible(timeout=20000)
    page.get_by_label("Active sheet").select_option("0")
    first_source=wait_for_drawing(page,".paper canvas")
    expect(page.get_by_label("Active sheet").locator("option")).to_have_count(2)
    page.get_by_label("Next sheet", exact=True).click()
    expect(page.get_by_label("Active sheet")).to_have_value("1")
    wait_for_drawing(page,".paper canvas",first_source)
    page.get_by_role("button", name="Source text", exact=True).click()
    expect(page.locator(".source-text")).to_contain_text("No searchable text")
    page.get_by_label("Previous sheet", exact=True).click()
    page.get_by_label("Drawing annotations", exact=True).click()
    page.get_by_label("Note text", exact=True).fill("SOFTWARE TEST ONLY - engineering unverified")
    page.get_by_role("button", name="Add annotation", exact=True).click()
    expect(page.locator(".free-annotation")).to_have_count(1)
    page.locator(".free-annotation").click()
    page.get_by_label("Left / start X (PDF points)", exact=True).fill("50")
    page.get_by_role("button", name="Save annotation", exact=True).click()
    expect(page.get_by_role("dialog")).to_have_count(0)
    page.reload()
    expect(page.locator(".free-annotation")).to_have_count(1)
    wait_for_drawing(page,".paper canvas")
    page.screenshot(path="/tmp/caesar-screens/1010-real-drawing.png", full_page=True)
    project = next(p for p in context.request.get(base + "/api/v1/projects").json()
                   if p["title"] == "1010 real drawing software test")
    assert project["annotations"][0]["rect"][0] == 50
    assert project["nodes"] == []  # No fabricated automatic engineering output.
    original = context.request.get(base + f"/api/v1/projects/{project['id']}/sources/{project['sheets'][0]['source_id']}").body()
    assert hashlib.sha256(original).digest() == hashlib.sha256(SOURCE.read_bytes()).digest()
    page.get_by_role("button", name="Export review", exact=True).click()
    page.get_by_role("button", name="Generate review bundle").click()
    expect(page.get_by_role("button", name="Download review bundle (.zip)")).to_be_visible(timeout=20000)
    with page.expect_download() as download:
        page.get_by_role("button", name="Download review bundle (.zip)").click()
    bundle = Path(directory) / "1010-real-review.zip"
    download.value.save_as(bundle)
    with zipfile.ZipFile(bundle) as archive:
        pdf = next(n for n in archive.namelist() if n.endswith(".pdf"))
        with fitz.open(SOURCE) as source, fitz.open(stream=archive.read(pdf), filetype="pdf") as output:
            assert len(output) == 2
            for i in range(2):
                assert content_hash(source[i]) == content_hash(output[i])
                original=Counter((a.type[0],a.info.get("content","")) for a in source[i].annots() or [])
                generated=Counter((a.type[0],a.info.get("content","")) for a in output[i].annots() or [])
                assert not (original-generated)
            assert any("SOFTWARE TEST ONLY" in a.info.get("content", "") for a in output[0].annots())
    page.get_by_role("button", name="Preview generated PDF", exact=True).click()
    expect(page.locator(".pdf-preview canvas")).to_be_visible(timeout=20000)
    first_preview=wait_for_drawing(page,".pdf-preview canvas")
    page.get_by_label("Next preview page", exact=True).click()
    wait_for_drawing(page,".pdf-preview canvas",first_preview)
    page.screenshot(path="/tmp/caesar-screens/1010-real-export.png", full_page=True)
    page.get_by_label("Close dialog", exact=True).click()
    events = context.request.get(base + "/api/v1/system/logs?q=pdf.export.published").json()["events"]
    assert any(e["project_id"] == project["id"] for e in events)
    print("PASS: real 1010 PDF upload, both sheets, saved note edit/reload, source integrity, native annotation export, browser preview and correlated logs.")
