from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from analyzer import AnalysisParams


class SettingsPanel(QWidget):
    """解析パラメータ設定パネル。

    Signals:
        open_requested: 画像を開くボタンが押されたとき
        run_requested: 解析実行ボタンが押されたとき
        auto_detect_requested: スケール自動検出ボタンが押されたとき
    """

    open_requested = pyqtSignal()
    run_requested = pyqtSignal()
    auto_detect_requested = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedWidth(270)

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

        # --- 画像を開くボタン ---
        self.btn_open = QPushButton("画像を開く...")
        self.btn_open.clicked.connect(self.open_requested)
        layout.addWidget(self.btn_open)

        # --- スケール設定 ---
        grp_scale = QGroupBox("スケール")
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

        # --- セグメンテーション (GSAT) ---
        grp_seg = QGroupBox("セグメンテーション (GSAT)")
        form_seg = QFormLayout(grp_seg)

        self.spin_denoise_h = QDoubleSpinBox()
        self.spin_denoise_h.setRange(0.1, 100.0)
        self.spin_denoise_h.setSingleStep(1.0)
        self.spin_denoise_h.setValue(10.0)
        form_seg.addRow("ノイズ除去 h:", self.spin_denoise_h)

        self.spin_sharpen_radius = QSpinBox()
        self.spin_sharpen_radius.setRange(0, 20)
        self.spin_sharpen_radius.setValue(3)
        form_seg.addRow("鮮鋭化半径:", self.spin_sharpen_radius)

        self.spin_sharpen_amount = QDoubleSpinBox()
        self.spin_sharpen_amount.setRange(0.0, 10.0)
        self.spin_sharpen_amount.setSingleStep(0.1)
        self.spin_sharpen_amount.setValue(1.2)
        form_seg.addRow("鮮鋭化強度:", self.spin_sharpen_amount)

        self.combo_threshold = QComboBox()
        self.combo_threshold.addItems(["グローバル閾値", "適応的閾値"])
        form_seg.addRow("閾値方法:", self.combo_threshold)

        self.spin_threshold_value = QSpinBox()
        self.spin_threshold_value.setRange(0, 255)
        self.spin_threshold_value.setValue(128)
        form_seg.addRow("閾値:", self.spin_threshold_value)

        self.combo_threshold.currentIndexChanged.connect(self._on_threshold_method_changed)

        self.spin_adaptive_block = QSpinBox()
        self.spin_adaptive_block.setRange(3, 201)
        self.spin_adaptive_block.setSingleStep(2)
        self.spin_adaptive_block.setValue(35)
        self.spin_adaptive_block.setEnabled(False)
        form_seg.addRow("適応ブロック:", self.spin_adaptive_block)

        self.spin_morph_close = QSpinBox()
        self.spin_morph_close.setRange(0, 20)
        self.spin_morph_close.setValue(3)
        form_seg.addRow("クロージング半径:", self.spin_morph_close)

        self.spin_morph_open = QSpinBox()
        self.spin_morph_open.setRange(0, 20)
        self.spin_morph_open.setValue(2)
        form_seg.addRow("オープニング半径:", self.spin_morph_open)

        self.spin_min_feature = QSpinBox()
        self.spin_min_feature.setRange(1, 10000)
        self.spin_min_feature.setValue(50)
        form_seg.addRow("最小フィーチャ (px²):", self.spin_min_feature)

        layout.addWidget(grp_seg)

        # --- インターセプト計測 ---
        grp_intercept = QGroupBox("インターセプト計測")
        form_intercept = QFormLayout(grp_intercept)

        self.spin_line_spacing = QSpinBox()
        self.spin_line_spacing.setRange(5, 500)
        self.spin_line_spacing.setValue(20)
        form_intercept.addRow("ライン間隔 (px):", self.spin_line_spacing)

        self.spin_theta_start = QDoubleSpinBox()
        self.spin_theta_start.setRange(0.0, 180.0)
        self.spin_theta_start.setSingleStep(15.0)
        self.spin_theta_start.setValue(0.0)
        form_intercept.addRow("角度 開始 (°):", self.spin_theta_start)

        self.spin_theta_end = QDoubleSpinBox()
        self.spin_theta_end.setRange(0.0, 180.0)
        self.spin_theta_end.setSingleStep(15.0)
        self.spin_theta_end.setValue(135.0)
        form_intercept.addRow("角度 終了 (°):", self.spin_theta_end)

        self.spin_n_theta = QSpinBox()
        self.spin_n_theta.setRange(1, 36)
        self.spin_n_theta.setValue(4)
        form_intercept.addRow("角度 分割数:", self.spin_n_theta)

        layout.addWidget(grp_intercept)

        # --- 粒子フィルタリング (Track B) ---
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

        # --- 解析実行ボタン ---
        self.btn_run = QPushButton("解析実行")
        self.btn_run.setEnabled(False)
        self.btn_run.setStyleSheet("QPushButton { font-weight: bold; padding: 6px; }")
        self.btn_run.clicked.connect(self.run_requested)
        layout.addWidget(self.btn_run)

        layout.addStretch()

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _on_threshold_method_changed(self, index: int) -> None:
        is_global = index == 0
        self.spin_threshold_value.setEnabled(is_global)
        self.spin_adaptive_block.setEnabled(not is_global)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_params(self) -> AnalysisParams:
        """現在のUI値から AnalysisParams を返す。"""
        ppu_value = self.spin_pixels_per_um.value()
        pixels_per_um = ppu_value if ppu_value > 0.0 else None

        threshold_method = (
            "global_threshold" if self.combo_threshold.currentIndex() == 0
            else "adaptive_threshold"
        )

        return AnalysisParams(
            denoise_h=self.spin_denoise_h.value(),
            denoise_patch=7,
            denoise_search=21,
            sharpen_radius=self.spin_sharpen_radius.value(),
            sharpen_amount=self.spin_sharpen_amount.value(),
            threshold_method=threshold_method,
            threshold_value=self.spin_threshold_value.value(),
            adaptive_block_size=self.spin_adaptive_block.value(),
            adaptive_offset=0.0,
            morph_close_radius=self.spin_morph_close.value(),
            morph_open_radius=self.spin_morph_open.value(),
            min_feature_size=self.spin_min_feature.value(),
            max_hole_size=10,
            line_spacing=self.spin_line_spacing.value(),
            theta_start=self.spin_theta_start.value(),
            theta_end=self.spin_theta_end.value(),
            n_theta_steps=self.spin_n_theta.value(),
            min_grain_area=self.spin_min_grain_area.value(),
            exclude_edge_grains=self.chk_exclude_edge.isChecked(),
            edge_buffer=self.spin_edge_buffer.value(),
            pixels_per_um=pixels_per_um,
        )

    def set_run_enabled(self, enabled: bool) -> None:
        self.btn_run.setEnabled(enabled)

    def set_auto_detect_enabled(self, enabled: bool) -> None:
        self.btn_auto_detect.setEnabled(enabled)

    def set_scale_from_detection(self, pixels_per_um: float, status_text: str) -> None:
        self.spin_pixels_per_um.setValue(pixels_per_um)
        self.lbl_scale_status.setText(status_text)

    def set_scale_status(self, text: str) -> None:
        self.lbl_scale_status.setText(text)
