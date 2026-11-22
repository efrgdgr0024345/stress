"""Engineering rules; independent of HTTP and presentation coordinates."""

from decimal import Decimal, InvalidOperation
from fractions import Fraction
import re


def dimension_mm(raw: str) -> Decimal:
    """Parse explicit mm, inches or feet/inches without floating-point scaling."""
    text = raw.strip().lower().replace("″", '"').replace("′", "'")
    sign = -1 if text.startswith("-") else 1
    text = (text[1:] if text.startswith(("+", "-")) else text).strip()

    def number(value):
        value = value.strip()
        if not re.fullmatch(
            r"(?:\d+(?:\.\d+)?|\.\d+|\d+/\d+|\d+(?:\s+|\s*-\s*)\d+/\d+)", value
        ):
            raise ValueError(
                "A dimension requires a numeric value; units alone do not mean zero."
            )
        parts = value.replace("-", " ").split()
        total = sum((Fraction(p) for p in parts), Fraction(0))
        return Decimal(total.numerator) / Decimal(total.denominator)

    try:
        if text.endswith("mm"):
            value = number(text[:-2])
        elif "'" in text:
            feet, inches = text.split("'", 1)
            inches = inches.strip()
            if inches.startswith("-"):
                inches = inches[1:].strip()
            inches = re.sub(r"(in|\")$", "", inches).strip()
            value = (number(feet) * 12 + number(inches or "0")) * Decimal("25.4")
        elif text.endswith(('"', "in")):
            value = number(re.sub(r"(in|\")$", "", text)) * Decimal("25.4")
        else:
            raise ValueError("Enter an explicit unit: mm, in, or feet/inches.")
    except (InvalidOperation, ZeroDivisionError, ValueError) as exc:
        raise ValueError(
            "Invalid dimension. Examples: 152.4 mm, 2 1/8 in, 3' 2\"."
        ) from exc
    if not value.is_finite():
        raise ValueError("Dimension must be finite.")
    return value * sign


