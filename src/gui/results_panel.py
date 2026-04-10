from __future__ import annotations

from PyQt6.QtCore import pyqtSignal, Qt
from PyQt6.QtWidgets import (
    QGroupBox,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class ResultsPanel(QWidget):
    """解析結果の統計表示とエクスポートボタンを提供するパネル。

    Signals:
        export_csv_requested: CSVエクスポートボタンが押されたとき
        save_image_requested: 画像保存ボタンが押されたとき
    """

    export_csv_requested = pyqtSignal()
    save_image_requested = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedWidth(200)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # --- 統計表示 ---
        grp_stats = QGroupBox("統計")
        stats_layout = QVBoxLayout(grp_stats)

        self.lbl_stats = QLabel("（解析前）")
        self.lbl_stats.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.lbl_stats.setWordWrap(True)
        self.lbl_stats.setTextFormat(Qt.TextFormat.PlainText)
        stats_layout.addWidget(self.lbl_stats)

        layout.addWidget(grp_stats)

        # --- エクスポートボタン ---
        self.btn_export_csv = QPushButton("CSVエクスポート")
        self.btn_export_csv.setEnabled(False)
        self.btn_export_csv.clicked.connect(self.export_csv_requested)
        layout.addWidget(self.btn_export_csv)

        self.btn_save_image = QPushButton("画像を保存")
        self.btn_save_image.setEnabled(False)
        self.btn_save_image.clicked.connect(self.save_image_requested)
        layout.addWidget(self.btn_save_image)

        layout.addStretch()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def update_stats(self, stats: dict, pixels_per_um: float | None = None) -> None:
        """統計量ラベルを更新する。"""
        if not stats:
            self.lbl_stats.setText("粒子が検出されませんでした。")
            return

        unit = "px²" if pixels_per_um is None else "µm²"
        diam_unit = "px" if pixels_per_um is None else "µm"
        ppu = pixels_per_um or 1.0

        def fmt_area(v: float) -> str:
            if pixels_per_um is None:
                return f"{v:.0f} {unit}"
            return f"{v / ppu**2:.3f} {unit}"

        lines = [
            f"粒子数: {stats['count']}",
            "",
            f"平均:   {fmt_area(stats['mean'])}",
            f"中央値: {fmt_area(stats['median'])}",
            f"標準偏差: {fmt_area(stats['std'])}",
            f"最小:   {fmt_area(stats['min'])}",
            f"最大:   {fmt_area(stats['max'])}",
            f"Q25:    {fmt_area(stats['q25'])}",
            f"Q75:    {fmt_area(stats['q75'])}",
        ]
        self.lbl_stats.setText("\n".join(lines))

    def set_export_enabled(self, enabled: bool) -> None:
        self.btn_export_csv.setEnabled(enabled)
        self.btn_save_image.setEnabled(enabled)

    def reset(self) -> None:
        self.lbl_stats.setText("（解析前）")
        self.set_export_enabled(False)
