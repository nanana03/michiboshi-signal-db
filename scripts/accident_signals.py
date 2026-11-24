# 警察庁「交通事故統計情報のオープンデータ」（本票）から、信号機が作動していた場所で起きた事故の地点を拾い、
# OSM の信号機 DB に無い信号交差点の候補を都道府県ごとに数える。--write-db を付けると候補を DB に足す。
#
# 使い方: python3 scripts/accident_signals.py build/signals.sqlite data/raw/npa/honhyo_20*.csv [--out cand.csv] [--write-db]
#
# 根拠（コード表 2025・「信号機」）: 事故が信号機の効力が及ぶ範囲（交差点の側端から 30m 以内／単路は横断歩道の側端から 30m 以内）
#   で起きたとき、当事者の対面する信号機の作動状況を記録する。1 点灯-3灯式 / 8 点灯-歩車分式 / 2 点灯-押ボタン式 /
#   3 点滅-3灯式 / 4 点滅-1灯式 / 5 消灯 / 6 故障 / 7 施設なし。→ 7 以外＝その近くに信号機がある。
# 緯度経度は世界測地系の度分秒を桁で詰めた数（430607590＝43°06'07.590"）。
# 利用条件: 警察庁ウェブサイト利用規約＝PDL1.0。出典「警察庁ウェブサイト（URL）」＋加工した旨を書く。
import csv, math, re, sqlite3, sys, collections

NPA_PREF = {**{c: '北海道' for c in (10, 11, 12, 13, 14)},
            20: '青森県', 21: '岩手県', 22: '宮城県', 23: '秋田県', 24: '山形県', 25: '福島県', 30: '東京都',
            40: '茨城県', 41: '栃木県', 42: '群馬県', 43: '埼玉県', 44: '千葉県', 45: '神奈川県', 46: '新潟県',
            47: '山梨県', 48: '長野県', 49: '静岡県', 50: '富山県', 51: '石川県', 52: '福井県', 53: '岐阜県',
            54: '愛知県', 55: '三重県', 60: '滋賀県', 61: '京都府', 62: '大阪府', 63: '兵庫県', 64: '奈良県',
            65: '和歌山県', 70: '鳥取県', 71: '島根県', 72: '岡山県', 73: '広島県', 74: '山口県', 80: '徳島県',
            81: '香川県', 82: '愛媛県', 83: '高知県', 90: '福岡県', 91: '佐賀県', 92: '長崎県', 93: '熊本県',
            94: '大分県', 95: '宮崎県', 96: '鹿児島県', 97: '沖縄県'}
SIGNAL_CODES = {'1', '2', '3', '4', '5', '6', '8'}
CODE_KIND = {'1': 'intersection', '8': 'intersection', '2': 'crossing', '3': 'blinker', '4': 'blinker'}  # 5 消灯・6 故障は種類を決めない
CLUSTER_M = 40   # 同じ交差点の事故をまとめる距離
MATCH_M = 60     # OSM の信号機がこの距離に在れば「OSM に在る」（効力の範囲 30m＋交差点の大きさ）
FAR_M = 150      # 最寄りの信号機からこれ以上離れた候補だけを「新しい交差点」と数える・DB に足す。
                 # 2019-2025 の実測：OSM がほぼ揃っている神奈川（95%）でも 60〜150m の候補は 533 か所出る
                 # ＝同じ交差点の別の流入路・位置のずれ。150m 以上に絞ると神奈川 100%・東京 97% で頭打ちになる。
DEDUP_M = 60     # 候補どうしはこれより近ければ1つにする（事故の多い方を残す）。150m で間引くと本物まで消える：
                 # 神奈川で OSM を伏せて事故データだけで作り OSM と 1 対 1（80m 以内）で突き合わせた実測（2019-2025）＝
                 #   間引き 60m：精度 87%・正解の 75% を拾う／150m：精度 90%・59%（東京は 79%・71% ／ 86%・52%）
                 # ＝重複は誤りの主因ではない。
CELL = 0.001     # 格子（緯度で約 111m）
NPA_URL = 'https://www.npa.go.jp/publications/statistics/koutsuu/opendata/index_opendata.html'

def dms(v, deg_digits):
    s = v.strip()
    if not s.isdigit(): return None
    d = int(s[:deg_digits]); m = int(s[deg_digits:deg_digits + 2]); sec = int(s[deg_digits + 2:]) / 1000
    return d + m / 60 + sec / 3600

def dist(a, b):
    return math.hypot((a[0] - b[0]) * 111320, (a[1] - b[1]) * 111320 * math.cos(math.radians(a[0])))

def grid(points, cell=CELL):
    g = collections.defaultdict(list)
    for i, p in enumerate(points): g[(int(p[0] / cell), int(p[1] / cell))].append(i)
    return g

def near(g, points, p, r):
    ci, cj = int(p[0] / CELL), int(p[1] / CELL)
    for di in (-1, 0, 1):
        for dj in (-1, 0, 1):
            for i in g.get((ci + di, cj + dj), ()):
                if dist(p, points[i]) <= r: yield i

