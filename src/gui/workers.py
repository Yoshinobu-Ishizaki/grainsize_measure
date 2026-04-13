"""Background worker threads for image processing and grain calculation."""
from __future__ import annotations

import cv2
import numpy as np

from PyQt6.QtCore import QObject, pyqtSignal

from analyzer import AnalysisParams, GrainAnalyzer


class _ImageProcessWorker(QObject):
    finished = pyqtSignal(object)   # binary_rgb ndarray (H, W, 3)
    error = pyqtSignal(str)
    cancelled = pyqtSignal()
    progress = pyqtSignal(str, int, int)   # label, current, total

    def __init__(self, analyzer: GrainAnalyzer, params: AnalysisParams) -> None:
        super().__init__()
        self._analyzer = analyzer
        self._params = params
        self._cancel_flag = False

    def cancel(self) -> None:
        self._cancel_flag = True

    def run(self) -> None:
        try:
            binary = self._analyzer.run_segmentation(
                self._params,
                progress_cb=lambda l, c, t: self.progress.emit(l, c, t),
                cancel_check=lambda: self._cancel_flag,
            )
            binary_rgb = cv2.cvtColor(binary, cv2.COLOR_GRAY2RGB)
            self.finished.emit(binary_rgb)
        except GrainAnalyzer.Cancelled:
            self.cancelled.emit()
        except Exception as exc:
            self.error.emit(str(exc))


class _GrainCalcWorker(QObject):
    finished = pyqtSignal(object, object, object)  # chord_df, grain_df, overlay ndarray
    error = pyqtSignal(str)
    cancelled = pyqtSignal()
    progress = pyqtSignal(str, int, int)   # label, current, total

    def __init__(self, analyzer: GrainAnalyzer, params: AnalysisParams) -> None:
        super().__init__()
        self._analyzer = analyzer
        self._params = params
        self._cancel_flag = False

    def cancel(self) -> None:
        self._cancel_flag = True

    def run(self) -> None:
        try:
            chord_df, grain_df = self._analyzer.run_measurement(
                self._params,
                progress_cb=lambda l, c, t: self.progress.emit(l, c, t),
                cancel_check=lambda: self._cancel_flag,
            )
            self.progress.emit("オーバーレイ生成中...", 0, 0)
            overlay = self._analyzer.render_overlay_image()
            self.finished.emit(chord_df, grain_df, overlay)
        except GrainAnalyzer.Cancelled:
            self.cancelled.emit()
        except Exception as exc:
            self.error.emit(str(exc))


class _ScaleDetectionWorker(QObject):
    finished = pyqtSignal(object)  # ScaleBarResult
    error = pyqtSignal(str)

    def __init__(self, image_bgr: np.ndarray, marker_roi: tuple[int, int, int, int] | None) -> None:
        super().__init__()
        self._image_bgr = image_bgr
        self._marker_roi = marker_roi

    def run(self) -> None:
        try:
            from scale_detector import detect_scale_bar  # noqa: PLC0415
            img = self._image_bgr
            strip_start = None
            if self._marker_roi is not None:
                x, y, w, h = self._marker_roi
                img = img[y:y + h, x:x + w]
                strip_start = 0  # entire cropped region is the scale bar area
            result = detect_scale_bar(img, strip_start=strip_start)
            self.finished.emit(result)
        except Exception as exc:
            self.error.emit(str(exc))
