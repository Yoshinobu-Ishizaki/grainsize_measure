from __future__ import annotations

import dataclasses
import json
from contextlib import contextmanager
from pathlib import Path


def _read_version() -> str:
    """Read version string from pyproject.toml at the project root."""
    from path_utils import read_app_version
    return read_app_version()

import cv2
import numpy as np

from PyQt6.QtCore import QObject, QProcess, QThread, QTimer, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QStatusBar,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from analyzer import AnalysisParams, GrainAnalyzer
from path_utils import make_relative_posix_str, resolve_image_path
from gui.workers import _ImageProcessWorker, _GrainCalcWorker, _ScaleDetectionWorker
from gui.dialogs import _OptimizerProgressDialog, _CalcProgressDialog
from gui.viewer_window import ViewerWindow
from i18n import _


# ---------------------------------------------------------------------------
# Tab widgets
# ---------------------------------------------------------------------------

class _ImageProcessTab(QWidget):
    """Tab 0: image processing parameters."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._image_shape: tuple[int, int] | None = None  # (h, w) of last loaded image
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        container = QWidget()
        scroll.setWidget(container)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

        layout = QVBoxLayout(container)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # --- Detection mode ---
        grp_mode = QGroupBox(_("Detection Mode"))
        form_mode = QFormLayout(grp_mode)
        self.combo_detection = QComboBox()
        self.combo_detection.addItems([
            _("Grayscale Threshold (GSAT)"),
            _("Color Region (Felzenszwalb)"),
        ])
        self.combo_detection.setCurrentIndex(0)
        form_mode.addRow(_("Detection Method:"), self.combo_detection)
        layout.addWidget(grp_mode)

        # --- Segmentation ---
        self.grp_seg = QGroupBox(_("Segmentation (GSAT)"))
        form_seg = QFormLayout(self.grp_seg)

        self.chk_invert = QCheckBox(_("Invert Grayscale (dark boundaries)"))
        self.chk_invert.setChecked(True)
        form_seg.addRow(self.chk_invert)

        self.spin_clahe_clip = QDoubleSpinBox()
        self.spin_clahe_clip.setRange(0.0, 20.0)
        self.spin_clahe_clip.setDecimals(1)
        self.spin_clahe_clip.setSingleStep(0.5)
        self.spin_clahe_clip.setValue(0.0)
        self.spin_clahe_clip.setToolTip(
            _("0.0 = disabled; 1.0\u20135.0 recommended for gray-region grain detection")
        )
        form_seg.addRow(_("CLAHE Clip Limit:"), self.spin_clahe_clip)

        self.spin_clahe_tile = QSpinBox()
        self.spin_clahe_tile.setRange(2, 64)
        self.spin_clahe_tile.setValue(8)
        self.spin_clahe_tile.setToolTip(
            _("CLAHE tile grid size (NxN). 'Auto' estimates from image dimensions.")
        )
        self._btn_clahe_tile_auto = QPushButton(_("Auto"))
        self._btn_clahe_tile_auto.setFixedWidth(48)
        self._btn_clahe_tile_auto.setToolTip(
            _("Calculate and set recommended tile size from image dimensions (max(8, min(H,W)\u00f720))")
        )
        self._btn_clahe_tile_auto.clicked.connect(self._auto_clahe_tile)
        tile_row = QHBoxLayout()
        tile_row.setContentsMargins(0, 0, 0, 0)
        tile_row.addWidget(self.spin_clahe_tile)
        tile_row.addWidget(self._btn_clahe_tile_auto)
        tile_row.addStretch()
        form_seg.addRow(_("CLAHE Tile Size:"), tile_row)

        self.spin_denoise_h = QDoubleSpinBox()
        self.spin_denoise_h.setRange(0.01, 100.0)
        self.spin_denoise_h.setDecimals(3)
        self.spin_denoise_h.setSingleStep(0.01)
        self.spin_denoise_h.setValue(0.04)
        form_seg.addRow(_("Denoise h:"), self.spin_denoise_h)

        self.spin_sharpen_radius = QSpinBox()
        self.spin_sharpen_radius.setRange(0, 20)
        self.spin_sharpen_radius.setValue(2)
        form_seg.addRow(_("Sharpen Radius:"), self.spin_sharpen_radius)

        self.spin_sharpen_amount = QDoubleSpinBox()
        self.spin_sharpen_amount.setRange(0.0, 10.0)
        self.spin_sharpen_amount.setSingleStep(0.1)
        self.spin_sharpen_amount.setValue(0.3)
        form_seg.addRow(_("Sharpen Amount:"), self.spin_sharpen_amount)

        self.combo_threshold = QComboBox()
        self.combo_threshold.addItems([
            _("Global Threshold"),
            _("Adaptive Threshold"),
            _("Hysteresis Threshold"),
        ])
        self.combo_threshold.setCurrentIndex(2)
        form_seg.addRow(_("Threshold Method:"), self.combo_threshold)

        self.spin_threshold_value = QSpinBox()
        self.spin_threshold_value.setRange(0, 255)
        self.spin_threshold_value.setValue(128)
        form_seg.addRow(_("Threshold (Low):"), self.spin_threshold_value)

        self.spin_threshold_high = QSpinBox()
        self.spin_threshold_high.setRange(0, 255)
        self.spin_threshold_high.setValue(200)
        self.spin_threshold_high.setEnabled(True)   # hysteresis is default
        form_seg.addRow(_("Threshold (High):"), self.spin_threshold_high)

        self.spin_adaptive_block = QSpinBox()
        self.spin_adaptive_block.setRange(3, 201)
        self.spin_adaptive_block.setSingleStep(2)
        self.spin_adaptive_block.setValue(35)
        self.spin_adaptive_block.setEnabled(False)
        form_seg.addRow(_("Adaptive Block:"), self.spin_adaptive_block)

        self.combo_threshold.currentIndexChanged.connect(self._on_threshold_changed)

        self.spin_morph_close = QSpinBox()
        self.spin_morph_close.setRange(0, 20)
        self.spin_morph_close.setValue(1)
        form_seg.addRow(_("Closing Radius:"), self.spin_morph_close)

        self.spin_morph_open = QSpinBox()
        self.spin_morph_open.setRange(0, 20)
        self.spin_morph_open.setValue(0)
        form_seg.addRow(_("Opening Radius:"), self.spin_morph_open)

        self.spin_min_feature = QSpinBox()
        self.spin_min_feature.setRange(1, 10000)
        self.spin_min_feature.setValue(64)
        form_seg.addRow(_("Min Feature (px\u00b2):"), self.spin_min_feature)

        self.chk_skeletonize = QCheckBox(_("Skeletonize (for SEM polished images)"))
        self.chk_skeletonize.setChecked(False)
        form_seg.addRow(self.chk_skeletonize)

        self.chk_skip_watershed = QCheckBox(_("Skip Watershed (fast mode)"))
        self.chk_skip_watershed.setChecked(False)
        self.chk_skip_watershed.setToolTip(
            _("Faster when boundaries are clearly closed. Touching grains may not be separated.")
        )
        form_seg.addRow(self.chk_skip_watershed)

        layout.addWidget(self.grp_seg)

        # --- Color-region segmentation (Felzenszwalb) ---
        self.grp_color = QGroupBox(_("Color Region Segmentation (Felzenszwalb)"))
        form_color = QFormLayout(self.grp_color)

        self.spin_color_scale = QDoubleSpinBox()
        self.spin_color_scale.setRange(10.0, 5000.0)
        self.spin_color_scale.setSingleStep(50.0)
        self.spin_color_scale.setValue(200.0)
        self.spin_color_scale.setToolTip(
            _("Larger \u2192 fewer, larger segments (50\u20132000 typical)")
        )
        form_color.addRow(_("Scale:"), self.spin_color_scale)

        self.spin_color_sigma = QDoubleSpinBox()
        self.spin_color_sigma.setRange(0.0, 5.0)
        self.spin_color_sigma.setSingleStep(0.1)
        self.spin_color_sigma.setDecimals(2)
        self.spin_color_sigma.setValue(0.8)
        self.spin_color_sigma.setToolTip(_("Pre-processing Gaussian \u03c3 (0.1\u20133.0)"))
        form_color.addRow(_("Sigma:"), self.spin_color_sigma)

        self.spin_color_min_size = QSpinBox()
        self.spin_color_min_size.setRange(10, 50000)
        self.spin_color_min_size.setSingleStep(50)
        self.spin_color_min_size.setValue(100)
        self.spin_color_min_size.setToolTip(_("Minimum segment size (px\u00b2)"))
        form_color.addRow(_("Min Size (px\u00b2):"), self.spin_color_min_size)

        self.spin_color_morph_close = QSpinBox()
        self.spin_color_morph_close.setRange(0, 20)
        self.spin_color_morph_close.setSingleStep(1)
        self.spin_color_morph_close.setValue(0)
        self.spin_color_morph_close.setToolTip(
            _("Dilation radius to close gaps in boundaries (px). 0 = disabled")
        )
        form_color.addRow(_("Boundary Closing Radius:"), self.spin_color_morph_close)

        layout.addWidget(self.grp_color)

        self.combo_detection.currentIndexChanged.connect(self._on_detection_mode_changed)
        self._on_detection_mode_changed(0)

        layout.addStretch()

    def _on_threshold_changed(self, index: int) -> None:
        is_global = index == 0
        is_hysteresis = index == 2
        is_adaptive = index == 1
        self.spin_threshold_value.setEnabled(is_global or is_hysteresis)
        self.spin_threshold_high.setEnabled(is_hysteresis)
        self.spin_adaptive_block.setEnabled(is_adaptive)

    def _on_detection_mode_changed(self, index: int) -> None:
        is_color = (index == 1)
        self.grp_seg.setVisible(not is_color)
        self.grp_color.setVisible(is_color)

    def suggest_clahe_tile(self, h: int, w: int) -> None:
        """Store image dimensions and update the tile-size spinbox with the auto estimate."""
        self._image_shape = (h, w)
        self.spin_clahe_tile.setValue(max(8, min(h, w) // 20))

    def _auto_clahe_tile(self) -> None:
        if self._image_shape is not None:
            h, w = self._image_shape
            self.spin_clahe_tile.setValue(max(8, min(h, w) // 20))

    def get_processing_params(self) -> dict:
        method_map = {0: "global_threshold", 1: "adaptive_threshold", 2: "hysteresis_threshold"}
        return {
            "invert_grayscale": self.chk_invert.isChecked(),
            "clahe_clip_limit": self.spin_clahe_clip.value(),
            "clahe_tile_size": self.spin_clahe_tile.value(),
            "denoise_h": self.spin_denoise_h.value(),
            "denoise_patch": 5,
            "denoise_search": 7,
            "sharpen_radius": self.spin_sharpen_radius.value(),
            "sharpen_amount": self.spin_sharpen_amount.value(),
            "threshold_method": method_map[self.combo_threshold.currentIndex()],
            "threshold_value": self.spin_threshold_value.value(),
            "threshold_high": self.spin_threshold_high.value(),
            "adaptive_block_size": self.spin_adaptive_block.value(),
            "adaptive_offset": 0.0,
            "morph_close_radius": self.spin_morph_close.value(),
            "morph_open_radius": self.spin_morph_open.value(),
            "min_feature_size": self.spin_min_feature.value(),
            "max_hole_size": 10,
            "skeletonize": self.chk_skeletonize.isChecked(),
            "skip_watershed": self.chk_skip_watershed.isChecked(),
            "detection_method": "color_region" if self.combo_detection.currentIndex() == 1 else "threshold",
            "color_scale": self.spin_color_scale.value(),
            "color_sigma": self.spin_color_sigma.value(),
            "color_min_size": self.spin_color_min_size.value(),
            "color_morph_close_radius": self.spin_color_morph_close.value(),
        }

    def set_processing_params(self, data: dict) -> None:
        method_map = {"global_threshold": 0, "adaptive_threshold": 1, "hysteresis_threshold": 2}
        self.chk_invert.setChecked(bool(data.get("invert_grayscale", True)))
        self.spin_clahe_clip.setValue(float(data.get("clahe_clip_limit", 0.0)))
        self.spin_clahe_tile.setValue(int(data.get("clahe_tile_size", 8)))
        self.spin_denoise_h.setValue(float(data.get("denoise_h", 0.04)))
        self.spin_sharpen_radius.setValue(int(data.get("sharpen_radius", 2)))
        self.spin_sharpen_amount.setValue(float(data.get("sharpen_amount", 0.3)))
        method = data.get("threshold_method", "hysteresis_threshold")
        self.combo_threshold.setCurrentIndex(method_map.get(method, 2))
        self.spin_threshold_value.setValue(int(data.get("threshold_value", 128)))
        self.spin_threshold_high.setValue(int(data.get("threshold_high", 200)))
        self.spin_adaptive_block.setValue(int(data.get("adaptive_block_size", 35)))
        self.spin_morph_close.setValue(int(data.get("morph_close_radius", 1)))
        self.spin_morph_open.setValue(int(data.get("morph_open_radius", 0)))
        self.spin_min_feature.setValue(int(data.get("min_feature_size", 64)))
        self.chk_skeletonize.setChecked(bool(data.get("skeletonize", False)))
        self.chk_skip_watershed.setChecked(bool(data.get("skip_watershed", False)))
        det_method = data.get("detection_method", "threshold")
        self.combo_detection.setCurrentIndex(1 if det_method == "color_region" else 0)
        self.spin_color_scale.setValue(float(data.get("color_scale", 200.0)))
        self.spin_color_sigma.setValue(float(data.get("color_sigma", 0.8)))
        self.spin_color_min_size.setValue(int(data.get("color_min_size", 100)))
        self.spin_color_morph_close.setValue(int(data.get("color_morph_close_radius", 0)))


class _GrainCalcTab(QWidget):
    """Tab 1: scale, ROI selection, intercept+area params."""

    auto_detect_requested = pyqtSignal()
    select_grain_roi_requested = pyqtSignal()
    select_marker_roi_requested = pyqtSignal()

    @contextmanager
    def _silent_update(self):
        self._updating_roi = True
        try:
            yield
        finally:
            self._updating_roi = False

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._updating_roi = False

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        container = QWidget()
        scroll.setWidget(container)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

        layout = QVBoxLayout(container)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # --- Scale ---
        grp_scale = QGroupBox(_("Scale Settings"))
        form_scale = QFormLayout(grp_scale)

        self.spin_pixels_per_um = QDoubleSpinBox()
        self.spin_pixels_per_um.setRange(0.0, 100000.0)
        self.spin_pixels_per_um.setDecimals(3)
        self.spin_pixels_per_um.setValue(1.0)
        self.spin_pixels_per_um.setSpecialValueText(_("(not set)"))
        self.spin_pixels_per_um.setMinimum(0.0)

        self.btn_auto_detect = QPushButton(_("Auto-detect"))
        self.btn_auto_detect.setFixedWidth(70)
        self.btn_auto_detect.setEnabled(False)
        self.btn_auto_detect.clicked.connect(self.auto_detect_requested)

        scale_row = QHBoxLayout()
        scale_row.addWidget(self.spin_pixels_per_um, stretch=1)
        scale_row.addWidget(self.btn_auto_detect)
        form_scale.addRow("px/\u00b5m:", scale_row)

        self.lbl_scale_status = QLabel()
        self.lbl_scale_status.setWordWrap(True)
        self.lbl_scale_status.setStyleSheet("color: gray; font-size: 10px;")
        self.lbl_scale_status.setAlignment(Qt.AlignmentFlag.AlignLeft)
        form_scale.addRow(self.lbl_scale_status)

        layout.addWidget(grp_scale)

        # --- Grain ROI ---
        grp_grain_roi = QGroupBox(_("Grain Region (ROI)"))
        form_grain_roi = QFormLayout(grp_grain_roi)

        self.spin_grain_x = QSpinBox()
        self.spin_grain_y = QSpinBox()
        self.spin_grain_w = QSpinBox()
        self.spin_grain_h = QSpinBox()
        for sp in (self.spin_grain_x, self.spin_grain_y, self.spin_grain_w, self.spin_grain_h):
            sp.setRange(0, 99999)
            sp.valueChanged.connect(self._on_grain_roi_spinbox_changed)

        grain_xy = QHBoxLayout()
        grain_xy.addWidget(QLabel("x:")); grain_xy.addWidget(self.spin_grain_x)
        grain_xy.addWidget(QLabel("y:")); grain_xy.addWidget(self.spin_grain_y)
        form_grain_roi.addRow(_("Coordinates:"), grain_xy)

        grain_wh = QHBoxLayout()
        grain_wh.addWidget(QLabel("w:")); grain_wh.addWidget(self.spin_grain_w)
        grain_wh.addWidget(QLabel("h:")); grain_wh.addWidget(self.spin_grain_h)
        form_grain_roi.addRow(_("Size:"), grain_wh)

        grain_btns = QHBoxLayout()
        self.btn_select_grain_roi = QPushButton(_("Select in Viewer"))
        self.btn_select_grain_roi.setEnabled(False)
        self.btn_select_grain_roi.clicked.connect(self.select_grain_roi_requested)
        self.btn_clear_grain_roi = QPushButton(_("Clear"))
        self.btn_clear_grain_roi.clicked.connect(self._clear_grain_roi)
        grain_btns.addWidget(self.btn_select_grain_roi)
        grain_btns.addWidget(self.btn_clear_grain_roi)
        form_grain_roi.addRow(grain_btns)

        layout.addWidget(grp_grain_roi)

        # --- Marker ROI ---
        grp_marker_roi = QGroupBox(_("Marker Region (ROI)"))
        form_marker_roi = QFormLayout(grp_marker_roi)

        self.spin_marker_x = QSpinBox()
        self.spin_marker_y = QSpinBox()
        self.spin_marker_w = QSpinBox()
        self.spin_marker_h = QSpinBox()
        for sp in (self.spin_marker_x, self.spin_marker_y, self.spin_marker_w, self.spin_marker_h):
            sp.setRange(0, 99999)
            sp.valueChanged.connect(self._on_marker_roi_spinbox_changed)

        marker_xy = QHBoxLayout()
        marker_xy.addWidget(QLabel("x:")); marker_xy.addWidget(self.spin_marker_x)
        marker_xy.addWidget(QLabel("y:")); marker_xy.addWidget(self.spin_marker_y)
        form_marker_roi.addRow(_("Coordinates:"), marker_xy)

        marker_wh = QHBoxLayout()
        marker_wh.addWidget(QLabel("w:")); marker_wh.addWidget(self.spin_marker_w)
        marker_wh.addWidget(QLabel("h:")); marker_wh.addWidget(self.spin_marker_h)
        form_marker_roi.addRow(_("Size:"), marker_wh)

        marker_btns = QHBoxLayout()
        self.btn_select_marker_roi = QPushButton(_("Select in Viewer"))
        self.btn_select_marker_roi.setEnabled(False)
        self.btn_select_marker_roi.clicked.connect(self.select_marker_roi_requested)
        self.btn_clear_marker_roi = QPushButton(_("Clear"))
        self.btn_clear_marker_roi.clicked.connect(self._clear_marker_roi)
        marker_btns.addWidget(self.btn_select_marker_roi)
        marker_btns.addWidget(self.btn_clear_marker_roi)
        form_marker_roi.addRow(marker_btns)

        layout.addWidget(grp_marker_roi)

        # --- Intercept ---
        grp_intercept = QGroupBox(_("Intercept Measurement"))
        form_intercept = QFormLayout(grp_intercept)

        self.spin_line_spacing = QSpinBox()
        self.spin_line_spacing.setRange(5, 500)
        self.spin_line_spacing.setValue(60)
        form_intercept.addRow(_("Line Spacing (px):"), self.spin_line_spacing)

        self.spin_theta_start = QDoubleSpinBox()
        self.spin_theta_start.setRange(0.0, 180.0)
        self.spin_theta_start.setSingleStep(15.0)
        self.spin_theta_start.setValue(0.0)
        form_intercept.addRow(_("Angle Start (\u00b0):"), self.spin_theta_start)

        self.spin_theta_end = QDoubleSpinBox()
        self.spin_theta_end.setRange(0.0, 180.0)
        self.spin_theta_end.setSingleStep(15.0)
        self.spin_theta_end.setValue(180.0)
        form_intercept.addRow(_("Angle End (\u00b0):"), self.spin_theta_end)

        self.spin_n_theta = QSpinBox()
        self.spin_n_theta.setRange(1, 36)
        self.spin_n_theta.setValue(5)
        form_intercept.addRow(_("Angle Steps:"), self.spin_n_theta)

        self.chk_reskeletonize = QCheckBox(_("Re-skeletonize"))
        self.chk_reskeletonize.setChecked(True)
        form_intercept.addRow(self.chk_reskeletonize)

        self.chk_pad_for_rotation = QCheckBox(_("Pad for Rotation"))
        self.chk_pad_for_rotation.setChecked(True)
        form_intercept.addRow(self.chk_pad_for_rotation)

        layout.addWidget(grp_intercept)

        # --- Grain filter ---
        grp_grain = QGroupBox(_("Grain Filtering"))
        form_grain = QFormLayout(grp_grain)

        self.spin_min_grain_area = QSpinBox()
        self.spin_min_grain_area.setRange(1, 100000)
        self.spin_min_grain_area.setValue(50)
        form_grain.addRow(_("Min Area (px\u00b2):"), self.spin_min_grain_area)

        self.chk_exclude_edge = QCheckBox(_("Exclude Edge Grains"))
        self.chk_exclude_edge.setChecked(True)
        form_grain.addRow(self.chk_exclude_edge)

        self.spin_edge_buffer = QSpinBox()
        self.spin_edge_buffer.setRange(0, 100)
        self.spin_edge_buffer.setValue(5)
        form_grain.addRow(_("Edge Buffer (px):"), self.spin_edge_buffer)

        self.chk_exclude_edge.toggled.connect(self.spin_edge_buffer.setEnabled)

        layout.addWidget(grp_grain)

        layout.addStretch()

    # ------------------------------------------------------------------
    # ROI spinbox change → emit viewer update (via parent)
    # ------------------------------------------------------------------

    grain_roi_changed = pyqtSignal(object)    # tuple or None
    marker_roi_changed = pyqtSignal(object)

    def _on_grain_roi_spinbox_changed(self) -> None:
        if self._updating_roi:
            return
        roi = self._read_grain_roi()
        self.grain_roi_changed.emit(roi)

    def _on_marker_roi_spinbox_changed(self) -> None:
        if self._updating_roi:
            return
        roi = self._read_marker_roi()
        self.marker_roi_changed.emit(roi)

    def _read_grain_roi(self) -> tuple[int, int, int, int] | None:
        w, h = self.spin_grain_w.value(), self.spin_grain_h.value()
        if w == 0 or h == 0:
            return None
        return (self.spin_grain_x.value(), self.spin_grain_y.value(), w, h)

    def _read_marker_roi(self) -> tuple[int, int, int, int] | None:
        w, h = self.spin_marker_w.value(), self.spin_marker_h.value()
        if w == 0 or h == 0:
            return None
        return (self.spin_marker_x.value(), self.spin_marker_y.value(), w, h)

    def _clear_grain_roi(self) -> None:
        with self._silent_update():
            for sp in (self.spin_grain_x, self.spin_grain_y, self.spin_grain_w, self.spin_grain_h):
                sp.setValue(0)
        self.grain_roi_changed.emit(None)

    def _clear_marker_roi(self) -> None:
        with self._silent_update():
            for sp in (self.spin_marker_x, self.spin_marker_y, self.spin_marker_w, self.spin_marker_h):
                sp.setValue(0)
        self.marker_roi_changed.emit(None)

    # ------------------------------------------------------------------
    # Called when viewer selects a ROI
    # ------------------------------------------------------------------

    def set_grain_roi(self, x: int, y: int, w: int, h: int) -> None:
        with self._silent_update():
            self.spin_grain_x.setValue(x)
            self.spin_grain_y.setValue(y)
            self.spin_grain_w.setValue(w)
            self.spin_grain_h.setValue(h)

    def set_marker_roi(self, x: int, y: int, w: int, h: int) -> None:
        with self._silent_update():
            self.spin_marker_x.setValue(x)
            self.spin_marker_y.setValue(y)
            self.spin_marker_w.setValue(w)
            self.spin_marker_h.setValue(h)

    # ------------------------------------------------------------------
    # Params get / set
    # ------------------------------------------------------------------

    def get_calc_params(self) -> dict:
        ppu = self.spin_pixels_per_um.value()
        return {
            "pixels_per_um": ppu if ppu > 0.0 else None,
            "grain_roi": self._read_grain_roi(),
            "marker_roi": self._read_marker_roi(),
            "line_spacing": self.spin_line_spacing.value(),
            "row_scan_start": 0,
            "theta_start": self.spin_theta_start.value(),
            "theta_end": self.spin_theta_end.value(),
            "n_theta_steps": self.spin_n_theta.value(),
            "reskeletonize": self.chk_reskeletonize.isChecked(),
            "pad_for_rotation": self.chk_pad_for_rotation.isChecked(),
            "min_grain_area": self.spin_min_grain_area.value(),
            "exclude_edge_grains": self.chk_exclude_edge.isChecked(),
            "edge_buffer": self.spin_edge_buffer.value(),
        }

    def set_calc_params(self, data: dict) -> None:
        ppu = data.get("pixels_per_um")
        self.spin_pixels_per_um.setValue(ppu if ppu is not None else 0.0)

        grain_roi = data.get("grain_roi")
        if grain_roi and len(grain_roi) == 4:
            self.set_grain_roi(*grain_roi)
        else:
            self._clear_grain_roi()

        marker_roi = data.get("marker_roi")
        if marker_roi and len(marker_roi) == 4:
            self.set_marker_roi(*marker_roi)
        else:
            self._clear_marker_roi()

        self.spin_line_spacing.setValue(int(data.get("line_spacing", 60)))
        self.spin_theta_start.setValue(float(data.get("theta_start", 0.0)))
        self.spin_theta_end.setValue(float(data.get("theta_end", 180.0)))
        self.spin_n_theta.setValue(int(data.get("n_theta_steps", 5)))
        self.chk_reskeletonize.setChecked(bool(data.get("reskeletonize", True)))
        self.chk_pad_for_rotation.setChecked(bool(data.get("pad_for_rotation", True)))
        self.spin_min_grain_area.setValue(int(data.get("min_grain_area", 50)))
        self.chk_exclude_edge.setChecked(bool(data.get("exclude_edge_grains", True)))
        self.spin_edge_buffer.setValue(int(data.get("edge_buffer", 5)))

    def set_scale_from_detection(self, pixels_per_um: float, status_text: str) -> None:
        self.spin_pixels_per_um.setValue(pixels_per_um)
        self.lbl_scale_status.setText(status_text)

    def set_scale_status(self, text: str) -> None:
        self.lbl_scale_status.setText(text)


class _SaveExportTab(QWidget):
    """Tab 2: results display (export/save actions are in the menu)."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        grp_chord = QGroupBox(_("ASTM E112 Intercept"))
        chord_layout = QVBoxLayout(grp_chord)
        self.lbl_chord_stats = QLabel(_("(before analysis)"))
        self.lbl_chord_stats.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.lbl_chord_stats.setWordWrap(True)
        chord_layout.addWidget(self.lbl_chord_stats)
        layout.addWidget(grp_chord)

        grp_grain = QGroupBox(_("Grain Area Measurement"))
        grain_layout = QVBoxLayout(grp_grain)
        self.lbl_grain_stats = QLabel(_("(before analysis)"))
        self.lbl_grain_stats.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.lbl_grain_stats.setWordWrap(True)
        grain_layout.addWidget(self.lbl_grain_stats)
        layout.addWidget(grp_grain)

        layout.addStretch()

    def update_chord_stats(self, stats: dict) -> None:
        if not stats:
            self.lbl_chord_stats.setText(_("No chords detected."))
            return
        lines = [_("Chords: {count}").format(count=stats['count'])]
        mean_px = stats.get("mean_px")
        if mean_px is not None:
            lines.append(_("Mean length:  {val:.1f} px").format(val=mean_px))
        mean_um = stats.get("mean_um")
        if mean_um is not None:
            lines.append(_("         {val:.3f} \u00b5m").format(val=mean_um))
        std_px = stats.get("std_px")
        if std_px is not None:
            lines.append(_("Std dev: {val:.1f} px").format(val=std_px))
        astm_g = stats.get("astm_grain_size_g")
        if astm_g is not None:
            lines.append(_("\nASTM G: {g:.2f}").format(g=astm_g))
        self.lbl_chord_stats.setText("\n".join(lines))

    def update_grain_stats(self, stats: dict, pixels_per_um: float | None = None) -> None:
        if not stats:
            self.lbl_grain_stats.setText(_("No grains detected."))
            return
        lines = [_("Grains: {count}").format(count=stats['count'])]
        mean_area = stats.get("mean_area_px")
        if mean_area is not None:
            if pixels_per_um:
                lines.append(_("Mean area: {val:.3f} \u00b5m\u00b2").format(
                    val=mean_area / (pixels_per_um ** 2)
                ))
            else:
                lines.append(_("Mean area: {val:.0f} px\u00b2").format(val=mean_area))
        mean_diam = stats.get("mean_diam_px")
        if mean_diam is not None:
            if pixels_per_um:
                lines.append(_("Mean diam: {val:.3f} \u00b5m").format(
                    val=mean_diam / pixels_per_um
                ))
            else:
                lines.append(_("Mean diam: {val:.1f} px").format(val=mean_diam))
        self.lbl_grain_stats.setText("\n".join(lines))

    def reset(self) -> None:
        self.lbl_chord_stats.setText(_("(before analysis)"))
        self.lbl_grain_stats.setText(_("(before analysis)"))


