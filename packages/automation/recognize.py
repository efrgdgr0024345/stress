"""Conservative, evidence-linked recognition; no physical measurements from pixels."""
from copy import deepcopy
from decimal import Decimal
import math
import re
from statistics import median
from uuid import NAMESPACE_URL, uuid5

import fitz
from packages.engineering import dimension_mm


def identity(*parts):
    return str(uuid5(NAMESPACE_URL, ":".join(map(str, parts))))


def text_rows(words):
    # Prefer native/high-confidence observations in overlapping OCR passes.
    unique = []
    for word in sorted(words, key=lambda w: (w["method"] == "native", w["confidence"]), reverse=True):
        rect = fitz.Rect(word["bbox"])
        if any((rect & fitz.Rect(v["bbox"])).get_area() > .55 * min(rect.get_area(), fitz.Rect(v["bbox"]).get_area())
               for v in unique if rect.intersects(fitz.Rect(v["bbox"]))):
            continue
        unique.append(word)
    tolerance = max(2, min(6, median([w["bbox"][3]-w["bbox"][1] for w in unique] or [8])*.55))
    rows = []
    for word in sorted(unique, key=lambda w: ((w["bbox"][1]+w["bbox"][3])/2, w["bbox"][0])):
        y = (word["bbox"][1]+word["bbox"][3])/2
        row = next((r for r in reversed(rows[-3:]) if abs(r["y"]-y)<tolerance), None)
        if row is None:
            row = {"y":y, "words":[]}
            rows.append(row)
        row["words"].append(word)
    for row in rows:
        row["words"].sort(key=lambda w:w["bbox"][0])
        row["text"] = " ".join(w["text"] for w in row["words"])
        row["bbox"] = list(fitz.Rect(min(w["bbox"][0] for w in row["words"]),
                                    min(w["bbox"][1] for w in row["words"]),
                                    max(w["bbox"][2] for w in row["words"]),
                                    max(w["bbox"][3] for w in row["words"])))
    return rows


def family(text):
    upper = text.upper()
    for name, expression in (("valve",r"\bVALVE\b"),("flange",r"\bFLANGE\b"),
                             ("elbow",r"\bELBOW\b"),("tee",r"\bTEE\b"),
                             ("instrument",r"\b(?:METER|INSTRUMENT|PIT)\b"),
                             ("support",r"\b(?:SUPPORT|CRADLE|U-BOLT|GUIDE|LUGS)\b"),
                             ("pipe",r"\bPIPE\b")):
        if re.search(expression,upper):return name
    return "other"


def specifications(text, size, category):
    upper = text.upper()
    spec = {"family":category, "nps":size.strip().replace('"', '').replace(" in", "")}
    for pattern, value in ((r"API\s*6A", "API 6A"),(r"B16[.]5\b", "ASME B16.5"),
                           (r"B16[.]10\b", "ASME B16.10")):
        if re.search(pattern,upper):spec["standard"]=value
    match = re.search(r"\b(?:CLASS\s*|CL\s*|)(150|300|600|900|1500|2500|10000)(?:\b|LB)",upper)
    if match:spec["rating"]=match[1]
    match = re.search(r"\b(WN|SW|SO|BLIND|BALL|GATE|GLOBE|CHECK)\b",upper)
    if match:spec["component_type"]=match[1]
    elif "RTJWN" in upper:spec["component_type"]="WN"
    match = re.search(r"\b(RTJ|RF|FF)\b",upper)
    if not match and "RTJWN" in upper:spec["facing"]="RTJ"
    if match:spec["facing" if category=="flange" else "end_connection"]=match[1]
    match = re.search(r"(\d+(?:\.\d+)?)\s*[\"”]?\s*BORE",upper)
    if match:spec['pipe_bore']=match[1]
    # A weld-neck pipe bore is not the true API flange bore. Require its own
    # explicit label; ambiguous SIZE/OCR fractions remain review evidence.
    match=re.search(r'\bAPI\s+(?:6A\s+)?BORE\s*[:=]?\s*(\d+(?:[ -]+\d+/\d+|/\d+|\.\d+)?)',upper)
    if match:spec['api_bore']=re.sub(r'\s*-\s*',' ',match[1]).strip()
    return spec


