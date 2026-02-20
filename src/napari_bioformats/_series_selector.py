from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
from qtpy.QtCore import QObject, QRectF, Qt, QThread, QTimer, Signal
from qtpy.QtGui import QColor, QImage, QPainter, QPen, QPixmap
from qtpy.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

if TYPE_CHECKING:
    from bffile import BioFile, Series
    from qtpy.QtGui import QPaintEvent

THUMB_SIZE = 64
_TIMES = "\u2009\u00d7\u2009"  # thin-space, multiplication sign, thin-space
_MAX_DIALOG_HEIGHT = 600


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _format_series_info(series: Series, name: str) -> tuple[str, str]:
    """Return (title, subtitle) for a series row."""
    title = f"Series {series.index}: {name}"
    shape = series.shape
    # shape is (T, C, Z, Y, X) or (T, C, Z, Y, X, S)
    if series.is_rgb and len(shape) == 6:
        t, c, z, y, x, s = shape
        ch = {3: "RGB", 4: "RGBA"}.get(s, f"{s}ch")
    elif len(shape) >= 5:
        t, c, z, y, x = shape[:5]
        ch = ""
    else:
        return title, str(shape)

    parts = [f"{y}{_TIMES}{x}"]
    if ch:
        parts.append(ch)
    if t > 1:
        parts.append(f"T={t}")
    if c > 1:
        parts.append(f"C={c}")
    if z > 1:
        parts.append(f"Z={z}")
    return title, ", ".join(parts)


def _to_uint8(img: np.ndarray, perc: tuple[float, float] = (0.1, 99)) -> np.ndarray:
    """Contrast-stretch to uint8."""
    if img.dtype == np.uint8:
        return img
    mn, mx = np.percentile(img, perc)
    if mn == mx:
        return np.zeros_like(img, dtype=np.uint8)
    scaled = (img.astype(np.float64) - mn) / (mx - mn) * 255
    return np.clip(scaled, 0, 255).astype(np.uint8)


def _ndarray_to_qimage(img: np.ndarray) -> QImage:
    """Convert an ndarray to a QImage (with contrast stretch). Thread-safe."""
    img = _to_uint8(img)
    if img.ndim == 2:
        h, w = img.shape
        return QImage(img.tobytes(), w, h, w, QImage.Format.Format_Grayscale8).copy()
    h, w, c = img.shape
    fmt = QImage.Format.Format_RGB888 if c == 3 else QImage.Format.Format_RGBA8888
    return QImage(img.tobytes(), w, h, w * c, fmt).copy()


# ---------------------------------------------------------------------------
# Widgets
# ---------------------------------------------------------------------------


