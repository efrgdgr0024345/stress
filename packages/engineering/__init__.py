"""Engineering rules; independent of HTTP and presentation coordinates."""

from decimal import Decimal, InvalidOperation, localcontext
from fractions import Fraction
from copy import deepcopy
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


def topology_assigned(node):
    """A located source feature is not an accepted place in an ordered route.

    Old explicit-route records predate this state and retain their behavior.
    New unassigned source points remain visible without creating adjacency.
    """
    return (node.get('topology_state', 'ASSIGNED') == 'ASSIGNED'
            and bool(re.fullmatch(r'main|branch-\d{2}', node.get('route') or ''))
            and isinstance(node.get('order'), int) and not isinstance(node.get('order'), bool)
            and 0 <= node['order'] <= 100000)


def assigned_nodes(nodes):
    return [node for node in nodes if topology_assigned(node)]


def source_observations(node):
    """Canonical per-source observations, retaining the primary legacy field."""
    result=[];seen=set()
    for observation in ([node['source_observation']] if node.get('source_observation') else [])+node.get('source_observations',[]):
        key=(observation.get('id'),observation.get('sheet_id'))
        if key in seen:continue
        seen.add(key);result.append(observation)
    return result


def _source_observation_reviewed(node,observation,sheets=None):
    proof=observation.get('review_proof') or {};anchor=proof.get('anchor')
    if not isinstance(anchor,(list,tuple)) or len(anchor)!=2:return False
    if observation.get('verification')!='reviewed' or not proof.get('reviewed_by') or not proof.get('evidence'):return False
    if proof.get('sheet_id')!=observation.get('sheet_id'):return False
    instance=next((i for i in node.get('instances',[]) if i['sheet_id']==proof['sheet_id']),None)
    if not instance or list(instance['anchor'])!=list(anchor):return False
    if observation.get('content_hash'):
        if proof.get('content_hash')!=observation['content_hash']:return False
    elif proof.get('source_sha256')!=observation.get('source_sha256'):return False
    if sheets is not None:
        sheet=sheets.get(proof['sheet_id'])
        if not sheet:return False
        if proof.get('content_hash'):
            if proof['content_hash']!=sheet.get('content_hash'):return False
        elif proof.get('source_sha256')!=sheet.get('sha256'):return False
    return True


def source_location_reviewed(node,sheets=None,sheet_id=None):
    """A shared UUID retains an independent inspection on each source sheet."""
    observations=source_observations(node)
    if sheet_id is not None:observations=[o for o in observations if o.get('sheet_id')==sheet_id]
    return bool(observations) and all(_source_observation_reviewed(node,o,sheets) for o in observations)


def record_source_location_review(node,proof):
    observations=source_observations(node)
    targets=[o for o in observations if o.get('sheet_id')==proof['sheet_id']]
    if not targets:raise ValueError('No source observation exists for the inspected sheet.')
    for observation in targets:
        if observation.get('verification')=='reviewed' and observation.get('review_proof'):
            observation.setdefault('review_history',[]).append(deepcopy(observation['review_proof']))
        observation.update(verification='reviewed',review_proof=deepcopy(proof))
        observation.pop('review_invalidated_reason',None)
    if node.get('source_observations') is not None or len(observations)>1:node['source_observations']=deepcopy(observations)


def refresh_source_locations(project):
    """Invalidate only changed source inspections, retaining every prior proof."""
    sheets={s['id']:s for s in project.get('sheets',[])}
    for node in project['nodes']:
        observations=source_observations(node)
        for observation in observations:
            if observation.get('verification')=='reviewed' and not _source_observation_reviewed(node,observation,sheets):
                if observation.get('review_proof'):observation.setdefault('review_history',[]).append(deepcopy(observation['review_proof']))
                observation['verification']='proposed';observation['review_invalidated_reason']='SOURCE_CONTENT_OR_ANCHOR_CHANGED'
        if node.get('source_observations') is not None or len(observations)>1:node['source_observations']=deepcopy(observations)


