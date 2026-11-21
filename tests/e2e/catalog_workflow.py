from pathlib import Path
from openpyxl import Workbook
from playwright.sync_api import expect


def exercise_catalogs(page, context, base, directory):
    values = {
        "family": "flange",
        "standard": "ASME B16.5",
        "rating": "150",
        "nps": "8",
        "component_type": "WN",
        "facing": "RF",
        "source": "Synthetic browser test datasource - not engineering data",
        "quality": "REFERENCE_ONLY",
        "weight_n": "100",
        "weight_scope": "BARE_FLANGE",
        "studs_weight_n": "40",
        "nut_weight_n": "5",
        "stud_count": "4",
    }
    book = Workbook()
    book.active.title = "Flanges"
    book.active.append(list(values))
    book.active.append(list(values.values()))
    path = Path(directory) / "browser-flange-source.xlsx"
    book.save(path)
    book.close()
    page.get_by_role("button", name="Component catalogs", exact=True).click()
    page.locator('input[accept=".xlsx"]').set_input_files(path)
    dialog = page.get_by_role("dialog", name="Map workbook columns")
    expect(dialog).to_be_visible()
    expect(dialog.locator(".catalog-preview")).to_be_visible()
    page.get_by_role("button", name="Create dataset version", exact=True).click()
    expect(page.get_by_role("dialog")).to_have_count(0)
    page.get_by_role("button", name="Inspect normalized records", exact=True).click()
    expect(page.locator(".catalog-preview")).to_contain_text("100")
    page.get_by_label("Dataset review evidence", exact=True).fill(
        "Synthetic browser QA: source fields, units and source quality checked"
    )
    page.get_by_role("button", name="Approve dataset for matching", exact=True).click()
    expect(page.locator(".catalog-version .badge")).to_have_text("Approved")
    page.get_by_role("button", name="Projects", exact=True).click()
    page.locator(".project-table tbody tr").filter(
        has_text="North utility corridor"
    ).click()
    page.get_by_role("button", name="Materials", exact=True).click()
    material_row = page.locator("tbody tr").filter(has_text="Weld neck flange").first
    material_row.get_by_role("button", name="Match catalog", exact=True).click()
    dialog = page.get_by_role("dialog", name="Catalog match · Item 3")
    expect(dialog).to_be_visible()
    for name, value in [
        ("Standard", "ASME B16.5"),
        ("Class / pressure rating", "150"),
        ("Pipe NPS", "8"),
        ("Component / flange type", "WN"),
        ("Facing", "RF"),
    ]:
        dialog.get_by_label(name, exact=True).fill(value)
    dialog.get_by_label("Match evidence / review reason", exact=True).fill(
        "Synthetic source item matches the full drawing specification exactly"
    )
    page.get_by_role("button", name="Find exact matches", exact=True).click()
    expect(
        page.get_by_role("button", name="Save this exact match", exact=True)
    ).to_be_visible()
    page.get_by_role("button", name="Save this exact match", exact=True).click()
    expect(page.get_by_role("dialog")).to_have_count(0)
    expect(material_row).to_contain_text("W 100 N")
    project = context.request.get(base + "/api/v1/projects").json()[0]
    matched = next(m for m in project["materials"] if m.get("catalog_match"))
    assert matched["catalog_match"]["record"]["half_weight_n"] == "140"
    assert matched["catalog_match"]["record"]["quality"] == "REFERENCE_ONLY"
