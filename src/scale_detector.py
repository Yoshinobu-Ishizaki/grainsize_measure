from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

import cv2
import numpy as np


# ---------------------------------------------------------------------------
# データクラス
# ---------------------------------------------------------------------------

@dataclass
class ScaleBarResult:
    bar_x1: int
    bar_x2: int
    bar_y: int
    bar_length_px: int
    strip_start_row: int
    physical_value: float | None
    unit: Literal["nm", "µm", "mm"] | None
    pixels_per_um: float | None
    ocr_text_raw: str | None
    confidence: Literal["high", "low", "bar_only"]


class ScaleDetectionError(Exception):
    pass


# ---------------------------------------------------------------------------
# OCR リーダーキャッシュ
# ---------------------------------------------------------------------------

_ocr_reader = None


def _get_ocr_reader():
    global _ocr_reader
    if _ocr_reader is None:
        import easyocr  # noqa: PLC0415
        _ocr_reader = easyocr.Reader(["en"], verbose=False)
    return _ocr_reader


# ---------------------------------------------------------------------------
# 内部アルゴリズム
# ---------------------------------------------------------------------------

def _find_strip_start(image_bgr: np.ndarray) -> int:
    """暗いインフォストリップの上端行を返す。

    Phase 1: 下から走査し「輝度 < 70 が 5 行連続」でストリップ存在を確認（アンカー行）。
    Phase 2: アンカー行から上へ走査し、輝度 < 100 の行が続く限り遡って真の上端を返す。
    """
    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
    h = gray.shape[0]
    row_mean = gray.mean(axis=1)

    # Phase 1: confirm strip exists
    consecutive = 0
    anchor_row = -1
    for row in range(h - 1, -1, -1):
        if row_mean[row] < 70:
            consecutive += 1
            if consecutive >= 5:
                anchor_row = row
                break
        else:
            consecutive = 0

    if anchor_row < 0:
        raise ScaleDetectionError("ストリップ領域が見つかりませんでした。")

    # Phase 2: walk upward to find the true top of the dark strip
    # Use a slightly lenient threshold (100) to tolerate the bright scale bar row
    strip_start = anchor_row
    for row in range(anchor_row - 1, -1, -1):
        if row_mean[row] < 100:
            strip_start = row
        else:
            break

    return strip_start


def _find_scale_bar_line(
    image_bgr: np.ndarray, strip_start: int
) -> tuple[int, int, int]:
    """ストリップ内のスケールバー水平線を検出し (bar_x1, bar_x2, bar_y) を返す。"""
    strip = image_bgr[strip_start:, :]
    gray = cv2.cvtColor(strip, cv2.COLOR_BGR2GRAY)
    strip_h = gray.shape[0]

    _, binary = cv2.threshold(gray, 150, 255, cv2.THRESH_BINARY)

    # 上端のアーティファクト除去
    margin = max(3, int(strip_h * 0.05))
    binary[:margin, :] = 0

    def _find_contour(binary_img, kernel_w):
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (kernel_w, 1))
        opened = cv2.morphologyEx(binary_img, cv2.MORPH_OPEN, kernel)
        contours, _ = cv2.findContours(
            opened, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )
        return contours

    contours = _find_contour(binary, 40)
    if not contours:
        contours = _find_contour(binary, 20)
    if not contours:
        raise ScaleDetectionError("スケールバーが見つかりませんでした。")

    # 最大幅コンターを選択
    best = max(contours, key=lambda c: cv2.boundingRect(c)[2])
    x, y, w, h_c = cv2.boundingRect(best)

    bar_x1 = x
    bar_x2 = x + w
    bar_y = strip_start + y + h_c // 2
    return bar_x1, bar_x2, bar_y


def _parse_scale_text(text: str) -> tuple[float | None, str | None]:
    """OCRテキストから (physical_value, unit) をパースする。"""
    text_clean = (
        text.lower()
        .replace("o", "0")
        .replace("l", "1")
        .replace("urn", "um")
        .replace("μm", "µm")
        .replace("um", "µm")
    )
    m = re.search(r"([\d]+(?:[.,]\d+)?)\s*(nm|µm|mm)", text_clean)
    if not m:
        return None, None
    value_str = m.group(1).replace(",", ".")
    unit_raw = m.group(2)
    unit_map = {"nm": "nm", "µm": "µm", "mm": "mm"}
    return float(value_str), unit_map.get(unit_raw)


