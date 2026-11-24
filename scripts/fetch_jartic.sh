#!/bin/zsh
# JARTIC（公益財団法人 日本道路交通情報センター）の交通規制情報（typeD）を 47 都道府県ぶん取る（2026-11-23）。
# 毎月月初に更新され、前の月の分は取れなくなる＝取ったら data/raw/jartic/（git の外）に置いておく。
# 一覧＝https://www.jartic.or.jp/d/opendata/opendata.json・利用規約＝https://www.jartic.or.jp/d/opendata/riyou_kiyaku.pdf（商用可・CC BY 4.0 互換）
set -eu
out=${1:-data/raw/jartic}
mkdir -p "$out"
curl -sfL -A "Mozilla/5.0" -o "$out/opendata.json" "https://www.jartic.or.jp/d/opendata/opendata.json"
python3 -I -c "import json,sys; d=json.load(open(sys.argv[1])); t=[x for x in d if x['type']=='typeD'][0]; print(t['targetMonth'], t['releaseDay'], file=sys.stderr); print('\n'.join(x['link'] for x in t['targetList']))" "$out/opendata.json" > "$out/links.txt"
n=0
while IFS= read -r L || [[ -n "$L" ]]; do   # 最後の行に改行が無くても読む（2026-11-23 に 1 県読み落とした）
  [[ -z "$L" ]] && continue
  curl -sfL -A "Mozilla/5.0" -o "$out/${L:t}" "https://www.jartic.or.jp/d/opendata$L"
  n=$((n+1)); sleep 1
done < "$out/links.txt"
echo "JARTIC 交通規制情報 ${n} 件 → $out"
