# 「自分の星図」の背景（全国の信号機＝薄い点と日本の外形）をアプリの同梱データにする（2026-11-23）。
#   python3 scripts/build_starmap_bg.py build/signals.sqlite app/assets/starmap_bg.dat
# 出力（作り直せる＝git の外）: {"n": 点の数, "b64": 経緯度を 0.001° に丸めた Int16 の組（lon-122, lat-20）, "outline": 日本の外形}
# 点滅（blinker）は除く（183,815 基）。外形は描画用の日本の輪郭 design/home_picker/japan.json（このリポジトリには入れていない・信号機の位置の作り方には関わらない）
import base64, json, os, sqlite3, struct, sys

HERE = os.path.dirname(os.path.abspath(__file__))
src, out = sys.argv[1], sys.argv[2]
db = sqlite3.connect(src)
rows = db.execute("select lat, lon from signal where kind != 'blinker' order by id").fetchall()
buf = bytearray()
for la, lo in rows:
    buf += struct.pack('<hh', round((lo - 122) * 1000), round((la - 20) * 1000))
outline = json.load(open(os.path.join(HERE, '..', 'design', 'home_picker', 'japan.json')))
with open(out, 'w') as f:
    json.dump({'n': len(rows), 'b64': base64.b64encode(bytes(buf)).decode(), 'outline': outline}, f, separators=(',', ':'))
print(out, len(rows), '基', os.path.getsize(out), 'バイト')
