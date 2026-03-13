# napari-bioformats

[![License](https://img.shields.io/pypi/l/napari-bioformats.svg?color=green)](https://github.com/napari/napari-bioformats/raw/master/LICENSE)
[![PyPI](https://img.shields.io/pypi/v/napari-bioformats.svg?color=green)](https://pypi.org/project/napari-bioformats)
[![Conda](https://img.shields.io/conda/v/conda-forge/napari-bioformats)](https://anaconda.org/conda-forge/napari-bioformats)
[![Python Version](https://img.shields.io/pypi/pyversions/napari-bioformats.svg?color=green)](https://python.org)
[![tests](https://github.com/imaging-formats/napari-bioformats/workflows/tests/badge.svg)](https://github.com/imaging-formats/napari-bioformats/actions)
[![codecov](https://codecov.io/gh/imaging-formats/napari-bioformats/branch/master/graph/badge.svg)](https://codecov.io/gh/imaging-formats/napari-bioformats)

Bioformats plugin for napari using [bffile](https://github.com/imaging-formats/bffile)

## Releasing

Anyone with write access can create a release:

1. **Locally:**

   checkout the version you want to release, then run:

   ```bash
   git tag -a vX.Y.Z -m vX.Y.Z
   git push upstream --follow-tags
   ```
