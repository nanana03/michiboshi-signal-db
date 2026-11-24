#!/bin/zsh
# 警察庁「交通事故統計情報のオープンデータ」の本票（年ごとの CSV・各 60MB 前後）を取る。既にあるものは取り直さない。
# 一覧＝https://www.npa.go.jp/publications/statistics/koutsuu/opendata/index_opendata.html（利用条件 PDL1.0）
# 使い方: scripts/fetch_npa.sh data/raw/npa [年 ...]（年を省くと 2019〜2025）
set -eu
out=$1; shift
if (( $# )); then years=("$@"); else years=(2019 2020 2021 2022 2023 2024 2025); fi
base=https://www.npa.go.jp/publications/statistics/koutsuu/opendata
mkdir -p $out
for y in $years; do
  f=$out/honhyo_$y.csv
  [[ -s $f ]] && continue
  if ! curl -fsSL -A "Mozilla/5.0" $base/$y/honhyo_$y.csv -o $f.part; then
    rm -f $f.part; echo "取得できない：$base/$y/honhyo_$y.csv" >&2; exit 1
  fi
  mv $f.part $f
  echo "取得 $f $(wc -c < $f) バイト"
  sleep 1
done
