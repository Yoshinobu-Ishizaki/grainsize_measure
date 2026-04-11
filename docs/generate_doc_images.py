"""
Generate documentation images for parameter_guide.md.

Run from project root:
    uv run docs/generate_doc_images.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import cv2
import numpy as np

# Make src importable
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from analyzer import AnalysisParams, GrainAnalyzer  # noqa: E402

SAMPLE_IMAGE = Path(__file__).parent.parent / "tests/sample/c2600p_asis.png"
OUTPUT_DIR = Path(__file__).parent / "images"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Baseline params (optimized for c2600p_asis.png)
BASELINE = dict(
    invert_grayscale=True,
    denoise_h=0.15,
    denoise_patch=5,
    denoise_search=7,
    sharpen_radius=3,
    sharpen_amount=0.2,
    threshold_method="adaptive_threshold",
    threshold_value=150,
    threshold_high=160,
    adaptive_block_size=15,
    adaptive_offset=0.0,
    morph_close_radius=0,
    morph_open_radius=1,
    min_feature_size=9,
    max_hole_size=10,
    pixels_per_um=0.49,
    grain_roi=(0, 22, 723, 304),
    marker_roi=(581, 399, 133, 18),
    line_spacing=20,
    row_scan_start=0,
    theta_start=0.0,
    theta_end=135.0,
    n_theta_steps=4,
    reskeletonize=False,
    pad_for_rotation=False,
    min_grain_area=50,
    exclude_edge_grains=True,
    edge_buffer=5,
)


def make_params(**overrides) -> AnalysisParams:
    d = {**BASELINE, **overrides}
    return AnalysisParams(**{k: v for k, v in d.items() if k in AnalysisParams.__dataclass_fields__})


def run_segmentation(overrides: dict) -> np.ndarray:
    analyzer = GrainAnalyzer()
    analyzer.load_image(SAMPLE_IMAGE)
    params = make_params(**overrides)
    analyzer.run_segmentation(params)
    return analyzer.binary_image.copy()


def overlay_binary(gray: np.ndarray, binary: np.ndarray) -> np.ndarray:
    """Return RGB image: original gray + red overlay where boundary pixels are."""
    rgb = cv2.cvtColor(gray, cv2.COLOR_GRAY2RGB)
    rgb[binary > 0] = [220, 60, 60]
    return rgb


def hstack_labeled(imgs: list[tuple[str, np.ndarray]], label_height: int = 24) -> np.ndarray:
    """Stack images horizontally with text labels on top."""
    h = imgs[0][1].shape[0]
    w = imgs[0][1].shape[1]
    font = cv2.FONT_HERSHEY_SIMPLEX
    out_parts = []
    for label, img in imgs:
        # Ensure RGB
        if img.ndim == 2:
            img = cv2.cvtColor(img, cv2.COLOR_GRAY2RGB)
        banner = np.zeros((label_height, w, 3), dtype=np.uint8)
        cv2.putText(banner, label, (4, label_height - 6), font, 0.45, (230, 230, 230), 1, cv2.LINE_AA)
        out_parts.append(np.vstack([banner, img]))
    return np.hstack(out_parts)


def save(name: str, img: np.ndarray) -> None:
    path = OUTPUT_DIR / f"{name}.png"
    cv2.imwrite(str(path), cv2.cvtColor(img, cv2.COLOR_RGB2BGR))
    print(f"  saved {path.relative_to(Path(__file__).parent.parent)}")


def load_gray() -> np.ndarray:
    analyzer = GrainAnalyzer()
    analyzer.load_image(SAMPLE_IMAGE)
    return analyzer.gray_image.copy()


# ---------------------------------------------------------------------------
# Crop to grain ROI for compact display
# ---------------------------------------------------------------------------
ROI_X, ROI_Y, ROI_W, ROI_H = BASELINE["grain_roi"]  # type: ignore[misc]


def crop_roi(img: np.ndarray) -> np.ndarray:
    if img.ndim == 2:
        return img[ROI_Y:ROI_Y + ROI_H, ROI_X:ROI_X + ROI_W]
    return img[ROI_Y:ROI_Y + ROI_H, ROI_X:ROI_X + ROI_W, :]


def make_comparison(gray_roi: np.ndarray, *variants: tuple[str, np.ndarray]) -> np.ndarray:
    """
    Build a side-by-side strip.
    variants: list of (label, binary_full_image)
    """
    panels: list[tuple[str, np.ndarray]] = [("Original (gray)", gray_roi)]
    for label, binary in variants:
        b_roi = crop_roi(binary)
        ov = overlay_binary(gray_roi, b_roi)
        panels.append((label, ov))
    return hstack_labeled(panels)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    print("Loading sample image...")
    gray = load_gray()
    gray_roi = crop_roi(gray)

    # ---- Baseline ----
    print("Generating baseline...")
    baseline_bin = run_segmentation({})
    save("baseline", make_comparison(gray_roi, ("Baseline", baseline_bin)))

    # ---- invert_grayscale ----
    print("invert_grayscale...")
    inv_on = run_segmentation({"invert_grayscale": True})
    inv_off = run_segmentation({"invert_grayscale": False})
    save("invert_grayscale", make_comparison(gray_roi,
        ("invert=True (default)", inv_on),
        ("invert=False", inv_off),
    ))

    # ---- denoise_h ----
    print("denoise_h...")
    d_low = run_segmentation({"denoise_h": 0.01})
    d_mid = run_segmentation({"denoise_h": 0.15})
    d_high = run_segmentation({"denoise_h": 5.0})
    save("denoise_h", make_comparison(gray_roi,
        ("h=0.01 (weak)", d_low),
        ("h=0.15 (default)", d_mid),
        ("h=5.0 (strong)", d_high),
    ))

    # ---- sharpen_radius & sharpen_amount ----
    print("sharpen...")
    sh_none = run_segmentation({"sharpen_radius": 0})
    sh_def = run_segmentation({"sharpen_radius": 3, "sharpen_amount": 0.2})
    sh_strong = run_segmentation({"sharpen_radius": 5, "sharpen_amount": 1.5})
    save("sharpen", make_comparison(gray_roi,
        ("radius=0 (off)", sh_none),
        ("r=3, a=0.2 (default)", sh_def),
        ("r=5, a=1.5 (strong)", sh_strong),
    ))

    # ---- threshold_method ----
    print("threshold_method...")
    t_global = run_segmentation({"threshold_method": "global_threshold", "threshold_value": 128})
    t_adaptive = run_segmentation({"threshold_method": "adaptive_threshold", "adaptive_block_size": 15})
    t_hysteresis = run_segmentation({"threshold_method": "hysteresis_threshold",
                                     "threshold_value": 100, "threshold_high": 160})
    save("threshold_method", make_comparison(gray_roi,
        ("global (128)", t_global),
        ("adaptive (block=15)", t_adaptive),
        ("hysteresis (100/160)", t_hysteresis),
    ))

    # ---- threshold_value (global) ----
    print("threshold_value...")
    tv_low = run_segmentation({"threshold_method": "global_threshold", "threshold_value": 80})
    tv_mid = run_segmentation({"threshold_method": "global_threshold", "threshold_value": 128})
    tv_high = run_segmentation({"threshold_method": "global_threshold", "threshold_value": 180})
    save("threshold_value", make_comparison(gray_roi,
        ("value=80 (low)", tv_low),
        ("value=128 (mid)", tv_mid),
        ("value=180 (high)", tv_high),
    ))

    # ---- adaptive_block_size ----
    print("adaptive_block_size...")
    ab_small = run_segmentation({"threshold_method": "adaptive_threshold", "adaptive_block_size": 7})
    ab_mid = run_segmentation({"threshold_method": "adaptive_threshold", "adaptive_block_size": 15})
    ab_large = run_segmentation({"threshold_method": "adaptive_threshold", "adaptive_block_size": 51})
    save("adaptive_block_size", make_comparison(gray_roi,
        ("block=7 (fine)", ab_small),
        ("block=15 (default)", ab_mid),
        ("block=51 (coarse)", ab_large),
    ))

    # ---- morph_close_radius ----
    print("morph_close_radius...")
    mc_0 = run_segmentation({"morph_close_radius": 0})
    mc_1 = run_segmentation({"morph_close_radius": 1})
    mc_3 = run_segmentation({"morph_close_radius": 3})
    save("morph_close_radius", make_comparison(gray_roi,
        ("close=0 (off)", mc_0),
        ("close=1 (default)", mc_1),
        ("close=3", mc_3),
    ))

    # ---- morph_open_radius ----
    print("morph_open_radius...")
    mo_0 = run_segmentation({"morph_open_radius": 0})
    mo_1 = run_segmentation({"morph_open_radius": 1})
    mo_3 = run_segmentation({"morph_open_radius": 3})
    save("morph_open_radius", make_comparison(gray_roi,
        ("open=0 (off)", mo_0),
        ("open=1 (default)", mo_1),
        ("open=3", mo_3),
    ))

    # ---- min_feature_size ----
    print("min_feature_size...")
    mf_1 = run_segmentation({"min_feature_size": 1})
    mf_9 = run_segmentation({"min_feature_size": 9})
    mf_100 = run_segmentation({"min_feature_size": 100})
    save("min_feature_size", make_comparison(gray_roi,
        ("min=1 (keep all)", mf_1),
        ("min=9 (default)", mf_9),
        ("min=100 (aggressive)", mf_100),
    ))

    print("\nDone. Images saved to docs/images/")


if __name__ == "__main__":
    main()
