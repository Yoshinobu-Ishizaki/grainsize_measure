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
        self._viewer_overlay = ImageViewer()

        self._tabs.addTab(self._viewer_original, "元画像")
        self._tabs.addTab(self._viewer_processed, "処理結果")
        self._tabs.addTab(self._viewer_overlay, "粒子オーバーレイ")

        # forward ROI signals from all viewers
        for viewer in (self._viewer_original, self._viewer_processed, self._viewer_overlay):
            viewer.grain_roi_selected.connect(self.grain_roi_selected)
            viewer.marker_roi_selected.connect(self.marker_roi_selected)
            viewer.pixel_hovered.connect(self._on_pixel_hovered)

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
        self._tabs.setCurrentIndex(0)

    def show_processed(self, rgb: np.ndarray) -> None:
        self._viewer_processed.set_image(rgb)
        self._tabs.setCurrentIndex(1)
        self._viewer_processed.fit_to_window()

    def show_overlay(self, rgb: np.ndarray) -> None:
        self._viewer_overlay.set_image(rgb)
        self._tabs.setCurrentIndex(2)
        self._viewer_overlay.fit_to_window()

    def clear_processed(self) -> None:
        self._viewer_processed.clear()
        self._viewer_overlay.clear()

    def set_grain_roi_mode(self, active: bool) -> None:
        mode = "grain_roi" if active else "none"
        for viewer in (self._viewer_original, self._viewer_processed, self._viewer_overlay):
            viewer.set_mode(mode)

    def set_marker_roi_mode(self, active: bool) -> None:
        mode = "marker_roi" if active else "none"
        for viewer in (self._viewer_original, self._viewer_processed, self._viewer_overlay):
            viewer.set_mode(mode)

    def set_grain_roi(self, roi: tuple[int, int, int, int] | None) -> None:
        for viewer in (self._viewer_original, self._viewer_processed, self._viewer_overlay):
            viewer.set_grain_roi(roi)

    def set_marker_roi(self, roi: tuple[int, int, int, int] | None) -> None:
        for viewer in (self._viewer_original, self._viewer_processed, self._viewer_overlay):
            viewer.set_marker_roi(roi)

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _on_pixel_hovered(self, x: int, y: int) -> None:
        self._lbl_coords.setText(f"x: {x}  y: {y}")
