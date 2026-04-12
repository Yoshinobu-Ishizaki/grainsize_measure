"""
optimize_params.py
==================
Standalone script (not part of the GUI) that uses the analyzer pipeline from
src/analyzer.py to find the parameter combination that maximizes grain
detection for the image and ROI defined in params.json.

Supports both detection modes:
  - threshold  (GSAT pipeline):  Phase 1 invert×method sweep + Phase 2 random search
  - color_region (Felzenszwalb): Phase 1 skipped, Phase 2 random search over color params

Usage:
    uv run scripts/optimize_params.py
    uv run scripts/optimize_params.py --params params.json --out params_optimized.json

Output:
    params_optimized.json  — best parameter set found
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import time
import warnings
from pathlib import Path

warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=UserWarning)

def log(*args, **kwargs):
    kwargs.setdefault("flush", True)
    print(*args, **kwargs)

import cv2
import numpy as np

# Make src/ importable without installing the package
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from analyzer import AnalysisParams, GrainAnalyzer  # noqa: E402


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

# Area range (pixels) that counts as a "real" grain.
# c2600p_asis.png grain_roi is 723×304 = ~220 k pixels.
# Expect roughly 20-500 grains → each 440-11000 px; use a wider window.
MIN_GRAIN_AREA = 200
MAX_GRAIN_AREA = 20_000
MIN_SOLIDITY = 0.35   # reject jagged noise fragments


def score_params(analyzer: GrainAnalyzer, p: AnalysisParams) -> float:
    """Run segmentation + grain measurement, return coverage-weighted quality score.

    Score = grain_count × coverage_ratio (capped at 0.90).
    This rewards finding more area as valid grains, not just over-segmenting
    already-detected regions.
    """
    try:
        analyzer.run_segmentation(p)
        df = analyzer.measure_grain_areas()
    except Exception:
        return 0.0

    if df is None or len(df) == 0:
        return 0.0

    mask = (
        (df["area_pixels"] >= MIN_GRAIN_AREA)
        & (df["area_pixels"] <= MAX_GRAIN_AREA)
        & (df["solidity"] >= MIN_SOLIDITY)
    )
    valid = df.filter(mask)
    grain_count = len(valid)
    if grain_count == 0:
        return 0.0

    roi_area = analyzer.gray_image.shape[0] * analyzer.gray_image.shape[1]
    covered_px = int(valid["area_pixels"].sum())
    coverage = min(covered_px / roi_area, 0.90)
    return grain_count * coverage


# ---------------------------------------------------------------------------
# Parameter space helpers — GSAT (threshold)
# ---------------------------------------------------------------------------

GSAT_SEARCH_SPACE = {
    "denoise_h":           [0.04, 0.045, 0.1, 0.5, 5.0, 10.0],
    "denoise_patch":       [5, 7],
    "denoise_search":      [7, 11, 21],
    "sharpen_radius":      [1, 2, 3],
    "sharpen_amount":      [0.1, 0.2, 0.3, 1.0, 2.0],
    "threshold_value":     [80, 100, 128, 150, 180],
    "threshold_high":      [160, 180, 200, 220],
    "adaptive_block_size": [11, 15, 21, 23, 25, 35, 51, 75],
    "adaptive_offset":     [-10.0, -5.0, 0.0, 5.0, 8.0, 12.0, 15.0],
    "morph_close_radius":  [0, 1, 2, 3],
    "morph_open_radius":   [0, 1, 2],
    "min_feature_size":    [9, 20, 50, 64, 100],
    "max_hole_size":       [4, 10, 25],
    "clahe_clip_limit":    [0.0, 1.0, 2.0, 3.0, 5.0],
    "clahe_tile_size":     [8, 16],
}

# ---------------------------------------------------------------------------
# Parameter space helpers — Felzenszwalb (color_region)
# ---------------------------------------------------------------------------

FELZENSZWALB_SEARCH_SPACE = {
    "color_scale":              [50.0, 100.0, 150.0, 200.0, 300.0, 400.0,
                                 600.0, 800.0, 1000.0, 1500.0, 2000.0],
    "color_sigma":              [0.1, 0.3, 0.5, 0.8, 1.0, 1.5, 2.0, 3.0],
    "color_min_size":           [20, 50, 100, 150, 200, 300, 500],
    "color_morph_close_radius": [0, 1, 2, 3],
}


def dict_to_params(base: AnalysisParams, overrides: dict) -> AnalysisParams:
    """Return a new AnalysisParams with overrides applied."""
    import dataclasses
    d = dataclasses.asdict(base)
    d.update(overrides)
    return AnalysisParams(**d)


def random_sample_gsat(base: AnalysisParams, rng: random.Random) -> AnalysisParams:
    overrides = {k: rng.choice(v) for k, v in GSAT_SEARCH_SPACE.items()}
    return dict_to_params(base, overrides)


def random_sample_felzenszwalb(base: AnalysisParams, rng: random.Random) -> AnalysisParams:
    overrides = {k: rng.choice(v) for k, v in FELZENSZWALB_SEARCH_SPACE.items()}
    return dict_to_params(base, overrides)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser(description="Optimize analyzer params for grain detection.")
    ap.add_argument("--params", default="params.json", help="Input params JSON file")
    ap.add_argument("--out", default="params_optimized.json", help="Output best params JSON")
    ap.add_argument("--phase2-samples", type=int, default=150,
                    help="Random samples per top combo in Phase 2 (default: 150)")
    ap.add_argument("--seed", type=int, default=42, help="Random seed")
    args = ap.parse_args()

    # ------------------------------------------------------------------
    # Load base params
    # ------------------------------------------------------------------
    params_path = Path(args.params)
    with params_path.open() as f:
        raw = json.load(f)

    image_path = raw.pop("image_path", None)
    grain_roi  = raw.pop("grain_roi", None)
    marker_roi = raw.pop("marker_roi", None)

    base_params = AnalysisParams()
    for k, v in raw.items():
        if hasattr(base_params, k):
            setattr(base_params, k, v)
    base_params.grain_roi  = tuple(grain_roi)  if grain_roi  else None
    base_params.marker_roi = tuple(marker_roi) if marker_roi else None

    detection_method = base_params.detection_method
    log(f"Image           : {image_path}")
    log(f"Grain ROI       : {grain_roi}")
    log(f"Detection method: {detection_method}")

    # ------------------------------------------------------------------
    # Load and prepare image (crop to grain ROI)
    # ------------------------------------------------------------------
    analyzer = GrainAnalyzer()
    analyzer.load_image(image_path)

    if grain_roi is not None:
        x, y, w, h = grain_roi
        analyzer.gray_image = analyzer.gray_image[y:y+h, x:x+w]
        # Color-region mode uses original_image; crop it too
        if analyzer.original_image is not None:
            analyzer.original_image = analyzer.original_image[y:y+h, x:x+w]
        # Disable ROI filtering inside measure_grain_areas since we already cropped
        base_params_no_roi = dict_to_params(base_params, {
            "grain_roi": None,
            "marker_roi": None,
        })
    else:
        base_params_no_roi = dict_to_params(base_params, {
            "grain_roi": None,
            "marker_roi": None,
        })

    # ------------------------------------------------------------------
    # Dispatch to method-specific optimizer
    # ------------------------------------------------------------------
    if detection_method == "color_region":
        _optimize_felzenszwalb(analyzer, base_params_no_roi, args,
                               image_path, grain_roi, marker_roi)
    else:
        _optimize_gsat(analyzer, base_params_no_roi, args,
                       image_path, grain_roi, marker_roi)


def _optimize_gsat(
    analyzer: GrainAnalyzer,
    base_params: AnalysisParams,
    args,
    image_path,
    grain_roi,
    marker_roi,
) -> None:
    """GSAT (threshold) optimization: Phase 1 invert×method sweep + Phase 2 random search."""

    # ------------------------------------------------------------------
    # Phase 1: coarse sweep of (invert_grayscale × threshold_method)
    # ------------------------------------------------------------------
    methods   = ["global_threshold", "hysteresis_threshold", "adaptive_threshold"]
    inverts   = [False, True]
    phase1_results: list[tuple[int, dict]] = []

    log("\n=== Phase 1: invert × threshold_method sweep ===")
    phase1_step = 0
    for inv in inverts:
        for method in methods:
            p = dict_to_params(base_params, {
                "invert_grayscale": inv,
                "threshold_method": method,
            })
            s = score_params(analyzer, p)
            label = f"invert={inv}, method={method}"
            log(f"  {label:60s}  score={s:.2f}")
            phase1_results.append((s, {"invert_grayscale": inv, "threshold_method": method}))
            phase1_step += 1
            log(f"##PHASE:1:{phase1_step}:6")

    phase1_results.sort(key=lambda x: x[0], reverse=True)
    top2_combos = [d for _, d in phase1_results[:2]]
    log(f"\nTop combos for Phase 2: {top2_combos}")

    # ------------------------------------------------------------------
    # Phase 2: random search within top combos
    # ------------------------------------------------------------------
    rng = random.Random(args.seed)
    best_score = -1
    best_params: AnalysisParams | None = None

    log(f"\n=== Phase 2: random search ({args.phase2_samples} samples × {len(top2_combos)} combos) ===")
    t0 = time.time()
    total = args.phase2_samples * len(top2_combos)
    iteration = 0

    EARLY_STOP_STREAK = 5
    EARLY_STOP_MIN_IMPROVEMENT = 0.01  # 1%
    no_improve_streak = 0
    stopped_early = False

    for base_combo in top2_combos:
        if stopped_early:
            break
        base_for_phase2 = dict_to_params(base_params, base_combo)
        for _ in range(args.phase2_samples):
            iteration += 1
            log(f"##PHASE:2:{iteration}:{total}")
            p = random_sample_gsat(base_for_phase2, rng)
            # Enforce adaptive_block_size must be odd
            if p.threshold_method == "adaptive_threshold" and p.adaptive_block_size % 2 == 0:
                p.adaptive_block_size += 1
            s = score_params(analyzer, p)
            if s >= best_score * (1 + EARLY_STOP_MIN_IMPROVEMENT):
                no_improve_streak = 0
            else:
                no_improve_streak += 1
            if s > best_score:
                best_score = s
                best_params = p
                elapsed = time.time() - t0
                log(f"  [{iteration:4d}/{total}] New best score={s:.2f}  "
                      f"invert={p.invert_grayscale}, method={p.threshold_method}, "
                      f"h={p.denoise_h}, close={p.morph_close_radius}, "
                      f"open={p.morph_open_radius}, clahe={p.clahe_clip_limit}  ({elapsed:.1f}s)")
                log(f"##BEST:{s:.4f}")
            if no_improve_streak >= EARLY_STOP_STREAK:
                log(f"  Early stop: no ≥1% improvement for {EARLY_STOP_STREAK} consecutive iterations.")
                stopped_early = True
                break

    _save_result(best_score, best_params, image_path, grain_roi, marker_roi, args.out)

    if best_params is not None:
        log(f"\nKey params (GSAT):")
        import dataclasses
        best_dict = dataclasses.asdict(best_params)
        best_dict["image_path"] = image_path
        best_dict["grain_roi"]  = grain_roi
        best_dict["marker_roi"] = marker_roi
        for k in ["invert_grayscale", "clahe_clip_limit", "clahe_tile_size",
                  "denoise_h", "sharpen_amount",
                  "threshold_method", "threshold_value", "threshold_high",
                  "adaptive_block_size", "adaptive_offset",
                  "morph_close_radius", "morph_open_radius",
                  "min_feature_size", "max_hole_size"]:
            log(f"  {k:30s} = {best_dict[k]}")


def _optimize_felzenszwalb(
    analyzer: GrainAnalyzer,
    base_params: AnalysisParams,
    args,
    image_path,
    grain_roi,
    marker_roi,
) -> None:
    """Felzenszwalb (color_region) optimization: Phase 1 skipped, Phase 2 random search."""

    # Phase 1 skipped — emit a completion marker so the GUI progress dialog advances
    log("\n=== Phase 1: skipped (color_region mode uses Felzenszwalb, no invert×method sweep) ===")
    log("##PHASE:1:1:1")

    # ------------------------------------------------------------------
    # Phase 2: random search over Felzenszwalb parameter space
    # ------------------------------------------------------------------
    rng = random.Random(args.seed)
    best_score = -1
    best_params: AnalysisParams | None = None

    total = args.phase2_samples
    log(f"\n=== Phase 2: random search ({total} samples, Felzenszwalb) ===")
    t0 = time.time()

    EARLY_STOP_STREAK = 10
    EARLY_STOP_MIN_IMPROVEMENT = 0.01  # 1%
    no_improve_streak = 0

    for iteration in range(1, total + 1):
        log(f"##PHASE:2:{iteration}:{total}")
        p = random_sample_felzenszwalb(base_params, rng)
        s = score_params(analyzer, p)
        if s >= best_score * (1 + EARLY_STOP_MIN_IMPROVEMENT):
            no_improve_streak = 0
        else:
            no_improve_streak += 1
        if s > best_score:
            best_score = s
            best_params = p
            elapsed = time.time() - t0
            log(f"  [{iteration:4d}/{total}] New best score={s:.2f}  "
                  f"scale={p.color_scale}, sigma={p.color_sigma}, "
                  f"min_size={p.color_min_size}, close={p.color_morph_close_radius}  ({elapsed:.1f}s)")
            log(f"##BEST:{s:.4f}")
        if no_improve_streak >= EARLY_STOP_STREAK:
            log(f"  Early stop: no ≥1% improvement for {EARLY_STOP_STREAK} consecutive iterations.")
            break

    _save_result(best_score, best_params, image_path, grain_roi, marker_roi, args.out)

    if best_params is not None:
        log(f"\nKey params (Felzenszwalb):")
        import dataclasses
        best_dict = dataclasses.asdict(best_params)
        for k in ["color_scale", "color_sigma", "color_min_size", "color_morph_close_radius"]:
            log(f"  {k:30s} = {best_dict[k]}")


def _save_result(
    best_score: float,
    best_params: AnalysisParams | None,
    image_path,
    grain_roi,
    marker_roi,
    out_path_str: str,
) -> None:
    log(f"\n=== Result ===")
    log(f"Best score : {best_score:.2f} (grain_count × coverage, capped at 0.90)")
    if best_params is None:
        log("No valid params found.")
        log("##DONE")
        return

    import dataclasses
    best_dict = dataclasses.asdict(best_params)

    # Restore image_path and ROIs from original params.json
    best_dict["image_path"] = image_path
    best_dict["grain_roi"]  = grain_roi
    best_dict["marker_roi"] = marker_roi

    out_path = Path(out_path_str)
    with out_path.open("w") as f:
        json.dump(best_dict, f, indent=2)
    log(f"Saved best params → {out_path}")
    log("##DONE")


if __name__ == "__main__":
    main()
