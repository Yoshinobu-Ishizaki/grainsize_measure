from __future__ import annotations

import numpy as np
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg, NavigationToolbar2QT
from matplotlib.figure import Figure
from PyQt6.QtWidgets import QWidget, QVBoxLayout


class ImageCanvas(QWidget):
    """matplotlib を Qt ウィジェットとして埋め込む画像表示コンポーネント。

    NavigationToolbar2QT によりズーム・パン・保存が標準提供される。
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.figure = Figure(tight_layout=True)
        self.canvas = FigureCanvasQTAgg(self.figure)
        self.toolbar = NavigationToolbar2QT(self.canvas, self)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.toolbar)
        layout.addWidget(self.canvas)

    def show_image(self, rgb_array: np.ndarray, title: str = "") -> None:
        """RGB uint8 の numpy 配列を表示する。"""
        self.figure.clear()
        ax = self.figure.add_subplot(111)
        ax.imshow(rgb_array)
        if title:
            ax.set_title(title, fontsize=10)
        ax.axis("off")
        self.canvas.draw()

    def clear(self) -> None:
        """表示をリセットする。"""
        self.figure.clear()
        self.canvas.draw()
