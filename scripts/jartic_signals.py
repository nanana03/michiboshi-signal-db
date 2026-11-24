"""JARTIC（公益財団法人 日本道路交通情報センター）の交通規制情報から信号機の位置を取り込む（2026-11-23）。
交通規制情報の共通規制種別コード 98（信号機の設置）が
位置つきで入っていて、44 都道府県で警察庁の基数とほぼ一致した。

使い方:
  python3 scripts/jartic_signals.py survey  data/raw/jartic data/npa_signal_stock_r7.tsv          # 束ねる距離ごとの数（取り込まない）
  python3 scripts/jartic_signals.py write   data/raw/jartic data/npa_signal_stock_r7.tsv build/signals.sqlite

入力＝data/raw/jartic/typeD_<県>.zip（scripts/fetch_jartic.sh が取る・git の外）。zip を解凍せずに読む。
利用規約（https://www.jartic.or.jp/d/opendata/riyou_kiyaku.pdf）：商用利用可・CC BY 4.0 と互換・出典と「加工して作成」を書く。

取り込み方（write）:
- JARTIC に信号機がある県（束ねた数が警察庁の基数の USE_MIN 以上）＝その県の信号機は JARTIC の点だけにする。
  OSM・事故データの点は消す（点滅＝blinker は JARTIC の点から NAME_M より遠いものだけ残す＝JARTIC に点滅が入っているかは分からないため）。
  交差点名・種類（intersection / crossing）は、NAME_M 以内の OSM の点から借りる。無ければ JARTIC の「交差点名称」。
- 信号機が入っていない県（神奈川・熊本・富山＝2026-09 分）は、いまの OSM＋事故データのまま。
"""
import collections, csv, glob, io, json, math, os, re, sqlite3, sys, zipfile

CODE = '98'            # 共通規制種別コード＝信号機の設置
USE_MIN = 0.8          # 警察庁の基数の 8 割以上あれば、その県は JARTIC を使う
NAME_M = 40            # 名前・種類を借りる OSM の点の距離
# 束ねる距離。ほとんどの県は 1 行＝ほぼ 1 基（行の数が警察庁の基数とほぼ同じ）＝30m。survey で県ごとに確かめた（2026-09 分）：
# 和歌山＝灯器ごとに載っていて行が 3.6 倍（30m で 132%・50m 104%・80m 97%）→ 60m／茨城＝行が 1 割多い（30m 107%・50m 103%）→ 50m
CLUSTER_M = 30
PREF_CLUSTER_M = {'和歌山県': 60, '茨城県': 50}
JARTIC_URL = 'https://www.jartic.or.jp/service/opendata/'

def dist(a, b):
    return math.hypot((a[0] - b[0]) * 111320, (a[1] - b[1]) * 111320 * math.cos(math.radians(a[0])))

def read_zip(path):
    """zip の中の CSV（cp932）→ (県名, [(lat, lon, 交差点名称)])。98 の点（点・線・面コード 1）だけ"""
    with zipfile.ZipFile(path) as z:
        name = next(n for n in z.namelist() if n.lower().endswith('.csv'))
        raw = z.read(name)
    try: text = raw.decode('cp932')
    except UnicodeDecodeError: text = raw.decode('utf-8-sig', errors='replace')
    rows = csv.reader(io.StringIO(text))
    h = next(rows)
    ci, pi, li, xi = (h.index(k) for k in ('共通規制種別コード', '点・線・面コード', '規制場所の経度緯度', '交差点名称(踏切名含む)'))
    pts = []
    for x in rows:
        if len(x) <= max(ci, pi, li, xi) or x[ci] != CODE or x[pi] != '1' or not x[li].strip(): continue
        try: lo, la = map(float, x[li].split(';')[0].split()[:2])
        except ValueError: continue
        if not (20 < la < 46 and 122 < lo < 154): continue   # 日本の外（入力の誤り）は捨てる
        pts.append((la, lo, x[xi].strip() or None))
    base = os.path.basename(name).split('_')[0]   # 例「山梨県警」「警視庁」「北海道警」
    pref = {'警視庁': '東京都', '北海道警': '北海道'}.get(base, re.sub(r'警$', '', base))
    return pref, pts

def cluster(pts, r):
    """近い点を束ねる（1 交差点に方向ごと・灯器ごとの行があるため）。最初の点を中心にし、名前は最初に見つかったもの"""
    G = max(r, 1) / 111320 * 1.5
    grid, out = {}, []
    for la, lo, nm in pts:
        k = (int(la / G), int(lo / G))
        hit = None
        for di in (-1, 0, 1):
            for dj in (-1, 0, 1):
                for c in grid.get((k[0] + di, k[1] + dj), ()):
                    if dist((la, lo), (c[0], c[1])) < r: hit = c; break
                if hit: break
            if hit: break
        if hit:
            hit[3] += 1
            if not hit[2] and nm: hit[2] = nm
            continue
        c = [la, lo, nm, 1]
        grid.setdefault(k, []).append(c); out.append(c)
    return out

def load_npa(path):
    return {r[0]: int(r[1]) for r in csv.reader(open(path, encoding='utf-8'), delimiter='\t') if len(r) > 1 and r[1].isdigit()}