def renumber(nodes, primary_line=None):
    """Deterministic labels only; route/source geometry and identities are retained.

    Explicit but incomplete legacy branches may still receive display numbers.
    Their missing takeoff remains a typed graph exception, never an invented edge.
    Invalid identity/order ambiguity fails before any number is changed.
    """
    ids=[n['id'] for n in nodes]
    if len(ids)!=len(set(ids)):raise ValueError('Duplicate physical point IDs prevent unambiguous numbering.')
    eligible=assigned_nodes(nodes)
    lines=sorted({n['line_id'] for n in eligible},key=lambda line:(line!=primary_line,line))
    planned={};previous_max=0
    for line_index,line in enumerate(lines):
        group=[n for n in eligible if n['line_id']==line]
        routes={route:sorted((n for n in group if n['route']==route),key=lambda n:(n['order'],n['id']))
                for route in {n['route'] for n in group}}
        for route,members in routes.items():
            if len({n['order'] for n in members})!=len(members):
                raise ValueError(f'{line} / {route}: duplicate route order must be resolved before numbering.')
        main=routes.get('main',[])
        if not main:raise ValueError(f'{line}: a main route is required before branch numbering.')
        start=10 if line_index==0 else next_boundary(previous_max,1000)
        for index,node in enumerate(main):planned[node['id']]=start+index*10
        branch_base=next_boundary(planned[main[-1]['id']],100)
        by_id={n['id']:n for n in main}
        def branch_key(route):
            takeoffs={n.get('takeoff_id') for n in routes[route]}
            takeoff=by_id.get(next(iter(takeoffs))) if len(takeoffs)==1 else None
            valid=takeoff and takeoff['kind']=='tee'
            return (takeoff['order'] if valid else 100001,route)
        for branch in sorted((r for r in routes if r!='main'),key=branch_key):
            for index,node in enumerate(routes[branch]):planned[node['id']]=branch_base+index*10
            branch_base=next_boundary(planned[routes[branch][-1]['id']],100)
        previous_max=max(planned[n['id']] for n in group)
    mapping=[{'point_id':n['id'],'old':n.get('number'),'new':planned.get(n['id'])}
             for n in sorted(nodes,key=lambda n:n['id'])]
    for node in nodes:node['number']=planned.get(node['id'])
    return mapping


def topology(nodes, primary_line=None):
    """Edges follow explicit unique order; only a common main tee joins a branch."""
    from collections import Counter
    edges=[];eligible=assigned_nodes(nodes);ids=[n['id'] for n in nodes]
    # A duplicate identity cannot be interpreted as two different vertices.
    duplicates={uid for uid,count in Counter(ids).items() if count>1}
    eligible=[n for n in eligible if n['id'] not in duplicates]
    by_id={n['id']:n for n in eligible}
    groups={key:sorted((n for n in eligible if (n['line_id'],n['route'])==key),
                       key=lambda n:(n['order'],n['id']))
            for key in {(n['line_id'],n['route']) for n in eligible}}
    ambiguous={key for key,members in groups.items() if len({n['order'] for n in members})!=len(members)}
    for line,route in sorted(groups,key=lambda key:(key[0]!=primary_line,key[0],key[1]!='main',key[1])):
        ordered=groups[(line,route)]
        if (line,route) in ambiguous:continue
        if route!='main':
            takeoffs={n.get('takeoff_id') for n in ordered}
            tee=by_id.get(next(iter(takeoffs))) if len(takeoffs)==1 else None
            if (tee and tee['line_id']==line and tee['route']=='main' and tee['kind']=='tee'
                    and (line,'main') not in ambiguous):
                edges.append({'from':tee['id'],'to':ordered[0]['id'],'line_id':line,'route':route})
        edges.extend({'from':a['id'],'to':b['id'],'line_id':line,'route':route}
                     for a,b in zip(ordered,ordered[1:]))
    return {'points':[n['id'] for n in nodes],
        'unassigned_points':[n['id'] for n in nodes if not topology_assigned(n)],
        'edges':edges,'source':'engineer-entered route order; not inferred from drawing pixels'}


