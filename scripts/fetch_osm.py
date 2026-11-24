"""OSM（Overpass API）から日本の信号機ノードを全部取ってくる。
使い方: python3 scripts/fetch_osm.py data/raw/jp_signals.json
約 38MB・数十秒〜数分。Overpass が混んでいると 406/429/504 が返る＝時間をおいてやり直す。"""
import sys, urllib.request, urllib.parse, os
out = sys.argv[1]
os.makedirs(os.path.dirname(out) or '.', exist_ok=True)
q = ('[out:json][timeout:280];area["ISO3166-1"="JP"][admin_level=2]->.jp;'
     'node["highway"="traffic_signals"](area.jp);out body;')
req = urllib.request.Request('https://overpass-api.de/api/interpreter',
                             data=urllib.parse.urlencode({'data': q}).encode(),
                             headers={'User-Agent': 'signaldrive-builder/0.1'})  # UA が無いと 406
with urllib.request.urlopen(req, timeout=300) as r, open(out, 'wb') as f:
    f.write(r.read())
print(out, os.path.getsize(out))
