from __future__ import annotations

import cv2
import numpy as np
from pathlib import Path

from PyQt6.QtCore import QObject, QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QStatusBar,
    QTabWidget,
    QWidget,
)

from analyzer import AnalysisParams, GrainAnalyzer
from gui.image_canvas import ImageCanvas
from gui.settings_panel import SettingsPanel
from gui.results_panel import ResultsPanel


# ---------------------------------------------------------------------------
# バックグラウンドワーカー
# ---------------------------------------------------------------------------

class AnalysisWorker(QObject):
    finished = pyqtSignal(object, object)  # (pl.DataFrame, np.ndarray overlay)
    error = pyqtSignal(str)

    def __init__(self, analyzer: GrainAnalyzer, params: AnalysisParams) -> None:
        super().__init__()
        self._analyzer = analyzer
        self._params = params

    def run(self) -> None:
        try:
            df = self._analyzer.run_pipeline(self._params)
            overlay = self._analyzer.render_overlay_image()
            self.finished.emit(df, overlay)
        except Exception as exc:
            self.error.emit(str(exc))


# ---------------------------------------------------------------------------
# メインウィンドウ
# ---------------------------------------------------------------------------

class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("結晶粒サイズ測定")
        self.resize(1200, 750)

        self._analyzer = GrainAnalyzer()
        self._thread: QThread | None = None
        self._worker: AnalysisWorker | None = None

        self._build_ui()
        self._build_status_bar()

    # ------------------------------------------------------------------
    # UI 構築
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(4, 4, 4, 4)
        main_layout.setSpacing(4)

        # 左パネル
        self._settings = SettingsPanel()
        self._settings.open_requested.connect(self._open_image)
        self._settings.run_requested.connect(self._run_analysis)
        main_layout.addWidget(self._settings)

        # 中央パネル（タブ）
        self._tabs = QTabWidget()
        self._canvas_original = ImageCanvas()
        self._canvas_overlay = ImageCanvas()
        self._tabs.addTab(self._canvas_original, "元画像")
        self._tabs.addTab(self._canvas_overlay, "粒子 Overlay")
        main_layout.addWidget(self._tabs, stretch=1)

        # 右パネル
        self._results = ResultsPanel()
        self._results.export_csv_requested.connect(self._export_csv)
        self._results.save_image_requested.connect(self._save_image)
        main_layout.addWidget(self._results)

    def _build_status_bar(self) -> None:
        self._status_image = QLabel("画像: なし")
        self._status_grains = QLabel("粒子数: --")
        status_bar = QStatusBar()
        status_bar.addWidget(self._status_image)
        status_bar.addWidget(QLabel("|"))
        status_bar.addWidget(self._status_grains)
        self.setStatusBar(status_bar)

    # ------------------------------------------------------------------
    # スロット
    # ------------------------------------------------------------------

    def _open_image(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "画像を開く",
            "",
            "画像ファイル (*.png *.jpg *.jpeg *.bmp *.tif *.tiff);;すべてのファイル (*)",
        )
        if not path:
            return

        try:
            self._analyzer.load_image(path)
        except ValueError as exc:
            QMessageBox.critical(self, "エラー", str(exc))
            return

        original_rgb = cv2.cvtColor(self._analyzer.original_image, cv2.COLOR_BGR2RGB)
        self._canvas_original.show_image(original_rgb, title=Path(path).name)
        self._canvas_overlay.clear()
        self._results.reset()
        self._settings.set_run_enabled(True)
        self._tabs.setCurrentIndex(0)

        h, w = self._analyzer.gray_image.shape
        self._status_image.setText(f"画像: {Path(path).name}  ({w}×{h} px)")
        self._status_grains.setText("粒子数: --")
        self.statusBar().showMessage("画像を読み込みました。", 3000)

    def _run_analysis(self) -> None:
        if self._thread is not None and self._thread.isRunning():
            return

        params = self._settings.get_params()
        self._settings.set_run_enabled(False)
        self.statusBar().showMessage("解析中...")

        self._thread = QThread()
        self._worker = AnalysisWorker(self._analyzer, params)
        self._worker.moveToThread(self._thread)

        self._thread.started.connect(self._worker.run)
        self._worker.finished.connect(self._on_analysis_done)
        self._worker.error.connect(self._on_analysis_error)
        self._worker.finished.connect(self._thread.quit)
        self._worker.error.connect(self._thread.quit)
        self._thread.finished.connect(self._thread.deleteLater)

        self._thread.start()

    def _on_analysis_done(self, df, overlay: np.ndarray) -> None:
        self._canvas_overlay.show_image(overlay, title="粒子 Overlay")
        self._tabs.setCurrentIndex(1)

        stats = self._analyzer.get_area_statistics()
        ppu = self._settings.get_params().pixels_per_um
        self._results.update_stats(stats, pixels_per_um=ppu)
        self._results.set_export_enabled(True)

        grain_count = stats.get("count", 0)
        self._status_grains.setText(f"粒子数: {grain_count}")
        self.statusBar().showMessage("解析が完了しました。", 5000)
        self._settings.set_run_enabled(True)

    def _on_analysis_error(self, message: str) -> None:
        QMessageBox.critical(self, "解析エラー", message)
        self.statusBar().showMessage("解析中にエラーが発生しました。", 5000)
        self._settings.set_run_enabled(True)

    def _export_csv(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self,
            "CSVを保存",
            "grain_analysis.csv",
            "CSV ファイル (*.csv);;すべてのファイル (*)",
        )
        if not path:
            return

        try:
            self._analyzer.save_csv(path)
            self.statusBar().showMessage(f"CSVを保存しました: {path}", 5000)
        except Exception as exc:
            QMessageBox.critical(self, "エラー", str(exc))

    def _save_image(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self,
            "画像を保存",
            "grain_overlay.png",
            "PNG ファイル (*.png);;JPEG ファイル (*.jpg);;すべてのファイル (*)",
        )
        if not path:
            return

        try:
            self._analyzer.save_labeled_image(path)
            self.statusBar().showMessage(f"画像を保存しました: {path}", 5000)
        except Exception as exc:
            QMessageBox.critical(self, "エラー", str(exc))
