#!/bin/zsh
# 信号機DBを一から作り直す（試作）。生成物は data/raw/ と build/（どちらも git の外）。
set -eu
cd "${0:A:h}/.."
mkdir -p data/raw build
[[ -f data/raw/jp_signals.json ]] || python3 scripts/fetch_osm.py data/raw/jp_signals.json
# 都道府県の境界＝data/boundaries/pref_detail.topojson（国土数値情報 N03 から作成・作り直しは scripts/build_boundaries.sh）
python3 scripts/assign_pref.py data/boundaries/pref_detail.topojson data/raw/jp_signals.json data/raw/pref_ids.json > build/assign_pref.log
python3 scripts/build_db.py data/raw/jp_signals.json data/raw/pref_ids.json build/signals.sqlite 30
# OSM が薄い地域を、警察庁の交通事故オープンデータ（本票・信号機が作動していた事故の地点）で埋める
scripts/fetch_npa.sh data/raw/npa
python3 scripts/accident_signals.py build/signals.sqlite data/raw/npa/honhyo_*.csv \
  --out build/accident_candidates.csv --write-db > build/accident_signals.log
tail -1 build/accident_signals.log
# 信号機の位置は JARTIC の交通規制情報（警察の規制データ・98＝信号機の設置）を土台にする（2026-11-23）。
# 信号機が入っている県（44）は OSM・事故データの点を JARTIC の点に置き換え、交差点名は近くの OSM から借りる。入っていない県（神奈川・熊本・富山）はそのまま
[[ -f data/raw/jartic/typeD_tokyo.zip ]] || scripts/fetch_jartic.sh data/raw/jartic
python3 scripts/jartic_signals.py write data/raw/jartic data/npa_signal_stock_r7.tsv build/signals.sqlite > build/jartic_signals.log
head -1 build/jartic_signals.log
# 信号機に標高を付ける（国土地理院の標高タイル DEM10B・ズーム 12・2026-11-23）。取ったタイルは data/raw/gsi_dem/ に残り、次は取らない（初回 約 30 分）
python3 scripts/signal_elev_tiles.py build/signals.sqlite data/raw/gsi_dem > build/signal_elev.log
tail -1 build/signal_elev.log
python3 scripts/compare.py build/signals.sqlite data/npa_signal_stock_r7.tsv | tee build/coverage.tsv
# アプリ同梱用（元ノードの表を落とした軽量版）
cp build/signals.sqlite build/signals_lean.sqlite
sqlite3 build/signals_lean.sqlite "drop table osm_node; vacuum;"
ls -la build/*.sqlite
