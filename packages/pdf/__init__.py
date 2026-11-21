"""Native PDF adapter. Display coordinates never establish physical dimensions."""

import csv
import hashlib
import io
import json
from pathlib import Path
import zipfile

import fitz
from packages.catalogs import schedule_lines

RED = (0.82, 0.19, 0.19)
BLUE = (0.12, 0.34, 0.85)


def inspect_pdf(path):
    with fitz.open(path) as doc:
        if doc.needs_pass:
            raise ValueError(
                "Password-protected PDFs are not supported. Upload an unlocked copy."
            )
        if not 1 <= len(doc) <= 100:
            raise ValueError("A source must contain between 1 and 100 pages.")
        result = []
        for i, page in enumerate(doc):
            if max(page.rect.width, page.rect.height) > 14400:
                raise ValueError("Page exceeds supported PDF dimensions.")
            text = page.get_text()[:100000]
            result.append(
                {
                    "page_index": i,
                    "width": page.cropbox.width,
                    "height": page.cropbox.height,
                    "rotation": page.rotation,
                    "text": text,
                    "format": (
                        "Vector / text" if text.strip() else "Raster / manual review"
                    ),
                }
            )
        return result


def create_sample(path):
    doc = fitz.open()
    for index in range(2):
        page = doc.new_page(width=1100, height=760)
        ink = (0.20, 0.24, 0.25)
        faint = (0.65, 0.68, 0.67)

        def text(x, y, value, size=9, color=ink):
            page.insert_text((x, y), value, fontsize=size, fontname="helv", color=color)

        def line(a, b, width=1, color=ink):
            page.draw_line(a, b, width=width, color=color)

        page.draw_rect(fitz.Rect(25, 25, 1075, 735), color=faint, width=0.6)
        text(46, 49, "SYNTHETIC TRAINING DRAWING  /  NOT FOR ENGINEERING USE", 9, faint)
        text(895, 53, "N", 12)
        line((900, 113), (900, 68), 1.3)
        line((900, 68), (895, 80))
        line((900, 68), (905, 80))
        coords = (
            [(160, 485), (340, 381), (500, 473), (500, 282), (710, 161), (885, 262)]
            if index == 0
            else [
                (170, 485),
                (350, 381),
                (540, 490),
                (730, 380),
                (730, 210),
                (920, 100),
            ]
        )
        for a, b in zip(coords, coords[1:]):
            line(a, b, 2.2)
        for j, (x, y) in enumerate(coords):
            page.draw_circle((x, y), 3, fill=ink, color=ink)
            if j in (1, 4):
                line((x - 9, y - 14), (x + 9, y + 14), 2)
                line((x - 4, y - 17), (x + 14, y + 11), 2)
        x, y = coords[2]
        line((x, y), (x + 146, y + 84), 2.2)
        line((x + 146, y + 84), (x + 146, y + 115), 2.2)
        text(x + 165, y + 112, "VENT / BRANCH 01", 9)
        for a, b in [(coords[0], coords[1]), (coords[3], coords[4])]:
            aa = (a[0] - 22, a[1] - 32)
            bb = (b[0] - 22, b[1] - 32)
            line(aa, bb, 0.5, faint)
            line((aa[0] - 4, aa[1] - 7), (aa[0] + 4, aa[1] + 7), 0.5)
            line((bb[0] - 4, bb[1] - 7), (bb[0] + 4, bb[1] + 7), 0.5)
            text((aa[0] + bb[0]) / 2 - 12, (aa[1] + bb[1]) / 2 - 10, "1200", 9)
        for j, (x, y) in enumerate([coords[0], coords[3]]):
            line((x - 12, y + 22), (x + 12, y + 22), 1)
            line((x, y), (x, y + 22))
            text(x - 16, y + 40, f"S-{index + 1}0{j + 1}", 8)
        text(
            coords[0][0] - 20,
            coords[0][1] + 68,
            "FROM EQUIPMENT" if index == 0 else "CONT. FROM SHEET 1",
            8,
        )
        text(
            coords[-1][0] - 40,
            coords[-1][1] - 20,
            "CONT. ON SHEET 2" if index == 0 else "TO BATTERY LIMIT",
            8,
        )
        page.draw_rect(fitz.Rect(47, 590, 560, 687), color=faint, width=0.7)
        text(57, 609, "BILL OF MATERIALS  /  SYNTHETIC EXAMPLE", 9)
        for j, value in enumerate(
            [
                "01   PIPE, SEAMLESS   8 IN   ASTM A106 GR B",
                "02   ELBOW, 90 DEG   8 IN   ASTM A234 WPB",
                "03   FLANGE, WN   8 IN   ASME B16.5",
                "04   BALL VALVE   8 IN   VENDOR TO BE CONFIRMED",
            ]
        ):
            text(57, 628 + j * 15, value, 8)
        page.draw_rect(fitz.Rect(590, 605, 1050, 710), color=faint, width=0.7)
        text(609, 628, "CAESAR  /  ENGINEERING SANDBOX", 12)
        text(609, 651, "LINE: DEMO-8-CS-001     /     UTILITY WATER", 10)
        text(
            609,
            675,
            f"ISO-TRAINING-001    |    SHEET {index + 1} OF 2    |    REV A",
            9,
        )
        text(609, 695, "NOT TO SCALE   -   ALL GEOMETRY IS ILLUSTRATIVE", 8)
    doc.save(path)
    doc.close()