class _SpinnerWidget(QWidget):
    """Small spinning arc indicator."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._angle = 0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._step)
        self._timer.start(60)

    def stop(self) -> None:
        self._timer.stop()

    def _step(self) -> None:
        self._angle = (self._angle + 30) % 360
        self.update()

    def paintEvent(self, a0: QPaintEvent | None) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        side = min(self.width(), self.height())
        pen_w = max(2, side // 12)
        margin = side * 0.25
        rect = QRectF(margin, margin, side - 2 * margin, side - 2 * margin)
        p.setPen(QPen(QColor(200, 200, 200), pen_w))
        p.drawEllipse(rect)
        p.setPen(QPen(QColor(120, 120, 120), pen_w))
        p.drawArc(rect, self._angle * 16, 90 * 16)
        p.end()


class SeriesRow(QWidget):
    """A single row: [checkbox] [thumbnail] [title / subtitle]."""

    def __init__(
        self, title: str, subtitle: str = "", parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        self.checkbox = QCheckBox()

        self._thumb_label = QLabel()
        self._thumb_label.setFixedSize(THUMB_SIZE, THUMB_SIZE)
        self._thumb_label.setStyleSheet("border: 1px solid #555; border-radius: 4px;")
        self._spinner = _SpinnerWidget(self._thumb_label)
        self._spinner.setGeometry(0, 0, THUMB_SIZE, THUMB_SIZE)

        text_col = QVBoxLayout()
        text_col.setContentsMargins(0, 0, 0, 0)
        text_col.setSpacing(0)
        text_col.addStretch()
        text_col.addWidget(QLabel(title))
        if subtitle:
            sub = QLabel(subtitle)
            sub.setStyleSheet("color: #888; margin: 0; max-height: 16px;")
            text_col.addWidget(sub)
        text_col.addStretch()

        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addWidget(self.checkbox)
        layout.addWidget(self._thumb_label)
        layout.addLayout(text_col, 1)

    def set_thumbnail(self, qimage: QImage) -> None:
        """Update the thumbnail from a QImage."""
        self._spinner.stop()
        self._spinner.hide()
        pix = QPixmap.fromImage(qimage).scaled(
            THUMB_SIZE,
            THUMB_SIZE,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.FastTransformation,
        )
        self._thumb_label.setPixmap(pix)


class _ThumbnailWorker(QObject):
    """Fetches thumbnails sequentially in a background thread."""

    thumbnail_ready = Signal(int, QImage)
    finished = Signal()

    def __init__(self, biofile: BioFile, series_count: int) -> None:
        super().__init__()
        self._biofile = biofile
        self._series_count = series_count
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def run(self) -> None:
        for idx in range(self._series_count):
            if self._cancelled:
                break
            try:
                arr = self._biofile[idx].get_thumbnail()
                if not self._cancelled:
                    self.thumbnail_ready.emit(idx, _ndarray_to_qimage(arr))
            except Exception:
                pass
        self.finished.emit()


class SeriesOptionsDialog(QDialog):
    """Dialog presenting series with async thumbnail loading."""

    def __init__(self, biofile: BioFile, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Bio-Formats Series")
        self.setMinimumWidth(400)

        # scrollable area for series rows
        container = QWidget()
        rows_layout = QVBoxLayout(container)
        rows_layout.setContentsMargins(4, 4, 4, 4)
        rows_layout.setSpacing(2)

        self._rows: list[SeriesRow] = []
        fname = Path(biofile.filename).stem
        for series in biofile:
            title, subtitle = _format_series_info(series, fname)
            row = SeriesRow(title, subtitle)
            self._rows.append(row)
            rows_layout.addWidget(row)
        rows_layout.addStretch()

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(container)

        outer = QVBoxLayout(self)
        outer.addWidget(scroll, 1)

        # button bar
        btn_layout = QHBoxLayout()
        cancel_btn = QPushButton("Cancel")
        ok_btn = QPushButton("OK")
        select_all_btn = QPushButton("Select All")
        deselect_all_btn = QPushButton("Deselect All")

        cancel_btn.clicked.connect(self.reject)
        ok_btn.clicked.connect(self.accept)
        select_all_btn.clicked.connect(lambda: self._set_all_checked(True))
        deselect_all_btn.clicked.connect(lambda: self._set_all_checked(False))

        btn_layout.addWidget(cancel_btn)
        btn_layout.addWidget(ok_btn)
        btn_layout.addStretch()
        btn_layout.addWidget(select_all_btn)
        btn_layout.addWidget(deselect_all_btn)
        outer.addLayout(btn_layout)

        # size to fit content, capping height
        hint = container.sizeHint()
        self.resize(hint.width() + 40, min(_MAX_DIALOG_HEIGHT, hint.height() + 80))

        # start background thumbnail fetching
        self._thread = QThread()
        self._worker = _ThumbnailWorker(biofile, len(self._rows))
        self._worker.moveToThread(self._thread)
        self._worker.thumbnail_ready.connect(self._on_thumbnail)
        self._worker.finished.connect(self._thread.quit)
        self._thread.started.connect(self._worker.run)
        self._thread.start()

    def _on_thumbnail(self, index: int, qimage: QImage) -> None:
        if 0 <= index < len(self._rows):
            self._rows[index].set_thumbnail(qimage)

    def _stop_worker(self) -> None:
        if self._thread.isRunning():
            self._worker.cancel()
            self._thread.quit()
            self._thread.wait()

    def done(self, a0: int) -> None:
        # Wait for the worker before returning — the caller will use
        # the (non-thread-safe) biofile immediately after.
        self._stop_worker()
        super().done(a0)

    def selected_indices(self) -> list[int]:
        """Return indices of checked series."""
        return [i for i, row in enumerate(self._rows) if row.checkbox.isChecked()]

    def _set_all_checked(self, checked: bool) -> None:
        for row in self._rows:
            row.checkbox.setChecked(checked)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def get_series(biofile: BioFile) -> list[int]:
    """Popup a dialog to ask the user which series they want to open."""
    if not QApplication.instance():
        return [0]

    parent = next(
        (w for w in QApplication.topLevelWidgets() if isinstance(w, QMainWindow)),
        None,
    )
    dialog = SeriesOptionsDialog(biofile, parent=parent)
    if dialog.exec() == QDialog.DialogCode.Accepted:
        return dialog.selected_indices()
    return []
