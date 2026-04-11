from __future__ import annotations

import numpy as np

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QLabel, QMainWindow, QStatusBar, QTabWidget, QWidget

from gui.image_viewer import ImageViewer


class ViewerWindow(QMainWindow):
    """Non-closeable viewer window showing original and processed images."""

    grain_roi_selected = pyqtSignal(int, int, int, int)
    marker_roi_selected = pyqtSignal(int, int, int, int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("ビューワ")
        self.resize(800, 650)

        self._tabs = QTabWidget()
        self.setCentralWidget(self._tabs)

        self._viewer_original = ImageViewer()
        self._viewer_processed = ImageViewer()

        self._tabs.addTab(self._viewer_original, "元画像")
        self._tabs.addTab(self._viewer_processed, "処理結果")

        # forward ROI signals from both viewers
        self._viewer_original.grain_roi_selected.connect(self.grain_roi_selected)
        self._viewer_original.marker_roi_selected.connect(self.marker_roi_selected)
        self._viewer_processed.grain_roi_selected.connect(self.grain_roi_selected)
        self._viewer_processed.marker_roi_selected.connect(self.marker_roi_selected)

        self._viewer_original.pixel_hovered.connect(self._on_pixel_hovered)
        self._viewer_processed.pixel_hovered.connect(self._on_pixel_hovered)

        self._lbl_coords = QLabel("x: --  y: --")
        status_bar = QStatusBar()
        status_bar.addWidget(self._lbl_coords)
        self.setStatusBar(status_bar)

    # ------------------------------------------------------------------
    # Non-closeable
    # ------------------------------------------------------------------

    def closeEvent(self, event) -> None:
        event.ignore()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def show_original(self, rgb: np.ndarray) -> None:
        self._viewer_original.set_image(rgb)

    def show_processed(self, rgb: np.ndarray) -> None:
        self._viewer_processed.set_image(rgb)
        self._tabs.setCurrentIndex(1)

    def show_overlay(self, rgb: np.ndarray) -> None:
        self._viewer_processed.set_image(rgb)
        self._tabs.setCurrentIndex(1)

    def clear_processed(self) -> None:
        self._viewer_processed.clear()

    def set_grain_roi_mode(self, active: bool) -> None:
        mode = "grain_roi" if active else "none"
        self._viewer_original.set_mode(mode)
        self._viewer_processed.set_mode(mode)

    def set_marker_roi_mode(self, active: bool) -> None:
        mode = "marker_roi" if active else "none"
        self._viewer_original.set_mode(mode)
        self._viewer_processed.set_mode(mode)

    def set_grain_roi(self, roi: tuple[int, int, int, int] | None) -> None:
        self._viewer_original.set_grain_roi(roi)
        self._viewer_processed.set_grain_roi(roi)

    def set_marker_roi(self, roi: tuple[int, int, int, int] | None) -> None:
        self._viewer_original.set_marker_roi(roi)
        self._viewer_processed.set_marker_roi(roi)

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _on_pixel_hovered(self, x: int, y: int) -> None:
        self._lbl_coords.setText(f"x: {x}  y: {y}")