def survey(src, npap):
    npa = load_npa(npap)
    print('県\t警察庁\t点\t20m\t30m\t50m\t80m')
    for z in sorted(glob.glob(os.path.join(src, 'typeD_*.zip'))):
        pref, pts = read_zip(z)
        n = npa.get(pref, 0)
        cs = [len(cluster(pts, r)) for r in (20, 30, 50, 80)]
        print(pref, n, len(pts), *[f'{c}({c / n:.0%})' if n else c for c in cs], sep='\t')

def write(src, npap, dbp):
    npa = load_npa(npap)
    con = sqlite3.connect(dbp)
    # OSM の点（名前・種類を借りる）を格子に
    G = 0.001
    osm = collections.defaultdict(list)
    for sid, la, lo, nm, ne, nk, kind in con.execute("select id, lat, lon, name, name_en, name_kana, kind from signal where source='osm'"):
        osm[(int(la / G), int(lo / G))].append((la, lo, nm, ne, nk, kind))
    def near_osm(p, want_blinker=False):
        best, bd = None, NAME_M
        for di in (-1, 0, 1):
            for dj in (-1, 0, 1):
                for o in osm.get((int(p[0] / G) + di, int(p[1] / G) + dj), ()):
                    if (o[5] == 'blinker') != want_blinker: continue
                    d = dist(p, o)
                    if d < bd: best, bd = o, d
        return best
    # 前回の分を消す（何度流しても同じ結果）
    old = [x[0] for x in con.execute("select id from signal where source='jartic'")]
    con.executemany('delete from signal_rtree where id=?', [(i,) for i in old])
    con.execute("delete from signal where source='jartic'")
    next_id = con.execute('select coalesce(max(id), 0) + 1 from signal').fetchone()[0]
    used, skipped, total, named = [], [], 0, 0
    for z in sorted(glob.glob(os.path.join(src, 'typeD_*.zip'))):
        pref, pts = read_zip(z)
        cs = cluster(pts, PREF_CLUSTER_M.get(pref, CLUSTER_M))
        n = npa.get(pref, 0)
        if not n or len(cs) < USE_MIN * n:
            skipped.append(f'{pref}（{len(cs)}／{n}）'); continue
        # この県の OSM・事故データの点を消す（点滅は JARTIC の点から遠いものだけ残す）
        jp = [(c[0], c[1]) for c in cs]
        jg = collections.defaultdict(list)
        for p in jp: jg[(int(p[0] / G), int(p[1] / G))].append(p)
        def near_j(p):
            return any(dist(p, q) < NAME_M for di in (-1, 0, 1) for dj in (-1, 0, 1) for q in jg.get((int(p[0] / G) + di, int(p[1] / G) + dj), ()))
        drop = [i for i, la, lo, kind in con.execute("select id, lat, lon, kind from signal where pref=? and source in ('osm','npa_accident')", (pref,))
                if kind != 'blinker' or near_j((la, lo))]
        con.executemany('delete from signal_rtree where id=?', [(i,) for i in drop])
        con.executemany('delete from signal where id=?', [(i,) for i in drop])
        for la, lo, nm, cnt in cs:
            o = near_osm((la, lo))
            name = (o[2] if o and o[2] else None) or nm
            if name: named += 1
            kind = o[5] if o else 'intersection'
            con.execute('INSERT INTO signal(id,lat,lon,name,name_en,name_kana,pref,node_count,radius_m,kind,cell,source) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',
                        (next_id, la, lo, name, o[3] if o else None, o[4] if o else None, pref, cnt, 0, kind,
                         int(la / 0.01) * 100000 + int(lo / 0.01), 'jartic'))
            con.execute('INSERT INTO signal_rtree VALUES(?,?,?,?,?)', (next_id, la, la, lo, lo))
            next_id += 1
        used.append(f'{pref} {len(cs)}（OSM・事故 {len(drop)} を置き換え）'); total += len(cs)
    meta = json.load(open(os.path.join(src, 'opendata.json'), encoding='utf-8')) if os.path.exists(os.path.join(src, 'opendata.json')) else []
    month = next((x.get('targetMonth') for x in meta if x.get('type') == 'typeD'), '?')
    con.executemany('INSERT OR REPLACE INTO meta VALUES(?,?)', [
        ('source_jartic', f'「交通規制情報」（公益財団法人日本道路交通情報センター）（{JARTIC_URL}）{month}分を加工して作成'),
        ('license_jartic', 'JARTIC オープンデータ利用規約（商用利用可・CC BY 4.0 互換）'),
        ('jartic_signal_count', str(total)), ('jartic_cluster_m', json.dumps({'default': CLUSTER_M, **PREF_CLUSTER_M}, ensure_ascii=False)), ('jartic_month', month)])
    con.commit()
    print(f'JARTIC の信号機 {total:,}（名前あり {named:,}＝{named / max(1, total):.0%}）')
    print('使った県', len(used)); [print('  ', u) for u in used]
    print('使わなかった県（束ねた数／警察庁）', '・'.join(skipped))

if __name__ == '__main__':
    mode = sys.argv[1]
    if mode == 'survey': survey(sys.argv[2], sys.argv[3])
    elif mode == 'write': write(sys.argv[2], sys.argv[3], sys.argv[4])
