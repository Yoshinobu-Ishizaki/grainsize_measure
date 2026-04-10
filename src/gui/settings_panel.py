from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QRadioButton,
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
    """

    open_requested = pyqtSignal()
    run_requested = pyqtSignal()
    auto_detect_requested = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedWidth(260)

        # スクロール可能なコンテナを作成
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
        self.spin_pixels_per_um.setRange(0.01, 100000.0)
        self.spin_pixels_per_um.setDecimals(3)
        self.spin_pixels_per_um.setValue(1.0)
        self.spin_pixels_per_um.setSpecialValueText("(未設定)")
        self.spin_pixels_per_um.setMinimum(0.0)  # 0 = 未設定

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

        # --- 前処理 ---
        grp_pre = QGroupBox("前処理")
        form_pre = QFormLayout(grp_pre)

        self.spin_sigma = QDoubleSpinBox()
        self.spin_sigma.setRange(0.1, 20.0)
        self.spin_sigma.setSingleStep(0.1)
        self.spin_sigma.setValue(1.0)
        form_pre.addRow("ぼかし (σ):", self.spin_sigma)

        self.spin_contrast = QDoubleSpinBox()
        self.spin_contrast.setRange(0.5, 5.0)
        self.spin_contrast.setSingleStep(0.1)
        self.spin_contrast.setValue(1.2)
        form_pre.addRow("コントラスト:", self.spin_contrast)
        layout.addWidget(grp_pre)

        # --- セグメンテーション ---
        grp_seg = QGroupBox("セグメンテーション")
        seg_layout = QVBoxLayout(grp_seg)

        self.radio_otsu = QRadioButton("Otsu")
        self.radio_adaptive = QRadioButton("Adaptive")
        self.radio_manual = QRadioButton("Manual")
        self.radio_otsu.setChecked(True)

        manual_row = QHBoxLayout()
        manual_row.addWidget(self.radio_manual)
        self.spin_manual_thresh = QSpinBox()
        self.spin_manual_thresh.setRange(0, 255)
        self.spin_manual_thresh.setValue(128)
        self.spin_manual_thresh.setEnabled(False)
        manual_row.addWidget(self.spin_manual_thresh)

        self.radio_manual.toggled.connect(self.spin_manual_thresh.setEnabled)

        seg_layout.addWidget(self.radio_otsu)
        seg_layout.addWidget(self.radio_adaptive)
        seg_layout.addLayout(manual_row)

        form_seg = QFormLayout()
        self.spin_min_dist = QSpinBox()
        self.spin_min_dist.setRange(1, 200)
        self.spin_min_dist.setValue(10)
        form_seg.addRow("最小距離 (px):", self.spin_min_dist)
        seg_layout.addLayout(form_seg)
        layout.addWidget(grp_seg)

        # --- フィルタリング ---
        grp_flt = QGroupBox("フィルタリング")
        form_flt = QFormLayout(grp_flt)

        self.spin_min_area = QSpinBox()
        self.spin_min_area.setRange(1, 100000)
        self.spin_min_area.setValue(50)
        form_flt.addRow("最小面積 (px²):", self.spin_min_area)

        self.chk_exclude_edge = QCheckBox("端部の粒子を除外")
        self.chk_exclude_edge.setChecked(True)
        form_flt.addRow(self.chk_exclude_edge)

        self.spin_edge_buffer = QSpinBox()
        self.spin_edge_buffer.setRange(0, 100)
        self.spin_edge_buffer.setValue(5)
        form_flt.addRow("端部バッファ (px):", self.spin_edge_buffer)

        self.chk_exclude_edge.toggled.connect(self.spin_edge_buffer.setEnabled)

        layout.addWidget(grp_flt)

        # --- 解析実行ボタン ---
        self.btn_run = QPushButton("解析実行")
        self.btn_run.setEnabled(False)
        self.btn_run.setStyleSheet("QPushButton { font-weight: bold; padding: 6px; }")
        self.btn_run.clicked.connect(self.run_requested)
        layout.addWidget(self.btn_run)

        layout.addStretch()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_params(self) -> AnalysisParams:
        """現在のUI値から AnalysisParams を返す。"""
        if self.radio_otsu.isChecked():
            method = "otsu"
        elif self.radio_adaptive.isChecked():
            method = "adaptive"
        else:
            method = "manual"

        ppu_value = self.spin_pixels_per_um.value()
        pixels_per_um = ppu_value if ppu_value > 0.0 else None

        return AnalysisParams(
            gaussian_sigma=self.spin_sigma.value(),
            contrast_factor=self.spin_contrast.value(),
            threshold_method=method,
            manual_threshold=self.spin_manual_thresh.value(),
            min_distance=self.spin_min_dist.value(),
            min_area=self.spin_min_area.value(),
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