def materials(page, sheet, source_sha):
    rows = text_rows(page["words"])
    headers = []
    for row in rows:
        words = row["words"]
        description = next((w for w in words if re.fullmatch(r"DESCRIPTION",w["text"],re.I)),None)
        quantity = next((w for w in words if re.fullmatch(r"QTY|QUANTITY",w["text"],re.I)),None)
        if description and quantity:
            size = next((w for w in words if w["text"].upper()=="SIZE"),None)
            code = next((w for w in words if w["text"].upper()=="CODE"),None)
            headers.append({"y":row["y"],"left":max(0,description["bbox"][0]-100),
                            "description":description["bbox"][0],"qty":quantity["bbox"][0],
                            "size":size["bbox"][0] if size else quantity["bbox"][0],
                            "code":code["bbox"][0]-40 if code else quantity["bbox"][0]})
    output, issues, ledger = [], [], []
    for index, header in enumerate(headers):
        end = headers[index+1]["y"]-25 if index+1<len(headers) else page["height"]*.82
        current = None
        for row in rows:
            if not header["y"]+8<row["y"]<end:continue
            words = [w for w in row["words"] if w["bbox"][0]>=header["left"]]
            if not words:continue
            description = [w for w in words if header["description"]-3<=w["bbox"][0]<header["size"]-6]
            text = " ".join(w["text"] for w in description)
            number = next((w for w in words if w["bbox"][0]<header["description"]-5 and re.fullmatch(r"\d+[A-Za-z]?",w["text"])),None)
            qty = [w for w in words if w["bbox"][0]>=header["qty"]-3]
            is_start = bool(number or (len(text)>10 and (qty or family(text)!="other") and
                                      re.match(r"PIPE |ELBOW |FLANGE |GASKET |BALL |GATE |FLOW |WELDED |U-BOLT |SUPPORT |BEAM |HVY |\d+[./]",text,re.I)))
            if number and current and current["item_no"].startswith("unreadable-") and row["y"]-current["source_bbox"][1]<45 and family(text)=="other":
                current["item_no"]=number["text"]
                raw_qty=" ".join(w["text"] for w in qty)
                current["quantity_raw"]=raw_qty
                current["quantity"]=int(raw_qty) if re.fullmatch(r"\d{1,5}",raw_qty) and min([w["confidence"] for w in qty] or [0])>=.8 else None
                issues[:]=[i for i in issues if not (i.get("evidence_id")==current["evidence_id"] and i["code"] in ("UNREADABLE_ITEM_NUMBER","UNRESOLVED_QUANTITY"))]
                if current["quantity"] is None:issues.append({"code":"UNRESOLVED_QUANTITY","sheet_id":sheet["id"],"evidence_id":current["evidence_id"]})
                is_start=False
            if is_start:
                raw_qty = " ".join(w["text"] for w in qty)
                count = int(raw_qty) if re.fullmatch(r"\d{1,5}",raw_qty) and min([w["confidence"] for w in qty] or [0])>=.8 else None
                if family(text)=='pipe':count=None
                item_no = number["text"] if number else f"unreadable-{len(output)+1}"
                size = " ".join(w["text"] for w in words if header["size"]-6<=w["bbox"][0]<header["code"]-3)
                box = [min(w["bbox"][0] for w in words),min(w["bbox"][1] for w in words),
                       max(w["bbox"][2] for w in words),max(w["bbox"][3] for w in words)]
                evidence = identity(source_sha,sheet["page_index"],"material",box[1],item_no)
                current = {"id":identity(sheet["id"],"material",index,item_no),"sheet_id":sheet["id"],"item_no":item_no,
                           "family":family(text),"description":text or "Unreadable source description",
                           "size":size[:100],"quantity":count,"observed":0,
                           "quantity_raw":raw_qty,"quantity_unit":"count" if count is not None else "unresolved",
                           "quantity_value":raw_qty if re.fullmatch(r'\d+(?:\.\d+)?',raw_qty) else None,
                           "evidence":f"Unreviewed source extraction; evidence {evidence}",
                           "evidence_id":evidence,"source_bbox":box,"source_sha256":source_sha,
                           "word_evidence_ids":[w.get("evidence_id") for w in words if w.get("evidence_id")],
                           "recognition_confidence":min(w["confidence"] for w in words),
                           "verification":"proposed", "origin":"automation"}
                output.append(current)
                if number is None:issues.append({"code":"UNREADABLE_ITEM_NUMBER","sheet_id":sheet["id"],"bbox":box,"evidence_id":evidence})
                if count is None:issues.append({"code":"UNRESOLVED_QUANTITY","sheet_id":sheet["id"],"bbox":box,"evidence_id":evidence})
            elif current and text and len(text)>8 and text.upper() not in ("ERECTION MATERIALS","FABRICATION MATERIALS"):
                current["description"] = (current["description"]+" "+text)[:1000]
                current["source_bbox"][3]=max(current["source_bbox"][3],row["bbox"][3])
            ledger.append({"sheet_id":sheet["id"],"bbox":row["bbox"],"text": " ".join(w["text"] for w in words),
                           "word_evidence_ids":[w.get("evidence_id") for w in words if w.get("evidence_id")],
                           "status":"proposed" if current else "unclassified"})
    for item in output:
        item["spec_proposal"]=specifications(item["description"],item["size"],item["family"])
        issues.append({"code":"ITEM_NOT_LOCATED","sheet_id":sheet["id"],"bbox":item["source_bbox"],"material_id":item["id"],"evidence_id":item["evidence_id"]})
    if not headers:issues.append({"code":"MATERIAL_TABLE_NOT_RECOGNIZED","sheet_id":sheet["id"]})
    return output, issues, ledger


