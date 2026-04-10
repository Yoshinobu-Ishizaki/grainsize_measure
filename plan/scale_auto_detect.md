# Plan: 寸法マーカーから px/µm スケールを自動判別

## Context

結晶粒サイズ測定アプリにおいて、スケール（px/µm）は現在ユーザーが手動入力する必要がある。
顕微鏡画像の下部に埋め込まれた寸法マーカー（スケールバー＋テキストラベル）から
自動的にスケールを算出することで、測定精度向上と操作効率化を図る。

テスト画像 `tests/sample/c2600p_asis.png` の確認結果:
- 画像下部に暗いインフォストリップが存在（高さの約25%）
- ストリップ内の右寄りに白色水平線のスケールバーあり（約97px幅）
- バーの下方に "50 µm" のようなテキストラベルあり

---

## 実装方針

### 依存ライブラリ
- `easyocr` を **オプション依存** として追加（`[project.optional-dependencies]` の `ocr` グループ）
- easyocr 未インストール時はバーのピクセル長のみ検出し、実寸をユーザー入力ダイアログで補完
- easyocr はモデルが大きい（torch 含む）ため、ハード依存にしない

### UX
- **ボタン押下時のみ** 検出実行（画像ロード時の自動実行はしない）
- 検出は既存の `AnalysisWorker` と同じ `QThread + QObject.moveToThread()` パターンで非同期実行
- 検出結果は `spin_pixels_per_um` に自動セット（ユーザーが上書き可能）

---

## 変更ファイル一覧

| ファイル | 変更種別 |
|---|---|
| `src/scale_detector.py` | 新規作成 |
| `src/gui/settings_panel.py` | 修正 |
| `src/gui/main_window.py` | 修正 |
| `pyproject.toml` | 修正 |

---

## 1. 新規: `src/scale_detector.py`

### データクラス

```python
@dataclass
class ScaleBarResult:
    bar_x1: int                        # スケールバー左端 (全画像座標)
    bar_x2: int                        # スケールバー右端 (全画像座標)
    bar_y: int                         # スケールバー中心行 (全画像座標)
    bar_length_px: int                 # スケールバーのピクセル幅
    strip_start_row: int               # ストリップ開始行
    physical_value: float | None       # OCR結果の実寸値 (例: 50.0)
    unit: Literal["nm", "µm", "mm"] | None
    pixels_per_um: float | None        # 算出結果; OCR失敗時は None
    ocr_text_raw: str | None
    confidence: Literal["high", "low", "bar_only"]
    # "high"     = バー検出 + OCR成功
    # "low"      = バー検出 + OCR結果が曖昧
    # "bar_only" = バー検出、OCR未実行または失敗 → ユーザー入力が必要

class ScaleDetectionError(Exception): ...
```

### パブリック API

```python
def detect_scale_bar(image_bgr: np.ndarray) -> ScaleBarResult:
    """フル自動検出パイプライン。バー未検出時は ScaleDetectionError を投げる。"""

def compute_pixels_per_um_from_bar(
    bar_length_px: int, physical_value: float, unit: str
) -> float:
    """バーピクセル長＋ユーザー入力実寸から px/µm を計算（OCR失敗時のダイアログ用）。"""
```

### 内部アルゴリズム

#### `_find_strip_start(image_bgr)` → int
1. グレースケール変換後、行ごとの平均輝度を計算
2. 下から走査し「輝度 < 70 が5行連続」となる境界行を返す

#### `_find_scale_bar_line(image_bgr, strip_start)` → (bar_x1, bar_x2, bar_y)
1. ストリップを切り出してグレースケール化
2. 閾値150でバイナリ化（スケールバーは輝度~200、背景は~44）
3. 上端から `max(3, strip_h*0.05)` 行をゼロクリア（境界アーティファクト除去）
4. `MORPH_RECT(40, 1)` で morphological open → 40px 未満の明領域を除去
5. フォールバック: コンター未検出なら 20px カーネルで再試行
6. 最大幅コンターを選択 → 全画像座標に変換して返す

#### `_ocr_label(image_bgr, bar_x1, bar_x2, bar_y)` → (raw_text, value, unit)
1. バー周辺の検索領域: 行`[bar_y, bar_y+40]`, 列`[bar_x1-10, bar_x2+10]`（境界クランプ）
2. 閾値150でバイナリ化、高さ5px超のコンター（バー自体）を除外してテキスト領域を特定
3. 6倍アップスケール (`INTER_CUBIC`) + アンシャープマスクでシャープ化
4. `easyocr.Reader(['en'])` を **モジュールレベルでキャッシュ** して readtext() 実行
5. `_parse_scale_text()` でパース

#### `_parse_scale_text(text)` → (float | None, str | None)
```python
# OCRアーティファクト補正 + 正規表現でパース
text_clean = text.lower().replace('o','0').replace('l','1').replace('urn','um')
m = re.search(r'([\d]+(?:[.,]\d+)?)\s*(nm|um|µm|μm|mm)', text_clean)
```

