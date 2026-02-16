from __future__ import annotations

import os
from collections.abc import Sequence
from typing import TYPE_CHECKING, Any

import numpy as np
from bffile import BioFile

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from napari.types import LayerData

    # example_plugin.some_module
    PathOrPaths = str | Sequence[str]
    ReaderFunction = Callable[[PathOrPaths], list[LayerData]]

SUFFIXES = tuple(BioFile.list_supported_suffixes())


def get_reader(path: PathOrPaths) -> ReaderFunction | None:
    """Napari reader plugin hook"""
    if isinstance(path, str):
        if path.endswith(SUFFIXES):
            return _reader_function
    return None


def _reader_function(path: PathOrPaths) -> list[LayerData]:
    assert isinstance(path, str), "Should not have been called with multiple paths"

    bf = BioFile(path).open()
    fname = os.path.split(path)[-1].rsplit(".", 1)[0]
    options = []
    if bf.series_count() == 1:
        indices = [0]
    else:
        from ._series_selector import SeriesInfo, get_series

        for series in bf:
            thumb = get_thumbnail(bf, series.index)
            thumb = _to_uint8(thumb)
            label = f"Series {series.index}: {fname}: {series.shape}"
            options.append(SeriesInfo(label=label, thumbnail=thumb))
        indices = get_series(options)

    if not indices:
        return [(None,)]

    split_channels = True
    ome_meta = bf.ome_metadata
    layers = []
    for i in indices:
        series = bf[i]
        if series.resolution_count > 1:
            data: Any = [
                series.as_array(resolution=r) for r in range(series.resolution_count)
            ]
            ndim = data[0].ndim
        else:
            data = series.as_array()
            ndim = data.ndim

        scale = [1] * (ndim - 1)
        try:
            pixels = ome_meta.images[i].pixels
            z, y, x = (
                getattr(pixels, f"physical_size_{dim}", None) or 1
                for dim in ("z", "y", "x")
            )
            scale[-3:] = (z, y, x)  # prolly wrong for rgb...
        except (IndexError, AttributeError):
            pass

        if split_channels:
            scale.pop(1)
            channel_axis = 1
        else:
            channel_axis = None

        kwargs = {
            "rgb": series.is_rgb,
            "channel_axis": channel_axis,
            "name": f"{fname} (Series {i})",
            "scale": scale,
        }

        layers.append((data, kwargs, "image"))
    return layers


# upstream this
def get_thumbnail(self, series: int = 0) -> np.ndarray:
    """Get thumbnail image for specified series.

    Returns a downsampled version of the first plane (t=0, c=0, z=0) from
    the specified series, scaled to fit within 128x128 pixels while
    maintaining aspect ratio.

    """
    reader = self._ensure_java_reader()
    meta = self.core_metadata(series=series)

    with self._lock:
        reader.setSeries(series)
        # Get thumbnail bytes for first plane (t=0, c=0, z=0)
        java_buffer = reader.openThumbBytes(0)

        # Convert to numpy array using metadata dtype
        thumb = np.frombuffer(memoryview(java_buffer), meta.dtype)  # type: ignore

        # Get thumbnail dimensions from reader (computed dynamically)
        thumb_height = reader.getThumbSizeY()
        thumb_width = reader.getThumbSizeX()

        # Reshape based on RGB channels and interleaving
        if meta.shape.rgb > 1:
            if meta.is_interleaved:
                thumb.shape = (thumb_height, thumb_width, meta.shape.rgb)
            else:
                thumb.shape = (meta.shape.rgb, thumb_height, thumb_width)
                thumb = np.transpose(thumb, (1, 2, 0))
        else:
            thumb.shape = (thumb_height, thumb_width)

        return thumb


def _to_uint8(img: np.ndarray) -> np.ndarray:
    if img.dtype == np.uint8:
        return img
    mn, mx = np.percentile(img, (1, 99))  # robust min/max for contrast stretching
    if mn == mx:
        return np.zeros_like(img, dtype=np.uint8)
    return ((img.astype(np.float64) - mn) / (mx - mn) * 255).astype(np.uint8)
