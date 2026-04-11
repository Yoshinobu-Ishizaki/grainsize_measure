# grainsize_measure

A Python GUI application that analyses grain structure observation images (with dimension markers) to detect grain boundaries, calculate individual grain areas, and export the results as CSV files.

## Features

- Automatic scale bar detection from embedded dimension markers (px/µm)
- GSAT-based image segmentation pipeline (CLAHE → denoise → sharpen → threshold → morphology)
- **Track A** — ASTM E112 intercept method: chord length measurement at multiple angles
- **Track B** — Per-grain area measurement via watershed segmentation
- Interactive ROI selection for grain area and scale bar regions
- Overlay visualisation of detected boundaries and grain colours
- Separate CSV export for chord data and grain data
- **Parameter optimizer** — automatically searches for the best segmentation parameters for any image (runnable from the GUI or terminal)
- Auto-run processing pipeline when a params JSON is loaded
- Original image tab always shows the unmodified image; ROI and scale bar overlays appear only on the processed view

## Requirements

- Python 3.11+
- [uv](https://github.com/astral-sh/uv)

## Usage

```bash
uv run src/grainsize_measure.py
```

## Documentation

| Document | Description |
|---|---|
| [Parameter Guide (English)](docs/parameter_guide.md) | How to tune each processing parameter for better grain detection, with example images |
| [Parameter Guide (日本語)](docs/parameter_guide_ja.md) | 各パラメータの設定方法と粒界検出への影響（画像付き） |
| [CSV Output Guide (English)](docs/csv_output_guide.md) | Explanation of every column in the exported chords and grains CSV files |
| [CSV Output Guide (日本語)](docs/csv_output_guide_ja.md) | 出力 CSV の全カラムの意味と計算方法の解説 |

## Acknowledgements

This software uses image processing functions from the **NIST Grain Size Analysis Tools (GSAT)**:

> [https://github.com/usnistgov/grain-size-analysis-tools](https://github.com/usnistgov/grain-size-analysis-tools)

GSAT is developed by the National Institute of Standards and Technology (NIST). The GSAT source code is used under its original license terms. grainsize_measure is not affiliated with or endorsed by NIST.

This application was developed with the assistance of [Claude Sonnet](https://claude.ai/) by Anthropic.

## License

MIT License
