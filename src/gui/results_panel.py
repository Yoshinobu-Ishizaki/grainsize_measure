from __future__ import annotations

from PyQt6.QtCore import pyqtSignal, Qt
from PyQt6.QtWidgets import (
    QGroupBox,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)


class ResultsPanel(QWidget):
    """解析結果の統計表示とエクスポートボタンを提供するパネル。

    Signals:
        export_chord_csv_requested: コード長CSVエクスポートボタンが押されたとき
        export_grain_csv_requested: 粒子面積CSVエクスポートボタンが押されたとき
        save_image_requested: 画像保存ボタンが押されたとき
    """

    export_chord_csv_requested = pyqtSignal()
    export_grain_csv_requested = pyqtSignal()
    save_image_requested = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedWidth(210)

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

        # --- ASTM E112 インターセプト結果 ---
        grp_chord = QGroupBox("ASTM E112 インターセプト")
        chord_layout = QVBoxLayout(grp_chord)

        self.lbl_chord_stats = QLabel("（解析前）")
        self.lbl_chord_stats.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.lbl_chord_stats.setWordWrap(True)
        self.lbl_chord_stats.setTextFormat(Qt.TextFormat.PlainText)
        chord_layout.addWidget(self.lbl_chord_stats)

        self.btn_export_chord_csv = QPushButton("コード長 CSV エクスポート")
        self.btn_export_chord_csv.setEnabled(False)
        self.btn_export_chord_csv.clicked.connect(self.export_chord_csv_requested)
        chord_layout.addWidget(self.btn_export_chord_csv)

        layout.addWidget(grp_chord)

        # --- 粒子面積結果 ---
        grp_grain = QGroupBox("粒子面積計測")
        grain_layout = QVBoxLayout(grp_grain)

        self.lbl_grain_stats = QLabel("（解析前）")
        self.lbl_grain_stats.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.lbl_grain_stats.setWordWrap(True)
        self.lbl_grain_stats.setTextFormat(Qt.TextFormat.PlainText)
        grain_layout.addWidget(self.lbl_grain_stats)

        self.btn_export_grain_csv = QPushButton("粒子面積 CSV エクスポート")
        self.btn_export_grain_csv.setEnabled(False)
        self.btn_export_grain_csv.clicked.connect(self.export_grain_csv_requested)
        grain_layout.addWidget(self.btn_export_grain_csv)

        layout.addWidget(grp_grain)

        # --- 画像を保存 ---
        self.btn_save_image = QPushButton("画像を保存")
        self.btn_save_image.setEnabled(False)
        self.btn_save_image.clicked.connect(self.save_image_requested)
        layout.addWidget(self.btn_save_image)

        layout.addStretch()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def update_chord_stats(self, stats: dict) -> None:
        """インターセプト統計量ラベルを更新する。"""
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
            lines.append("")
            lines.append(f"ASTM G数: {astm_g:.2f}")

        self.lbl_chord_stats.setText("\n".join(lines))

    def update_grain_stats(self, stats: dict, pixels_per_um: float | None = None) -> None:
        """粒子面積統計量ラベルを更新する。"""
        if not stats:
            self.lbl_grain_stats.setText("粒子が検出されませんでした。")
            return

        lines = [f"粒子数: {stats['count']}"]

        mean_area = stats.get("mean_area_px")
        if mean_area is not None:
            if pixels_per_um is not None:
                area_um2 = mean_area / (pixels_per_um ** 2)
                lines.append(f"平均面積: {area_um2:.3f} µm²")
            else:
                lines.append(f"平均面積: {mean_area:.0f} px²")

        mean_diam = stats.get("mean_diam_px")
        if mean_diam is not None:
            if pixels_per_um is not None:
                diam_um = mean_diam / pixels_per_um
                lines.append(f"平均直径: {diam_um:.3f} µm")
            else:
                lines.append(f"平均直径: {mean_diam:.1f} px")

        std_area = stats.get("std_area_px")
        if std_area is not None:
            if pixels_per_um is not None:
                std_um2 = std_area / (pixels_per_um ** 2)
                lines.append(f"標準偏差: {std_um2:.3f} µm²")
            else:
                lines.append(f"標準偏差: {std_area:.0f} px²")

        self.lbl_grain_stats.setText("\n".join(lines))

    def set_export_enabled(self, enabled: bool) -> None:
        self.btn_export_chord_csv.setEnabled(enabled)
        self.btn_export_grain_csv.setEnabled(enabled)
        self.btn_save_image.setEnabled(enabled)

    def reset(self) -> None:
        self.lbl_chord_stats.setText("（解析前）")
        self.lbl_grain_stats.setText("（解析前）")
        self.set_export_enabled(False)
