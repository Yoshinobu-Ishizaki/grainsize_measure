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

from i18n import _


class _OptimizerProgressDialog(QDialog):
    """Modal progress dialog shown while the parameter optimizer subprocess runs."""

    cancel_requested = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(_("Parameter Optimization"))
        self.setModal(True)
        self.setMinimumWidth(420)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowCloseButtonHint)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(16, 16, 16, 16)

        self._phase_label = QLabel(_("Phase 1: Initial scan..."))
        layout.addWidget(self._phase_label)

        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 6)
        self._progress_bar.setValue(0)
        self._progress_bar.setTextVisible(True)
        layout.addWidget(self._progress_bar)

        self._score_label = QLabel(_("Best score: —"))
        layout.addWidget(self._score_label)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        self._cancel_btn = QPushButton(_("Cancel"))
        self._cancel_btn.setFixedWidth(100)
        self._cancel_btn.clicked.connect(self._on_cancel_clicked)
        btn_layout.addWidget(self._cancel_btn)
        layout.addLayout(btn_layout)

    def set_phase1_progress(self, n: int, total: int) -> None:
        self._phase_label.setText(
            _("Phase 1: Initial scan ({n}/{total})").format(n=n, total=total)
        )
        self._progress_bar.setRange(0, total)
        self._progress_bar.setValue(n)

    def set_phase2_start(self, total: int) -> None:
        self._phase_label.setText(
            _("Phase 2: Random search ({n}/{total})").format(n=0, total=total)
        )
        self._progress_bar.setRange(0, total)
        self._progress_bar.setValue(0)

    def set_phase2_progress(self, n: int, total: int) -> None:
        self._phase_label.setText(
            _("Phase 2: Random search ({n}/{total})").format(n=n, total=total)
        )
        self._progress_bar.setValue(n)

    def set_best_score(self, score: float) -> None:
        self._score_label.setText(_("Best score: {score:.2f}").format(score=score))

    def mark_done(self) -> None:
        try:
            self._cancel_btn.clicked.disconnect()
        except RuntimeError:
            pass
        self.accept()

    def _on_cancel_clicked(self) -> None:
        self._cancel_btn.setEnabled(False)
        self._cancel_btn.setText(_("Cancelling..."))
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

        self._step_label = QLabel(_("Preparing..."))
        layout.addWidget(self._step_label)

        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 0)   # indeterminate until first update
        self._progress_bar.setTextVisible(True)
        layout.addWidget(self._progress_bar)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        self._cancel_btn = QPushButton(_("Cancel"))
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
        self._cancel_btn.setText(_("Cancelling..."))
        self.cancel_requested.emit()

    def closeEvent(self, event) -> None:
        event.ignore()  # close only via mark_done() or mark_cancelled()
