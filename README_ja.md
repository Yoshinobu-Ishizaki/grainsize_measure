# grainsize_measure

結晶粒観察画像（寸法マーカー入り）を解析し、粒界を検出して各粒子の面積を計算し、結果を CSV ファイルとして出力する Python GUI アプリケーションです。

## 機能

- 埋め込まれた寸法マーカーからスケールバーを自動検出（px/µm）
- GSAT ベースの画像セグメンテーションパイプライン（CLAHE → ノイズ除去 → シャープ化 → 閾値処理 → モルフォロジー）
- **カラー領域検出** — Felzenszwalb グラフベースセグメンテーションにより、明示的な境界線ではなく色で粒子を区別する画像（EBSD マップ、エッチング光学顕微鏡画像など）に対応
- **トラック A** — ASTM E112 インターセプト法：複数角度でのコード長測定
- **トラック B** — ウォータシェッドセグメンテーションによる粒子ごとの面積測定
- 粒子領域およびスケールバー領域の対話的 ROI 選択
- 検出された境界と粒子色のオーバーレイ可視化
- コードデータと粒子データの個別 CSV エクスポート
- **パラメータオプティマイザー** — 任意の画像に対して最適なセグメンテーションパラメータを自動探索（GUI またはターミナルから実行可能）
- params JSON 読み込み時に処理パイプラインを自動実行
- オリジナル画像タブは常に未加工画像を表示；ROI とスケールバーのオーバーレイは処理済みビューにのみ表示

## 必要環境

- Python 3.11+
- [uv](https://github.com/astral-sh/uv)

## GUI 起動

```bash
uv run src/grainsize_measure.py
```

### ビューアー操作

| 操作 | 動作 |
|--------|--------|
| Ctrl + スクロールホイール | ズームイン／ズームアウト |
| Ctrl + 左ボタンドラッグ | 画像をパン（移動） |
| Ctrl + 左ボタンダブルクリック | ズームをウィンドウに合わせてリセット |

## CLI

GUI を使わずに解析を実行する場合：

```bash
# 画像からデフォルトの params JSON を生成：
uv run src/grainsize_measure_cli.py image.png

# 解析を実行してすべての出力タイプを書き出す：
uv run src/grainsize_measure_cli.py params.json --out grain chord stat image

# カスタム出力名ステムで粒子 CSV のみ書き出す：
uv run src/grainsize_measure_cli.py params.json --out grain --oname results
```

params JSON はすべての解析オプション（検出モードを含む）を制御します。カラーベースの粒子検出を使用するには `"detection_method": "color_region"` と Felzenszwalb パラメータを設定してください。すべての JSON フィールドについては[パラメータガイド](docs/parameter_guide_ja.md)を参照してください。

## パラメータ JSON — パス処理について

パラメータ JSON ファイル内の `image_path` フィールドは、JSON ファイルが置かれているディレクトリからの **Unix スタイル（スラッシュ区切り）の相対パス** として保存されます。これにより、JSON ファイルと画像ファイルをセットで移動すれば、どの OS でもそのまま動作します。

**パラメータファイル読み込み時のルール：**

| 保存されている値 | 解決方法 |
|---|---|
| 相対パス（`images/sample.png`） | JSON ファイルのディレクトリを基準に解決 |
| 絶対パス・ファイルが存在する（`/data/sample.png`） | そのまま使用 |
| 絶対パス・ファイルが存在しない — JSON ディレクトリが共通プレフィックス | 共通サブパスを JSON ディレクトリからの相対パスとして試行 |
| Windows の Git Bash パス（`/c/Users/…`） | 自動的に `C:/Users/…` に変換 |

**このバージョンでは絶対パスの自動保存は行われません。**
絶対パスを使用したい場合は、JSON を手動で編集して `image_path` に `/` で始まる文字列（例：`"/data/images/sample.png"`）を設定してください。`/` で始まるパスは常に絶対パスとして解釈されます。

## ドキュメント

| ドキュメント | 内容 |
|---|---|
| [パラメータガイド](docs/parameter_guide_ja.md) | 各パラメータの設定方法と粒界検出への影響（画像付き） |
| [CSV 出力ガイド](docs/csv_output_guide_ja.md) | 出力 CSV の全カラムの意味と計算方法の解説 |

英語版 README は [README.md](README.md) を参照してください。

## 謝辞

本ソフトウェアは **NIST Grain Size Analysis Tools (GSAT)** の画像処理関数を使用しています：

> [https://github.com/usnistgov/grain-size-analysis-tools](https://github.com/usnistgov/grain-size-analysis-tools)

GSAT は米国国立標準技術研究所（NIST）によって開発されています。GSAT のソースコードは元のライセンス条件のもとで使用されています。grainsize_measure は NIST とは無関係であり、NIST による推奨を受けているものではありません。

本アプリケーションは Anthropic の [Claude Sonnet](https://claude.ai/) の支援を受けて開発されました。

## ライセンス

MIT License