def next_boundary(number, block):
    return (number // block + 1) * block


def renumber(nodes):
    """Route order is explicitly engineer-entered; sheets never set numbering order."""
    lines = list(dict.fromkeys(n["line_id"] for n in nodes))
    mapping, previous_max = [], 0
    for line_index, line in enumerate(lines):
        group = [n for n in nodes if n["line_id"] == line]
        main = sorted(
            [n for n in group if n["route"] == "main"],
            key=lambda n: (n["order"], n["id"]),
        )
        if not main:
            raise ValueError(
                f"{line}: a main route is required before branch numbering."
            )
        start = 10 if line_index == 0 else next_boundary(previous_max, 1000)
        assigned = []
        for i, node in enumerate(main):
            assigned.append((node, start + i * 10))
        branch_base = next_boundary(assigned[-1][1], 100)
        by_id = {n["id"]: n for n in main}

        def branch_key(route):
            members = [n for n in group if n["route"] == route]
            takeoff = by_id.get(members[0].get("takeoff_id"))
            return (takeoff["order"] if takeoff else 100001, route)

        branches = sorted(
            set(n["route"] for n in group if n["route"] != "main"), key=branch_key
        )
        for branch in branches:
            points = sorted(
                [n for n in group if n["route"] == branch],
                key=lambda n: (n["order"], n["id"]),
            )
            for i, node in enumerate(points):
                assigned.append((node, branch_base + i * 10))
            branch_base = next_boundary(assigned[-1][1], 100)
        for node, number in assigned:
            mapping.append(
                {"point_id": node["id"], "old": node.get("number"), "new": number}
            )
            node["number"] = number
        previous_max = max(number for _, number in assigned)
    return mapping


def topology(nodes):
    """Build directed route edges from explicit model order and shared main-run tees."""
    edges = []
    for line, route in sorted(set((n["line_id"], n["route"]) for n in nodes)):
        ordered = sorted(
            [n for n in nodes if n["line_id"] == line and n["route"] == route],
            key=lambda n: (n["order"], n["id"]),
        )
        if route != "main" and ordered and ordered[0].get("takeoff_id"):
            edges.append(
                {
                    "from": ordered[0]["takeoff_id"],
                    "to": ordered[0]["id"],
                    "line_id": line,
                    "route": route,
                }
            )
        edges += [
            {"from": a["id"], "to": b["id"], "line_id": line, "route": route}
            for a, b in zip(ordered, ordered[1:])
        ]
    return {
        "points": [n["id"] for n in nodes],
        "edges": edges,
        "source": "engineer-entered route order; not inferred from drawing pixels",
    }


def compute_reasons(nodes):
    for node in nodes:
        reasons = []
        if node.get("origin")=="automation" and node.get("verification")!="reviewed":
            reasons.append("SOURCE_PROPOSAL_REVIEW")
        if node.get("station_mm") is None or not node.get("evidence", "").strip():
            reasons.append("UNVERIFIED_DIMENSION")
        if node.get("kind") == "continuation" and len(node["instances"]) < 2:
            reasons.append("PROVISIONAL_CONTINUATION")
        reasons.extend(r for r in node.get('component_review_reasons',[]) if r not in reasons)
        node["reasons"] = reasons
        node["support_gap_mm"] = None
    routes = set((n["line_id"], n["route"]) for n in nodes)
    for line, route in routes:
        supports = sorted(
            [
                n
                for n in nodes
                if n["line_id"] == line
                and n["route"] == route
                and (n["kind"] == "support" or any(p['kind']=='support' for p in n.get('component_ports',[])))
            ],
            key=lambda n: (n["order"], n["id"]),
        )
        for first, second in zip(supports, supports[1:]):
            if all(
                n.get("station_mm") is not None and n.get("evidence", "").strip()
                for n in (first, second)
            ):
                gap = abs(Decimal(second["station_mm"]) - Decimal(first["station_mm"]))
                second["support_gap_mm"] = str(gap)
                if gap <= Decimal("152.4"):
                    second["reasons"].append("SUPPORT_WITHIN_6_IN")
    return nodes


def validate(project):
    compute_reasons(project["nodes"])
    project["graph"] = topology(project["nodes"])
    issues = list(project.get("automation",{}).get("issues",[]))
    from packages.physical import audit as physical_audit
    from packages.physical.constraints import solve
    issues.extend(physical_audit(project)['issues'])
    if project.get('physical_model') or project.get('analysis_model'):issues.extend(solve(project)['issues'])
    orders = {}
    for node in project["nodes"]:
        key = (node["line_id"], node["route"], node["order"])
        orders[key] = orders.get(key, 0) + 1
    for (line, route, order), count in orders.items():
        if count > 1:
            issues.append(
                {
                    "code": "DUPLICATE_ROUTE_ORDER",
                    "severity": "critical",
                    "message": f"{line} / {route}: {count} points share route order {order}. Confirm their physical sequence.",
                }
            )
    if not project["sheets"]:
        issues.append(
            {
                "code": "NO_SOURCE",
                "severity": "critical",
                "message": "Upload a source PDF to begin.",
            }
        )
    if not project["nodes"]:
        issues.append(
            {
                "code": "NO_REVIEWED_ROUTE",
                "severity": "critical",
                "message": "Add and review a main route before release.",
            }
        )
    for node in project["nodes"]:
        if node["route"] != "main" and not node.get("takeoff_id"):
            issues.append(
                {
                    "code": "BRANCH_TAKEOFF_REQUIRED",
                    "severity": "critical",
                    "point_id": node["id"],
                    "node": node.get("number"),
                    "message": f"Node {node.get('number')}: associate this branch with its existing main-run tee.",
                }
            )
        for reason in node["reasons"]:
            issues.append(
                {
                    "code": reason,
                    "severity": (
                        "review" if reason == "SUPPORT_WITHIN_6_IN" else "critical"
                    ),
                    "point_id": node["id"],
                    "node": node.get("number"),
                    "message": f"Node {node.get('number', '—')}: {reason.replace('_', ' ').lower()}.",
                }
            )
    for item in project["materials"]:
        unit=item.get('quantity_unit','count')
        if item.get("quantity") is None and unit in ('count','unresolved'):
            issues.append({"code":"UNKNOWN_SOURCE_QUANTITY","severity":"critical","material_id":item["id"],"message":f"Item {item['item_no']}: listed quantity/unit needs source review; original value retained."})
        if item.get("origin")=="automation" and item.get("verification")!="reviewed":
            issues.append({"code":"MATERIAL_PROPOSAL_REVIEW","severity":"critical","material_id":item["id"],"message":f"Item {item['item_no']}: verify extracted description, size and quantity against the source."})
        if unit not in ('count','unresolved') and (item.get('quantity_value') is None or item.get('observed_quantity_value') is None or Decimal(item['quantity_value'])!=Decimal(item['observed_quantity_value'])):
            issues.append({'code':'LENGTH_QUANTITY_RECONCILIATION','severity':'critical','material_id':item['id'],'message':f"Item {item['item_no']}: reconcile the source length quantity in {unit}; component counts are a separate observation."})
        if unit=='unresolved':
            issues.append({'code':'SOURCE_QUANTITY_UNIT_REVIEW','severity':'critical','material_id':item['id'],'message':f"Item {item['item_no']}: confirm the source quantity and unit; decimal lengths are not component counts."})
        if unit=='count' and item["observed"] != item["quantity"]:
            issues.append(
                {
                    "code": "QUANTITY_MISMATCH",
                    "severity": "critical",
                    "message": f"Item {item['item_no']}: {item['observed']} located / {item['quantity']} listed.",
                    "material_id": item["id"],
                }
            )
        if item["family"] in ("flange", "valve"):
            match = item.get("catalog_match")
            if not match:
                issues.append(
                    {
                        "code": "NO_EXACT_MATCH",
                        "severity": "critical",
                        "message": f"Item {item['item_no']}: authoritative {item['family']} catalog match required.",
                        "material_id": item["id"],
                    }
                )
            else:
                record = match["record"]
                if match.get("status") != "MANUFACTURER_CONFIRMED":
                    issues.append(
                        {
                            "code": "MANUFACTURER_UNCONFIRMED",
                            "severity": "critical",
                            "material_id": item["id"],
                            "message": f"Item {item['item_no']}: catalog values are {record.get('quality','unconfirmed')}; confirm actual manufacturer data before final modelling.",
                        }
                    )
                for key in ["weight_n"] + (
                    ["length_mm"]
                    if item["family"] == "valve"
                    else ["half_weight_n", "full_weight_n"]
                ):
                    if record.get(key) is None:
                        issues.append(
                            {
                                "code": "UNKNOWN_CATALOG_VALUE",
                                "severity": "critical",
                                "material_id": item["id"],
                                "message": f"Item {item['item_no']}: {key} remains unknown (N/A), not zero.",
                            }
                        )
    if not project.get("materials_reviewed"):
        issues.append(
            {
                "code": "MATERIALS_REVIEW_REQUIRED",
                "severity": "critical",
                "message": "Reconcile the source materials list and confirm the review.",
            }
        )
    if not project.get("layout_reviewed"):
        issues.append(
            {
                "code": "LAYOUT_REVIEW_REQUIRED",
                "severity": "critical",
                "message": "Review all sheets for annotation collisions, north-arrow clearance and readable placement.",
            }
        )
    issues.append(
        {
            "code": "TARGET_EDITOR_NOT_TESTED",
            "severity": "critical",
            "message": "Native PDF objects are tested structurally. Editor-specific editing behavior still needs compatibility testing; drawings remain editable within this website.",
        }
    )
    return issues
