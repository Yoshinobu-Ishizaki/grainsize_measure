"""Progress dialogs for long-running operations."""
from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class _OptimizerProgressDialog(QDialog):
    """Modal progress dialog shown while the parameter optimizer subprocess runs."""

    cancel_requested = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("パラメータ最適化")
        self.setModal(True)
        self.setMinimumWidth(420)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowCloseButtonHint)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(16, 16, 16, 16)

        self._phase_label = QLabel("フェーズ 1: 初期スキャン中...")
        layout.addWidget(self._phase_label)

        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 6)
        self._progress_bar.setValue(0)
        self._progress_bar.setTextVisible(True)
        layout.addWidget(self._progress_bar)

        self._score_label = QLabel("最高スコア: —")
        layout.addWidget(self._score_label)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        self._cancel_btn = QPushButton("キャンセル")
        self._cancel_btn.setFixedWidth(100)
        self._cancel_btn.clicked.connect(self._on_cancel_clicked)
        btn_layout.addWidget(self._cancel_btn)
        layout.addLayout(btn_layout)

    def set_phase1_progress(self, n: int, total: int) -> None:
        self._phase_label.setText(f"フェーズ 1: 初期スキャン ({n}/{total})")
        self._progress_bar.setRange(0, total)
        self._progress_bar.setValue(n)

    def set_phase2_start(self, total: int) -> None:
        self._phase_label.setText(f"フェーズ 2: ランダム探索 (0/{total})")
        self._progress_bar.setRange(0, total)
        self._progress_bar.setValue(0)

    def set_phase2_progress(self, n: int, total: int) -> None:
        self._phase_label.setText(f"フェーズ 2: ランダム探索 ({n}/{total})")
        self._progress_bar.setValue(n)

    def set_best_score(self, score: float) -> None:
        self._score_label.setText(f"最高スコア: {score:.2f}")

    def mark_done(self) -> None:
        try:
            self._cancel_btn.clicked.disconnect()
        except RuntimeError:
            pass
        self.accept()

    def _on_cancel_clicked(self) -> None:
        self._cancel_btn.setEnabled(False)
        self._cancel_btn.setText("キャンセル中...")
        self.cancel_requested.emit()

    def closeEvent(self, event) -> None:
        self._on_cancel_clicked()
        event.ignore()


class _CalcProgressDialog(QDialog):
    """Non-blocking progress dialog with cancel button for long calculations."""

    cancel_requested = pyqtSignal()

    def __init__(self, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.setMinimumWidth(380)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowCloseButtonHint)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(16, 16, 16, 16)

        self._step_label = QLabel("準備中...")
        layout.addWidget(self._step_label)

        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 0)   # indeterminate until first update
        self._progress_bar.setTextVisible(True)
        layout.addWidget(self._progress_bar)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        self._cancel_btn = QPushButton("キャンセル")
        self._cancel_btn.setFixedWidth(110)
        self._cancel_btn.clicked.connect(self._on_cancel_clicked)
        btn_layout.addWidget(self._cancel_btn)
        layout.addLayout(btn_layout)

    def update_progress(self, label: str, current: int, total: int) -> None:
        self._step_label.setText(label)
        self._progress_bar.setRange(0, total)
        self._progress_bar.setValue(current)

    def mark_done(self) -> None:
        try:
            self._cancel_btn.clicked.disconnect()
        except RuntimeError:
            pass
        self.accept()

    def _on_cancel_clicked(self) -> None:
        self._cancel_btn.setEnabled(False)
        self._cancel_btn.setText("キャンセル中...")
        self.cancel_requested.emit()

    def closeEvent(self, event) -> None:
        event.ignore()  # close only via mark_done() or mark_cancelled()
