"""アプリに同梱する信号機 DB を作る（build/signals.sqlite から必要な列だけ）。
使い方: python3 scripts/build_app_db.py build/signals.sqlite app/assets/signals.db

- expo-sqlite（SDK 54）の SQLite は R*Tree を組み込んでいない（ExpoSQLite.podspec の cflags に SQLITE_ENABLE_RTREE が無い）
  ＝signal_rtree は使えない。代わりに (lat, lon) の索引で「緯度の帯 × 経度の範囲」を引く。
- 出典（OSM・警察庁）は meta 表に残す＝アプリの「データについて」に出す。"""
import sqlite3, sys, os
src, out = sys.argv[1:3]
if os.path.exists(out): os.remove(out)
s = sqlite3.connect(src); d = sqlite3.connect(out)
d.executescript("""
CREATE TABLE signal(
  id INTEGER PRIMARY KEY, lat REAL NOT NULL, lon REAL NOT NULL,
  name TEXT, kind TEXT NOT NULL, source TEXT NOT NULL,     -- source: osm / npa_accident / jartic
  elev REAL                                                -- 標高 m（国土地理院の標高タイル・scripts/signal_elev_tiles.py）。無ければ NULL
);
CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT);
""")
has_elev = 'elev' in [r[1] for r in s.execute('pragma table_info(signal)')]
rows = s.execute(f"select id, round(lat, 6), round(lon, 6), name, kind, source, {'elev' if has_elev else 'NULL'} from signal order by lat").fetchall()
d.executemany('INSERT INTO signal VALUES(?,?,?,?,?,?,?)', rows)
d.execute('CREATE INDEX signal_lat_lon ON signal(lat, lon)')
d.executemany('INSERT INTO meta VALUES(?,?)', s.execute('select key, value from meta').fetchall())
d.commit(); d.execute('VACUUM'); d.close()
print(f'{len(rows):,} 交差点 → {out} {os.path.getsize(out):,} バイト')
# 端末の中の DB の名前に中身の目印を付ける（2026-11-23）。expo-sqlite は同じ名前の DB が端末にあると同梱の新しい DB で上書きしない
# （assetSource.forceOverwrite の既定は false）＝JARTIC に作り直した DB が、入れ直したシミュレータでも 11-22 の古いまま使われていた。
# アプリは app/src/signalsDb.json の name で開き、古い名前の DB は起動時に消す（App.js）
import hashlib, json
sha = hashlib.sha1(open(out, 'rb').read()).hexdigest()
meta = dict(s.execute("select key, value from meta where key in ('jartic_month', 'osm_timestamp')").fetchall())
ver = os.path.join(os.path.dirname(os.path.abspath(out)), '..', 'src', 'signalsDb.json')
json.dump({'name': f'signals-{sha[:12]}.db', 'sha1': sha, 'count': len(rows), 'jartic_month': meta.get('jartic_month'), 'osm_timestamp': meta.get('osm_timestamp')},
          open(ver, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
print('端末での名前', f'signals-{sha[:12]}.db', '→', os.path.normpath(ver))
