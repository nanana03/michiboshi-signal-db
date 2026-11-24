"""信号機に標高を付ける（国土地理院の標高タイル・2026-11-23）。
標高をアプリの中で取ると時間がかかるため、DB に入れておく（ズーム 12）。
取り込んだ記録（GPS の高度が無い）の 3D の高さを、アプリが国土地理院の標高 API に 1 地点 0.5 秒ずつ問い合わせていた（542 地点で約 6 分）。
DB に最初から標高を入れておけば、アプリは読むだけ（待ちなし・電波なし）。

使い方: python3 scripts/signal_elev_tiles.py build/signals.sqlite [data/raw/gsi_dem]
- タイル＝標高タイル DEM10B（PNG）https://cyberjapandata.gsi.go.jp/xyz/dem_png/{z}/{x}/{y}.png・ズーム 12（1 画素≈31m）。
  信号機のあるタイルだけ取る（2026-11-23 に数えた＝4,383 枚・平均 72KB）。取ったタイルは data/raw/gsi_dem/12/（git の外）に残し、次は取らない。
- 正しさ：富士見高原の 60 地点で標高 API と比べて、差の中央 1.1m・9 割が 2.6m 以内（ズーム 14 でも 1.1m・2.5m＝ほぼ同じ）。
- 利用条件：地理院タイル一覧で「基本測量成果以外で出典の記載のみで利用可能なもの」＝申請不要・出典「国土地理院」（https://maps.gsi.go.jp/development/ichiran.html）。
  取るときは 1 枚ずつ WAIT 秒あける（サーバに過度の負担をかけない）。
- PNG は標準ライブラリだけで読む（zlib だけ・numpy も PIL も要らない）。標高＝(R·2^16+G·2^8+B)×0.01m・(128,0,0)＝無効値。
"""
import math, os, sqlite3, struct, sys, time, urllib.request, zlib

Z = 12
WAIT = 0.2
URL = 'https://cyberjapandata.gsi.go.jp/xyz/dem_png/{z}/{x}/{y}.png'

def tile_px(lat, lon, z=Z):
    n = 2 ** z; fx = (lon + 180) / 360 * n * 256; r = math.radians(lat)
    fy = (1 - math.log(math.tan(r) + 1 / math.cos(r)) / math.pi) / 2 * n * 256
    return int(fx // 256), int(fy // 256), int(fx % 256), int(fy % 256)

def png_rows(data):
    """PNG（8bit・RGB または RGBA・インターレースなし）→ (幅, 1 画素のバイト数, 行の bytes の list)"""
    assert data[:8] == b'\x89PNG\r\n\x1a\n', 'PNG ではない'
    i, idat, w = 8, [], None
    while i < len(data):
        ln, typ = struct.unpack('>I4s', data[i:i + 8]); body = data[i + 8:i + 8 + ln]; i += 12 + ln
        if typ == b'IHDR':
            w, h, depth, ctype, _, _, inter = struct.unpack('>IIBBBBB', body)
            assert depth == 8 and ctype in (2, 6) and inter == 0, f'想定外の PNG（深さ {depth}・色 {ctype}・インターレース {inter}）'
            bpp = 3 if ctype == 2 else 4
        elif typ == b'IDAT': idat.append(body)
        elif typ == b'IEND': break
    raw = zlib.decompress(b''.join(idat)); stride = w * bpp; rows, prev = [], bytearray(stride)
    for y in range(h):
        f = raw[y * (stride + 1)]; cur = bytearray(raw[y * (stride + 1) + 1:(y + 1) * (stride + 1)])
        if f == 1:
            for k in range(bpp, stride): cur[k] = (cur[k] + cur[k - bpp]) & 255
        elif f == 2:
            for k in range(stride): cur[k] = (cur[k] + prev[k]) & 255
        elif f == 3:
            for k in range(stride): cur[k] = (cur[k] + ((cur[k - bpp] if k >= bpp else 0) + prev[k]) // 2) & 255
        elif f == 4:
            for k in range(stride):
                a = cur[k - bpp] if k >= bpp else 0; b = prev[k]; c = prev[k - bpp] if k >= bpp else 0
                p = a + b - c; pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                cur[k] = (cur[k] + (a if pa <= pb and pa <= pc else b if pb <= pc else c)) & 255
        rows.append(cur); prev = cur
    return w, bpp, rows

def elev_at(rows, bpp, ix, iy):
    o = ix * bpp; R, G, B = rows[iy][o], rows[iy][o + 1], rows[iy][o + 2]
    x = R * 65536 + G * 256 + B
    if x == 2 ** 23: return None   # 無効値（海など）
    return round((x if x < 2 ** 23 else x - 2 ** 24) * 0.01, 1)

def get_tile(cache, z, x, y):
    p = os.path.join(cache, str(z), f'{x}_{y}.png')
    if os.path.exists(p): return open(p, 'rb').read(), False
    os.makedirs(os.path.dirname(p), exist_ok=True)
    req = urllib.request.Request(URL.format(z=z, x=x, y=y), headers={'User-Agent': 'Mozilla/5.0'})
    try: data = urllib.request.urlopen(req, timeout=60).read()
    except urllib.error.HTTPError as e:
        if e.code == 404: data = b''   # タイルが無い（海の上など）＝空のファイルを置いて次は取らない
        else: raise
    open(p, 'wb').write(data); time.sleep(WAIT)
    return data, True

def main():
    dbp = sys.argv[1]; cache = sys.argv[2] if len(sys.argv) > 2 else 'data/raw/gsi_dem'
    con = sqlite3.connect(dbp)
    if 'elev' not in [r[1] for r in con.execute('pragma table_info(signal)')]:
        con.execute('ALTER TABLE signal ADD COLUMN elev REAL')   # 標高（m・国土地理院の標高タイル）
    by_tile = {}
    for sid, la, lo in con.execute('select id, lat, lon from signal'):
        x, y, ix, iy = tile_px(la, lo); by_tile.setdefault((x, y), []).append((sid, ix, iy))
    t0 = time.time(); fetched = done = none = 0; upd = []
    for n, ((x, y), sigs) in enumerate(sorted(by_tile.items()), 1):
        data, new = get_tile(cache, Z, x, y); fetched += new
        if data:
            _, bpp, rows = png_rows(data)
            for sid, ix, iy in sigs:
                v = elev_at(rows, bpp, ix, iy)
                upd.append((v, sid)); done += v is not None; none += v is None
        else:
            upd += [(None, sid) for sid, _, _ in sigs]; none += len(sigs)
        if n % 200 == 0:
            el = time.time() - t0
            print(f'{n:,}/{len(by_tile):,} 枚（取った {fetched:,}）・{el / 60:.1f} 分・残り約 {el / n * (len(by_tile) - n) / 60:.0f} 分', flush=True)
    con.executemany('update signal set elev=? where id=?', upd)
    con.executemany('INSERT OR REPLACE INTO meta VALUES(?,?)', [
        ('source_elev', f'国土地理院 標高タイル（DEM10B・ズーム {Z}）（https://maps.gsi.go.jp/development/ichiran.html）'),
        ('elev_zoom', str(Z)), ('elev_count', str(done))])
    con.commit()
    print(f'標高を付けた {done:,}・付かなかった {none:,}（海の上・タイル無し）・タイル {len(by_tile):,} 枚（新しく取った {fetched:,}）・{(time.time() - t0) / 60:.1f} 分')

if __name__ == '__main__':
    main()
