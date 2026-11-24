#!/bin/zsh
# data/boundaries/*.topojson を国土数値情報（行政区域 N03・2026-01-01 時点）から作り直す。
# 出典：国土交通省国土数値情報ダウンロードサイト（https://nlftp.mlit.go.jp/ksj/gml/datalist/KsjTmplt-N03-2026.html）
# 利用条件＝オープンデータ（CC BY 4.0）。加工したことを書き添える（README のライセンス節）。
# ⚠️ 元の zip は約 803MB（展開すると 2.6GB）＝data/raw/ に置く（git の外）。
set -eu
cd "${0:A:h}/.."
mkdir -p data/raw/n03 data/boundaries
Z=data/raw/n03/N03-20260101_GML.zip
[[ -f $Z ]] || curl -sL -m 3600 -A 'signaldrive-builder/0.1' -o $Z https://nlftp.mlit.go.jp/ksj/gml/data/N03/N03-2026/N03-20260101_GML.zip
unzip -o -q $Z 'N03-20260101_prefecture.shp' 'N03-20260101_prefecture.shx' 'N03-20260101_prefecture.dbf' 'N03-20260101_prefecture.prj' 'N03-20260101_prefecture.cpg' -d data/raw/n03
MS=(npx -y mapshaper@0.7.101)   # 版を固定（2026-10-29 公開）
# 市区町村の島ごとの 123,025 件 → 47 都道府県にまとめる
$MS -i data/raw/n03/N03-20260101_prefecture.shp -dissolve N03_001 copy-fields=N03_007 \
    -rename-fields pref=N03_001,code=N03_007 -o data/raw/n03/pref_full.shp
# 細かい版（拡大用）＝20m 間隔・0.01km² 未満の島を落とす／粗い版（日本全体用）＝300m 間隔・1km² 未満の島を落とす
$MS -i data/raw/n03/pref_full.shp -simplify interval=20 keep-shapes -filter-islands min-area=10000 remove-empty \
    -o data/boundaries/pref_detail.topojson format=topojson precision=0.00001
$MS -i data/raw/n03/pref_full.shp -simplify interval=300 keep-shapes -filter-islands min-area=1000000 remove-empty \
    -o data/boundaries/pref_overview.topojson format=topojson precision=0.00001
ls -la data/boundaries
