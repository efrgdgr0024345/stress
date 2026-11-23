"""Bounded native/vector/OCR observations in unrotated PDF coordinates."""
import csv
import hashlib
import io
import os
import math
from pathlib import Path
import shutil
import subprocess
import tempfile

import fitz
from packages.automation import VERSION
from packages.automation.symbols import flange_symbols
from uuid import uuid5,NAMESPACE_URL


def extract_page(path, index, ocr=True):
    source_sha=hashlib.sha256(Path(path).read_bytes()).hexdigest()
    with fitz.open(path) as doc:
        page = doc[index]
        words = [{"text": w[4][:300], "bbox": list(w[:4]), "confidence": 1.0,
                  "method": "native"} for w in page.get_text("words")[:30000]]
        paths = page.get_cdrawings()
        limited=len(paths)>50000 or len(words)>=30000
        segments, exclusions = [], []
        # The threshold identifies graphical candidates, never physical lengths.
        for drawing in paths[:50000]:
            rect = list(drawing["rect"])
            if len(exclusions) < 20000:
                exclusions.append(rect)
            if drawing["type"] != "s" or drawing.get("width", 0) < 0.7:
                continue
            for item in drawing["items"]:
                if item[0] == "l" and len(segments) < 1000:
                    a, b = list(item[1]), list(item[2])
                    if math.dist(a, b) >= 8:
                        segments.append({"a": a, "b": b, "width": drawing["width"]})
        symbols, symbols_limited = flange_symbols(paths, source_sha, index)
        symbols = [s for s in symbols if 0 <= s['bbox'][0] < s['bbox'][2] <= page.cropbox.width
                   and 0 <= s['bbox'][1] < s['bbox'][3] <= page.cropbox.height]
        issues = []
        uncertain=[]
        if limited or len(segments)>=1000 or len(exclusions)>=20000 or symbols_limited:issues.append("OBSERVATION_LIMIT_REACHED")
        for annotation in list(page.annots() or [])[:1000]:
            if len(exclusions)<20000:exclusions.append(list(annotation.rect))
        if page.get_image_info():
            scale=min(1,800/max(page.rect.width,page.rect.height))
            occupancy=page.get_pixmap(matrix=fitz.Matrix(scale,scale),colorspace=fitz.csGRAY,alpha=False,annots=False)
            pixels=occupancy.samples
            for top in range(0,occupancy.height,16):
                for left in range(0,occupancy.width,16):
                    if any(pixels[y*occupancy.width+x]<245 for y in range(top,min(top+16,occupancy.height),2) for x in range(left,min(left+16,occupancy.width),2)):
                        box=fitz.Rect(left/scale,top/scale,min(left+16,occupancy.width)/scale,min(top+16,occupancy.height)/scale)*page.derotation_matrix
                        if len(exclusions)<20000:exclusions.append(list(box))
        used_ocr = False
        if ocr and len(" ".join(w["text"] for w in words)) < 200:
            native_ocr=shutil.which('tesseract')
            portable=None
            if not native_ocr and os.environ.get('CAESAR_OCR_HOME'):
                import tesserocr
                portable=tesserocr
            if not native_ocr and portable is None:
                issues.append("OCR_UNAVAILABLE")
            else:
                # A whole-page pass plus a higher-resolution right-table pass.
                # No drawing-template anchors or known 1010 text are embedded.
                regions = [(page.rect, 1.8, "11"),
                           (fitz.Rect(page.rect.width * .65, 0, page.rect.width,
                                      page.rect.height * .85), 3.0, "6")]
                for clip, scale, segmentation in regions:
                    scale = min(scale, math.sqrt(14000000 / max(1, clip.get_area())))
                    image = page.get_pixmap(matrix=fitz.Matrix(scale, scale), clip=clip,
                                            colorspace=fitz.csGRAY, alpha=False, annots=False)
                    with tempfile.TemporaryDirectory(prefix="ocr-", dir=Path.cwd()) as directory:
                        png = Path(directory) / "page.png"
                        image.save(png)
                        if native_ocr:
                            result = subprocess.run([native_ocr, str(png), "stdout", "-l", "eng",
                                                     "--psm", segmentation, "tsv"], capture_output=True,
                                                    timeout=100, check=True)
                            tsv=result.stdout.decode('utf8','replace')
                        else:
                            with portable.PyTessBaseAPI(path=str(Path(os.environ['CAESAR_OCR_HOME'])/'tessdata'),lang='eng',psm=int(segmentation)) as engine:
                                engine.SetImageFile(str(png));tsv='level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext\n'+engine.GetTSVText(0)
                    used_ocr = True
                    for row in csv.DictReader(io.StringIO(tsv), delimiter="\t", quoting=csv.QUOTE_NONE):
                        text = (row.get("text") or "").strip()[:300]
                        if not text or len(words) >= 30000:
                            continue
                        confidence = float(row["conf"]) / 100
                        x, y, w, h = (float(row[k]) for k in ("left", "top", "width", "height"))
                        box = fitz.Rect(clip.x0 + x / scale, clip.y0 + y / scale,
                                        clip.x0 + (x+w) / scale, clip.y0 + (y+h) / scale)
                        box = box * page.derotation_matrix
                        if confidence<.15:
                            if len(uncertain)<5000:uncertain.append({"text":text,"bbox":list(box),"confidence":max(0,confidence),"method":"ocr"})
                            continue
                        # Crop overlaps/native review text must not duplicate observations.
                        if any(v["text"].casefold() == text.casefold() and
                               fitz.Rect(v["bbox"]).intersects(box) for v in words):
                            continue
                        words.append({"text": text, "bbox": list(box),
                                      "confidence": round(confidence, 4), "method": "ocr"})
        if uncertain:issues.append("LOW_CONFIDENCE_TEXT")
        for word in words+uncertain:word["evidence_id"]=str(uuid5(NAMESPACE_URL,source_sha+f':{index}:'+repr(word)))
        return {"page_index": index, "width": page.cropbox.width,
                "height": page.cropbox.height, "rotation": page.rotation,
                "words": words, "uncertain_words":uncertain,"segments": segments, "exclusions": exclusions,"symbols":symbols,
                "source_sha256":source_sha,"extractor_version":VERSION,"pdf_library_version":fitz.VersionBind,
                "ocr_used": used_ocr, "issues": issues,
                "content_hash": [__import__("hashlib").sha256(doc.xref_stream(x)).hexdigest()
                                 for x in page.get_contents()]}
