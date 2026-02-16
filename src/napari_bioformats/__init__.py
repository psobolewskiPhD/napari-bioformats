from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("napari-bioformats")
except PackageNotFoundError:  # pragma: no cover
    __version__ = "uninstalled"
