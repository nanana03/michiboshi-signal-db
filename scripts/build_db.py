"""OSM の信号機ノードを交差点単位にまとめて SQLite に入れる（試作）。
使い方: python3 build_db.py jp_signals.json pref_ids.json out.sqlite [閾値m]"""
import json, sys, math, collections, sqlite3, os
src, prefsrc, out = sys.argv[1:4]
TH = float(sys.argv[4]) if len(sys.argv) > 4 else 30.0
d = json.load(open(src))
meta = d['osm3s']
els = [e for e in d['elements'] if e['type'] == 'node']
pref_of = {}
if os.path.exists(prefsrc):
    for p, ids in json.load(open(prefsrc)).items():
        for i in ids: pref_of[i] = p

def dist(a, b):
    dlat = (a['lat'] - b['lat']) * 111320
    dlon = (a['lon'] - b['lon']) * 111320 * math.cos(math.radians(a['lat']))
    return math.hypot(dlat, dlon)

cell = TH / 111000.0
grid = collections.defaultdict(list)
for i, e in enumerate(els):
    grid[(int(e['lat'] / cell), int(e['lon'] / cell))].append(i)
parent = list(range(len(els)))
def f(x):
    while parent[x] != x:
        parent[x] = parent[parent[x]]; x = parent[x]
    return x
for (gy, gx), idx in grid.items():
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            for j in grid.get((gy + dy, gx + dx), []):
                for i in idx:
                    if i < j and dist(els[i], els[j]) < TH:
                        ra, rb = f(i), f(j)
                        if ra != rb: parent[ra] = rb
groups = collections.defaultdict(list)
for i in range(len(els)): groups[f(i)].append(els[i])

if os.path.exists(out): os.remove(out)
db = sqlite3.connect(out)
db.executescript("""
CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT);
-- 交差点（＝アプリが「1つの信号機」として数える単位）
CREATE TABLE signal(
  id INTEGER PRIMARY KEY,
  lat REAL NOT NULL, lon REAL NOT NULL,      -- 構成ノードの重心
  name TEXT, name_en TEXT, name_kana TEXT,   -- 交差点名（OSM の name。無いものが多い）
  pref TEXT,                                 -- 都道府県
  node_count INTEGER NOT NULL,               -- まとめた OSM ノード数
  radius_m REAL NOT NULL,                    -- 重心から最も遠いノードまで
  kind TEXT NOT NULL,                        -- 'intersection' / 'crossing'（押しボタン等の単独横断） / 'blinker'
  cell INTEGER NOT NULL,                     -- 約1km 格子の番号（近傍検索用）
  source TEXT NOT NULL DEFAULT 'osm'         -- 'osm' / 'npa_accident'（警察庁の事故データから足した交差点＝scripts/accident_signals.py）
);
CREATE INDEX signal_cell ON signal(cell);
CREATE VIRTUAL TABLE signal_rtree USING rtree(id, min_lat, max_lat, min_lon, max_lon);
-- 元の OSM ノード（帰属表示と差分更新のため残す）
CREATE TABLE osm_node(
  osm_id INTEGER PRIMARY KEY, signal_id INTEGER NOT NULL REFERENCES signal(id),
  lat REAL NOT NULL, lon REAL NOT NULL, direction TEXT, tags TEXT
);
CREATE INDEX osm_node_signal ON osm_node(signal_id);
""")
def cell_of(lat, lon):  # 0.01度（約1km）格子
    return int((lat + 90) * 100) * 100000 + int((lon + 180) * 100)

stats = collections.Counter()
for sid, (root, ns) in enumerate(sorted(groups.items(), key=lambda kv: (kv[1][0]['lat'], kv[1][0]['lon'])), start=1):
    lat = sum(n['lat'] for n in ns) / len(ns); lon = sum(n['lon'] for n in ns) / len(ns)
    c = {'lat': lat, 'lon': lon}
    r = max(dist(c, n) for n in ns)
    names = collections.Counter(n['tags']['name'] for n in ns if 'name' in n['tags'])
    def pick(k):
        v = collections.Counter(n['tags'][k] for n in ns if k in n['tags'])
        return v.most_common(1)[0][0] if v else None
    tsv = {n['tags'].get('traffic_signals') for n in ns}
    if tsv <= {'blinker'}: kind = 'blinker'
    elif len(ns) == 1 and (n0 := ns[0]['tags']).get('crossing') == 'traffic_signals' or tsv & {'crossing', 'pedestrian_crossing', 'on_demand', 'request_button'} and len(ns) <= 2:
        kind = 'crossing'
    else: kind = 'intersection'
    stats[kind] += 1
    prefs = collections.Counter(pref_of.get(n['id']) for n in ns)
    pref = prefs.most_common(1)[0][0]
    db.execute('INSERT INTO signal(id,lat,lon,name,name_en,name_kana,pref,node_count,radius_m,kind,cell) VALUES(?,?,?,?,?,?,?,?,?,?,?)',
               (sid, lat, lon, names.most_common(1)[0][0] if names else None, pick('name:en'), pick('name:ja-Hira'),
                pref, len(ns), round(r, 1), kind, cell_of(lat, lon)))
    db.execute('INSERT INTO signal_rtree VALUES(?,?,?,?,?)', (sid, min(n['lat'] for n in ns), max(n['lat'] for n in ns),
                                                            min(n['lon'] for n in ns), max(n['lon'] for n in ns)))
    for n in ns:
        db.execute('INSERT INTO osm_node VALUES(?,?,?,?,?,?)', (n['id'], sid, n['lat'], n['lon'],
                   n['tags'].get('traffic_signals:direction'), json.dumps(n['tags'], ensure_ascii=False)))
db.executemany('INSERT INTO meta VALUES(?,?)', [
    ('source', 'OpenStreetMap highway=traffic_signals'), ('license', 'ODbL 1.0 — © OpenStreetMap contributors'),
    ('osm_timestamp', meta['timestamp_osm_base']), ('cluster_threshold_m', str(TH)),
    ('node_count', str(len(els))), ('signal_count', str(len(groups)))])
db.commit(); db.execute('VACUUM'); db.close()
print('nodes', len(els), 'signals', len(groups), dict(stats), 'size', os.path.getsize(out))
