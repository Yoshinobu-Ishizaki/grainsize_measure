from __future__ import annotations

import numpy as np

from PyQt6.QtCore import Qt, QPoint, QRect, QSize, pyqtSignal
from PyQt6.QtGui import QColor, QCursor, QImage, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import QLabel, QRubberBand, QScrollArea, QSizePolicy, QVBoxLayout, QWidget


class _ImageLabel(QLabel):
    """QLabel subclass that supports rubber-band ROI selection and overlay drawing."""

    grain_roi_selected = pyqtSignal(int, int, int, int)    # x, y, w, h (image coords)
    marker_roi_selected = pyqtSignal(int, int, int, int)
    pixel_hovered = pyqtSignal(int, int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

        self._full_pixmap: QPixmap | None = None
        self._zoom_factor: float = 1.0
        self._mode: str = "none"   # "none" | "grain_roi" | "marker_roi"

        self._grain_roi: QRect | None = None    # image coordinates
        self._marker_roi: QRect | None = None   # image coordinates

        self._rubber_band: QRubberBand | None = None
        self._origin: QPoint = QPoint()

        self.setMouseTracking(True)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_pixmap_full(self, pixmap: QPixmap) -> None:
        self._full_pixmap = pixmap
        self._apply_zoom()

    def set_zoom(self, factor: float) -> None:
        self._zoom_factor = max(0.1, min(factor, 10.0))
        self._apply_zoom()

    def set_mode(self, mode: str) -> None:
        self._mode = mode
        if mode != "none":
            self.setCursor(QCursor(Qt.CursorShape.CrossCursor))
        else:
            self.setCursor(QCursor(Qt.CursorShape.ArrowCursor))

    def set_grain_roi(self, roi: tuple[int, int, int, int] | None) -> None:
        self._grain_roi = QRect(roi[0], roi[1], roi[2], roi[3]) if roi else None
        self.update()

    def set_marker_roi(self, roi: tuple[int, int, int, int] | None) -> None:
        self._marker_roi = QRect(roi[0], roi[1], roi[2], roi[3]) if roi else None
        self.update()

    # ------------------------------------------------------------------
    # Mouse events
    # ------------------------------------------------------------------

    def mousePressEvent(self, event) -> None:
        if self._mode == "none" or self._full_pixmap is None:
            return
        if event.button() == Qt.MouseButton.LeftButton:
            self._origin = event.pos()
            if self._rubber_band is None:
                self._rubber_band = QRubberBand(QRubberBand.Shape.Rectangle, self)
            self._rubber_band.setGeometry(QRect(self._origin, QSize()))
            self._rubber_band.show()

    def mouseMoveEvent(self, event) -> None:
        if self._full_pixmap is not None:
            ix, iy = self._display_to_image(event.pos())
            self.pixel_hovered.emit(ix, iy)
        if self._rubber_band is not None and not self._origin.isNull():
            self._rubber_band.setGeometry(
                QRect(self._origin, event.pos()).normalized()
            )

    def mouseReleaseEvent(self, event) -> None:
        if self._rubber_band is None or self._mode == "none":
            return
        if event.button() == Qt.MouseButton.LeftButton:
            rect = QRect(self._origin, event.pos()).normalized()
            self._rubber_band.hide()

            if rect.width() > 2 and rect.height() > 2:
                img_rect = self._display_rect_to_image_rect(rect)
                if self._mode == "grain_roi":
                    self._grain_roi = img_rect
                    self.grain_roi_selected.emit(
                        img_rect.x(), img_rect.y(), img_rect.width(), img_rect.height()
                    )
                elif self._mode == "marker_roi":
                    self._marker_roi = img_rect
                    self.marker_roi_selected.emit(
                        img_rect.x(), img_rect.y(), img_rect.width(), img_rect.height()
                    )

            self._mode = "none"
            self.setCursor(QCursor(Qt.CursorShape.ArrowCursor))
            self.update()

    # ------------------------------------------------------------------
    # Paint overlay
    # ------------------------------------------------------------------

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        if self._full_pixmap is None:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        self._draw_roi(painter, self._grain_roi, QColor(255, 200, 0, 80), QColor(255, 200, 0), "粒子領域")
        self._draw_roi(painter, self._marker_roi, QColor(0, 200, 255, 80), QColor(0, 200, 255), "マーカー")

        painter.end()

    def _draw_roi(
        self,
        painter: QPainter,
        roi: QRect | None,
        fill: QColor,
        border: QColor,
        label: str,
    ) -> None:
        if roi is None:
            return
        disp_rect = self._image_rect_to_display_rect(roi)

        painter.fillRect(disp_rect, fill)

        pen = QPen(border, 2, Qt.PenStyle.SolidLine)
        painter.setPen(pen)
        painter.drawRect(disp_rect)

        text = f"{label} ({roi.x()}, {roi.y()}, {roi.width()}×{roi.height()})"
        text_pos = disp_rect.topLeft() + QPoint(4, 14)
        fm = painter.fontMetrics()
        text_w = fm.horizontalAdvance(text)
        text_h = fm.height()
        # Filled dark background behind text for legibility on any image content
        bg = QRect(text_pos.x() - 2, text_pos.y() - fm.ascent() - 1, text_w + 4, text_h + 2)
        painter.fillRect(bg, QColor(0, 0, 0, 180))
        # Text in border color on top
        painter.setPen(border)
        painter.drawText(text_pos, text)

    # ------------------------------------------------------------------
    # Coordinate helpers
    # ------------------------------------------------------------------

    def _display_to_image(self, pos: QPoint) -> tuple[int, int]:
        x = int(pos.x() / self._zoom_factor)
        y = int(pos.y() / self._zoom_factor)
        if self._full_pixmap:
            x = max(0, min(x, self._full_pixmap.width() - 1))
            y = max(0, min(y, self._full_pixmap.height() - 1))
        return x, y

    def _display_rect_to_image_rect(self, rect: QRect) -> QRect:
        x, y = self._display_to_image(rect.topLeft())
        x2, y2 = self._display_to_image(rect.bottomRight())
        return QRect(x, y, x2 - x, y2 - y)

    def _image_rect_to_display_rect(self, rect: QRect) -> QRect:
        x = int(rect.x() * self._zoom_factor)
        y = int(rect.y() * self._zoom_factor)
        w = int(rect.width() * self._zoom_factor)
        h = int(rect.height() * self._zoom_factor)
        return QRect(x, y, w, h)

    def _apply_zoom(self) -> None:
        if self._full_pixmap is None or self._full_pixmap.isNull():
            self.clear()
            return
        w = int(self._full_pixmap.width() * self._zoom_factor)
        h = int(self._full_pixmap.height() * self._zoom_factor)
        scaled = self._full_pixmap.scaled(
            w, h,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.setPixmap(scaled)
        self.resize(scaled.width(), scaled.height())


class ImageViewer(QWidget):
    """Scrollable image viewer with rubber-band ROI selection."""

    grain_roi_selected = pyqtSignal(int, int, int, int)
    marker_roi_selected = pyqtSignal(int, int, int, int)
    pixel_hovered = pyqtSignal(int, int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._zoom_factor: float = 1.0

        self._scroll = QScrollArea(self)
        self._scroll.setWidgetResizable(False)
        self._scroll.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._label = _ImageLabel()
        self._label.grain_roi_selected.connect(self.grain_roi_selected)
        self._label.marker_roi_selected.connect(self.marker_roi_selected)
        self._label.pixel_hovered.connect(self.pixel_hovered)

        self._scroll.setWidget(self._label)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._scroll)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_image(self, rgb: np.ndarray) -> None:
        """Display a numpy uint8 RGB image."""
        h, w = rgb.shape[:2]
        if rgb.ndim == 2:
            # grayscale
            q_img = QImage(rgb.data, w, h, w, QImage.Format.Format_Grayscale8)
        else:
            bytes_per_line = 3 * w
            q_img = QImage(rgb.data, w, h, bytes_per_line, QImage.Format.Format_RGB888)
        pixmap = QPixmap.fromImage(q_img.copy())
        self._label.set_pixmap_full(pixmap)
        self.fit_to_window()

    def clear(self) -> None:
        self._label._full_pixmap = None
        self._label.clear()

    def set_mode(self, mode: str) -> None:
        """Set ROI selection mode: 'none' | 'grain_roi' | 'marker_roi'."""
        self._label.set_mode(mode)

    def set_grain_roi(self, roi: tuple[int, int, int, int] | None) -> None:
        self._label.set_grain_roi(roi)

    def set_marker_roi(self, roi: tuple[int, int, int, int] | None) -> None:
        self._label.set_marker_roi(roi)

    def zoom_in(self) -> None:
        self._zoom_factor *= 1.25
        self._label.set_zoom(self._zoom_factor)

    def zoom_out(self) -> None:
        self._zoom_factor /= 1.25
        self._label.set_zoom(self._zoom_factor)

    def fit_to_window(self) -> None:
        if self._label._full_pixmap is None or self._label._full_pixmap.isNull():
            return
        vw = self._scroll.viewport().width()
        vh = self._scroll.viewport().height()
        iw = self._label._full_pixmap.width()
        ih = self._label._full_pixmap.height()
        if iw == 0 or ih == 0 or vw == 0 or vh == 0:
            return
        self._zoom_factor = min(vw / iw, vh / ih)
        self._label.set_zoom(self._zoom_factor)

    def wheelEvent(self, event) -> None:
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            delta = event.angleDelta().y()
            if delta > 0:
                self.zoom_in()
            else:
                self.zoom_out()
            event.accept()
        else:
            super().wheelEvent(event)