#### `_compute_pixels_per_um(bar_length_px, physical_value, unit)` → float
- nm: `physical_value / 1000` → µm
- mm: `physical_value * 1000` → µm
- result = `bar_length_px / physical_um`

---

## 2. 修正: `src/gui/settings_panel.py`

### 追加シグナル
```python
auto_detect_requested = pyqtSignal()
```

### `grp_scale` ブロック変更（現行 lines 56-66）

現行の `spin_pixels_per_um` 単体のフォームレイアウトを以下に置き換え:

```
[QFormLayout grp_scale]
  Row 1 label "px/µm:": [QHBoxLayout]
                           spin_pixels_per_um (stretch=1)
                           btn_auto_detect ("自動検出", 固定70px幅, 初期 disabled)
  Row 2:                  lbl_scale_status (薄いグレー, 10px, wordWrap)
```

### 追加パブリックメソッド
```python
def set_auto_detect_enabled(self, enabled: bool) -> None:
    self.btn_auto_detect.setEnabled(enabled)

def set_scale_from_detection(self, pixels_per_um: float, status_text: str) -> None:
    self.spin_pixels_per_um.setValue(pixels_per_um)
    self.lbl_scale_status.setText(status_text)

def set_scale_status(self, text: str) -> None:
    self.lbl_scale_status.setText(text)
```

`get_params()` は変更不要（`spin_pixels_per_um.value()` を読むだけ）

---

## 3. 修正: `src/gui/main_window.py`

### 追加クラス: `ScaleDetectionWorker(QObject)`
```python
class ScaleDetectionWorker(QObject):
    finished = pyqtSignal(object)   # ScaleBarResult を emit
    error = pyqtSignal(str)

    def __init__(self, image_bgr: np.ndarray) -> None: ...

    def run(self) -> None:
        try:
            from scale_detector import detect_scale_bar
            result = detect_scale_bar(self._image_bgr)
            self.finished.emit(result)
        except Exception as exc:
            self.error.emit(str(exc))
```

### `MainWindow` への追加

**`__init__`**: インスタンス変数追加
```python
self._scale_thread: QThread | None = None
self._scale_worker: ScaleDetectionWorker | None = None
```

**`_build_ui()`**: シグナル接続追加（`run_requested` 接続の次行）
```python
self._settings.auto_detect_requested.connect(self._run_scale_detection)
```

**`_open_image()`**: `set_run_enabled(True)` の直後に追記
```python
self._settings.set_auto_detect_enabled(True)
self._settings.set_scale_status("")
```

**新規メソッド**:

```python
def _run_scale_detection(self) -> None:
    # スレッド起動、ボタン無効化、"検出中..." 表示

def _on_scale_done(self, result) -> None:
    # pixels_per_um が取れていればスピンボックスに反映
    # 取れていなければ _prompt_physical_dimension() を呼ぶ

def _on_scale_error(self, message: str) -> None:
    # エラー表示

def _on_scale_thread_finished(self) -> None:
    # self._scale_thread = None / self._scale_worker = None

def _prompt_physical_dimension(self, result) -> None:
    # OCR失敗時の実寸入力ダイアログ
    # QDoubleSpinBox (実寸値) + QComboBox (nm/µm/mm)
    # OK → compute_pixels_per_um_from_bar() → set_scale_from_detection()
```

### ステータス表示仕様

| 状態 | lbl_scale_status | ステータスバー |
|---|---|---|
| 検出中 | "検出中..." | "スケールバーを検出中..." |
| OCR成功 | "検出: 97px = 50µm → 1.940 px/µm" | "スケール自動検出: 1.940 px/µm" (5s) |
| バー検出・OCR失敗 | ダイアログ確定後に結果表示 | "スケール設定: X.XXX px/µm" (5s) |
| バー未検出 | "検出失敗: スケールバーが見つかりませんでした" | "スケールバーの検出に失敗しました。" (5s) |
| キャンセル | "キャンセルされました" | — |

---

## 4. 修正: `pyproject.toml`

```toml
[project.optional-dependencies]
ocr = [
    "easyocr>=1.7",
]
```

easyocr を使う場合: `uv pip install "grainsize-measure[ocr]"`

`[project.dependencies]` には追加しない（torch 等の大きな依存を強制しないため）

---

## 検証方法

1. `uv run src/grainsize_measure.py` で起動
2. `tests/sample/c2600p_asis.png` を開く
3. スケールグループの「自動検出」ボタンをクリック
4. ステータスラベルに "検出中..." が表示されること
5. 完了後、`spin_pixels_per_um` に推定値が自動入力されること
6. ステータスラベルに "検出: Xpx = Yµm → Z px/µm" が表示されること
7. easyocr 未インストール環境では実寸入力ダイアログが表示されること
8. 解析実行後、実寸単位（µm²）でCSV出力されること
