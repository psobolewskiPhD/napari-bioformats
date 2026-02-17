from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING

from qtpy.QtCore import Qt
from qtpy.QtGui import QImage, QPixmap
from qtpy.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QFrame,
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
    from collections.abc import Sequence

    import numpy as np

THUMB_SIZE = 48


@dataclass
class SeriesInfo:
    """Metadata for a single series entry."""

    label: str
    thumbnail: np.ndarray | None = None  # 2D uint8 array for the preview
    checked: bool = False


class SeriesRow(QFrame):
    """A single row: checkbox + label + thumbnail."""

    def __init__(self, info: SeriesInfo, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setFrameShadow(QFrame.Shadow.Plain)
        self.setLineWidth(1)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 2, 8, 2)

        self.checkbox = QCheckBox(info.label)
        self.checkbox.setChecked(info.checked)
        self.checkbox.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        layout.addWidget(self.checkbox)

        # thumbnail
        thumb_label = QLabel()
        thumb_label.setFixedSize(THUMB_SIZE, THUMB_SIZE)
        thumb_label.setStyleSheet("border: 1px solid #ccc;")
        if info.thumbnail is not None:
            img = info.thumbnail
            if img.ndim == 2:
                h, w = img.shape
                qimg = QImage(img.tobytes(), w, h, w, QImage.Format.Format_Grayscale8)
            else:
                h, w, c = img.shape
                bpl = w * c
                fmt = (
                    QImage.Format.Format_RGB888
                    if c == 3
                    else QImage.Format.Format_RGBA8888
                )
                qimg = QImage(img.tobytes(), w, h, bpl, fmt)
            pix = QPixmap.fromImage(qimg).scaled(
                THUMB_SIZE,
                THUMB_SIZE,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.FastTransformation,
            )
            thumb_label.setPixmap(pix)
        layout.addWidget(thumb_label)


class SeriesOptionsDialog(QDialog):
    """Dialog presenting a list of series with checkboxes and thumbnails."""

    def __init__(
        self,
        series: Sequence[SeriesInfo],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Bio-Formats Series Options")
        self.setMinimumWidth(400)

        outer = QVBoxLayout(self)

        # scrollable area for series rows
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        container = QWidget()
        self._rows_layout = QVBoxLayout(container)
        self._rows_layout.setContentsMargins(8, 8, 8, 8)
        self._rows_layout.setSpacing(6)

        self._rows: list[SeriesRow] = []
        for info in series:
            row = SeriesRow(info)
            self._rows.append(row)
            self._rows_layout.addWidget(row)
        self._rows_layout.addStretch()

        scroll.setWidget(container)
        outer.addWidget(scroll, 1)

        # button bar
        btn_layout = QHBoxLayout()
        cancel_btn = QPushButton("Cancel")
        ok_btn = QPushButton("OK")
        select_all_btn = QPushButton("Select All")
        deselect_all_btn = QPushButton("Deselect All")

        cancel_btn.clicked.connect(self.reject)
        ok_btn.clicked.connect(self.accept)
        select_all_btn.clicked.connect(self._select_all)
        deselect_all_btn.clicked.connect(self._deselect_all)

        btn_layout.addWidget(cancel_btn)
        btn_layout.addWidget(ok_btn)
        btn_layout.addStretch()
        btn_layout.addWidget(select_all_btn)
        btn_layout.addWidget(deselect_all_btn)
        outer.addLayout(btn_layout)

    # -- public API --

    def selected_indices(self) -> list[int]:
        """Return indices of checked series."""
        return [i for i, row in enumerate(self._rows) if row.checkbox.isChecked()]

    # -- private --

    def _select_all(self) -> None:
        for row in self._rows:
            row.checkbox.setChecked(True)

    def _deselect_all(self) -> None:
        for row in self._rows:
            row.checkbox.setChecked(False)


def get_series(options: list[SeriesInfo]) -> list[int]:
    """Popup a dialog to ask the user which series they want to open"""
    # if not in a qapp, just return the first series
    if not (QApplication.instance()):
        return [0]

    # try to find the first MainWindow instance to parent the dialog to:
    parent = next(
        (w for w in QApplication.topLevelWidgets() if isinstance(w, QMainWindow)), None
    )

    dialog = SeriesOptionsDialog(options, parent=parent)
    if dialog.exec() == QDialog.DialogCode.Accepted:
        return dialog.selected_indices()
    return []
