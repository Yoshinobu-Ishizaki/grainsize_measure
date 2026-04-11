from __future__ import annotations

import cv2
import numpy as np
from pathlib import Path

from PyQt6.QtCore import QObject, QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QStatusBar,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from analyzer import AnalysisParams, GrainAnalyzer
from gui.image_canvas import ImageCanvas
from gui.settings_panel import SettingsPanel
from gui.results_panel import ResultsPanel


# ---------------------------------------------------------------------------
# バックグラウンドワーカー
# ---------------------------------------------------------------------------

class ScaleDetectionWorker(QObject):
    finished = pyqtSignal(object)  # ScaleBarResult を emit
    error = pyqtSignal(str)

    def __init__(self, image_bgr: np.ndarray) -> None:
        super().__init__()
        self._image_bgr = image_bgr

    def run(self) -> None:
        try:
            from scale_detector import detect_scale_bar  # noqa: PLC0415
            result = detect_scale_bar(self._image_bgr)
            self.finished.emit(result)
        except Exception as exc:
            self.error.emit(str(exc))


class AnalysisWorker(QObject):
    finished = pyqtSignal(object, object, object)  # (chord_df, grain_df, np.ndarray overlay)
    error = pyqtSignal(str)

    def __init__(self, analyzer: GrainAnalyzer, params: AnalysisParams) -> None:
        super().__init__()
        self._analyzer = analyzer
        self._params = params

    def run(self) -> None:
        try:
            chord_df, grain_df = self._analyzer.run_pipeline(self._params)
            overlay = self._analyzer.render_overlay_image()
            self.finished.emit(chord_df, grain_df, overlay)
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
        self._scale_thread: QThread | None = None
        self._scale_worker: ScaleDetectionWorker | None = None

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
        self._settings.auto_detect_requested.connect(self._run_scale_detection)
        self._settings.load_params_requested.connect(self._load_params)
        self._settings.save_params_requested.connect(self._save_params)
        main_layout.addWidget(self._settings)

        # 中央パネル（タブ）
        self._tabs = QTabWidget()
        self._canvas_original = ImageCanvas()
        self._canvas_gray = ImageCanvas()
        self._canvas_overlay = ImageCanvas()
        self._tabs.addTab(self._canvas_original, "元画像")
        self._tabs.addTab(self._canvas_gray, "グレースケール")
        self._tabs.addTab(self._canvas_overlay, "粒子 Overlay")
        main_layout.addWidget(self._tabs, stretch=1)

        # 右パネル
        self._results = ResultsPanel()
        self._results.export_chord_csv_requested.connect(self._export_chord_csv)
        self._results.export_grain_csv_requested.connect(self._export_grain_csv)
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
        gray_rgb = cv2.cvtColor(self._analyzer.gray_image, cv2.COLOR_GRAY2RGB)
        self._canvas_gray.show_image(gray_rgb, title=f"{Path(path).name} (Grayscale)")
        self._canvas_overlay.clear()
        self._results.reset()
        self._settings.set_run_enabled(True)
        self._settings.set_auto_detect_enabled(True)
        self._settings.set_save_enabled(True)
        self._settings.set_scale_status("")
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
        self._thread.finished.connect(self._on_thread_finished)

        self._thread.start()

    def _on_thread_finished(self) -> None:
        self._thread = None
        self._worker = None

    def _on_analysis_done(self, chord_df, grain_df, overlay: np.ndarray) -> None:
        self._canvas_overlay.show_image(overlay, title="Grain Overlay")
        self._tabs.setCurrentIndex(2)

        ppu = self._settings.get_params().pixels_per_um
        chord_stats = self._analyzer.get_chord_statistics()
        grain_stats = self._analyzer.get_grain_statistics()

        self._results.update_chord_stats(chord_stats)
        self._results.update_grain_stats(grain_stats, pixels_per_um=ppu)
        self._results.set_export_enabled(True)

        chord_count = chord_stats.get("count", 0)
        grain_count = grain_stats.get("count", 0)
        self._status_grains.setText(f"コード数: {chord_count}  粒子数: {grain_count}")
        self.statusBar().showMessage("解析が完了しました。", 5000)
        self._settings.set_run_enabled(True)

    def _on_analysis_error(self, message: str) -> None:
        QMessageBox.critical(self, "解析エラー", message)
        self.statusBar().showMessage("解析中にエラーが発生しました。", 5000)
        self._settings.set_run_enabled(True)

    def _run_scale_detection(self) -> None:
        if self._scale_thread is not None and self._scale_thread.isRunning():
            return

        self._settings.set_auto_detect_enabled(False)
        self._settings.set_scale_status("検出中...")
        self.statusBar().showMessage("スケールバーを検出中...")

        self._scale_thread = QThread()
        self._scale_worker = ScaleDetectionWorker(self._analyzer.original_image)
        self._scale_worker.moveToThread(self._scale_thread)

        self._scale_thread.started.connect(self._scale_worker.run)
        self._scale_worker.finished.connect(self._on_scale_done)
        self._scale_worker.error.connect(self._on_scale_error)
        self._scale_worker.finished.connect(self._scale_thread.quit)
        self._scale_worker.error.connect(self._scale_thread.quit)
        self._scale_thread.finished.connect(self._scale_thread.deleteLater)
        self._scale_thread.finished.connect(self._on_scale_thread_finished)

        self._scale_thread.start()

    def _on_scale_done(self, result) -> None:
        self._settings.set_auto_detect_enabled(True)

        if result.pixels_per_um is not None:
            unit_str = result.unit or "µm"
            status = (
                f"検出: {result.bar_length_px}px = {result.physical_value}{unit_str}"
                f" → {result.pixels_per_um:.3f} px/µm"
            )
            self._settings.set_scale_from_detection(result.pixels_per_um, status)
            self.statusBar().showMessage(
                f"スケール自動検出: {result.pixels_per_um:.3f} px/µm", 5000
            )
        else:
            self._prompt_physical_dimension(result)

    def _on_scale_error(self, message: str) -> None:
        self._settings.set_auto_detect_enabled(True)
        self._settings.set_scale_status(f"検出失敗: {message}")
        self.statusBar().showMessage("スケールバーの検出に失敗しました。", 5000)

    def _on_scale_thread_finished(self) -> None:
        self._scale_thread = None
        self._scale_worker = None

    def _prompt_physical_dimension(self, result) -> None:
        """OCR失敗時に実寸値をユーザーから入力させるダイアログ。"""
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
            ppu = compute_pixels_per_um_from_bar(
                result.bar_length_px, spin_value.value(), unit
            )
            status = (
                f"設定: {result.bar_length_px}px = {spin_value.value()}{unit}"
                f" → {ppu:.3f} px/µm"
            )
            self._settings.set_scale_from_detection(ppu, status)
            self.statusBar().showMessage(f"スケール設定: {ppu:.3f} px/µm", 5000)
        else:
            self._settings.set_scale_status("キャンセルされました")

    def _load_params(self) -> None:
        import json
        path, _ = QFileDialog.getOpenFileName(
            self, "パラメータを読み込む", "", "JSON ファイル (*.json);;すべてのファイル (*)"
        )
        if not path:
            return
        try:
            with open(path) as f:
                data = json.load(f)
        except Exception as exc:
            QMessageBox.critical(self, "エラー", f"JSONの読み込みに失敗しました:\n{exc}")
            return

        image_path = self._settings.set_params(data)

        if image_path:
            try:
                self._analyzer.load_image(image_path)
                original_rgb = cv2.cvtColor(self._analyzer.original_image, cv2.COLOR_BGR2RGB)
                self._canvas_original.show_image(original_rgb, title=Path(image_path).name)
                gray_rgb = cv2.cvtColor(self._analyzer.gray_image, cv2.COLOR_GRAY2RGB)
                self._canvas_gray.show_image(gray_rgb, title=f"{Path(image_path).name} (Grayscale)")
                self._canvas_overlay.clear()
                self._results.reset()
                self._settings.set_run_enabled(True)
                self._settings.set_auto_detect_enabled(True)
                self._settings.set_save_enabled(True)
                self._settings.set_scale_status("")
                self._tabs.setCurrentIndex(0)
                h, w = self._analyzer.gray_image.shape
                self._status_image.setText(f"画像: {Path(image_path).name}  ({w}×{h} px)")
                self._status_grains.setText("粒子数: --")
            except Exception as exc:
                QMessageBox.warning(self, "画像読み込み失敗", f"{image_path}\n\n{exc}")

        self.statusBar().showMessage(f"パラメータを読み込みました: {Path(path).name}", 3000)

    def _save_params(self) -> None:
        import json
        import dataclasses
        path, _ = QFileDialog.getSaveFileName(
            self, "パラメータを保存", "params.json", "JSON ファイル (*.json);;すべてのファイル (*)"
        )
        if not path:
            return
        params = self._settings.get_params()
        data = dataclasses.asdict(params)
        data["image_path"] = (
            str(self._analyzer.image_path) if self._analyzer.image_path else None
        )
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            self.statusBar().showMessage(f"パラメータを保存しました: {Path(path).name}", 3000)
        except Exception as exc:
            QMessageBox.critical(self, "エラー", f"保存に失敗しました:\n{exc}")

    def _export_chord_csv(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self,
            "コード長CSVを保存",
            "chord_lengths.csv",
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
        path, _ = QFileDialog.getSaveFileName(
            self,
            "粒子面積CSVを保存",
            "grain_areas.csv",
            "CSV ファイル (*.csv);;すべてのファイル (*)",
        )
        if not path:
            return
        try:
            self._analyzer.save_grain_csv(path)
            self.statusBar().showMessage(f"粒子面積CSVを保存しました: {path}", 5000)
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
