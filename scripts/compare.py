"""都道府県ごと：交差点の数 ÷ 警察庁の信号機数（令和7年度末・基）。OSM と、警察庁の事故データから足した分（npa_accident）と、JARTIC の交通規制情報（jartic・2026-11-23〜）を分けて出す。
使い方: python3 scripts/compare.py build/signals.sqlite data/npa_signal_stock_r7.tsv
⚠️ 「基」と交差点は 1 対 1 ではない＝比率は目安（100% を超える県もある）。点滅（blinker）は数えない。"""
import sqlite3, sys, collections
db = sqlite3.connect(sys.argv[1])
npa = {}
for line in open(sys.argv[2], encoding='utf-8'):
    if line.startswith('#') or line.startswith('pref\t'): continue
    p, n = line.rstrip('\n').split('\t'); npa[p] = int(n)
has_source = 'source' in [r[1] for r in db.execute('pragma table_info(signal)')]
q = "select pref, source, count(*) from signal where kind!='blinker' group by pref, source" if has_source else \
    "select pref, 'osm', count(*) from signal where kind!='blinker' group by pref"
cnt = collections.defaultdict(lambda: collections.Counter())
for p, s, c in db.execute(q): cnt[p][s] = c
rows = []
for p, n in npa.items():
    o, a, j = cnt[p]['osm'], cnt[p]['npa_accident'], cnt[p]['jartic']
    rows.append((p, o, a, j, n, (o + a + j) / n))
rows.sort(key=lambda r: -r[5])
print('pref\tosm\taccident\tjartic\tnpa\ttotal_ratio')
for p, o, a, j, n, r in rows: print(f'{p}\t{o}\t{a}\t{j}\t{n}\t{r:.0%}')
to, ta, tj, tn = (sum(r[i] for r in rows) for i in (1, 2, 3, 4))
none = sum(cnt[None].values())
print(f'合計\t{to}\t{ta}\t{tj}\t{tn}\t{(to + ta + tj) / tn:.0%}\t（都道府県なし {none}）')