def compute_reasons(nodes):
    for node in nodes:
        reasons = []
        if not topology_assigned(node):
            reasons.append('TOPOLOGY_UNASSIGNED')
        if node.get("origin")=="automation" and node.get("verification")!="reviewed":
            reasons.append("SOURCE_PROPOSAL_REVIEW")
        if node.get('source_observation') and not source_location_reviewed(node):
            reasons.append('SOURCE_LOCATION_REVIEW_REQUIRED')
            if node['source_observation'].get('source_interface_uncertain'):
                reasons.append('SOURCE_INTERFACE_UNCERTAIN')
        elif node.get('origin') == 'source-review-profile' and not node.get('source_observation'):
            reasons.append('SOURCE_LOCATION_REVIEW_REQUIRED')
        if node.get("station_mm") is None or not node.get("evidence", "").strip():
            reasons.append("UNVERIFIED_DIMENSION")
        if node.get("kind") == "continuation" and len(node["instances"]) < 2:
            reasons.append("PROVISIONAL_CONTINUATION")
        reasons.extend(r for r in node.get('component_review_reasons',[]) if r not in reasons)
        reasons.extend(r for r in node.get('continuation_review_reasons',[]) if r not in reasons)
        reasons.extend(r for r in node.get('geometry_review_reasons',[]) if r not in reasons)
        reasons.extend(r for r in node.get('station_review_reasons',[]) if r not in reasons)
        reasons.extend(r for r in node.get('source_review_reasons',[]) if r not in reasons)
        reasons.extend(r for r in node.get('source_exception_reasons',[]) if r not in reasons)
        reasons.extend(r for r in node.get('topology_review_reasons',[]) if r not in reasons)
        node["reasons"] = reasons
        node["support_gap_mm"] = None
    eligible = assigned_nodes(nodes)
    routes = set((n["line_id"], n["route"]) for n in eligible)
    for line, route in routes:
        supports = sorted(
            [
                n
                for n in eligible
                if n["line_id"] == line
                and n["route"] == route
                and (n["kind"] == "support" or any(p['kind']=='support' for p in n.get('component_ports',[])))
            ],
            key=lambda n: (n["order"], n["id"]),
        )
        for first, second in zip(supports, supports[1:]):
            from packages.physical.stations import station_pair_comparable
            if station_pair_comparable(first, second):
                with localcontext() as context:
                    context.prec = 200
                    gap = abs(Decimal(second["station_mm"]) - Decimal(first["station_mm"]))
                second["support_gap_mm"] = str(gap)
                if gap <= Decimal("152.4"):
                    second["reasons"].append("SUPPORT_WITHIN_6_IN")
    return nodes


def validate(project):
    refresh_source_locations(project)
    from packages.engineering.continuations import apply_reasons
    continuation_issues=apply_reasons(project)
    compute_reasons(project["nodes"])
    project["graph"] = topology(project["nodes"])
    issues = list(project.get("automation",{}).get("issues",[]))
    issues.extend(continuation_issues)
    from packages.physical import audit as physical_audit
    from packages.physical.constraints import apply_geometry_reasons
    issues.extend(physical_audit(project)['issues'])
    issues.extend(apply_geometry_reasons(project))
    from packages.physical.stations import apply_station_reasons
    issues.extend(apply_station_reasons(project))
    from packages.physical.source_exceptions import refresh_source_exceptions
    issues.extend(refresh_source_exceptions(project))
    from packages.engineering.graph_review import apply_topology_reasons
    issues.extend(apply_topology_reasons(project))
    compute_reasons(project['nodes'])
    orders = {}
    for node in assigned_nodes(project["nodes"]):
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
    if not assigned_nodes(project["nodes"]):
        issues.append(
            {
                "code": "NO_REVIEWED_ROUTE",
                "severity": "critical",
                "message": "Add and review a main route before release.",
            }
        )
    for node in project["nodes"]:
        if topology_assigned(node) and node["route"] != "main" and not node.get("takeoff_id"):
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
