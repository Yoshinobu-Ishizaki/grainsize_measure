#!/usr/bin/env python3
"""CLI for grainsize_measure — run grain analysis without the GUI.

Usage:
    # Bootstrap a default params JSON from an image:
    uv run src/grainsize_measure_cli.py image.png

    # Run analysis with a params JSON:
    uv run src/grainsize_measure_cli.py params.json --out grain chord stat image

    # Specify output filename stem:
    uv run src/grainsize_measure_cli.py params.json --out stat --oname results
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import sys
from pathlib import Path

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".webp"}

# Ensure src/ is on the import path when run via `uv run src/...`
sys.path.insert(0, str(Path(__file__).parent))

from analyzer import AnalysisParams, GrainAnalyzer  # noqa: E402
from path_utils import make_relative_posix_str, resolve_image_path  # noqa: E402


def _default_params_dict(image_path: Path, json_path: Path) -> dict:
    """Return a JSON-serialisable dict of default AnalysisParams + image_path.

    *image_path* is stored as a Unix-style relative path from *json_path*'s
    parent directory so that param files remain portable.
    """
    params = AnalysisParams()
    d: dict = {"image_path": make_relative_posix_str(image_path, json_path)}
    for f in dataclasses.fields(params):
        d[f.name] = getattr(params, f.name)
    return d


def _resolve_output_path(
    out_type: str,
    image_stem: str,
    image_dir: Path,
    oname: str | None,
) -> Path:
    suffix_map = {
        "grain": ("_grain", ".csv"),
        "chord": ("_chord", ".csv"),
        "stat":  ("_stat",  ".csv"),
        "image": ("_overlay", ".png"),
    }
    type_suffix, ext = suffix_map[out_type]
    if oname is not None:
        return Path(f"{oname}{type_suffix}{ext}")
    return image_dir / f"{image_stem}{type_suffix}{ext}"


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="grainsize_measure_cli",
        description=(
            "Grain size analysis CLI. Pass a .json params file to run analysis, "
            "or an image file to generate a default params JSON."
        ),
    )
    parser.add_argument(
        "input",
        help="Path to a parameter JSON file, or an image file to bootstrap a default JSON.",
    )
    parser.add_argument(
        "--out",
        nargs="+",
        choices=["grain", "chord", "stat", "image"],
        default=["grain", "chord", "stat", "image"],
        metavar="TYPE",
        help="Output type(s): grain, chord, stat, image. Default: all four.",
    )
    parser.add_argument(
        "--oname",
        default=None,
        metavar="STEM",
        help=(
            "Output filename stem (used with --out). "
            "Each output is named <STEM>_grain.csv, <STEM>_chord.csv, etc. "
            "If omitted, the image filename stem is used."
        ),
    )
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Error: input file not found: {input_path}", file=sys.stderr)
        sys.exit(1)

    # ------------------------------------------------------------------ #
    # Image file mode: generate default params JSON and exit
    # ------------------------------------------------------------------ #
    if input_path.suffix.lower() in IMAGE_EXTENSIONS:
        params_path = input_path.with_name(input_path.stem + "_params.json").resolve()
        default_dict = _default_params_dict(input_path.resolve(), params_path)
        with open(params_path, "w", encoding="utf-8") as f:
            json.dump(default_dict, f, indent=2, ensure_ascii=False)
        print(f"Generated default parameter file: {params_path}")
        print("Edit it as needed, then re-run:")
        print(f"  uv run src/grainsize_measure_cli.py {params_path}")
        return

    # ------------------------------------------------------------------ #
    # JSON mode: load params and run analysis
    # ------------------------------------------------------------------ #
    if input_path.suffix.lower() != ".json":
        print(
            f"Error: unsupported file type '{input_path.suffix}'. "
            "Pass a .json params file or an image file.",
            file=sys.stderr,
        )
        sys.exit(1)

    with open(input_path, encoding="utf-8") as f:
        data = json.load(f)

    image_path_str = data.get("image_path")
    if not image_path_str:
        print("Error: 'image_path' key not found in JSON.", file=sys.stderr)
        sys.exit(1)

    image_path = resolve_image_path(image_path_str, input_path)
    if not image_path.exists():
        print(f"Error: image not found: {image_path}", file=sys.stderr)
        sys.exit(1)

    # Build AnalysisParams from JSON, ignoring unknown keys (e.g. image_path)
    known_fields = {f.name for f in dataclasses.fields(AnalysisParams)}
    params_kwargs = {k: v for k, v in data.items() if k in known_fields}
    # grain_roi / marker_roi are stored as JSON arrays; convert to tuples
    for roi_key in ("grain_roi", "marker_roi"):
        if params_kwargs.get(roi_key) is not None:
            params_kwargs[roi_key] = tuple(params_kwargs[roi_key])
    params = AnalysisParams(**params_kwargs)

    analyzer = GrainAnalyzer()
    print(f"Loading image: {image_path}")
    analyzer.load_image(image_path)

    # Auto-detect scale if pixels_per_um is absent but marker_roi is provided
    if params.pixels_per_um is None and params.marker_roi is not None:
        print("Detecting scale bar …")
        try:
            from scale_detector import detect_scale_bar
            img = analyzer.original_image
            x, y, w, h = params.marker_roi
            cropped = img[y : y + h, x : x + w]
            result = detect_scale_bar(cropped, strip_start=0)
            if result.pixels_per_um is not None:
                params.pixels_per_um = result.pixels_per_um
                print(
                    f"  Scale detected: {params.pixels_per_um:.4f} px/µm "
                    f"(confidence: {result.confidence})"
                )
            else:
                print(
                    "  Warning: scale bar found but OCR could not read label. "
                    "Set pixels_per_um manually in the JSON."
                )
        except Exception as exc:
            print(f"  Warning: scale bar detection failed: {exc}")

    print("Running analysis …")
    analyzer.run_pipeline(params)

    image_stem = image_path.stem
    image_dir = image_path.parent
    out_types: list[str] = list(dict.fromkeys(args.out))  # deduplicate, preserve order

    for out_type in out_types:
        out_path = _resolve_output_path(out_type, image_stem, image_dir, args.oname)
        if out_type == "grain":
            analyzer.save_grain_csv(out_path)
        elif out_type == "chord":
            analyzer.save_chord_csv(out_path)
        elif out_type == "stat":
            analyzer.save_result_csv(out_path)
        elif out_type == "image":
            analyzer.save_labeled_image(out_path)
        print(f"  Saved {out_type}: {out_path}")

    # Print summary to stdout
    print()
    if analyzer.grain_df is not None and len(analyzer.grain_df) > 0:
        gs = analyzer.get_grain_statistics()
        print(f"Grain count : {gs.get('count', 0)}")
        mean_d = gs.get("mean_diam_um")
        if mean_d is not None:
            print(f"Mean diameter: {mean_d:.2f} µm")
        else:
            mean_d_px = gs.get("mean_diam_px")
            if mean_d_px is not None:
                print(f"Mean diameter: {mean_d_px:.2f} px (no scale set)")
    if analyzer.chord_df is not None and len(analyzer.chord_df) > 0:
        cs = analyzer.get_chord_statistics()
        astm_g = cs.get("astm_grain_size_g")
        if astm_g is not None:
            print(f"ASTM G       : {astm_g:.2f}")


if __name__ == "__main__":
    main()
