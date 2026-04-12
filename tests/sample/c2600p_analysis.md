# C2600P 真鍮の結晶粒径解析：加工なし vs 600°C / 60分焼鈍
yoshinobu.ishizaki
2026-04-12

- [はじめに](#はじめに)
- [結論](#結論)
- [ミクロ組織画像](#ミクロ組織画像)
  - [オリジナル画像の比較](#オリジナル画像の比較)
  - [粒界オーバーレイの比較](#粒界オーバーレイの比較)
- [データと解析手法](#データと解析手法)
  - [解析パラメータ](#解析パラメータ)
- [記述統計](#記述統計)
- [粒径分布](#粒径分布)
  - [ヒストグラム（粒数）](#ヒストグラム粒数)
  - [確率密度の比較](#確率密度の比較)
- [統計分布フィッティング](#統計分布フィッティング)
  - [フィッティングパラメータと適合度](#フィッティングパラメータと適合度)
  - [密度オーバーレイ](#密度オーバーレイ)
  - [Q-Qプロット](#q-qプロット)

## はじめに

C2600P について grainsize_measure ツールで解析した二つの試料を比較する。

- **加工なし**（c2600p_asis）：未熱処理の原板(O材)
- **焼鈍**（c2600p_600c60min）：600°C・60分焼鈍後に空冷

再結晶温度以上での加熱により結晶粒界が移動し（粒成長），
粒数が減少して平均粒径が増大することが予想される。

------------------------------------------------------------------------

## 結論

焼鈍処理によって，結晶粒径は顕著に増大した。

- **粒数**：加工なし 713 粒 → 焼鈍 131 粒（約 82% 減少）
- **平均等価円直径**：加工なし 28.2 µm → 焼鈍 64.8 µm（約 2.3 倍）
- **中央値**：加工なし 26 µm → 焼鈍 46.5 µm
- **標準偏差**：加工なし 16.7 µm → 焼鈍 44.8 µm

粒径分布は両条件とも右裾の長い非対称分布を示した。 AIC
最小の最適モデルは，加工なしが **ガンマ分布**，焼鈍が **対数正規分布**
であった。
統一的に当てはめるとしたら、ちょうど中間程度の当てはまりになっているガンマ分布が良さそう。

------------------------------------------------------------------------

## ミクロ組織画像

### オリジナル画像の比較

| 加工なし | 600°C/60分焼鈍 |
|:--:|:--:|
| ![加工なし オリジナル](c2600p_asis.png) | ![焼鈍 オリジナル](c2600p_600c60min.png) |

### 粒界オーバーレイの比較

| 加工なし | 600°C/60分焼鈍 |
|:--:|:--:|
| ![加工なし 粒界検出](c2600p_asis_overlay.png) | ![焼鈍 粒界検出](c2600p_600c60min_overlay.png) |

加工なし材では微細な粒が密に分布しているのに対し，
焼鈍材では明らかに粒が粗大化し，粒界が明瞭に観察できる。

------------------------------------------------------------------------

## データと解析手法

### 解析パラメータ

各試料の画像解析に用いたパラメータを以下に示す。

| パラメータ                    |   加工なし   | 600°C/60分焼鈍 |
|:------------------------------|:------------:|:--------------:|
| スケール (px/µm)              |     0.49     |      0.49      |
| 検出手法                      | color_region |  color_region  |
| CLAHE クリップ上限            |      0       |       5        |
| 適応閾値ブロックサイズ        |      23      |       15       |
| モルフォロジー閉演算半径 (px) |      1       |       3        |
| 最小粒面積 (px²)              |      5       |       50       |
| 最小特徴サイズ (px)           |      9       |       50       |
| 境界粒子除外                  |     TRUE     |      TRUE      |

主な差異：

- **CLAHE クリップ上限**：焼鈍材ではコントラスト強調（clip =
  5.0）を適用。粒界コントラストが低い大粒に対応。
- **モルフォロジー閉演算半径**：焼鈍材で大きく設定（1 → 3
  px）し，太くなった粒界を確実に閉じる。
- **最小粒面積 /
  最小特徴サイズ**：粒が粗大化しているため，ノイズ除去の閾値を引き上げ（9
  → 50 px²）。
- **適応閾値ブロックサイズ**：各画像の輝度分布に合わせて調整（23 → 15
  px）。

------------------------------------------------------------------------

## 記述統計

| 統計量         | 加工なし | 600°C/60分焼鈍 |
|:---------------|---------:|---------------:|
| 粒数           |   713.00 |         131.00 |
| 平均径 (µm)    |    28.21 |          64.78 |
| 中央値 (µm)    |    25.95 |          46.46 |
| 標準偏差 (µm)  |    16.72 |          44.80 |
| 変動係数 (%)   |    59.27 |          69.15 |
| 最小径 (µm)    |     5.15 |          16.45 |
| 最大径 (µm)    |    96.99 |         213.23 |
| 平均面積 (µm²) |   844.31 |        4860.35 |

焼鈍材は粒数が大幅に減少（713 → 131 粒）し， 平均粒径は約 2.3
倍に増大した。 変動係数は両条件とも 100%
前後と大きく，粒径分布の散らばりが顕著である。

------------------------------------------------------------------------

## 粒径分布

### ヒストグラム（粒数）

![](c2600p_analysis_files/figure-commonmark/histogram-count-1.png)

### 確率密度の比較

![](c2600p_analysis_files/figure-commonmark/density-comparison-1.png)

加工なし材の分布は小径側に大きなピークを持つ一方，
焼鈍材の分布は全体的に大径側にシフトし，裾が長い右歪み分布を示す。

------------------------------------------------------------------------

## 統計分布フィッティング

対数正規分布・ワイブル分布・ガンマ分布 の 3 種類を対象として、
各分布の最尤推定を `fitdistrplus::fitdist` で実施した。

### フィッティングパラメータと適合度

<div id="luwuxyzpgc" style="padding-left:0px;padding-right:0px;padding-top:10px;padding-bottom:10px;overflow-x:auto;overflow-y:auto;width:auto;height:auto;">
<style>#luwuxyzpgc table {
  font-family: system-ui, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif, 'Apple Color Emoji', 'Segoe UI Emoji', 'Segoe UI Symbol', 'Noto Color Emoji';
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
}
&#10;#luwuxyzpgc thead, #luwuxyzpgc tbody, #luwuxyzpgc tfoot, #luwuxyzpgc tr, #luwuxyzpgc td, #luwuxyzpgc th {
  border-style: none;
}
&#10;#luwuxyzpgc p {
  margin: 0;
  padding: 0;
}
&#10;#luwuxyzpgc .gt_table {
  display: table;
  border-collapse: collapse;
  line-height: normal;
  margin-left: auto;
  margin-right: auto;
  color: #333333;
  font-size: 16px;
  font-weight: normal;
  font-style: normal;
  background-color: #FFFFFF;
  width: auto;
  border-top-style: solid;
  border-top-width: 2px;
  border-top-color: #A8A8A8;
  border-right-style: none;
  border-right-width: 2px;
  border-right-color: #D3D3D3;
  border-bottom-style: solid;
  border-bottom-width: 2px;
  border-bottom-color: #A8A8A8;
  border-left-style: none;
  border-left-width: 2px;
  border-left-color: #D3D3D3;
}
&#10;#luwuxyzpgc .gt_caption {
  padding-top: 4px;
  padding-bottom: 4px;
}
&#10;#luwuxyzpgc .gt_title {
  color: #333333;
  font-size: 125%;
  font-weight: initial;
  padding-top: 4px;
  padding-bottom: 4px;
  padding-left: 5px;
  padding-right: 5px;
  border-bottom-color: #FFFFFF;
  border-bottom-width: 0;
}
&#10;#luwuxyzpgc .gt_subtitle {
  color: #333333;
  font-size: 85%;
  font-weight: initial;
  padding-top: 3px;
  padding-bottom: 5px;
  padding-left: 5px;
  padding-right: 5px;
  border-top-color: #FFFFFF;
  border-top-width: 0;
}
&#10;#luwuxyzpgc .gt_heading {
  background-color: #FFFFFF;
  text-align: center;
  border-bottom-color: #FFFFFF;
  border-left-style: none;
  border-left-width: 1px;
  border-left-color: #D3D3D3;
  border-right-style: none;
  border-right-width: 1px;
  border-right-color: #D3D3D3;
}
&#10;#luwuxyzpgc .gt_bottom_border {
  border-bottom-style: solid;
  border-bottom-width: 2px;
  border-bottom-color: #D3D3D3;
}
&#10;#luwuxyzpgc .gt_col_headings {
  border-top-style: solid;
  border-top-width: 2px;
  border-top-color: #D3D3D3;
  border-bottom-style: solid;
  border-bottom-width: 2px;
  border-bottom-color: #D3D3D3;
  border-left-style: none;
  border-left-width: 1px;
  border-left-color: #D3D3D3;
  border-right-style: none;
  border-right-width: 1px;
  border-right-color: #D3D3D3;
}
&#10;#luwuxyzpgc .gt_col_heading {
  color: #333333;
  background-color: #FFFFFF;
  font-size: 100%;
  font-weight: bold;
  text-transform: inherit;
  border-left-style: none;
  border-left-width: 1px;
  border-left-color: #D3D3D3;
  border-right-style: none;
  border-right-width: 1px;
  border-right-color: #D3D3D3;
  vertical-align: bottom;
  padding-top: 5px;
  padding-bottom: 6px;
  padding-left: 5px;
  padding-right: 5px;
  overflow-x: hidden;
}
&#10;#luwuxyzpgc .gt_column_spanner_outer {
  color: #333333;
  background-color: #FFFFFF;
  font-size: 100%;
  font-weight: bold;
  text-transform: inherit;
  padding-top: 0;
  padding-bottom: 0;
  padding-left: 4px;
  padding-right: 4px;
}
&#10;#luwuxyzpgc .gt_column_spanner_outer:first-child {
  padding-left: 0;
}
&#10;#luwuxyzpgc .gt_column_spanner_outer:last-child {
  padding-right: 0;
}
&#10;#luwuxyzpgc .gt_column_spanner {
  border-bottom-style: solid;
  border-bottom-width: 2px;
  border-bottom-color: #D3D3D3;
  vertical-align: bottom;
  padding-top: 5px;
  padding-bottom: 5px;
  overflow-x: hidden;
  display: inline-block;
  width: 100%;
}
&#10;#luwuxyzpgc .gt_spanner_row {
  border-bottom-style: hidden;
}
&#10;#luwuxyzpgc .gt_group_heading {
  padding-top: 8px;
  padding-bottom: 8px;
  padding-left: 5px;
  padding-right: 5px;
  color: #333333;
  background-color: #FFFFFF;
  font-size: 100%;
  font-weight: initial;
  text-transform: inherit;
  border-top-style: solid;
  border-top-width: 2px;
  border-top-color: #D3D3D3;
  border-bottom-style: solid;
  border-bottom-width: 2px;
  border-bottom-color: #D3D3D3;
  border-left-style: none;
  border-left-width: 1px;
  border-left-color: #D3D3D3;
  border-right-style: none;
  border-right-width: 1px;
  border-right-color: #D3D3D3;
  vertical-align: middle;
  text-align: left;
}
&#10;#luwuxyzpgc .gt_empty_group_heading {
  padding: 0.5px;
  color: #333333;
  background-color: #FFFFFF;
  font-size: 100%;
  font-weight: initial;
  border-top-style: solid;
  border-top-width: 2px;
  border-top-color: #D3D3D3;
  border-bottom-style: solid;
  border-bottom-width: 2px;
  border-bottom-color: #D3D3D3;
  vertical-align: middle;
}
&#10;#luwuxyzpgc .gt_from_md > :first-child {
  margin-top: 0;
}
&#10;#luwuxyzpgc .gt_from_md > :last-child {
  margin-bottom: 0;
}
&#10;#luwuxyzpgc .gt_row {
  padding-top: 8px;
  padding-bottom: 8px;
  padding-left: 5px;
  padding-right: 5px;
  margin: 10px;
  border-top-style: solid;
  border-top-width: 1px;
  border-top-color: #D3D3D3;
  border-left-style: none;
  border-left-width: 1px;
  border-left-color: #D3D3D3;
  border-right-style: none;
  border-right-width: 1px;
  border-right-color: #D3D3D3;
  vertical-align: middle;
  overflow-x: hidden;
}
&#10;#luwuxyzpgc .gt_stub {
  color: #333333;
  background-color: #FFFFFF;
  font-size: 100%;
  font-weight: bold;
  text-transform: inherit;
  border-right-style: solid;
  border-right-width: 2px;
  border-right-color: #D3D3D3;
  padding-left: 5px;
  padding-right: 5px;
}
&#10;#luwuxyzpgc .gt_stub_row_group {
  color: #333333;
  background-color: #FFFFFF;
  font-size: 100%;
  font-weight: initial;
  text-transform: inherit;
  border-right-style: solid;
  border-right-width: 2px;
  border-right-color: #D3D3D3;
  padding-left: 5px;
  padding-right: 5px;
  vertical-align: top;
}
&#10;#luwuxyzpgc .gt_row_group_first td {
  border-top-width: 2px;
}
&#10;#luwuxyzpgc .gt_row_group_first th {
  border-top-width: 2px;
}
&#10;#luwuxyzpgc .gt_summary_row {
  color: #333333;
  background-color: #FFFFFF;
  text-transform: inherit;
  padding-top: 8px;
  padding-bottom: 8px;
  padding-left: 5px;
  padding-right: 5px;
}
&#10;#luwuxyzpgc .gt_first_summary_row {
  border-top-style: solid;
  border-top-color: #D3D3D3;
}
&#10;#luwuxyzpgc .gt_first_summary_row.thick {
  border-top-width: 2px;
}
&#10;#luwuxyzpgc .gt_last_summary_row {
  padding-top: 8px;
  padding-bottom: 8px;
  padding-left: 5px;
  padding-right: 5px;
  border-bottom-style: solid;
  border-bottom-width: 2px;
  border-bottom-color: #D3D3D3;
}
&#10;#luwuxyzpgc .gt_grand_summary_row {
  color: #333333;
  background-color: #FFFFFF;
  text-transform: inherit;
  padding-top: 8px;
  padding-bottom: 8px;
  padding-left: 5px;
  padding-right: 5px;
}
&#10;#luwuxyzpgc .gt_first_grand_summary_row {
  padding-top: 8px;
  padding-bottom: 8px;
  padding-left: 5px;
  padding-right: 5px;
  border-top-style: double;
  border-top-width: 6px;
  border-top-color: #D3D3D3;
}
&#10;#luwuxyzpgc .gt_last_grand_summary_row_top {
  padding-top: 8px;
  padding-bottom: 8px;
  padding-left: 5px;
  padding-right: 5px;
  border-bottom-style: double;
  border-bottom-width: 6px;
  border-bottom-color: #D3D3D3;
}
&#10;#luwuxyzpgc .gt_striped {
  background-color: rgba(128, 128, 128, 0.05);
}
&#10;#luwuxyzpgc .gt_table_body {
  border-top-style: solid;
  border-top-width: 2px;
  border-top-color: #D3D3D3;
  border-bottom-style: solid;
  border-bottom-width: 2px;
  border-bottom-color: #D3D3D3;
}
&#10;#luwuxyzpgc .gt_footnotes {
  color: #333333;
  background-color: #FFFFFF;
  border-bottom-style: none;
  border-bottom-width: 2px;
  border-bottom-color: #D3D3D3;
  border-left-style: none;
  border-left-width: 2px;
  border-left-color: #D3D3D3;
  border-right-style: none;
  border-right-width: 2px;
  border-right-color: #D3D3D3;
}
&#10;#luwuxyzpgc .gt_footnote {
  margin: 0px;
  font-size: 90%;
  padding-top: 4px;
  padding-bottom: 4px;
  padding-left: 5px;
  padding-right: 5px;
}
&#10;#luwuxyzpgc .gt_sourcenotes {
  color: #333333;
  background-color: #FFFFFF;
  border-bottom-style: none;
  border-bottom-width: 2px;
  border-bottom-color: #D3D3D3;
  border-left-style: none;
  border-left-width: 2px;
  border-left-color: #D3D3D3;
  border-right-style: none;
  border-right-width: 2px;
  border-right-color: #D3D3D3;
}
&#10;#luwuxyzpgc .gt_sourcenote {
  font-size: 90%;
  padding-top: 4px;
  padding-bottom: 4px;
  padding-left: 5px;
  padding-right: 5px;
}
&#10;#luwuxyzpgc .gt_left {
  text-align: left;
}
&#10;#luwuxyzpgc .gt_center {
  text-align: center;
}
&#10;#luwuxyzpgc .gt_right {
  text-align: right;
  font-variant-numeric: tabular-nums;
}
&#10;#luwuxyzpgc .gt_font_normal {
  font-weight: normal;
}
&#10;#luwuxyzpgc .gt_font_bold {
  font-weight: bold;
}
&#10;#luwuxyzpgc .gt_font_italic {
  font-style: italic;
}
&#10;#luwuxyzpgc .gt_super {
  font-size: 65%;
}
&#10;#luwuxyzpgc .gt_footnote_marks {
  font-size: 75%;
  vertical-align: 0.4em;
  position: initial;
}
&#10;#luwuxyzpgc .gt_asterisk {
  font-size: 100%;
  vertical-align: 0;
}
&#10;#luwuxyzpgc .gt_indent_1 {
  text-indent: 5px;
}
&#10;#luwuxyzpgc .gt_indent_2 {
  text-indent: 10px;
}
&#10;#luwuxyzpgc .gt_indent_3 {
  text-indent: 15px;
}
&#10;#luwuxyzpgc .gt_indent_4 {
  text-indent: 20px;
}
&#10;#luwuxyzpgc .gt_indent_5 {
  text-indent: 25px;
}
&#10;#luwuxyzpgc .katex-display {
  display: inline-flex !important;
  margin-bottom: 0.75em !important;
}
&#10;#luwuxyzpgc div.Reactable > div.rt-table > div.rt-thead > div.rt-tr.rt-tr-group-header > div.rt-th-group:after {
  height: 0px !important;
}
</style>

