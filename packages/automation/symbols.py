"""Bounded graphical proposals for a weld-neck flange drawing convention.

A thin plate, a separate filled pipe dot, and collinear heavy pipe linework
must agree. These are source-page locations, not physical dimensions, material
identities, route order, or engineering approval. Other conventions are unknown.
"""
import math
from uuid import NAMESPACE_URL, uuid5

PROFILE = 'iso-weld-neck-plate-v1'
MAX_SYMBOLS = 500
MAX_MATCH_WORK = 250000


def polygon(drawing):
    items = drawing['items']
    if not 3 <= len(items) <= 24 or any(i[0] != 'l' for i in items):
        return []
    if any(math.dist(a[2], b[1]) > .15 for a, b in zip(items, items[1:])):
        return []
    points = [list(i[1]) for i in items] + [list(items[-1][2])]
    if math.dist(points[0], points[-1]) < .15:
        points.pop()
    elif not drawing.get('closePath'):
        return []
    # CAD exporters often split one straight plate edge at its centre.
    changed = True
    while len(points) > 3 and changed:
        changed = False
        for i, b in enumerate(points):
            a, c = points[i-1], points[(i+1) % len(points)]
            ab = [b[j]-a[j] for j in (0, 1)]
            bc = [c[j]-b[j] for j in (0, 1)]
            norm = math.hypot(*ab) * math.hypot(*bc)
            if (norm and abs(ab[0]*bc[1]-ab[1]*bc[0])/norm < .03
                    and sum(ab[j]*bc[j] for j in (0, 1)) > 0):
                points.pop(i)
                changed = True
                break
    return points


def cross_fraction(a, b):
    norm = math.hypot(*a) * math.hypot(*b)
    return abs(a[0]*b[1]-a[1]*b[0])/norm if norm else 1


def flange_symbols(paths, source_sha, page_index):
    dots, plates, pipes = [], [], []
    limited = len(paths) > 50000
    for path_index, drawing in enumerate(paths[:50000]):
        width = drawing.get('width', 0) or 0
        if drawing['type'] == 's' and .7 <= width < 3:
            for item in drawing['items']:
                if item[0] == 'l' and math.dist(item[1], item[2]) >= 8 and len(pipes) < 1000:
                    pipes.append((item[1], item[2]))
        if not 3 <= len(drawing['items']) <= 24:
            continue
        points = polygon(drawing)
        if not points:
            continue
        rect = drawing['rect']
        centre = [(rect[0]+rect[2])/2, (rect[1]+rect[3])/2]
        if drawing['type'] in ('f', 'fs') and len(points) == 6:
            fill = drawing.get('fill')
            if not fill or max(fill) > .2:
                continue
            span = max(rect[2]-rect[0], rect[3]-rect[1])
            if not 3 <= span <= 60 or min(rect[2]-rect[0], rect[3]-rect[1]) < span*.3:
                continue
            # A compact, centrally symmetric convex marker; ignore half-paths,
            # glyphs and filled arrows instead of treating all fill as a dot.
            if any(math.dist(points[i], [2*centre[j]-points[i+3][j] for j in (0, 1)]) > span*.15 for i in range(3)):
                continue
            turns = []
            for i in range(6):
                a, b, c = points[i-1], points[i], points[(i+1) % 6]
                turns.append((b[0]-a[0])*(c[1]-b[1])-(b[1]-a[1])*(c[0]-b[0]))
            if not (all(t > 0 for t in turns) or all(t < 0 for t in turns)):
                continue
            if not any(math.dist(centre, d[1]) < .5 for d in dots):
                if len(dots) < 1000:dots.append((path_index, centre, list(rect)))
                else:limited = True
        elif drawing['type'] == 's' and width < .7 and len(points) == 4 and len(plates) < 2000:
            sides = [[points[(i+1) % 4][j]-points[i][j] for j in (0, 1)] for i in range(4)]
            lengths = [math.hypot(*v) for v in sides]
            if not (min(lengths) >= 1 and max(lengths) <= 80 and 3 < max(lengths)/min(lengths) < 12):
                continue
            if (max(abs(lengths[0]-lengths[2]), abs(lengths[1]-lengths[3])) > max(lengths)*.06
                    or cross_fraction(sides[0], sides[2]) > .12 or cross_fraction(sides[1], sides[3]) > .12):
                continue
            plates.append((path_index, points, sides, lengths, list(rect)))
    output = []; work = 0
    for path_index, points, sides, lengths, rect in plates:
        if not dots or not pipes:
            break
        centre = [sum(p[j] for p in points)/4 for j in (0, 1)]
        long = max(lengths)
        matches = []
        for dot_index, dot, dot_box in dots:
            work += 1
            if work > MAX_MATCH_WORK:return output, True
            vector = [centre[j]-dot[j] for j in (0, 1)]
            if not 2 <= math.hypot(*vector) <= long*1.5:
                continue
            if cross_fraction(vector, sides[lengths.index(min(lengths))]) > .12:
                continue
            # Flow-arrow symbols can interrupt a centreline. A bounded,
            # collinear gap supports a proposal but never proves connectivity.
            supported = False
            for a, b in pipes:
                work += 1
                if work > MAX_MATCH_WORK:return output, True
                if min(math.dist(dot, a), math.dist(dot, b)) > long*2.5:
                    continue
                other = max((a, b), key=lambda p: math.dist(dot, p))
                dv = [other[j]-dot[j] for j in (0, 1)]
                tangent = [b[j]-a[j] for j in (0, 1)]
                if (cross_fraction(dv, vector) < .12 and cross_fraction(tangent, vector) < .12
                        and sum(dv[j]*vector[j] for j in (0, 1)) < 0):
                    supported = True
                    break
            if supported:
                matches.append((dot_index, dot, dot_box))
        # Ambiguous neighbouring dots require review, never nearest-count fit.
        if len(matches) != 1:
            continue
        dot_index, dot, dot_box = matches[0]
        edge_centres = [[(points[k][j]+points[(k+1) % 4][j])/2 for j in (0, 1)]
                        for k in range(4) if lengths[k] > long*.8]
        face = max(edge_centres, key=lambda p: math.dist(dot, p))
        if any(math.dist(face, v['flange_face']) < .5 for v in output):
            continue
        box = [min(rect[0], dot_box[0]), min(rect[1], dot_box[1]),
               max(rect[2], dot_box[2]), max(rect[3], dot_box[3])]
        uid = str(uuid5(NAMESPACE_URL, f'{source_sha}:{page_index}:{PROFILE}:{face}:{dot}'))
        output.append({'id': uid, 'kind': 'flange', 'profile': PROFILE, 'bbox': box,
                       'flange_face': face, 'opposite_pipe_dot': dot, 'source_paths': [path_index, dot_index]})
        if len(output) >= MAX_SYMBOLS:
            return output, True
    return output, limited or len(plates) >= 2000 or len(pipes) >= 1000