def content_hash(page):
    return [
        hashlib.sha256(page.parent.xref_stream(x)).hexdigest()
        for x in page.get_contents()
    ]


def wrap_text(text, width, fontsize=6.5):
    if width < 10:
        raise ValueError("Annotation is too narrow for readable text.")
    lines = []
    for paragraph in str(text).split("\n"):
        segment = ""
        for character in paragraph:
            if (
                fitz.get_text_length(
                    segment + character, fontname="helv", fontsize=fontsize
                )
                > width
            ):
                lines.append(segment)
                segment = ""
            segment += character
        lines.append(segment)
    return lines


def wrapped_schedule(materials, width):
    return [
        line
        for text in schedule_lines(materials)
        for line in wrap_text(text, width - 10)
    ]


def export_bundle(project, source_path, output_path):
    doc = fitz.open()
    originals = []
    for sheet in project["sheets"]:
        with fitz.open(source_path(sheet["source_id"])) as source:
            page = source[sheet["page_index"]]
            originals.append(content_hash(page))
            doc.insert_pdf(
                source,
                from_page=sheet["page_index"],
                to_page=sheet["page_index"],
                annots=True,
            )
    manifest = []

    def register(annot, page, sheet, role, group, color=RED):
        name = f"caesar:{project['id']}:{sheet['id']}:{group}:{role}"
        annot.set_info(
            title="CAESAR ISO",
            subject=f"{role} | {group}",
            content=annot.info.get("content", ""),
        )
        doc.xref_set_key(annot.xref, "NM", fitz.get_pdf_str(name))
        annot.update()
        manifest.append(
            {
                "name": name,
                "type": annot.type[1],
                "sheet_id": sheet["id"],
                "group": group,
                "role": role,
                "rect": list(annot.rect),
                "revision": project["version"],
            }
        )

    for i, sheet in enumerate(project["sheets"]):
        page = doc[i]
        for note in [
            n for n in project.get("annotations", []) if n["sheet_id"] == sheet["id"]
        ]:
            rect = fitz.Rect(note["rect"])
            color = tuple(int(note["color"][j : j + 2], 16) / 255 for j in (1, 3, 5))
            if note["kind"] == "FreeText":
                lines = wrap_text(note["text"], rect.width - 4, 10)
                if len(lines) * 12 > rect.height - 4:
                    doc.close()
                    raise ValueError(
                        "A text note does not fit its box. Enlarge the annotation before exporting."
                    )
                annotation = page.add_freetext_annot(
                    rect, "\n".join(lines), fontsize=10, text_color=color
                )
            elif note["kind"] == "Circle":
                annotation = page.add_circle_annot(rect)
                annotation.set_colors(stroke=color)
            elif note["kind"] == "Square":
                annotation = page.add_rect_annot(rect)
                annotation.set_colors(stroke=color)
            else:
                annotation = page.add_line_annot(note["rect"][:2], note["rect"][2:])
                annotation.set_colors(stroke=color)
            register(annotation, page, sheet, "drawing-note", note["id"], color)
        for node in project["nodes"]:
            for inst in [v for v in node["instances"] if v["sheet_id"] == sheet["id"]]:
                color = BLUE if node["reasons"] else RED
                x, y = inst["bubble"]
                ax, ay = inst["anchor"]
                radius = 12
                leader = page.add_line_annot((ax, ay), (x, y))
                leader.set_colors(stroke=color)
                leader.set_border(width=0.8)
                register(leader, page, sheet, "leader", node["id"], color)
                circle = page.add_circle_annot(
                    fitz.Rect(x - radius, y - radius, x + radius, y + radius)
                )
                circle.set_colors(stroke=color, fill=(1, 1, 1))
                circle.set_border(width=1)
                register(circle, page, sheet, "bubble", node["id"], color)
                label = page.add_freetext_annot(
                    fitz.Rect(x - 12, y - 6, x + 12, y + 9),
                    str(node["number"]),
                    fontsize=8,
                    text_color=color,
                    align=1,
                )
                register(label, page, sheet, "number", node["id"], color)
        # All notices are native editable objects; source page streams are untouched.
        notice = page.add_freetext_annot(
            fitz.Rect(32, 6, max(200, sheet["width"] - 32), 23),
            "ENGINEERING REVIEW DRAFT | NOT VERIFIED FOR MODELLING",
            fontsize=8,
            text_color=RED,
        )
        register(notice, page, sheet, "draft-status", "release")
        if sheet.get("axis"):
            x, y = sheet["axis"]
            for label, dx, dy in [
                ("X / +Mx", 36, 20),
                ("Y / +My", -30, 20),
                ("Z / +Mz", 0, -35),
            ]:
                arrow = page.add_line_annot((x, y), (x + dx, y + dy))
                arrow.set_colors(stroke=RED)
                arrow.set_line_ends(0, 4)
                register(arrow, page, sheet, f"axis-{label[0]}-line", "triad")
                note = page.add_freetext_annot(
                    fitz.Rect(x + dx - 10, y + dy - 12, x + dx + 46, y + dy + 2),
                    label,
                    fontsize=7,
                    text_color=RED,
                )
                register(note, page, sheet, f"axis-{label[0]}-label", "triad")
        rows = [
            m
            for m in project["materials"]
            if m["sheet_id"] == sheet["id"] and m["family"] in ("flange", "valve")
        ]
        if rows and sheet.get("table"):
            x, y = sheet["table"]
            width = min(370, sheet["width"] - x - 8)
            lines = wrapped_schedule(rows, width)
            if y + len(lines) * 15 + 8 > sheet["height"] - 8 or any(
                fitz.get_text_length(value, fontname="helv", fontsize=6.5) > width - 10
                for value in lines
            ):
                doc.close()
                raise ValueError(
                    "The component schedule does not fit. Move it to a larger clear area or shorten item / size labels before exporting."
                )
            border = page.add_rect_annot(
                fitz.Rect(x, y, x + width, y + len(lines) * 15 + 8)
            )
            border.set_colors(stroke=RED)
            register(border, page, sheet, "schedule-border", "schedule")
            for index, value in enumerate(lines):
                note = page.add_freetext_annot(
                    fitz.Rect(
                        x + 5, y + 5 + index * 15, x + width - 4, y + 20 + index * 15
                    ),
                    value,
                    fontsize=6.5,
                    text_color=RED,
                )
                register(note, page, sheet, f"schedule-row-{index}", "schedule")
    pdf_bytes = doc.tobytes(garbage=3, deflate=True)
    doc.close()
    with fitz.open(stream=pdf_bytes, filetype="pdf") as check:
        if any(content_hash(page) != originals[i] for i, page in enumerate(check)):
            raise ValueError("Original source content changed. Export aborted.")
        names = {a.info["id"] for page in check for a in (page.annots() or [])}
        if not all(m["name"] in names for m in manifest):
            raise ValueError("Native annotation integrity check failed.")
    csv_file = io.StringIO()
    writer = csv.writer(csv_file)
    writer.writerow(
        [
            "physical_point_id",
            "node_number",
            "line_id",
            "route",
            "kind",
            "station_mm",
            "dimension_input",
            "evidence",
            "reasons",
            "sheet_instances",
        ]
    )

    def safe_cell(value):
        # Text from drawings / engineer input must stay literal in spreadsheet apps.
        return (
            "'" + value
            if isinstance(value, str)
            and value.startswith(("=", "+", "-", "@", "\t", "\r", "\n"))
            else value
        )

    for n in project["nodes"]:
        writer.writerow(
            [
                n["id"],
                n["number"],
                safe_cell(n["line_id"]),
                n["route"],
                n["kind"],
                n["station_mm"],
                safe_cell(n.get("dimension_input", "")),
                safe_cell(n["evidence"]),
                "|".join(n["reasons"]),
                len(n["instances"]),
            ]
        )
    with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("annotated-review.pdf", pdf_bytes)
        archive.writestr("nodes.csv", csv_file.getvalue())
        for filename, value in [
            ("project.json", project),
            ("annotation-manifest.json", manifest),
            ("exceptions.json", project["issues"]),
            ("materials.json", project["materials"]),
            (
                "catalog-provenance.json",
                [
                    {"material_id": m["id"], **m["catalog_match"]}
                    for m in project["materials"]
                    if m.get("catalog_match")
                ],
            ),
            ("numbering-map.json", project.get("numbering_map", [])),
            (
                "qa.json",
                {
                    "source_content_unchanged": True,
                    "native_annotations": len(manifest),
                    "structural_check": "passed",
                    "desktop_editor_roundtrip": "not tested",
                    "release": "ENGINEERING_REVIEW_DRAFT",
                },
            ),
        ]:
            archive.writestr(filename, json.dumps(value, indent=2))
    return len(manifest)
