# ミチボシ 信号機データの作り方

iOS アプリ「ミチボシ」に同梱している信号機のデータベース（`signals.db`）と、星図の背景（`starmap_bg.dat`）を作る道具と手順です。

このデータベースは OpenStreetMap のデータ（Open Database License 1.0）を加工して作っています。
ODbL 第 4.6 条に従い、元のデータベースから派生データベースを作る方法をここで公開しています。

アプリ本体のコードは含みません。

このリポジトリの道具には、再利用の許可（ライセンス）を付けていません。作り方を示すために公開しています。

## 使うデータと利用条件

| データ | 取得する道具 | 利用条件 |
|---|---|---|
| OpenStreetMap の信号機（`highway=traffic_signals`）。Overpass API（https://overpass-api.de/api/interpreter）から取得 | `scripts/fetch_osm.py` | © OpenStreetMap contributors・ODbL 1.0（https://opendatacommons.org/licenses/odbl/1-0/） |
| 公益財団法人日本道路交通情報センター（JARTIC）「交通規制情報」（https://www.jartic.or.jp/service/opendata/） | `scripts/fetch_jartic.sh` | JARTIC オープンデータ利用規約（https://www.jartic.or.jp/d/opendata/riyou_kiyaku.pdf）。出典を示し、加工して作成した旨を書く |
| 警察庁「交通事故統計情報のオープンデータ」本票（https://www.npa.go.jp/publications/statistics/koutsuu/opendata/index_opendata.html） | `scripts/fetch_npa.sh` | 警察庁ウェブサイト利用規約（PDL1.0）。出典と、編集・加工した旨を書く |
| 警察庁「都道府県別交通信号機ストック数」令和7年度末（`data/npa_signal_stock_r7.tsv`・出典はファイルの先頭） | 同梱 | 警察庁ウェブサイト利用規約（PDL1.0） |
| 国土交通省「国土数値情報（行政区域 N03）」（https://nlftp.mlit.go.jp/ksj/gml/datalist/KsjTmplt-N03-2026.html） | `scripts/build_boundaries.sh` | CC BY 4.0。加工して作成した旨を書く |
| 国土地理院「標高タイル（DEM10B）」（https://maps.gsi.go.jp/development/ichiran.html） | `scripts/signal_elev_tiles.py` | 国土地理院コンテンツ利用規約。出典を書く・サーバーに過度の負担をかけない |

## 手順

必要なもの：`zsh`・`python3`（標準ライブラリだけ）・`sqlite3`・`curl`・`unzip`・Node.js（`npx mapshaper` を使う）。

```sh
scripts/build_boundaries.sh   # 都道府県の境界（data/boundaries/）を国土数値情報から作る。元の zip は約 800MB
scripts/build_all.sh          # 信号機のデータベースを一から作る（build/signals.sqlite）
python3 scripts/build_app_db.py build/signals.sqlite signals.db          # アプリに入れる形にする
python3 scripts/build_starmap_bg.py build/signals.sqlite starmap_bg.dat  # 星図の背景（全国の信号機の点）
```

- 取ってきた元のデータは `data/raw/`、途中の生成物は `build/` に置きます（どちらも大きいので、このリポジトリには入れていません）。
- 標高タイルの取得は初回に約 30 分かかります。取ったタイルは `data/raw/gsi_dem/` に残り、次からは取りに行きません。
- `scripts/build_starmap_bg.py` は、描画用の日本の外形（`design/home_picker/japan.json`）も読みます。これは信号機の位置の作り方には関わらない絵の素材なので、ここには入れていません。
- 各道具が何をするかは、それぞれのファイルの先頭に書いてあります。

## 出典の表記

アプリの中では、次のように表示しています。

- © OpenStreetMap contributors（ODbL）
- 信号機：「交通規制情報」（公益財団法人日本道路交通情報センター）を加工して作成
- 警察庁「交通事故統計情報のオープンデータ」を加工して作成
- 外形・県境：「国土数値情報（行政区域データ）」（国土交通省）をもとに簡略化して作成
- 標高：国土地理院（標高タイル）