<table class="gt_table" style="width:100%;"
data-quarto-postprocess="true" data-quarto-disable-processing="false"
data-quarto-bootstrap="false">
<colgroup>
<col style="width: 14%" />
<col style="width: 14%" />
<col style="width: 14%" />
<col style="width: 14%" />
<col style="width: 14%" />
<col style="width: 14%" />
<col style="width: 14%" />
</colgroup>
<thead>
<tr class="gt_heading">
<th colspan="7"
class="gt_heading gt_title gt_font_normal gt_bottom_border">分布フィッティングパラメータと適合度指標</th>
</tr>
<tr class="gt_col_headings gt_spanner_row">
<th rowspan="2" id="a::stub"
class="gt_col_heading gt_columns_bottom_border gt_left"
data-quarto-table-cell-role="th" scope="col"></th>
<th colspan="3" id="加工なし"
class="gt_center gt_columns_top_border gt_column_spanner_outer"
data-quarto-table-cell-role="th" style="font-weight: bold"
scope="colgroup"><div class="gt_column_spanner">
加工なし
</div></th>
<th colspan="3" id="焼鈍"
class="gt_center gt_columns_top_border gt_column_spanner_outer"
data-quarto-table-cell-role="th" style="font-weight: bold"
scope="colgroup"><div class="gt_column_spanner">
焼鈍
</div></th>
</tr>
<tr class="gt_col_headings">
<th id="lnorm_asis"
class="gt_col_heading gt_columns_bottom_border gt_left"
data-quarto-table-cell-role="th" scope="col">対数正規</th>
<th id="weibull_asis"
class="gt_col_heading gt_columns_bottom_border gt_left"
data-quarto-table-cell-role="th" scope="col">ワイブル</th>
<th id="gamma_asis"
class="gt_col_heading gt_columns_bottom_border gt_left"
data-quarto-table-cell-role="th" scope="col">ガンマ</th>
<th id="lnorm_heat"
class="gt_col_heading gt_columns_bottom_border gt_left"
data-quarto-table-cell-role="th" scope="col">対数正規</th>
<th id="weibull_heat"
class="gt_col_heading gt_columns_bottom_border gt_left"
data-quarto-table-cell-role="th" scope="col">ワイブル</th>
<th id="gamma_heat"
class="gt_col_heading gt_columns_bottom_border gt_left"
data-quarto-table-cell-role="th" scope="col">ガンマ</th>
</tr>
</thead>
<tbody class="gt_table_body">
<tr>
<td id="stub_1_1" class="gt_row gt_center gt_stub"
data-quarto-table-cell-role="th" scope="row">パラメータ1</td>
<td class="gt_row gt_left" headers="stub_1_1 lnorm_asis">meanlog =
3.1401</td>
<td class="gt_row gt_left" headers="stub_1_1 weibull_asis">shape =
1.7693</td>
<td class="gt_row gt_left" headers="stub_1_1 gamma_asis">shape =
2.6591</td>
<td class="gt_row gt_left" headers="stub_1_1 lnorm_heat">meanlog =
3.9505</td>
<td class="gt_row gt_left" headers="stub_1_1 weibull_heat">shape =
1.5694</td>
<td class="gt_row gt_left" headers="stub_1_1 gamma_heat">shape =
2.4212</td>
</tr>
<tr>
<td id="stub_1_2" class="gt_row gt_center gt_stub"
data-quarto-table-cell-role="th" scope="row">パラメータ2</td>
<td class="gt_row gt_left" headers="stub_1_2 lnorm_asis">sdlog =
0.6749</td>
<td class="gt_row gt_left" headers="stub_1_2 weibull_asis">scale =
31.7751</td>
<td class="gt_row gt_left" headers="stub_1_2 gamma_asis">rate =
0.0942</td>
<td class="gt_row gt_left" headers="stub_1_2 lnorm_heat">sdlog =
0.6622</td>
<td class="gt_row gt_left" headers="stub_1_2 weibull_heat">scale =
72.7244</td>
<td class="gt_row gt_left" headers="stub_1_2 gamma_heat">rate =
0.0374</td>
</tr>
<tr>
<td id="stub_1_3" class="gt_row gt_center gt_stub"
data-quarto-table-cell-role="th" scope="row">AIC</td>
<td class="gt_row gt_left" headers="stub_1_3 lnorm_asis">5944.5</td>
<td class="gt_row gt_left" headers="stub_1_3 weibull_asis">5898.3</td>
<td class="gt_row gt_left" headers="stub_1_3 gamma_asis">5896.4</td>
<td class="gt_row gt_left" headers="stub_1_3 lnorm_heat">1302.8</td>
<td class="gt_row gt_left" headers="stub_1_3 weibull_heat">1321.2</td>
<td class="gt_row gt_left" headers="stub_1_3 gamma_heat">1312.8</td>
</tr>
<tr>
<td id="stub_1_4" class="gt_row gt_center gt_stub"
data-quarto-table-cell-role="th" scope="row">BIC</td>
<td class="gt_row gt_left" headers="stub_1_4 lnorm_asis">5953.6</td>
<td class="gt_row gt_left" headers="stub_1_4 weibull_asis">5907.4</td>
<td class="gt_row gt_left" headers="stub_1_4 gamma_asis">5905.5</td>
<td class="gt_row gt_left" headers="stub_1_4 lnorm_heat">1308.5</td>
<td class="gt_row gt_left" headers="stub_1_4 weibull_heat">1327</td>
<td class="gt_row gt_left" headers="stub_1_4 gamma_heat">1318.6</td>
</tr>
</tbody>
</table>

</div>

AIC が最小のモデル（最適フィット）：加工なし = **ガンマ分布**， 焼鈍 =
**対数正規分布**。

### 密度オーバーレイ

![](c2600p_analysis_files/figure-commonmark/fit-overlay-asis-1.png)

![](c2600p_analysis_files/figure-commonmark/fit-overlay-heat-1.png)

### Q-Qプロット

![](c2600p_analysis_files/figure-commonmark/qqplot-asis-1.png)

![](c2600p_analysis_files/figure-commonmark/qqplot-heat-1.png)

Q-Qプロットにおいて，対角線に近い分布ほど観測データへの適合が良好であることを示す。
