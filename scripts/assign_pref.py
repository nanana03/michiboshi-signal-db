"""都道府県の境界（TopoJSON）で各 OSM ノードの都道府県を決める。
境界の外（埋立地の新しい部分・境界の粗さ）に落ちたノードは、最も近い県のノードに寄せず未割り当て（pref=NULL）のまま。
使い方: python3 scripts/assign_pref.py data/boundaries/pref_detail.topojson data/raw/jp_signals.json data/raw/pref_ids.json"""
import json, sys, collections, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import topo

pref_rings = topo.polygons(sys.argv[1])
nodes = [e for e in json.load(open(sys.argv[2]))['elements'] if e['type'] == 'node']
polys = []  # (pref, bbox, ring)
for props, rings in pref_rings:
    for ring in rings:
        xs = [c[0] for c in ring]; ys = [c[1] for c in ring]
        polys.append((props['pref'], (min(xs), min(ys), max(xs), max(ys)), ring))

def inside(x, y, ring):
    c = False; j = len(ring) - 1
    for i in range(len(ring)):
        xi, yi = ring[i]; xj, yj = ring[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi: c = not c
        j = i
    return c

grid = collections.defaultdict(list)  # 0.5度の格子
for k, (p, b, r) in enumerate(polys):
    for gx in range(int(b[0] * 2), int(b[2] * 2) + 1):
        for gy in range(int(b[1] * 2), int(b[3] * 2) + 1): grid[(gx, gy)].append(k)

res = collections.defaultdict(list); miss = 0
for n in nodes:
    x, y = n['lon'], n['lat']
    # 県ごとに偶奇判定（穴＝湖などの内側の輪も同じ県の輪として数える）
    cnt = collections.Counter()
    for k in grid.get((int(x * 2), int(y * 2)), []):
        p, b, r = polys[k]
        if b[0] <= x <= b[2] and b[1] <= y <= b[3] and inside(x, y, r): cnt[p] += 1
    hit = [p for p, c in cnt.items() if c % 2 == 1]
    if hit: res[hit[0]].append(n['id'])
    else: miss += 1
json.dump(res, open(sys.argv[3], 'w'), ensure_ascii=False)
print('nodes', len(nodes), 'assigned', sum(len(v) for v in res.values()), 'miss', miss)