def station_constraints(points, dimensions):
    """Exact signed graph propagation; inconsistent components retain nulls."""
    links = {key:[] for key in points}
    for a,b,raw in dimensions:
        if a not in points or b not in points:continue
        value=dimension_mm(raw)
        links[a].append((b,value));links[b].append((a,-value))
    values, errors, visited = {}, [], set()
    for start in points:
        if start in visited:continue
        relative={start:Decimal(0)};stack=[start];conflict=False
        while stack:
            a=stack.pop();visited.add(a)
            for b,delta in links[a]:
                proposed=relative[a]+delta
                if b in relative:
                    if relative[b]!=proposed:conflict=True
                else:relative[b]=proposed;stack.append(b)
        offsets={dimension_mm(points[k])-value for k,value in relative.items() if points[k]}
        if len(offsets)>1:conflict=True
        if conflict:
            errors.append({"code":"DIMENSION_CONFLICT","tags":sorted(relative)})
        offset=next(iter(offsets)) if len(offsets)==1 and not conflict else None
        values.update({k:str(v+offset) if offset is not None else None for k,v in relative.items()})
    return values, errors


def node_proposals(page,sheet,sha):
    rows=text_rows(page["words"]); points={}; dimensions=[]; definitions={};issues=[]
    # Qualified semantic profile: explicit kind, route and order printed in PDF.
    # Arbitrary vector endpoints never silently acquire an engineering sequence.
    pattern=r"\bPOINT\s+(\S+)\s+(ENDPOINT|SUPPORT|TEE|ELBOW)\s+ROUTE\s+(main|branch-\d{2})\s+ORDER\s+(\d+)(?:\s+STATION\s+(.+))?$"
    for row in rows:
        match=re.search(pattern,row["text"],re.I)
        if match:
            tag,kind,route,order,raw=match.groups()
            if tag in definitions:
                issues.append({"code":"AMBIGUOUS_POINT_TAG","sheet_id":sheet["id"],"bbox":row["bbox"]});continue
            try:
                if raw:dimension_mm(raw)
            except ValueError:raw=None
            points[tag]=raw;definitions[tag]=(kind.lower(),route.lower(),int(order),row)
        match=re.search(r"\bDIM\s+(\S+)\s*->\s*(\S+)\s*=\s*(.+)$",row["text"],re.I)
        if match:
            try:dimension_mm(match[3]);dimensions.append(tuple(match.groups()))
            except ValueError:issues.append({"code":"UNREADABLE_DIMENSION","sheet_id":sheet["id"],"bbox":row["bbox"]})
    solved,conflicts=station_constraints(points,dimensions)
    issues.extend(conflicts);nodes=[]
    for tag,(kind,route,order,row) in definitions.items():
        box=row["bbox"];anchor=[max(12,box[0]-12),max(12,(box[1]+box[3])/2)]
        anchor=[min(sheet["width"]-12,anchor[0]),min(sheet["height"]-12,anchor[1])]
        evidence=identity(sha,sheet["page_index"],"point",tag)
        nodes.append({"id":identity(sheet["id"],tag),"line_id":sheet["line_id"],"route":route,"order":order,
                      "kind":kind,"station_mm":None,"dimension_input":"",
                      "proposed_station_mm":solved.get(tag),"proposed_dimension_input":points[tag] or (f"{solved[tag]} mm" if solved.get(tag) is not None else ""),
                      "evidence":f"Unreviewed explicit source constraints: {tag}; evidence {evidence}",
                      "evidence_id":evidence,"origin":"automation","verification":"proposed","tag":tag,
                      "word_evidence_ids":[w.get("evidence_id") for w in row["words"] if w.get("evidence_id")],
                      "source_sha256":sha,
                      "number":None,"instances":[{"sheet_id":sheet["id"],"anchor":anchor,"bubble":anchor[:]}]})
    return nodes,issues