def cell_of(lat, lon):  # build_db.py と同じ 0.01度（約1km）格子
    return int((lat + 90) * 100) * 100000 + int((lon + 180) * 100)

def main():
    args = list(sys.argv[1:])
    out = None; write_db = '--write-db' in args
    if write_db: args.remove('--write-db')
    if '--out' in args: k = args.index('--out'); out = args[k + 1]; del args[k:k + 2]
    db, files = args[0], args[1:]
    con = sqlite3.connect(db)
    cols = [r[1] for r in con.execute('pragma table_info(signal)')]
    where = " where source='osm'" if 'source' in cols else ''
    osm = con.execute('select lat, lon, pref from signal' + where).fetchall()
    osm_pts = [(a, b) for a, b, _ in osm]; og = grid(osm_pts)
    osm_by_pref = collections.Counter(p for _, _, p in osm)

    acc = []   # (lat, lon, pref, code, year)
    n_rows = n_sig = n_bad = 0
    for fn in files:
        f = open(fn, encoding='cp932', errors='replace', newline=''); r = csv.reader(f); h = next(r)
        i_s, i_p, i_y = h.index('信号機'), h.index('都道府県コード'), h.index('発生日時　　年')
        i_la = h.index('地点　緯度（北緯）'); i_lo = h.index('地点　経度（東経）')
        for row in r:
            n_rows += 1
            if row[i_s] not in SIGNAL_CODES: continue
            n_sig += 1
            la, lo = dms(row[i_la], 2), dms(row[i_lo], 3)
            if la is None or lo is None or not (20 < la < 46 and 122 < lo < 154): n_bad += 1; continue
            acc.append((la, lo, NPA_PREF.get(int(row[i_p]), '?'), row[i_s], int(row[i_y])))
    pts = [(a[0], a[1]) for a in acc]; ag = grid(pts)

    # 事故地点を交差点ごとにまとめる（union-find）
    parent = list(range(len(pts)))
    def find(x):
        while parent[x] != x: parent[x] = parent[parent[x]]; x = parent[x]
        return x
    for i, p in enumerate(pts):
        for j in near(ag, pts, p, CLUSTER_M):
            if j > i:
                a, b = find(i), find(j)
                if a != b: parent[a] = b
    groups = collections.defaultdict(list)
    for i in range(len(pts)): groups[find(i)].append(i)

    coarse = collections.defaultdict(list)   # 最寄りの距離を測るための粗い格子（約 1.1km）
    for p in osm_pts: coarse[(int(p[0] / 0.01), int(p[1] / 0.01))].append(p)
    def nearest(p):
        ci, cj = int(p[0] / 0.01), int(p[1] / 0.01)
        return min((dist(p, q) for di in (-1, 0, 1) for dj in (-1, 0, 1) for q in coarse.get((ci + di, cj + dj), ())),
                   default=float('inf'))

    stat = collections.defaultdict(lambda: [0, 0, 0, 0])   # pref -> [交差点, OSM に在る, 事故件数, 遠い候補]
    cands = []   # (pref, lat, lon, 事故件数, 最寄りの OSM まで, members)
    for members in groups.values():
        la = sum(pts[i][0] for i in members) / len(members); lo = sum(pts[i][1] for i in members) / len(members)
        pref = collections.Counter(acc[i][2] for i in members).most_common(1)[0][0]
        hit = any(True for _ in near(og, osm_pts, (la, lo), MATCH_M))
        s = stat[pref]; s[0] += 1; s[1] += hit; s[2] += len(members)
        if not hit:
            d = nearest((la, lo)); s[3] += d >= FAR_M
            cands.append((pref, la, lo, len(members), d, members))

    npa = {}
    try:
        for line in open(db.replace('build/signals.sqlite', 'data/npa_signal_stock_r7.tsv'), encoding='utf-8'):
            c = line.rstrip('\n').split('\t')
            if len(c) >= 2 and c[1].isdigit(): npa[c[0]] = int(c[1])
    except OSError: pass

    print(f'行 {n_rows:,} / 信号機あり {n_sig:,} / 緯度経度が読めない {n_bad:,} / 交差点にまとめて {len(groups):,}')
    print(f'都道府県\t事故の信号交差点\tOSMに在る\t在る率\tOSMに無い\tうち{FAR_M}m以上\tOSM(束ね)\t警察庁の基数\tOSM率\t遠い候補を足すと')
    rows = []
    for p, (n, h, _, far) in stat.items():
        o = osm_by_pref.get(p, 0); base = npa.get(p, 0)
        rows.append((p, n, h, h / n if n else 0, n - h, far, o, base, o / base if base else 0, (o + far) / base if base else 0))
    for p, n, h, rate, miss, far, o, base, orate, after in sorted(rows, key=lambda x: x[3]):
        print(f'{p}\t{n:,}\t{h:,}\t{rate:.0%}\t{miss:,}\t{far:,}\t{o:,}\t{base:,}\t{orate:.0%}\t{after:.0%}')
    tn = sum(r[1] for r in rows); th = sum(r[2] for r in rows); tf = sum(r[5] for r in rows)
    to = sum(osm_by_pref.values()); tb = sum(npa.values())
    print(f'全国\t{tn:,}\t{th:,}\t{th / tn:.0%}\t{tn - th:,}\t{tf:,}\t{to:,}\t{tb:,}\t{to / tb:.0%}\t{(to + tf) / tb:.0%}')
    if out:
        with open(out, 'w', encoding='utf-8', newline='') as w:
            cw = csv.writer(w); cw.writerow(['pref', 'lat', 'lon', 'accidents', 'nearest_osm_m'])
            cw.writerows(sorted((p, round(la, 6), round(lo, 6), n, round(min(d, 99999))) for p, la, lo, n, d, _ in cands))
    if write_db:   # 年版はファイル名から（本票には届け出の遅れで前の年に起きた事故も入っている）
        eds = sorted(m.group(1) for fn in files if (m := re.search(r'honhyo_(\d{4})', fn)))
        write(con, cands, acc, f'{eds[0]}-{eds[-1]}' if eds else '?')

