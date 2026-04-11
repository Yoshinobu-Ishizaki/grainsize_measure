from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import cv2
import numpy as np

from PyQt6.QtCore import QObject, QThread, Qt, pyqtSignal
from PyQt6.QtWidgets import (
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
    QPushButton,
    QScrollArea,
    QSpinBox,
    QStatusBar,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from analyzer import AnalysisParams, GrainAnalyzer
from gui.viewer_window import ViewerWindow


# ---------------------------------------------------------------------------
# Background workers
# ---------------------------------------------------------------------------

class _ImageProcessWorker(QObject):
    finished = pyqtSignal(object)   # binary ndarray
    error = pyqtSignal(str)

    def __init__(self, analyzer: GrainAnalyzer, params: AnalysisParams) -> None:
        super().__init__()
        self._analyzer = analyzer
        self._params = params

    def run(self) -> None:
        try:
            binary = self._analyzer.run_segmentation(self._params)
            self.finished.emit(binary)
        except Exception as exc:
            self.error.emit(str(exc))


class _GrainCalcWorker(QObject):
    finished = pyqtSignal(object, object, object)  # chord_df, grain_df, overlay ndarray
    error = pyqtSignal(str)

    def __init__(self, analyzer: GrainAnalyzer, params: AnalysisParams) -> None:
        super().__init__()
        self._analyzer = analyzer
        self._params = params

    def run(self) -> None:
        try:
            chord_df, grain_df = self._analyzer.run_measurement(self._params)
            overlay = self._analyzer.render_overlay_image()
            self.finished.emit(chord_df, grain_df, overlay)
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


# ---------------------------------------------------------------------------
# Tab widgets
# ---------------------------------------------------------------------------

class _ImageProcessTab(QWidget):
    """Tab 0: image processing parameters."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
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

        # --- Segmentation ---
        grp_seg = QGroupBox("セグメンテーション (GSAT)")
        form_seg = QFormLayout(grp_seg)

        self.chk_invert = QCheckBox("グレースケール反転 (暗い境界線)")
        self.chk_invert.setChecked(True)
        form_seg.addRow(self.chk_invert)

        self.spin_denoise_h = QDoubleSpinBox()
        self.spin_denoise_h.setRange(0.01, 100.0)
        self.spin_denoise_h.setDecimals(3)
        self.spin_denoise_h.setSingleStep(0.01)
        self.spin_denoise_h.setValue(0.04)
        form_seg.addRow("ノイズ除去 h:", self.spin_denoise_h)

        self.spin_sharpen_radius = QSpinBox()
        self.spin_sharpen_radius.setRange(0, 20)
        self.spin_sharpen_radius.setValue(2)
        form_seg.addRow("鮮鋭化半径:", self.spin_sharpen_radius)

        self.spin_sharpen_amount = QDoubleSpinBox()
        self.spin_sharpen_amount.setRange(0.0, 10.0)
        self.spin_sharpen_amount.setSingleStep(0.1)
        self.spin_sharpen_amount.setValue(0.3)
        form_seg.addRow("鮮鋭化強度:", self.spin_sharpen_amount)

        self.combo_threshold = QComboBox()
        self.combo_threshold.addItems(["グローバル閾値", "適応的閾値", "ヒステリシス閾値"])
        self.combo_threshold.setCurrentIndex(2)
        form_seg.addRow("閾値方法:", self.combo_threshold)

        self.spin_threshold_value = QSpinBox()
        self.spin_threshold_value.setRange(0, 255)
        self.spin_threshold_value.setValue(128)
        form_seg.addRow("閾値 (低):", self.spin_threshold_value)

        self.spin_threshold_high = QSpinBox()
        self.spin_threshold_high.setRange(0, 255)
        self.spin_threshold_high.setValue(200)
        self.spin_threshold_high.setEnabled(True)   # hysteresis is default
        form_seg.addRow("閾値 (高):", self.spin_threshold_high)

        self.spin_adaptive_block = QSpinBox()
        self.spin_adaptive_block.setRange(3, 201)
        self.spin_adaptive_block.setSingleStep(2)
        self.spin_adaptive_block.setValue(35)
        self.spin_adaptive_block.setEnabled(False)
        form_seg.addRow("適応ブロック:", self.spin_adaptive_block)

        self.combo_threshold.currentIndexChanged.connect(self._on_threshold_changed)

        self.spin_morph_close = QSpinBox()
        self.spin_morph_close.setRange(0, 20)
        self.spin_morph_close.setValue(1)
        form_seg.addRow("クロージング半径:", self.spin_morph_close)

        self.spin_morph_open = QSpinBox()
        self.spin_morph_open.setRange(0, 20)
        self.spin_morph_open.setValue(0)
        form_seg.addRow("オープニング半径:", self.spin_morph_open)

        self.spin_min_feature = QSpinBox()
        self.spin_min_feature.setRange(1, 10000)
        self.spin_min_feature.setValue(64)
        form_seg.addRow("最小フィーチャ (px²):", self.spin_min_feature)

        layout.addWidget(grp_seg)

        layout.addStretch()

    def _on_threshold_changed(self, index: int) -> None:
        is_global = index == 0
        is_hysteresis = index == 2
        is_adaptive = index == 1
        self.spin_threshold_value.setEnabled(is_global or is_hysteresis)
        self.spin_threshold_high.setEnabled(is_hysteresis)
        self.spin_adaptive_block.setEnabled(is_adaptive)

    def get_processing_params(self) -> dict:
        method_map = {0: "global_threshold", 1: "adaptive_threshold", 2: "hysteresis_threshold"}
        return {
            "invert_grayscale": self.chk_invert.isChecked(),
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
        }

    def set_processing_params(self, data: dict) -> None:
        method_map = {"global_threshold": 0, "adaptive_threshold": 1, "hysteresis_threshold": 2}
        self.chk_invert.setChecked(bool(data.get("invert_grayscale", True)))
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


class _GrainCalcTab(QWidget):
    """Tab 1: scale, ROI selection, intercept+area params."""

    auto_detect_requested = pyqtSignal()
    select_grain_roi_requested = pyqtSignal()
    select_marker_roi_requested = pyqtSignal()

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
        grp_scale = QGroupBox("スケール設定")
        form_scale = QFormLayout(grp_scale)

        self.spin_pixels_per_um = QDoubleSpinBox()
        self.spin_pixels_per_um.setRange(0.0, 100000.0)
        self.spin_pixels_per_um.setDecimals(3)
        self.spin_pixels_per_um.setValue(1.0)
        self.spin_pixels_per_um.setSpecialValueText("(未設定)")
        self.spin_pixels_per_um.setMinimum(0.0)

        self.btn_auto_detect = QPushButton("自動検出")
        self.btn_auto_detect.setFixedWidth(70)
        self.btn_auto_detect.setEnabled(False)
        self.btn_auto_detect.clicked.connect(self.auto_detect_requested)

        scale_row = QHBoxLayout()
        scale_row.addWidget(self.spin_pixels_per_um, stretch=1)
        scale_row.addWidget(self.btn_auto_detect)
        form_scale.addRow("px/µm:", scale_row)

        self.lbl_scale_status = QLabel()
        self.lbl_scale_status.setWordWrap(True)
        self.lbl_scale_status.setStyleSheet("color: gray; font-size: 10px;")
        self.lbl_scale_status.setAlignment(Qt.AlignmentFlag.AlignLeft)
        form_scale.addRow(self.lbl_scale_status)

        layout.addWidget(grp_scale)

        # --- Grain ROI ---
        grp_grain_roi = QGroupBox("粒子領域 (ROI)")
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
        form_grain_roi.addRow("座標:", grain_xy)

        grain_wh = QHBoxLayout()
        grain_wh.addWidget(QLabel("w:")); grain_wh.addWidget(self.spin_grain_w)
        grain_wh.addWidget(QLabel("h:")); grain_wh.addWidget(self.spin_grain_h)
        form_grain_roi.addRow("サイズ:", grain_wh)

        grain_btns = QHBoxLayout()
        self.btn_select_grain_roi = QPushButton("ビューワで選択")
        self.btn_select_grain_roi.setEnabled(False)
        self.btn_select_grain_roi.clicked.connect(self.select_grain_roi_requested)
        self.btn_clear_grain_roi = QPushButton("クリア")
        self.btn_clear_grain_roi.clicked.connect(self._clear_grain_roi)
        grain_btns.addWidget(self.btn_select_grain_roi)
        grain_btns.addWidget(self.btn_clear_grain_roi)
        form_grain_roi.addRow(grain_btns)

        layout.addWidget(grp_grain_roi)

        # --- Marker ROI ---
        grp_marker_roi = QGroupBox("マーカー領域 (ROI)")
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
        form_marker_roi.addRow("座標:", marker_xy)

        marker_wh = QHBoxLayout()
        marker_wh.addWidget(QLabel("w:")); marker_wh.addWidget(self.spin_marker_w)
        marker_wh.addWidget(QLabel("h:")); marker_wh.addWidget(self.spin_marker_h)
        form_marker_roi.addRow("サイズ:", marker_wh)

        marker_btns = QHBoxLayout()
        self.btn_select_marker_roi = QPushButton("ビューワで選択")
        self.btn_select_marker_roi.setEnabled(False)
        self.btn_select_marker_roi.clicked.connect(self.select_marker_roi_requested)
        self.btn_clear_marker_roi = QPushButton("クリア")
        self.btn_clear_marker_roi.clicked.connect(self._clear_marker_roi)
        marker_btns.addWidget(self.btn_select_marker_roi)
        marker_btns.addWidget(self.btn_clear_marker_roi)
        form_marker_roi.addRow(marker_btns)

        layout.addWidget(grp_marker_roi)

        # --- Intercept ---
        grp_intercept = QGroupBox("インターセプト計測")
        form_intercept = QFormLayout(grp_intercept)

        self.spin_line_spacing = QSpinBox()
        self.spin_line_spacing.setRange(5, 500)
        self.spin_line_spacing.setValue(60)
        form_intercept.addRow("ライン間隔 (px):", self.spin_line_spacing)

        self.spin_theta_start = QDoubleSpinBox()
        self.spin_theta_start.setRange(0.0, 180.0)
        self.spin_theta_start.setSingleStep(15.0)
        self.spin_theta_start.setValue(0.0)
        form_intercept.addRow("角度 開始 (°):", self.spin_theta_start)

        self.spin_theta_end = QDoubleSpinBox()
        self.spin_theta_end.setRange(0.0, 180.0)
        self.spin_theta_end.setSingleStep(15.0)
        self.spin_theta_end.setValue(180.0)
        form_intercept.addRow("角度 終了 (°):", self.spin_theta_end)

        self.spin_n_theta = QSpinBox()
        self.spin_n_theta.setRange(1, 36)
        self.spin_n_theta.setValue(5)
        form_intercept.addRow("角度 分割数:", self.spin_n_theta)

        self.chk_reskeletonize = QCheckBox("再スケルトン化")
        self.chk_reskeletonize.setChecked(True)
        form_intercept.addRow(self.chk_reskeletonize)

        self.chk_pad_for_rotation = QCheckBox("回転用パディング")
        self.chk_pad_for_rotation.setChecked(True)
        form_intercept.addRow(self.chk_pad_for_rotation)

        layout.addWidget(grp_intercept)

        # --- Grain filter ---
        grp_grain = QGroupBox("粒子フィルタリング")
        form_grain = QFormLayout(grp_grain)

        self.spin_min_grain_area = QSpinBox()
        self.spin_min_grain_area.setRange(1, 100000)
        self.spin_min_grain_area.setValue(50)
        form_grain.addRow("最小面積 (px²):", self.spin_min_grain_area)

        self.chk_exclude_edge = QCheckBox("端部の粒子を除外")
        self.chk_exclude_edge.setChecked(True)
        form_grain.addRow(self.chk_exclude_edge)

        self.spin_edge_buffer = QSpinBox()
        self.spin_edge_buffer.setRange(0, 100)
        self.spin_edge_buffer.setValue(5)
        form_grain.addRow("端部バッファ (px):", self.spin_edge_buffer)

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
        self._updating_roi = True
        for sp in (self.spin_grain_x, self.spin_grain_y, self.spin_grain_w, self.spin_grain_h):
            sp.setValue(0)
        self._updating_roi = False
        self.grain_roi_changed.emit(None)

    def _clear_marker_roi(self) -> None:
        self._updating_roi = True
        for sp in (self.spin_marker_x, self.spin_marker_y, self.spin_marker_w, self.spin_marker_h):
            sp.setValue(0)
        self._updating_roi = False
        self.marker_roi_changed.emit(None)

    # ------------------------------------------------------------------
    # Called when viewer selects a ROI
    # ------------------------------------------------------------------

    def set_grain_roi(self, x: int, y: int, w: int, h: int) -> None:
        self._updating_roi = True
        self.spin_grain_x.setValue(x)
        self.spin_grain_y.setValue(y)
        self.spin_grain_w.setValue(w)
        self.spin_grain_h.setValue(h)
        self._updating_roi = False

    def set_marker_roi(self, x: int, y: int, w: int, h: int) -> None:
        self._updating_roi = True
        self.spin_marker_x.setValue(x)
        self.spin_marker_y.setValue(y)
        self.spin_marker_w.setValue(w)
        self.spin_marker_h.setValue(h)
        self._updating_roi = False

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

        grp_chord = QGroupBox("ASTM E112 インターセプト")
        chord_layout = QVBoxLayout(grp_chord)
        self.lbl_chord_stats = QLabel("（解析前）")
        self.lbl_chord_stats.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.lbl_chord_stats.setWordWrap(True)
        chord_layout.addWidget(self.lbl_chord_stats)
        layout.addWidget(grp_chord)

        grp_grain = QGroupBox("粒子面積計測")
        grain_layout = QVBoxLayout(grp_grain)
        self.lbl_grain_stats = QLabel("（解析前）")
        self.lbl_grain_stats.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.lbl_grain_stats.setWordWrap(True)
        grain_layout.addWidget(self.lbl_grain_stats)
        layout.addWidget(grp_grain)

        layout.addStretch()

    def update_chord_stats(self, stats: dict) -> None:
        if not stats:
            self.lbl_chord_stats.setText("コードが検出されませんでした。")
            return
        lines = [f"コード数: {stats['count']}"]
        mean_px = stats.get("mean_px")
        if mean_px is not None:
            lines.append(f"平均長:  {mean_px:.1f} px")
        mean_um = stats.get("mean_um")
        if mean_um is not None:
            lines.append(f"         {mean_um:.3f} µm")
        std_px = stats.get("std_px")
        if std_px is not None:
            lines.append(f"標準偏差: {std_px:.1f} px")
        astm_g = stats.get("astm_grain_size_g")
        if astm_g is not None:
            lines.append(f"\nASTM G数: {astm_g:.2f}")
        self.lbl_chord_stats.setText("\n".join(lines))

    def update_grain_stats(self, stats: dict, pixels_per_um: float | None = None) -> None:
        if not stats:
            self.lbl_grain_stats.setText("粒子が検出されませんでした。")
            return
        lines = [f"粒子数: {stats['count']}"]
        mean_area = stats.get("mean_area_px")
        if mean_area is not None:
            if pixels_per_um:
                lines.append(f"平均面積: {mean_area / (pixels_per_um ** 2):.3f} µm²")
            else:
                lines.append(f"平均面積: {mean_area:.0f} px²")
        mean_diam = stats.get("mean_diam_px")
        if mean_diam is not None:
            if pixels_per_um:
                lines.append(f"平均直径: {mean_diam / pixels_per_um:.3f} µm")
            else:
                lines.append(f"平均直径: {mean_diam:.1f} px")
        self.lbl_grain_stats.setText("\n".join(lines))

    def reset(self) -> None:
        self.lbl_chord_stats.setText("（解析前）")
        self.lbl_grain_stats.setText("（解析前）")


# ---------------------------------------------------------------------------
# Main settings dialog
# ---------------------------------------------------------------------------

class SettingsDialog(QMainWindow):
    """Primary application window. Closing it quits the app."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("結晶粒サイズ測定 v0.6.0")
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
        self._scale_bar_result = None

        self._build_viewer()
        self._build_menu()
        self._build_tabs()
        self._build_status_bar()

        self._update_button_states()

    def _build_viewer(self) -> None:
        self._viewer = ViewerWindow()
        self._viewer.show()
        # Position viewer to the right of the dialog
        dg = self.frameGeometry()
        self._viewer.move(dg.right() + 20, dg.top())

        self._viewer.grain_roi_selected.connect(self._on_viewer_grain_roi)
        self._viewer.marker_roi_selected.connect(self._on_viewer_marker_roi)

    def _build_menu(self) -> None:
        menu_bar = self.menuBar()

        file_menu = menu_bar.addMenu("ファイル")
        act_open = file_menu.addAction("画像を開く...")
        act_open.setShortcut("Ctrl+O")
        act_open.triggered.connect(self._open_image)
        act_open_params = file_menu.addAction("パラメータを開く...")
        act_open_params.setShortcut("Ctrl+P")
        act_open_params.triggered.connect(self._open_params)
        act_save_params = file_menu.addAction("パラメータを保存...")
        act_save_params.setShortcut("Ctrl+Shift+S")
        act_save_params.triggered.connect(self._save_params)
        file_menu.addSeparator()
        act_quit = file_menu.addAction("終了")
        act_quit.setShortcut("Ctrl+Q")
        act_quit.triggered.connect(self.close)

        proc_menu = menu_bar.addMenu("処理")
        self._act_image_process = proc_menu.addAction("画像処理")
        self._act_image_process.setShortcut("F5")
        self._act_image_process.triggered.connect(self._image_process)
        self._act_grain_calc = proc_menu.addAction("粒子計算")
        self._act_grain_calc.setShortcut("F6")
        self._act_grain_calc.triggered.connect(self._grain_calc)
        proc_menu.addSeparator()
        self._act_save_image = proc_menu.addAction("画像を保存...")
        self._act_save_image.triggered.connect(self._save_image)
        self._act_export_chord_csv = proc_menu.addAction("コード長 CSV エクスポート...")
        self._act_export_chord_csv.triggered.connect(self._export_chord_csv)
        self._act_export_grain_csv = proc_menu.addAction("粒子面積 CSV エクスポート...")
        self._act_export_grain_csv.triggered.connect(self._export_grain_csv)

    def _build_tabs(self) -> None:
        self._tab_widget = QTabWidget()
        self.setCentralWidget(self._tab_widget)

        self._tab_process = _ImageProcessTab()
        self._tab_calc = _GrainCalcTab()
        self._tab_save = _SaveExportTab()

        self._tab_widget.addTab(self._tab_process, "画像処理")
        self._tab_widget.addTab(self._tab_calc, "粒子計算")
        self._tab_widget.addTab(self._tab_save, "保存・出力")

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
        self._lbl_status_image = QLabel("画像: なし")
        self._lbl_status_grains = QLabel("粒子数: --")
        status_bar = QStatusBar()
        status_bar.addWidget(self._lbl_status_image)
        status_bar.addWidget(QLabel("|"))
        status_bar.addWidget(self._lbl_status_grains)
        self.setStatusBar(status_bar)

    # ------------------------------------------------------------------
    # State management
    # ------------------------------------------------------------------

    def _update_button_states(self) -> None:
        self._act_image_process.setEnabled(self._image_loaded)

        self._tab_calc.btn_auto_detect.setEnabled(self._image_loaded)
        self._tab_calc.btn_select_grain_roi.setEnabled(self._image_loaded)
        self._tab_calc.btn_select_marker_roi.setEnabled(self._image_loaded)
        self._act_grain_calc.setEnabled(self._image_processed)

        self._act_save_image.setEnabled(self._calc_done)
        self._act_export_chord_csv.setEnabled(self._calc_done)
        self._act_export_grain_csv.setEnabled(self._calc_done)

    # ------------------------------------------------------------------
    # File actions
    # ------------------------------------------------------------------

    def _open_image(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "画像を開く", "",
            "画像ファイル (*.png *.jpg *.jpeg *.bmp *.tif *.tiff);;すべてのファイル (*)",
        )
        if not path:
            return
        self._load_image_path(path)

    def _load_image_path(self, path: str) -> None:
        try:
            self._analyzer.load_image(path)
        except ValueError as exc:
            QMessageBox.critical(self, "エラー", str(exc))
            return

        original_rgb = cv2.cvtColor(self._analyzer.original_image, cv2.COLOR_BGR2RGB)
        self._original_rgb = original_rgb
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
        self._lbl_status_image.setText(f"画像: {Path(path).name}  ({w}×{h} px)")
        self._lbl_status_grains.setText("粒子数: --")
        self.statusBar().showMessage("画像を読み込みました。", 3000)

    def _open_params(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "パラメータを開く", "", "JSON ファイル (*.json);;すべてのファイル (*)"
        )
        if not path:
            return
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except Exception as exc:
            QMessageBox.critical(self, "エラー", f"JSON読み込み失敗:\n{exc}")
            return

        self._tab_process.set_processing_params(data)
        self._tab_calc.set_calc_params(data)

        # Restore ROI overlays
        grain_roi = data.get("grain_roi")
        marker_roi = data.get("marker_roi")
        self._viewer.set_grain_roi(tuple(grain_roi) if grain_roi else None)  # type: ignore[arg-type]
        self._viewer.set_marker_roi(tuple(marker_roi) if marker_roi else None)  # type: ignore[arg-type]

        image_path = data.get("image_path")
        if image_path:
            try:
                self._load_image_path(image_path)
            except Exception as exc:
                QMessageBox.warning(self, "画像読み込み失敗", f"{image_path}\n\n{exc}")

        self.statusBar().showMessage(f"パラメータを読み込みました: {Path(path).name}", 3000)

    def _save_params(self) -> None:
        default_name = f"{self._image_stem}_params.json" if self._image_stem else "params.json"
        path, _ = QFileDialog.getSaveFileName(
            self, "パラメータを保存", default_name, "JSON ファイル (*.json);;すべてのファイル (*)"
        )
        if not path:
            return

        proc = self._tab_process.get_processing_params()
        calc = self._tab_calc.get_calc_params()
        data = {**proc, **calc}
        data["image_path"] = (
            str(self._analyzer.image_path) if self._analyzer.image_path else None
        )
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            self.statusBar().showMessage(f"パラメータを保存しました: {Path(path).name}", 3000)
        except Exception as exc:
            QMessageBox.critical(self, "エラー", f"保存に失敗しました:\n{exc}")

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
        self.statusBar().showMessage("画像処理中...")

        self._process_thread = QThread()
        self._process_worker = _ImageProcessWorker(self._analyzer, params)
        self._process_worker.moveToThread(self._process_thread)

        self._process_thread.started.connect(self._process_worker.run)
        self._process_worker.finished.connect(self._on_image_process_done)
        self._process_worker.error.connect(self._on_image_process_error)
        self._process_worker.finished.connect(self._process_thread.quit)
        self._process_worker.error.connect(self._process_thread.quit)
        self._process_thread.finished.connect(self._process_thread.deleteLater)
        self._process_thread.finished.connect(self._on_process_thread_finished)

        self._process_thread.start()

    def _on_process_thread_finished(self) -> None:
        self._process_thread = None
        self._process_worker = None

    def _on_image_process_done(self, binary: np.ndarray) -> None:
        # Convert binary (0/255) to RGB for display
        binary_rgb = cv2.cvtColor(binary, cv2.COLOR_GRAY2RGB)
        self._viewer.show_processed(binary_rgb)

        self._image_processed = True
        self._calc_done = False
        self._update_button_states()
        self.statusBar().showMessage("画像処理が完了しました。", 3000)

    def _on_image_process_error(self, message: str) -> None:
        QMessageBox.critical(self, "画像処理エラー", message)
        self.statusBar().showMessage("画像処理中にエラーが発生しました。", 5000)
        self._update_button_states()

    def _grain_calc(self) -> None:
        if not self._image_processed:
            return
        if self._calc_thread is not None and self._calc_thread.isRunning():
            return

        params = self._build_params()
        self.statusBar().showMessage("粒子計算中...")

        self._calc_thread = QThread()
        self._calc_worker = _GrainCalcWorker(self._analyzer, params)
        self._calc_worker.moveToThread(self._calc_thread)

        self._calc_thread.started.connect(self._calc_worker.run)
        self._calc_worker.finished.connect(self._on_grain_calc_done)
        self._calc_worker.error.connect(self._on_grain_calc_error)
        self._calc_worker.finished.connect(self._calc_thread.quit)
        self._calc_worker.error.connect(self._calc_thread.quit)
        self._calc_thread.finished.connect(self._calc_thread.deleteLater)
        self._calc_thread.finished.connect(self._on_calc_thread_finished)

        self._calc_thread.start()

    def _on_calc_thread_finished(self) -> None:
        self._calc_thread = None
        self._calc_worker = None

    def _on_grain_calc_done(self, chord_df, grain_df, overlay: np.ndarray) -> None:
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
        self._lbl_status_grains.setText(f"コード数: {chord_count}  粒子数: {grain_count}")
        self.statusBar().showMessage("粒子計算が完了しました。", 5000)
        self._tab_widget.setCurrentIndex(2)  # switch to save/export tab

    def _on_grain_calc_error(self, message: str) -> None:
        QMessageBox.critical(self, "粒子計算エラー", message)
        self.statusBar().showMessage("粒子計算中にエラーが発生しました。", 5000)
        self._update_button_states()

    # ------------------------------------------------------------------
    # Scale detection
    # ------------------------------------------------------------------

    def _run_scale_detection(self) -> None:
        if self._scale_thread is not None and self._scale_thread.isRunning():
            return
        marker_roi = self._tab_calc._read_marker_roi()
        self._tab_calc.btn_auto_detect.setEnabled(False)
        self._tab_calc.set_scale_status("検出中...")
        self.statusBar().showMessage("スケールバーを検出中...")

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

    def _refresh_original_with_scale_bar(self) -> None:
        if self._original_rgb is None:
            return
        img = self._original_rgb.copy()
        if self._scale_bar_result is not None:
            r = self._scale_bar_result
            # Coordinates from the worker are relative to the cropped marker_roi region;
            # add the roi offset to map back to full-image coordinates.
            x_off, y_off = 0, 0
            marker_roi = self._tab_calc._read_marker_roi()
            if marker_roi:
                x_off, y_off = marker_roi[0], marker_roi[1]
            x1 = r.bar_x1 + x_off
            x2 = r.bar_x2 + x_off
            y  = r.bar_y  + y_off
            cv2.line(img, (x1, y), (x2, y), (255, 80, 0), 3)
            cv2.line(img, (x1, y - 4), (x2, y - 4), (255, 80, 0), 3)
        self._viewer.show_original(img)

    def _on_scale_done(self, result) -> None:
        self._tab_calc.btn_auto_detect.setEnabled(True)
        if result.pixels_per_um is not None:
            unit_str = result.unit or "µm"
            status = (
                f"検出: {result.bar_length_px}px = {result.physical_value}{unit_str}"
                f" → {result.pixels_per_um:.3f} px/µm"
            )
            self._tab_calc.set_scale_from_detection(result.pixels_per_um, status)
            self._scale_bar_result = result
            self._refresh_original_with_scale_bar()
            self.statusBar().showMessage(f"スケール自動検出: {result.pixels_per_um:.3f} px/µm", 5000)
        else:
            self._prompt_physical_dimension(result)

    def _on_scale_error(self, message: str) -> None:
        self._tab_calc.btn_auto_detect.setEnabled(True)
        self._tab_calc.set_scale_status(f"検出失敗: {message}")
        self.statusBar().showMessage("スケールバーの検出に失敗しました。", 5000)

    def _prompt_physical_dimension(self, result) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("実寸入力")
        form = QFormLayout()
        spin_value = QDoubleSpinBox()
        spin_value.setRange(0.001, 100000.0)
        spin_value.setDecimals(3)
        spin_value.setValue(50.0)
        combo_unit = QComboBox()
        combo_unit.addItems(["µm", "nm", "mm"])
        form.addRow(f"バー長: {result.bar_length_px} px  実寸値:", spin_value)
        form.addRow("単位:", combo_unit)
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
            ppu = compute_pixels_per_um_from_bar(result.bar_length_px, spin_value.value(), unit)
            status = (
                f"設定: {result.bar_length_px}px = {spin_value.value()}{unit}"
                f" → {ppu:.3f} px/µm"
            )
            self._tab_calc.set_scale_from_detection(ppu, status)
            self._scale_bar_result = result
            self._refresh_original_with_scale_bar()
            self.statusBar().showMessage(f"スケール設定: {ppu:.3f} px/µm", 5000)
        else:
            self._tab_calc.set_scale_status("キャンセルされました")

    # ------------------------------------------------------------------
    # Export / save actions
    # ------------------------------------------------------------------

    def _save_image(self) -> None:
        default_name = f"{self._image_stem}_overlay.png" if self._image_stem else "grain_overlay.png"
        path, _ = QFileDialog.getSaveFileName(
            self, "画像を保存", default_name,
            "PNG ファイル (*.png);;JPEG ファイル (*.jpg);;すべてのファイル (*)",
        )
        if not path:
            return
        try:
            self._analyzer.save_labeled_image(path)
            self.statusBar().showMessage(f"画像を保存しました: {path}", 5000)
        except Exception as exc:
            QMessageBox.critical(self, "エラー", str(exc))

    def _export_chord_csv(self) -> None:
        default_name = f"{self._image_stem}_chord.csv" if self._image_stem else "chord_lengths.csv"
        path, _ = QFileDialog.getSaveFileName(
            self, "コード長CSVを保存", default_name,
            "CSV ファイル (*.csv);;すべてのファイル (*)",
        )
        if not path:
            return
        try:
            self._analyzer.save_chord_csv(path)
            self.statusBar().showMessage(f"コード長CSVを保存しました: {path}", 5000)
        except Exception as exc:
            QMessageBox.critical(self, "エラー", str(exc))

    def _export_grain_csv(self) -> None:
        default_name = f"{self._image_stem}_grain.csv" if self._image_stem else "grain_areas.csv"
        path, _ = QFileDialog.getSaveFileName(
            self, "粒子面積CSVを保存", default_name,
            "CSV ファイル (*.csv);;すべてのファイル (*)",
        )
        if not path:
            return
        try:
            self._analyzer.save_grain_csv(path)
            self.statusBar().showMessage(f"粒子面積CSVを保存しました: {path}", 5000)
        except Exception as exc:
            QMessageBox.critical(self, "エラー", str(exc))

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