# ---------------------------------------------------------------------------
# Main settings dialog
# ---------------------------------------------------------------------------

class SettingsDialog(QMainWindow):
    """Primary application window. Closing it quits the app."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(
            _("Grain Size Measurement v{version}").format(version=_read_version())
        )
        self.setMinimumWidth(380)

        self._analyzer = GrainAnalyzer()
        self._process_thread: QThread | None = None
        self._process_worker: _ImageProcessWorker | None = None
        self._calc_thread: QThread | None = None
        self._calc_worker: _GrainCalcWorker | None = None
        self._scale_thread: QThread | None = None
        self._scale_worker: _ScaleDetectionWorker | None = None

        self._image_loaded = False
        self._image_processed = False
        self._calc_done = False
        self._image_stem: str = ""
        self._original_rgb: np.ndarray | None = None
        self._processed_binary_rgb: np.ndarray | None = None
        self._scale_bar_result = None
        self._last_scale_bar_value: float = 50.0
        self._last_scale_bar_unit: str = "\u00b5m"
        self._auto_run_grain_calc: bool = False
        self._last_dir: str = ""
        self._process_dlg: _CalcProgressDialog | None = None
        self._calc_dlg: _CalcProgressDialog | None = None
        self._optimizer_proc: QProcess | None = None
        self._optimizer_out_path: Path | None = None
        self._optimizer_progress_dlg: _OptimizerProgressDialog | None = None
        self._optimizer_cancelled: bool = False
        self._optimizer_line_buffer: str = ""
        self._optimizer_phase2_configured: bool = False
        self._optimizer_kill_timer: QTimer | None = None

        self._build_viewer()
        self._build_menu()
        self._build_tabs()
        self._build_status_bar()

        self._update_button_states()

    def _build_viewer(self) -> None:
        self._viewer = ViewerWindow()
        # Do NOT show here — position_and_show() will move then show both windows

        self._viewer.grain_roi_selected.connect(self._on_viewer_grain_roi)
        self._viewer.marker_roi_selected.connect(self._on_viewer_marker_roi)

    def position_and_show(self) -> None:
        """Position both windows before showing them.

        Mutter ignores move() calls after a window is already mapped.
        Moving before show() is the only reliable way to set initial position.
        """
        avail = QApplication.primaryScreen().availableGeometry()
        self.move(avail.left(), avail.top())
        # Resize to show all controls without scrolling; clamp to available height
        target_h = min(950, avail.height())
        self.resize(self.minimumWidth(), target_h)
        # Frame width ≈ minimumWidth + WM decoration (~28 px observed)
        viewer_x = avail.left() + self.minimumWidth() + 28 + 10
        self._viewer.move(viewer_x, avail.top())
        self.show()
        self._viewer.show()

    def _build_menu(self) -> None:
        menu_bar = self.menuBar()

        file_menu = menu_bar.addMenu(_("File"))
        act_open = file_menu.addAction(_("Open Image..."))
        act_open.setShortcut("Ctrl+O")
        act_open.triggered.connect(self._open_image)
        act_open_params = file_menu.addAction(_("Open Parameters..."))
        act_open_params.setShortcut("Ctrl+P")
        act_open_params.triggered.connect(self._open_params)
        act_save_params = file_menu.addAction(_("Save Parameters..."))
        act_save_params.setShortcut("Ctrl+Shift+S")
        act_save_params.triggered.connect(self._save_params)
        file_menu.addSeparator()
        self._act_optimize = file_menu.addAction(_("Run Parameter Optimization..."))
        self._act_optimize.triggered.connect(self._run_optimizer)
        file_menu.addSeparator()
        act_quit = file_menu.addAction(_("Quit"))
        act_quit.setShortcut("Ctrl+Q")
        act_quit.triggered.connect(self.close)

        proc_menu = menu_bar.addMenu(_("Processing"))
        self._act_image_process = proc_menu.addAction(_("Image Processing"))
        self._act_image_process.setShortcut("F5")
        self._act_image_process.triggered.connect(self._image_process)
        self._act_grain_calc = proc_menu.addAction(_("Grain Calculation"))
        self._act_grain_calc.setShortcut("F6")
        self._act_grain_calc.triggered.connect(self._grain_calc)
        proc_menu.addSeparator()
        self._act_save_image = proc_menu.addAction(_("Save Image..."))
        self._act_save_image.triggered.connect(self._save_image)
        self._act_export_chord_csv = proc_menu.addAction(_("Chord Length CSV Export..."))
        self._act_export_chord_csv.triggered.connect(self._export_chord_csv)
        self._act_export_grain_csv = proc_menu.addAction(_("Grain Area CSV Export..."))
        self._act_export_grain_csv.triggered.connect(self._export_grain_csv)
        self._act_export_result_csv = proc_menu.addAction(_("Result Summary CSV Export..."))
        self._act_export_result_csv.triggered.connect(self._export_result_csv)

    def _build_tabs(self) -> None:
        self._tab_widget = QTabWidget()
        self.setCentralWidget(self._tab_widget)

        self._tab_process = _ImageProcessTab()
        self._tab_calc = _GrainCalcTab()
        self._tab_save = _SaveExportTab()

        self._tab_widget.addTab(self._tab_process, _("Image Processing"))
        self._tab_widget.addTab(self._tab_calc, _("Grain Calculation"))
        self._tab_widget.addTab(self._tab_save, _("Results"))

        # Connect tab signals
        self._tab_calc.auto_detect_requested.connect(self._run_scale_detection)
        self._tab_calc.select_grain_roi_requested.connect(
            lambda: self._viewer.set_grain_roi_mode(True)
        )
        self._tab_calc.select_marker_roi_requested.connect(
            lambda: self._viewer.set_marker_roi_mode(True)
        )
        self._tab_calc.grain_roi_changed.connect(self._on_grain_roi_spinbox_changed)
        self._tab_calc.marker_roi_changed.connect(self._on_marker_roi_spinbox_changed)

    def _build_status_bar(self) -> None:
        self._lbl_status_image = QLabel(_("Image: none"))
        self._lbl_status_grains = QLabel(_("Grains: --"))
        status_bar = QStatusBar()
        status_bar.addWidget(self._lbl_status_image)
        status_bar.addWidget(QLabel("|"))
        status_bar.addWidget(self._lbl_status_grains)
        self.setStatusBar(status_bar)

    # ------------------------------------------------------------------
    # State management
    # ------------------------------------------------------------------

    def _update_button_states(self) -> None:
        self._act_optimize.setEnabled(self._image_loaded and self._optimizer_proc is None)
        self._act_image_process.setEnabled(self._image_loaded)

        self._tab_calc.btn_auto_detect.setEnabled(self._image_loaded)
        self._tab_calc.btn_select_grain_roi.setEnabled(self._image_loaded)
        self._tab_calc.btn_select_marker_roi.setEnabled(self._image_loaded)
        self._act_grain_calc.setEnabled(self._image_processed)

        self._act_save_image.setEnabled(self._calc_done)
        self._act_export_chord_csv.setEnabled(self._calc_done)
        self._act_export_grain_csv.setEnabled(self._calc_done)
        self._act_export_result_csv.setEnabled(self._calc_done)

    # ------------------------------------------------------------------
    # File actions
    # ------------------------------------------------------------------

    def _open_image(self) -> None:
        path, _filter = QFileDialog.getOpenFileName(
            self, _("Open Image"), self._last_dir,
            _("Image files (*.png *.jpg *.jpeg *.bmp *.tif *.tiff *.webp);;All files (*)"),
        )
        if not path:
            return
        self._last_dir = str(Path(path).parent)
        self._load_image_path(path)

    def _load_image_path(self, path: str) -> None:
        try:
            self._analyzer.load_image(path)
        except ValueError as exc:
            QMessageBox.critical(self, _("Error"), str(exc))
            return

        original_rgb = cv2.cvtColor(self._analyzer.original_image, cv2.COLOR_BGR2RGB)
        self._original_rgb = original_rgb
        self._processed_binary_rgb = None
        self._scale_bar_result = None
        self._image_stem = Path(path).stem
        self._viewer.show_original(original_rgb)
        self._viewer.clear_processed()
        self._tab_save.reset()

        self._image_loaded = True
        self._image_processed = False
        self._calc_done = False
        self._update_button_states()

        h, w = self._analyzer.gray_image.shape
        self._tab_process.suggest_clahe_tile(h, w)
        self._lbl_status_image.setText(
            _("Image: {name}  ({w}\u00d7{h} px)").format(name=Path(path).name, w=w, h=h)
        )
        self._lbl_status_grains.setText(_("Grains: --"))
        self.statusBar().showMessage(_("Image loaded."), 3000)

    def _open_params(self) -> None:
        path, _filter = QFileDialog.getOpenFileName(
            self, _("Open Parameters"), self._last_dir,
            _("JSON files (*.json);;All files (*)")
        )
        if not path:
            return
        self._last_dir = str(Path(path).parent)
        self._load_params_from_path(path)

    def _load_params_from_path(self, path: str) -> None:
        """Load a params JSON, restore UI state, and auto-run processing if image is available."""
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except Exception as exc:
            QMessageBox.critical(self, _("Error"), _("JSON load failed:\n{exc}").format(exc=exc))
            return

        self._tab_process.set_processing_params(data)
        self._tab_calc.set_calc_params(data)

        # Restore ROI overlays
        grain_roi = data.get("grain_roi")
        marker_roi = data.get("marker_roi")
        self._viewer.set_grain_roi(tuple(grain_roi) if grain_roi else None)  # type: ignore[arg-type]
        self._viewer.set_marker_roi(tuple(marker_roi) if marker_roi else None)  # type: ignore[arg-type]

        # Extract scale bar coords BEFORE _load_image_path() clears _scale_bar_result
        saved_x1 = data.get("scale_bar_x1")
        saved_x2 = data.get("scale_bar_x2")
        saved_y  = data.get("scale_bar_y")

        image_path_str = data.get("image_path")
        if image_path_str:
            try:
                resolved = resolve_image_path(image_path_str, Path(path))
                self._load_image_path(str(resolved))
            except Exception as exc:
                QMessageBox.warning(self, _("Image Load Failed"), f"{image_path_str}\n\n{exc}")

        # Restore scale bar result AFTER image load (which clears _scale_bar_result)
        if saved_x1 is not None and saved_x2 is not None and saved_y is not None:
            from scale_detector import ScaleBarResult  # noqa: PLC0415
            x_off, y_off = (marker_roi[0], marker_roi[1]) if marker_roi else (0, 0)
            self._scale_bar_result = ScaleBarResult(
                bar_x1=int(saved_x1) - x_off,
                bar_x2=int(saved_x2) - x_off,
                bar_y=int(saved_y) - y_off,
                bar_length_px=int(saved_x2) - int(saved_x1),
                strip_start_row=0,
                physical_value=None,
                unit=None,
                pixels_per_um=None,
                ocr_text_raw=None,
                confidence="bar_only",
            )
            self._refresh_original_with_scale_bar()
            self._refresh_processed_with_scale_bar()
            self._viewer.set_marker_roi(None)  # Clear overlay so scale bar line is visible

        self.statusBar().showMessage(
            _("Parameters loaded: {name}").format(name=Path(path).name), 3000
        )

        # Auto-run image processing → grain calculation
        if self._image_loaded:
            self._auto_run_grain_calc = True
            self._image_process()

    def _collect_params_dict(self, json_save_path: Path | None = None) -> dict:
        """Build the params dict that represents current UI state (for save/optimizer).

        When *json_save_path* is provided the image path is stored as a
        Unix-style (POSIX) relative path from that file's directory.
        Otherwise it falls back to an absolute POSIX string.
        """
        from path_utils import APP_NAME
        proc = self._tab_process.get_processing_params()
        calc = self._tab_calc.get_calc_params()
        data = {**proc, **calc}
        data["app_name"] = APP_NAME
        data["app_version"] = _read_version()
        img = self._analyzer.image_path
        if img is None:
            data["image_path"] = None
        elif json_save_path is not None:
            data["image_path"] = make_relative_posix_str(img, json_save_path)
        else:
            data["image_path"] = img.as_posix()
        if self._scale_bar_result is not None:
            r = self._scale_bar_result
            marker_roi = self._tab_calc._read_marker_roi()
            x_off, y_off = (marker_roi[0], marker_roi[1]) if marker_roi else (0, 0)
            data["scale_bar_x1"] = r.bar_x1 + x_off
            data["scale_bar_x2"] = r.bar_x2 + x_off
            data["scale_bar_y"] = r.bar_y + y_off
        else:
            data["scale_bar_x1"] = None
            data["scale_bar_x2"] = None
            data["scale_bar_y"] = None
        return data

    def _save_params(self) -> None:
        default_name = f"{self._image_stem}_params.json" if self._image_stem else "params.json"
        initial = str(Path(self._last_dir) / default_name) if self._last_dir else default_name
        path, _filter = QFileDialog.getSaveFileName(
            self, _("Save Parameters"), initial,
            _("JSON files (*.json);;All files (*)")
        )
        if not path:
            return
        self._last_dir = str(Path(path).parent)
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self._collect_params_dict(json_save_path=Path(path)), f, indent=2, ensure_ascii=False)
            self.statusBar().showMessage(
                _("Parameters saved: {name}").format(name=Path(path).name), 3000
            )
        except Exception as exc:
            QMessageBox.critical(self, _("Error"), _("Save failed:\n{exc}").format(exc=exc))

    # ------------------------------------------------------------------
    # Parameter optimizer
    # ------------------------------------------------------------------

    def _run_optimizer(self) -> None:
        if not self._image_loaded:
            return
        if self._optimizer_proc is not None:
            return  # already running

        grain_roi = self._tab_calc._read_grain_roi()
        if not grain_roi:
            QMessageBox.warning(
                self, _("Optimization"),
                _("Please set the Grain ROI before running optimization.")
            )
            return

        image_path = self._analyzer.image_path
        if image_path is None:
            QMessageBox.warning(self, _("Optimization"), _("Image path is unknown."))
            return

        image_dir = Path(image_path).parent
        input_path  = image_dir / f"{self._image_stem}_params.json"
        output_path = image_dir / f"{self._image_stem}_params_optimized.json"

        try:
            with open(input_path, "w", encoding="utf-8") as f:
                json.dump(self._collect_params_dict(json_save_path=input_path), f, indent=2, ensure_ascii=False)
        except Exception as exc:
            QMessageBox.critical(self, _("Error"), _("Parameter save failed:\n{exc}").format(exc=exc))
            return

        script_path = Path(__file__).resolve().parent.parent.parent / "scripts" / "optimize_params.py"
        repo_root   = script_path.parent.parent

        self._optimizer_out_path = output_path
        self._optimizer_cancelled = False
        self._optimizer_line_buffer = ""
        self._optimizer_phase2_configured = False

        self._optimizer_proc = QProcess(self)
        self._optimizer_proc.setWorkingDirectory(str(repo_root))
        self._optimizer_proc.finished.connect(self._on_optimizer_finished)
        self._optimizer_proc.readyReadStandardOutput.connect(self._on_optimizer_stdout)
        self._optimizer_proc.readyReadStandardError.connect(self._on_optimizer_stderr)
        self._optimizer_proc.start("uv", [
            "run", str(script_path),
            "--params", str(input_path),
            "--out",    str(output_path),
        ])
        self._act_optimize.setEnabled(False)
        self.statusBar().showMessage(_("Optimizing... (this may take a while)"))

        self._optimizer_progress_dlg = _OptimizerProgressDialog(self)
        self._optimizer_progress_dlg.cancel_requested.connect(self._on_optimizer_cancel)
        self._optimizer_progress_dlg.show()

    def _on_optimizer_stdout(self) -> None:
        if self._optimizer_proc is None:
            return
        raw = self._optimizer_proc.readAllStandardOutput()
        text = bytes(raw).decode("utf-8", errors="replace")
        self._optimizer_line_buffer += text
        while "\n" in self._optimizer_line_buffer:
            line, self._optimizer_line_buffer = self._optimizer_line_buffer.split("\n", 1)
            self._parse_optimizer_line(line.rstrip("\r"))

    def _on_optimizer_stderr(self) -> None:
        if self._optimizer_proc is None:
            return
        raw = self._optimizer_proc.readAllStandardError()
        text = bytes(raw).decode("utf-8", errors="replace").strip()
        if text:
            self.statusBar().showMessage(
                _("Optimization error: {msg}").format(msg=text[:120]), 8000
            )

    def _parse_optimizer_line(self, line: str) -> None:
        dlg = self._optimizer_progress_dlg
        if dlg is None:
            return
        if line.startswith("##PHASE:1:"):
            parts = line.split(":")
            if len(parts) == 4:
                try:
                    dlg.set_phase1_progress(int(parts[2]), int(parts[3]))
                except ValueError:
                    pass
        elif line.startswith("##PHASE:2:"):
            parts = line.split(":")
            if len(parts) == 4:
                try:
                    n, total = int(parts[2]), int(parts[3])
                    if not self._optimizer_phase2_configured:
                        dlg.set_phase2_start(total)
                        self._optimizer_phase2_configured = True
                    dlg.set_phase2_progress(n, total)
                except ValueError:
                    pass
        elif line.startswith("##BEST:"):
            try:
                dlg.set_best_score(float(line[7:]))
            except ValueError:
                pass
        elif line == "##DONE":
            dlg.mark_done()
            self._optimizer_progress_dlg = None

    def _on_optimizer_cancel(self) -> None:
        if self._optimizer_proc is None:
            if self._optimizer_progress_dlg is not None:
                self._optimizer_progress_dlg.accept()
                self._optimizer_progress_dlg = None
            return
        self._optimizer_cancelled = True
        self._optimizer_proc.terminate()
        self._optimizer_kill_timer = QTimer(self)
        self._optimizer_kill_timer.setSingleShot(True)
        self._optimizer_kill_timer.timeout.connect(self._force_kill_optimizer)
        self._optimizer_kill_timer.start(3000)

    def _force_kill_optimizer(self) -> None:
        if self._optimizer_proc is not None:
            self._optimizer_proc.kill()

    def _on_optimizer_finished(self, exit_code: int, exit_status) -> None:
        if self._optimizer_kill_timer is not None:
            self._optimizer_kill_timer.stop()
            self._optimizer_kill_timer = None

        if self._optimizer_progress_dlg is not None:
            self._optimizer_progress_dlg.accept()
            self._optimizer_progress_dlg = None

        self._optimizer_proc = None
        self._act_optimize.setEnabled(self._image_loaded)

        if self._optimizer_cancelled:
            self._optimizer_cancelled = False
            self.statusBar().showMessage(_("Optimization cancelled."), 3000)
            return

        if exit_code != 0:
            QMessageBox.critical(
                self, _("Optimization Error"),
                _("Optimization script failed with exit code {code}.").format(code=exit_code)
            )
            self.statusBar().showMessage(_("Optimization failed."), 5000)
            return

        if self._optimizer_out_path and self._optimizer_out_path.exists():
            self.statusBar().showMessage(_("Optimization complete. Starting processing."), 3000)
            self._load_params_from_path(str(self._optimizer_out_path))
        else:
            QMessageBox.warning(self, _("Optimization"), _("Output file not found."))
            self.statusBar().showMessage(_("Optimization complete (no output)."), 5000)

    # ------------------------------------------------------------------
    # Processing actions
    # ------------------------------------------------------------------

    def _build_params(self) -> AnalysisParams:
        proc = self._tab_process.get_processing_params()
        calc = self._tab_calc.get_calc_params()
        merged = {**proc, **calc}
        # Build AnalysisParams from merged dict; use field names matching dataclass
        fields = {f.name for f in dataclasses.fields(AnalysisParams)}
        kwargs = {k: v for k, v in merged.items() if k in fields}
        return AnalysisParams(**kwargs)

    def _image_process(self) -> None:
        if not self._image_loaded:
            return
        if self._process_thread is not None and self._process_thread.isRunning():
            return

        params = self._build_params()
        self.statusBar().showMessage(_("Processing image..."))

        self._process_thread = QThread()
        self._process_worker = _ImageProcessWorker(self._analyzer, params)
        self._process_worker.moveToThread(self._process_thread)

        self._process_dlg = _CalcProgressDialog(_("Image Processing"), self)
        self._process_dlg.cancel_requested.connect(self._cancel_image_process)
        self._process_worker.progress.connect(self._process_dlg.update_progress)

        self._process_thread.started.connect(self._process_worker.run)
        self._process_worker.finished.connect(self._on_image_process_done)
        self._process_worker.cancelled.connect(self._on_image_process_cancelled)
        self._process_worker.error.connect(self._on_image_process_error)
        self._process_worker.finished.connect(self._process_thread.quit)
        self._process_worker.cancelled.connect(self._process_thread.quit)
        self._process_worker.error.connect(self._process_thread.quit)
        self._process_thread.finished.connect(self._process_thread.deleteLater)
        self._process_thread.finished.connect(self._on_process_thread_finished)

        self._process_dlg.show()
        self._process_thread.start()

    def _cancel_image_process(self) -> None:
        if self._process_worker is not None:
            self._process_worker.cancel()

    def _on_process_thread_finished(self) -> None:
        self._process_thread = None
        self._process_worker = None

    def _on_image_process_done(self, binary_rgb: np.ndarray) -> None:
        if self._process_dlg is not None:
            self._process_dlg.mark_done()
            self._process_dlg = None

        self._processed_binary_rgb = binary_rgb
        self._refresh_original_with_scale_bar()
        self._refresh_processed_with_scale_bar()

        self._image_processed = True
        self._calc_done = False
        self._update_button_states()
        self.statusBar().showMessage(_("Image processing complete."), 3000)

        if self._auto_run_grain_calc:
            self._auto_run_grain_calc = False
            self._grain_calc()

    def _on_image_process_cancelled(self) -> None:
        if self._process_dlg is not None:
            self._process_dlg.mark_done()
            self._process_dlg = None
        self.statusBar().showMessage(_("Image processing cancelled."), 4000)
        self._update_button_states()

    def _on_image_process_error(self, message: str) -> None:
        if self._process_dlg is not None:
            self._process_dlg.mark_done()
            self._process_dlg = None
        QMessageBox.critical(self, _("Image Processing Error"), message)
        self.statusBar().showMessage(_("An error occurred during image processing."), 5000)
        self._update_button_states()

    def _grain_calc(self) -> None:
        if not self._image_processed:
            return
        if self._calc_thread is not None and self._calc_thread.isRunning():
            return

        params = self._build_params()
        self.statusBar().showMessage(_("Calculating grains..."))

        self._calc_thread = QThread()
        self._calc_worker = _GrainCalcWorker(self._analyzer, params)
        self._calc_worker.moveToThread(self._calc_thread)

        self._calc_dlg = _CalcProgressDialog(_("Grain Calculation"), self)
        self._calc_dlg.cancel_requested.connect(self._cancel_grain_calc)
        self._calc_worker.progress.connect(self._calc_dlg.update_progress)

        self._calc_thread.started.connect(self._calc_worker.run)
        self._calc_worker.finished.connect(self._on_grain_calc_done)
        self._calc_worker.cancelled.connect(self._on_grain_calc_cancelled)
        self._calc_worker.error.connect(self._on_grain_calc_error)
        self._calc_worker.finished.connect(self._calc_thread.quit)
        self._calc_worker.cancelled.connect(self._calc_thread.quit)
        self._calc_worker.error.connect(self._calc_thread.quit)
        self._calc_thread.finished.connect(self._calc_thread.deleteLater)
        self._calc_thread.finished.connect(self._on_calc_thread_finished)

        self._calc_dlg.show()
        self._calc_thread.start()

    def _cancel_grain_calc(self) -> None:
        if self._calc_worker is not None:
            self._calc_worker.cancel()

    def _on_calc_thread_finished(self) -> None:
        self._calc_thread = None
        self._calc_worker = None

    def _on_grain_calc_done(self, chord_df, grain_df, overlay: np.ndarray) -> None:
        if self._calc_dlg is not None:
            self._calc_dlg.mark_done()
            self._calc_dlg = None

        self._viewer.show_overlay(overlay)

        ppu = self._tab_calc.spin_pixels_per_um.value()
        ppu = ppu if ppu > 0 else None
        chord_stats = self._analyzer.get_chord_statistics()
        grain_stats = self._analyzer.get_grain_statistics()
        self._tab_save.update_chord_stats(chord_stats)
        self._tab_save.update_grain_stats(grain_stats, pixels_per_um=ppu)

        self._calc_done = True
        self._update_button_states()

        chord_count = chord_stats.get("count", 0)
        grain_count = grain_stats.get("count", 0)
        self._lbl_status_grains.setText(
            _("Chords: {chords}  Grains: {grains}").format(
                chords=chord_count, grains=grain_count
            )
        )
        self.statusBar().showMessage(_("Grain calculation complete."), 5000)
        self._tab_widget.setCurrentIndex(2)  # switch to save/export tab

    def _on_grain_calc_cancelled(self) -> None:
        if self._calc_dlg is not None:
            self._calc_dlg.mark_done()
            self._calc_dlg = None
        self.statusBar().showMessage(_("Grain calculation cancelled."), 4000)
        self._update_button_states()

    def _on_grain_calc_error(self, message: str) -> None:
        if self._calc_dlg is not None:
            self._calc_dlg.mark_done()
            self._calc_dlg = None
        QMessageBox.critical(self, _("Grain Calculation Error"), message)
        self.statusBar().showMessage(_("An error occurred during grain calculation."), 5000)
        self._update_button_states()

    # ------------------------------------------------------------------
    # Scale detection
    # ------------------------------------------------------------------

    def _run_scale_detection(self) -> None:
        if self._scale_thread is not None and self._scale_thread.isRunning():
            return
        marker_roi = self._tab_calc._read_marker_roi()
        self._tab_calc.btn_auto_detect.setEnabled(False)
        self._tab_calc.set_scale_status(_("Detecting..."))
        self.statusBar().showMessage(_("Detecting scale bar..."))

        self._scale_thread = QThread()
        self._scale_worker = _ScaleDetectionWorker(self._analyzer.original_image, marker_roi)
        self._scale_worker.moveToThread(self._scale_thread)

        self._scale_thread.started.connect(self._scale_worker.run)
        self._scale_worker.finished.connect(self._on_scale_done)
        self._scale_worker.error.connect(self._on_scale_error)
        self._scale_worker.finished.connect(self._scale_thread.quit)
        self._scale_worker.error.connect(self._scale_thread.quit)
        self._scale_thread.finished.connect(self._scale_thread.deleteLater)
        self._scale_thread.finished.connect(self._on_scale_thread_finished)

        self._scale_thread.start()

    def _on_scale_thread_finished(self) -> None:
        self._scale_thread = None
        self._scale_worker = None

    def _scale_bar_draw_coords(self) -> tuple[int, int, int, int] | None:
        """Return (x1, x2, y, strip_start) in full-image coords, or None if no result."""
        if self._scale_bar_result is None:
            return None
        r = self._scale_bar_result
        x_off, y_off = 0, 0
        marker_roi = self._tab_calc._read_marker_roi()
        if marker_roi:
            x_off, y_off = marker_roi[0], marker_roi[1]
        x1 = r.bar_x1 + x_off
        x2 = r.bar_x2 + x_off
        y  = r.bar_y  + y_off
        if marker_roi:
            strip_start = y_off
        elif r.strip_start_row > 0:
            strip_start = r.strip_start_row
        else:
            strip_start = max(0, y - 5)
        return x1, x2, y, strip_start

    def _apply_scale_bar_to_image(self, img: np.ndarray) -> np.ndarray:
        """Blank the scale bar strip and draw the red line onto img (in-place copy)."""
        coords = self._scale_bar_draw_coords()
        if coords is None:
            return img
        x1, x2, y, strip_start = coords
        img = img.copy()
        img[strip_start:, :] = 0
        cv2.line(img, (x1, y), (x2, y), (255, 0, 0), 3)
        cv2.line(img, (x1, y - 4), (x2, y - 4), (255, 0, 0), 3)
        return img

    def _refresh_original_with_scale_bar(self) -> None:
        """Refresh original tab with the truly unmodified image."""
        if self._original_rgb is None:
            return
        self._viewer.show_original(self._original_rgb)

    def _refresh_processed_with_scale_bar(self) -> None:
        """Show processed binary with scale bar strip blanked + red line."""
        if self._processed_binary_rgb is None:
            return
        img = self._apply_scale_bar_to_image(self._processed_binary_rgb)
        self._viewer.show_processed(img)

    def _on_scale_done(self, result) -> None:
        self._tab_calc.btn_auto_detect.setEnabled(True)
        if result.pixels_per_um is not None:
            unit_str = result.unit or "\u00b5m"
            status = (
                _("Detected: {px}px = {val}{unit} \u2192 {ppu:.3f} px/\u00b5m").format(
                    px=result.bar_length_px,
                    val=result.physical_value,
                    unit=unit_str,
                    ppu=result.pixels_per_um,
                )
            )
            self._tab_calc.set_scale_from_detection(result.pixels_per_um, status)
            self._scale_bar_result = result
            self._refresh_original_with_scale_bar()
            self._refresh_processed_with_scale_bar()
            self._viewer.set_marker_roi(None)  # Clear overlay so scale bar line is visible
            self.statusBar().showMessage(
                _("Scale auto-detected: {ppu:.3f} px/\u00b5m").format(ppu=result.pixels_per_um),
                5000
            )
        else:
            self._prompt_physical_dimension(result)

    def _on_scale_error(self, message: str) -> None:
        self._tab_calc.btn_auto_detect.setEnabled(True)
        self._tab_calc.set_scale_status(_("Detection failed: {msg}").format(msg=message))
        self.statusBar().showMessage(_("Scale bar detection failed."), 5000)

    def _prompt_physical_dimension(self, result) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle(_("Enter Physical Dimension"))
        form = QFormLayout()
        spin_value = QDoubleSpinBox()
        spin_value.setRange(0.001, 100000.0)
        spin_value.setDecimals(3)
        spin_value.setValue(self._last_scale_bar_value)
        combo_unit = QComboBox()
        combo_unit.addItems(["\u00b5m", "nm", "mm"])
        idx = combo_unit.findText(self._last_scale_bar_unit)
        if idx >= 0:
            combo_unit.setCurrentIndex(idx)
        form.addRow(
            _("Bar length: {px} px  Physical value:").format(px=result.bar_length_px),
            spin_value
        )
        form.addRow(_("Unit:"), combo_unit)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        vbox = QVBoxLayout(dialog)
        vbox.addLayout(form)
        vbox.addWidget(buttons)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            from scale_detector import compute_pixels_per_um_from_bar  # noqa: PLC0415
            unit = combo_unit.currentText()
            self._last_scale_bar_value = spin_value.value()
            self._last_scale_bar_unit = unit
            ppu = compute_pixels_per_um_from_bar(result.bar_length_px, spin_value.value(), unit)
            status = (
                _("Set: {px}px = {val}{unit} \u2192 {ppu:.3f} px/\u00b5m").format(
                    px=result.bar_length_px,
                    val=spin_value.value(),
                    unit=unit,
                    ppu=ppu,
                )
            )
            self._tab_calc.set_scale_from_detection(ppu, status)
            self._scale_bar_result = result
            self._refresh_original_with_scale_bar()
            self._refresh_processed_with_scale_bar()
            self._viewer.set_marker_roi(None)  # Clear overlay so scale bar line is visible
            self.statusBar().showMessage(
                _("Scale set: {ppu:.3f} px/\u00b5m").format(ppu=ppu), 5000
            )
        else:
            self._tab_calc.set_scale_status(_("Cancelled"))

    # ------------------------------------------------------------------
    # Export / save actions
    # ------------------------------------------------------------------

    def _save_image(self) -> None:
        default_name = f"{self._image_stem}_overlay.png" if self._image_stem else "grain_overlay.png"
        initial = str(Path(self._last_dir) / default_name) if self._last_dir else default_name
        path, _filter = QFileDialog.getSaveFileName(
            self, _("Save Image"), initial,
            _("PNG files (*.png);;JPEG files (*.jpg);;All files (*)"),
        )
        if not path:
            return
        self._last_dir = str(Path(path).parent)
        try:
            self._analyzer.save_labeled_image(path)
            self.statusBar().showMessage(_("Image saved: {path}").format(path=path), 5000)
        except Exception as exc:
            QMessageBox.critical(self, _("Error"), str(exc))

    def _export_chord_csv(self) -> None:
        default_name = f"{self._image_stem}_chord.csv" if self._image_stem else "chord_lengths.csv"
        initial = str(Path(self._last_dir) / default_name) if self._last_dir else default_name
        path, _filter = QFileDialog.getSaveFileName(
            self, _("Save Chord Length CSV"), initial,
            _("CSV files (*.csv);;All files (*)"),
        )
        if not path:
            return
        self._last_dir = str(Path(path).parent)
        try:
            self._analyzer.save_chord_csv(path)
            self.statusBar().showMessage(_("Chord length CSV saved: {path}").format(path=path), 5000)
        except Exception as exc:
            QMessageBox.critical(self, _("Error"), str(exc))

    def _export_grain_csv(self) -> None:
        default_name = f"{self._image_stem}_grain.csv" if self._image_stem else "grain_areas.csv"
        initial = str(Path(self._last_dir) / default_name) if self._last_dir else default_name
        path, _filter = QFileDialog.getSaveFileName(
            self, _("Save Grain Area CSV"), initial,
            _("CSV files (*.csv);;All files (*)"),
        )
        if not path:
            return
        self._last_dir = str(Path(path).parent)
        try:
            self._analyzer.save_grain_csv(path)
            self.statusBar().showMessage(_("Grain area CSV saved: {path}").format(path=path), 5000)
        except Exception as exc:
            QMessageBox.critical(self, _("Error"), str(exc))

    def _export_result_csv(self) -> None:
        default_name = f"{self._image_stem}_result.csv" if self._image_stem else "result.csv"
        initial = str(Path(self._last_dir) / default_name) if self._last_dir else default_name
        path, _filter = QFileDialog.getSaveFileName(
            self, _("Save Result Summary CSV"), initial,
            _("CSV files (*.csv);;All files (*)"),
        )
        if not path:
            return
        self._last_dir = str(Path(path).parent)
        try:
            self._analyzer.save_result_csv(path)
            self.statusBar().showMessage(_("Result summary CSV saved: {path}").format(path=path), 5000)
        except Exception as exc:
            QMessageBox.critical(self, _("Error"), str(exc))

    # ------------------------------------------------------------------
    # ROI sync: viewer → spinboxes
    # ------------------------------------------------------------------

    def _on_viewer_grain_roi(self, x: int, y: int, w: int, h: int) -> None:
        self._tab_calc.set_grain_roi(x, y, w, h)
        self._viewer.set_grain_roi((x, y, w, h))

    def _on_viewer_marker_roi(self, x: int, y: int, w: int, h: int) -> None:
        self._tab_calc.set_marker_roi(x, y, w, h)
        self._viewer.set_marker_roi((x, y, w, h))

    # ROI sync: spinboxes → viewer
    def _on_grain_roi_spinbox_changed(self, roi) -> None:
        self._viewer.set_grain_roi(roi)

    def _on_marker_roi_spinbox_changed(self, roi) -> None:
        self._viewer.set_marker_roi(roi)

    # ------------------------------------------------------------------
    # Close event — closes viewer too
    # ------------------------------------------------------------------

    def closeEvent(self, event) -> None:
        self._viewer.deleteLater()
        super().closeEvent(event)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        # Position viewer to the right of the dialog after it is shown
        geo = self.frameGeometry()
        self._viewer.move(geo.right() + 10, geo.top())
        self._viewer.show()
