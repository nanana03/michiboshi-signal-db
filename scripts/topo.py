"""TopoJSON を読む小さな道具（外部ライブラリなし）。
polygons(path) → [(properties, [ring, ...]), ...]（ring は [(lon, lat), ...]・外周と穴の区別はしない＝偶奇判定で使う）"""
import json

def _arcs(t):
    tr = t.get('transform')
    out = []
    for arc in t['arcs']:
        if tr:
            (sx, sy), (tx, ty) = tr['scale'], tr['translate']
            x = y = 0; pts = []
            for dx, dy in arc:
                x += dx; y += dy; pts.append((x * sx + tx, y * sy + ty))
        else:
            pts = [tuple(p) for p in arc]
        out.append(pts)
    return out

def _ring(idx, arcs):
    pts = []
    for i in idx:
        a = arcs[i] if i >= 0 else arcs[~i][::-1]
        pts.extend(a if not pts else a[1:])
    return pts

def polygons(path):
    t = json.load(open(path)); arcs = _arcs(t)
    res = []
    for obj in t['objects'].values():
        for g in obj['geometries']:
            polys = g['arcs'] if g['type'] == 'MultiPolygon' else [g['arcs']] if g['type'] == 'Polygon' else []
            rings = [_ring(r, arcs) for poly in polys for r in poly]
            res.append((g.get('properties', {}), rings))
    return res

def lines(path):
    """弧を「海岸線（1つの県だけが使う）」と「県境（2つの県が共有する）」に分けて返す → (coast, borders)"""
    t = json.load(open(path)); arcs = _arcs(t)
    used = {}
    for obj in t['objects'].values():
        for gi, g in enumerate(obj['geometries']):
            polys = g['arcs'] if g['type'] == 'MultiPolygon' else [g['arcs']] if g['type'] == 'Polygon' else []
            for poly in polys:
                for ring in poly:
                    for i in ring:
                        used.setdefault(i if i >= 0 else ~i, set()).add(gi)
    coast, borders = [], []
    for i, a in enumerate(arcs):
        (borders if len(used.get(i, ())) > 1 else coast).append(a)
    return coast, borders