def _ocr_label(
    image_bgr: np.ndarray, bar_x1: int, bar_x2: int, bar_y: int
) -> tuple[str | None, float | None, str | None]:
    """バー周辺のラベルをOCRして (raw_text, value, unit) を返す。"""
    h, w = image_bgr.shape[:2]

    # 検索領域: バー下方40px、左右に10px余白
    y1 = bar_y
    y2 = min(h, bar_y + 40)
    x1 = max(0, bar_x1 - 10)
    x2 = min(w, bar_x2 + 10)

    roi = image_bgr[y1:y2, x1:x2]
    if roi.size == 0:
        return None, None, None

    gray_roi = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    _, binary_roi = cv2.threshold(gray_roi, 150, 255, cv2.THRESH_BINARY)

    # バー自体（高さ 5px 超のコンター）を除外
    contours, _ = cv2.findContours(
        binary_roi, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
    )
    mask = np.ones_like(binary_roi) * 255
    for c in contours:
        _, _, _, ch = cv2.boundingRect(c)
        if ch > 5:
            cv2.drawContours(mask, [c], -1, 0, -1)
    text_region = cv2.bitwise_and(binary_roi, mask)

    # アップスケール + アンシャープマスク
    scaled = cv2.resize(text_region, None, fx=6, fy=6, interpolation=cv2.INTER_CUBIC)
    blurred = cv2.GaussianBlur(scaled, (0, 0), 3)
    sharpened = cv2.addWeighted(scaled, 1.5, blurred, -0.5, 0)

    try:
        reader = _get_ocr_reader()
        results = reader.readtext(sharpened, detail=0)
        raw_text = " ".join(results)
    except Exception:
        return None, None, None

    value, unit = _parse_scale_text(raw_text)
    return raw_text, value, unit


def _compute_pixels_per_um(
    bar_length_px: int, physical_value: float, unit: str
) -> float:
    """バーピクセル長と実寸から px/µm を計算する。"""
    if unit == "nm":
        physical_um = physical_value / 1000.0
    elif unit == "mm":
        physical_um = physical_value * 1000.0
    else:  # µm
        physical_um = physical_value
    return bar_length_px / physical_um


# ---------------------------------------------------------------------------
# パブリック API
# ---------------------------------------------------------------------------

def detect_scale_bar(
    image_bgr: np.ndarray, strip_start: int | None = None
) -> ScaleBarResult:
    """フル自動検出パイプライン。バー未検出時は ScaleDetectionError を投げる。

    strip_start が指定された場合はストリップ検出をスキップし、その行から下を
    スケールバー領域として扱う（marker_roi でクロップ済み画像に渡す場合は 0 を指定）。
    """
    if strip_start is None:
        strip_start = _find_strip_start(image_bgr)
    bar_x1, bar_x2, bar_y = _find_scale_bar_line(image_bgr, strip_start)
    bar_length_px = bar_x2 - bar_x1

    # OCR 試行
    ocr_available = True
    try:
        import easyocr  # noqa: F401, PLC0415
    except ImportError:
        ocr_available = False

    if ocr_available:
        raw_text, physical_value, unit = _ocr_label(image_bgr, bar_x1, bar_x2, bar_y)
        if physical_value is not None and unit is not None:
            pixels_per_um = _compute_pixels_per_um(bar_length_px, physical_value, unit)
            confidence: Literal["high", "low", "bar_only"] = "high"
        else:
            pixels_per_um = None
            confidence = "low"
    else:
        raw_text = None
        physical_value = None
        unit = None
        pixels_per_um = None
        confidence = "bar_only"

    return ScaleBarResult(
        bar_x1=bar_x1,
        bar_x2=bar_x2,
        bar_y=bar_y,
        bar_length_px=bar_length_px,
        strip_start_row=strip_start,
        physical_value=physical_value,
        unit=unit,
        pixels_per_um=pixels_per_um,
        ocr_text_raw=raw_text,
        confidence=confidence,
    )


def compute_pixels_per_um_from_bar(
    bar_length_px: int, physical_value: float, unit: str
) -> float:
    """バーピクセル長＋ユーザー入力実寸から px/µm を計算する（OCR失敗時のダイアログ用）。"""
    return _compute_pixels_per_um(bar_length_px, physical_value, unit)
