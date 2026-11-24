"""アプリの 3D の地面に描く外形・県境と、都道府県の範囲を1つのファイルにする。
使い方: python3 scripts/build_app_base.py app/assets/base.dat
- detail（20m 簡略化・全国）はアプリが走った範囲だけ切り出して使う（src/viewer.js）。overview（300m）は日本全体の表示用。
- 拡張子を .json にしないのは、Metro が JS に埋め込んでしまうため（.dat は資産として同梱される＝metro.config.js）。"""
import sys, os, json
here = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, here); import topo
root = os.path.join(here, '..')
def rnd(lines, nd): return [[[round(x, nd), round(y, nd)] for x, y in l] for l in lines]
dc, db = topo.lines(os.path.join(root, 'data/boundaries/pref_detail.topojson'))
oc, ob = topo.lines(os.path.join(root, 'data/boundaries/pref_overview.topojson'))
prefs = []
for props, rings in topo.polygons(os.path.join(root, 'data/boundaries/pref_detail.topojson')):
    xs = [x for r in rings for x, _ in r]; ys = [y for r in rings for _, y in r]
    prefs.append({'name': props['pref'], 'box': [round(min(ys), 4), round(max(ys), 4), round(min(xs), 4), round(max(xs), 4)]})
# 陸の面（3D の描写で陸を薄く塗るため）：県ごとの多角形（島ごとに [外周, 穴…]）。
# 座標は 1e-4 度の整数の差分で詰める（そのままだと 9MB・差分で 2.6MB）。アプリは走った範囲にかかる県だけ戻して使う（src/viewer.js の makeBase）
def enc(r):
    out, px, py = [], 0, 0
    for x, y in r:
        ix, iy = round(x * 1e4), round(y * 1e4); out += [ix - px, iy - py]; px, py = ix, iy
    return out
t = json.load(open(os.path.join(root, 'data/boundaries/pref_detail.topojson'))); arcs = topo._arcs(t); land = []
for obj in t['objects'].values():
    for g in obj['geometries']:
        for poly in (g['arcs'] if g['type'] == 'MultiPolygon' else [g['arcs']] if g['type'] == 'Polygon' else []):
            land.append([g['properties']['pref'], [enc(topo._ring(r, arcs)) for r in poly]])
out = {'detail': {'coast': rnd(dc, 4), 'borders': rnd(db, 4)}, 'overview': {'coast': rnd(oc, 3), 'borders': rnd(ob, 3)}, 'prefs': prefs, 'land': land}
s = json.dumps(out, separators=(',', ':'), ensure_ascii=False)
open(sys.argv[1], 'w', encoding='utf-8').write(s)
print(f'{sys.argv[1]} {len(s.encode()):,} バイト・都道府県 {len(prefs)}')