def vector_graph(page):
    vertices=[];edges=[]
    def endpoint(p):
        match=next((i for i,v in enumerate(vertices) if math.dist(p,v)<1),None)
        if match is None:vertices.append(p);return len(vertices)-1
        return match
    for segment in page["segments"]:
        a,b=endpoint(segment["a"]),endpoint(segment["b"])
        if a!=b and [a,b] not in edges and [b,a] not in edges:edges.append([a,b])
    return {"vertices":vertices,"edges":edges,"status":"GRAPHICAL_CANDIDATES_ONLY",
            "physical_units":None,"main_route":None,"crossings_are_junctions":False}


def free_box(width,height,box_size,exclusions,preferred=None):
    w,h=box_size
    starts=[preferred] if preferred else []
    starts += [(x,y) for y in range(60,max(61,int(height-h-12)),30)
               for x in range(60,max(61,int(width-w-12)),30)]
    for start in starts[:30000]:
        if not start:continue
        x,y=start
        box=fitz.Rect(x,y,x+w,y+h)
        if box.x0<12 or box.y0<28 or box.x1>width-12 or box.y1>height-12:continue
        if not any(box.intersects(fitz.Rect(r)+(-3,-3,3,3)) for r in exclusions):return [x,y]
    return None


def layout(project,pages):
    issues=[]
    from packages.pdf import wrapped_schedule
    for sheet in project["sheets"]:
        page=pages.get(sheet["id"])
        if not page:continue
        excluded=deepcopy(page["exclusions"])+[w["bbox"] for w in page["words"]]
        for note in project.get("annotations",[]):
            if note["sheet_id"]==sheet["id"]:excluded.append(note["rect"])
        for node in project["nodes"]:
            for instance in node["instances"]:
                if instance["sheet_id"]!=sheet["id"]:continue
                if node.get("origin")!="automation" or node.get("verification")=="reviewed":
                    x,y=instance["bubble"];excluded.append([x-14,y-14,x+14,y+14]);continue
                ax,ay=instance["anchor"]
                candidates=[(ax+dx,ay+dy) for radius in (24,45,70,100) for dx,dy in
                            ((radius,0),(-radius,0),(0,radius),(0,-radius),(radius,radius),(-radius,-radius))]
                position=next((p for p in candidates if 26<=p[0]<=sheet["width"]-26 and 42<=p[1]<=sheet["height"]-26
                               and not any(fitz.Rect(p[0]-14,p[1]-14,p[0]+14,p[1]+14).intersects(fitz.Rect(r)+(-3,-3,3,3)) for r in excluded)),None)
                if position:instance["bubble"]=list(position);excluded.append([position[0]-14,position[1]-14,position[0]+14,position[1]+14])
                else:issues.append({"code":"LABEL_LAYOUT_UNRESOLVED","sheet_id":sheet["id"],"point_id":node["id"]})
        if not sheet.get("axis"):
            position=free_box(min(sheet["width"],500),min(sheet["height"],500),(140,100),excluded)
            if position:sheet["axis"]=[position[0]+40,position[1]+48];excluded.append([*position,position[0]+140,position[1]+100])
            else:issues.append({"code":"AXIS_LAYOUT_UNRESOLVED","sheet_id":sheet["id"]})
        items=[m for m in project["materials"] if m["sheet_id"]==sheet["id"] and m["family"] in ("flange","valve")]
        if items and not sheet.get("table"):
            h=len(wrapped_schedule(items,370))*15+8
            sheet["table"]=free_box(sheet["width"],sheet["height"],(370,h),excluded)
            if not sheet["table"]:issues.append({"code":"SCHEDULE_LAYOUT_UNRESOLVED","sheet_id":sheet["id"]})
    return issues
