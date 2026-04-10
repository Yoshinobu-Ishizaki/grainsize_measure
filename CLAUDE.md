## Core concepts

- grainsize_measure は 与えた結晶粒観察画像(寸法マーカー入)を画像分析して、結晶粒子境界を認識し、各粒子面積を計算し、その分布を表としてCSVで出力するpython GUI プログラムである。
- Consider to use https://github.com/usnistgov/grain-size-analysis-tools as a first method.
- Also you can consider to use Flood-fill to find grain boundary. It should be implemented in OpenCV2 library or scikit-image.
- 寸法マーカーから px/mm スケールを自動判別する。
- 結果は結晶粒の番号と面積、等価な面積を持つ円の直径を並べたCSVファイルとする。

## User Interface

- `uv run src/grainsize_measure.py`で起動する。
- 画像の外周境界線にまたがった粒子は除外するかどうかはオプションとして計算設定画面で選択できるようにする。
- 確認のため、結晶粒番号をマップした画像ファイルも元ファイルとは名称変更して保存できるようにする。
- 境界判定のためにプロセスされた画像とオリジナルの画像を見比べるために、どちらを表示するかを選べるようにする。
- Overlay colored line onto auto detected scale bar so that user can see its auto detection is actually correct.

## Development notes

- Use semantic versioning -- major.minor.patch 
- Add one to minor version if user asks to elevate it. バージョンを上げて、などのトリガーでバージョンを上げる。pyproject.toml の version を変更する。パッチレベルを上げる、と具体的に指示された場合はその通りのバージョン番号にする。
- pythonスクリプトは `src` フォルダに保存される。
- テストコードは `tests` フォルダに保存する。
- テスト用のサンプルデータは `tests/sample` フォルダに保存される。
- Use some GSAT sample data to verify implementation. Absolutely same result must be achieved as GSAT original.
- GUIには PyQT6 を使用する。

## Documentation

- Clearly acknowledge NIST's GSAT source code in README.md .
- This project is in MIT License.