def write(con, cands, acc, editions):
    """150m 以上離れた候補を signal 表に足す（source='npa_accident'）。何度流しても同じ結果になるよう、前回の分は消してから足す。"""
    con.executescript("""
    CREATE TABLE IF NOT EXISTS accident_site(            -- 事故データから足した交差点の根拠
      signal_id INTEGER PRIMARY KEY REFERENCES signal(id),
      accidents INTEGER NOT NULL,                        -- 束ねた事故の件数（信号機が作動していた事故のみ）
      first_year INTEGER NOT NULL, last_year INTEGER NOT NULL,
      codes TEXT NOT NULL                                -- 「信号機」コードの内訳（例 1:5,2:1）
    );""")
    old = [r[0] for r in con.execute("select id from signal where source='npa_accident'")]
    con.executemany('delete from signal_rtree where id=?', [(i,) for i in old])
    con.execute("delete from signal where source='npa_accident'"); con.execute('delete from accident_site')

    G = 0.001   # 約 110m 格子＝60m を 3×3 で見られる（OSM からの 150m は d＝最寄りの距離で先に判定済み）
    kg = collections.defaultdict(list)
    def clear(p):
        ci, cj = int(p[0] / G), int(p[1] / G)
        return all(dist(p, q) >= DEDUP_M for di in (-1, 0, 1) for dj in (-1, 0, 1) for q in kg.get((ci + di, cj + dj), ()))
    next_id = con.execute('select coalesce(max(id), 0) + 1 from signal').fetchone()[0]
    added = collections.Counter(); kinds = collections.Counter()
    for pref, la, lo, n, d, members in sorted(cands, key=lambda c: (-c[3], c[1], c[2])):   # 事故の多い候補から
        if d < FAR_M or not clear((la, lo)): continue
        codes = collections.Counter(acc[i][3] for i in members)
        kc = collections.Counter(CODE_KIND[c] for c in codes.elements() if c in CODE_KIND)
        lit = collections.Counter({k: v for k, v in kc.items() if k != 'blinker'})   # 点灯の記録が1件でもあれば点滅にしない
        kind = (lit or kc).most_common(1)[0][0] if kc else 'intersection'
        years = [acc[i][4] for i in members]
        r = max(dist((la, lo), (acc[i][0], acc[i][1])) for i in members)
        con.execute('INSERT INTO signal(id,lat,lon,name,name_en,name_kana,pref,node_count,radius_m,kind,cell,source) '
                    'VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',
                    (next_id, la, lo, None, None, None, pref, 0, round(r, 1), kind, cell_of(la, lo), 'npa_accident'))
        con.execute('INSERT INTO signal_rtree VALUES(?,?,?,?,?)',
                    (next_id, min(acc[i][0] for i in members), max(acc[i][0] for i in members),
                     min(acc[i][1] for i in members), max(acc[i][1] for i in members)))
        con.execute('INSERT INTO accident_site VALUES(?,?,?,?,?)',
                    (next_id, n, min(years), max(years), ','.join(f'{c}:{k}' for c, k in sorted(codes.items()))))
        kg[(int(la / G), int(lo / G))].append((la, lo))
        next_id += 1; added[pref] += 1; kinds[kind] += 1
    con.executemany('INSERT OR REPLACE INTO meta VALUES(?,?)', [
        ('source_npa', f'警察庁「交通事故統計情報のオープンデータ」本票 {editions} 年版（{NPA_URL}）を加工して作成'),
        ('license_npa', '公共データ利用規約（第1.0版）PDL1.0 — 出典：警察庁ウェブサイト'),
        ('npa_far_m', str(FAR_M)), ('npa_signal_count', str(sum(added.values())))])
    con.commit()
    print(f'DB に足した：{sum(added.values()):,} 交差点 {dict(kinds)}（前回の分 {len(old):,} は消してから）')

if __name__ == '__main__':
    main()
