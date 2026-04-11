from __future__ import annotations

import cv2
import math
import numpy as np
import polars as pl
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from skimage import segmentation, measure, morphology
from skimage.transform import rotate as ski_rotate
from scipy import ndimage

from gsat import ski_driver_functions as sdrv
from gsat import grain_size_functions as gsz


@dataclass
class AnalysisParams:
    # --- Segmentation (GSAT pipeline) ---
    denoise_h: float = 10.0
    denoise_patch: int = 7
    denoise_search: int = 21
    sharpen_radius: int = 3
    sharpen_amount: float = 1.2
    invert_grayscale: bool = False   # invert before segmentation (for dark-boundary images)
    threshold_method: Literal["global_threshold", "adaptive_threshold", "hysteresis_threshold"] = "global_threshold"
    threshold_value: int = 128
    threshold_high: int = 200        # upper threshold for hysteresis method
    adaptive_block_size: int = 35
    adaptive_offset: float = 0.0
    morph_close_radius: int = 3
    morph_open_radius: int = 2
    min_feature_size: int = 50
    max_hole_size: int = 10
    skeletonize: bool = False  # apply skeletonization as final segmentation step (e.g. SEM polished)
    clahe_clip_limit: float = 0.0  # 0.0 = disabled; CLAHE clip limit (typical 1.0–5.0)
    clahe_tile_size: int = 8       # CLAHE tile grid size (NxN)

    # --- Intercept measurement (Track A) ---
    line_spacing: int = 20       # pixels between parallel lines
    row_scan_start: int = 0      # first row to scan (0 = GSAT-compatible)
    theta_start: float = 0.0     # degrees
    theta_end: float = 135.0     # degrees
    n_theta_steps: int = 4
    reskeletonize: bool = False  # re-skeletonize after each rotation (GSAT-compatible)
    pad_for_rotation: bool = False  # pad image before rotation to avoid clipping

    # --- Per-grain area measurement (Track B) ---
    min_grain_area: int = 50
    exclude_edge_grains: bool = True
    edge_buffer: int = 5

    # --- Scale ---
    pixels_per_um: float | None = None
    scale_bar_x1: int | None = None   # detected bar left edge (full-image coords)
    scale_bar_x2: int | None = None   # detected bar right edge
    scale_bar_y: int | None = None    # detected bar center row

    # --- ROI regions (pixel coords, None = full image) ---
    grain_roi: tuple[int, int, int, int] | None = None   # (x, y, w, h)
    marker_roi: tuple[int, int, int, int] | None = None  # (x, y, w, h)


class GrainAnalyzer:
    def __init__(self) -> None:
        self.image_path: Path | None = None
        self.original_image: np.ndarray | None = None   # BGR (3-channel), uint8
        self.gray_image: np.ndarray | None = None       # Grayscale, uint8
        self.binary_image: np.ndarray | None = None     # Binary, uint8 (255=boundary, 0=interior)
        self.labeled_grains: np.ndarray | None = None   # int32 label map
        self.chord_df: pl.DataFrame | None = None       # Track A results
        self.grain_df: pl.DataFrame | None = None       # Track B results
        self.params: AnalysisParams = AnalysisParams()

    def load_image(self, path: str | Path) -> None:
        """Load image and convert to grayscale."""
        self.image_path = Path(path)
        self.original_image = cv2.imread(str(self.image_path), cv2.IMREAD_UNCHANGED)
        if self.original_image is None:
            raise ValueError(f"Could not load image from {self.image_path}")

        if self.original_image.ndim == 3:
            n_channels = self.original_image.shape[2]
            if n_channels == 4:
                self.gray_image = cv2.cvtColor(self.original_image, cv2.COLOR_BGRA2GRAY)
                self.original_image = cv2.cvtColor(self.original_image, cv2.COLOR_BGRA2BGR)
            else:
                self.gray_image = cv2.cvtColor(self.original_image, cv2.COLOR_BGR2GRAY)
        else:
            self.gray_image = self.original_image.copy()

        self.binary_image = None
        self.labeled_grains = None
        self.chord_df = None
        self.grain_df = None

    def segment_image(self) -> None:
        """Run GSAT segmentation pipeline → binary image (255=boundary, 0=interior)."""
        if self.gray_image is None:
            raise RuntimeError("load_image() を先に呼び出してください。")

        p = self.params
        img = self.gray_image.copy()

        # 0. Optionally invert (for optical images where boundaries are dark)
        if p.invert_grayscale:
            img = 255 - img

        # 0a. Optional CLAHE (contrast enhancement for gray-area grains)
        if p.clahe_clip_limit > 0.0:
            clahe = cv2.createCLAHE(
                clipLimit=p.clahe_clip_limit,
                tileGridSize=(p.clahe_tile_size, p.clahe_tile_size)
            )
            img = clahe.apply(img)

        # 1. Denoise
        img = sdrv.apply_driver_denoise(
            img, ["nl_means", p.denoise_h, p.denoise_patch, p.denoise_search], quiet_in=True
        )

        # 2. Sharpen
        img = sdrv.apply_driver_sharpen(
            img, ["unsharp_mask", p.sharpen_radius, p.sharpen_amount], quiet_in=True
        )

        # 3. Threshold → binary
        if p.threshold_method == "global_threshold":
            img = sdrv.apply_driver_thresholding(
                img, ["global_threshold", p.threshold_value], quiet_in=True
            )
        elif p.threshold_method == "hysteresis_threshold":
            img = sdrv.apply_driver_thresholding(
                img, ["hysteresis_threshold", p.threshold_value, p.threshold_high], quiet_in=True
            )
        else:
            img = sdrv.apply_driver_thresholding(
                img, ["adaptive_threshold", p.adaptive_block_size, p.adaptive_offset], quiet_in=True
            )

        # 4. Morphological closing (fill gaps in boundaries); skipped when radius=0
        if p.morph_close_radius > 0:
            img = sdrv.apply_driver_morph(img, [0, 1, p.morph_close_radius], quiet_in=True)

        # 5. Morphological opening (remove isolated noise); skipped when radius=0
        if p.morph_open_radius > 0:
            img = sdrv.apply_driver_morph(img, [1, 1, p.morph_open_radius], quiet_in=True)

        # 6. Remove small features / fill small holes
        # apply_driver_del_features: ["scikit", max_hole_sz, min_feat_sz]
        img = sdrv.apply_driver_del_features(
            img, ["scikit", p.max_hole_size, p.min_feature_size], quiet_in=True
        )

        # 7. Optional skeletonization (e.g. for SEM polished samples)
        if p.skeletonize:
            from skimage.morphology import skeletonize as ski_skeletonize
            from skimage.util import img_as_bool, img_as_ubyte as _ubyte
            img = _ubyte(ski_skeletonize(img_as_bool(img)))

        self.binary_image = img

    def run_segmentation(self, params: AnalysisParams) -> np.ndarray:
        """Step 1: run GSAT pipeline on the full image → binary. Returns binary_image."""
        self.params = params
        self.segment_image()
        return self.binary_image  # type: ignore[return-value]

    def run_measurement(self, params: AnalysisParams) -> tuple[pl.DataFrame, pl.DataFrame]:
        """Step 2: assumes binary_image already set by run_segmentation(). Measures only."""
        self.params = params
        chord_df = self.measure_intercepts()
        grain_df = self.measure_grain_areas()
        return chord_df, grain_df

    def measure_intercepts(self) -> pl.DataFrame:
        """Track A: GSAT intercept method → chord length DataFrame."""
        if self.binary_image is None:
            raise RuntimeError("segment_image() を先に呼び出してください。")

        p = self.params
        height, width = self.binary_image.shape

        all_chord_lengths: list[float] = []

        if p.n_theta_steps <= 1:
            thetas = np.array([p.theta_start])
        else:
            thetas = np.linspace(p.theta_start, p.theta_end, p.n_theta_steps)

        # Optionally pad to avoid clipping during rotation (GSAT-compatible)
        if p.pad_for_rotation:
            circle_min_diameter = int(np.ceil(np.sqrt(height ** 2 + width ** 2)))
            n_pad = int(np.ceil(1.1 * (circle_min_diameter - min(height, width)) * 0.5))
            work_img = np.pad(self.binary_image, n_pad, constant_values=0)
        else:
            work_img = self.binary_image

        for theta in thetas:
            # Rotate image so we can scan horizontal lines
            if abs(theta) < 0.1:
                rotated = work_img
            else:
                rotated = ski_rotate(
                    work_img, theta, preserve_range=True, order=1
                ).astype(np.uint8)
                rotated[rotated >= 128] = 255
                rotated[rotated < 128] = 0

                if p.reskeletonize:
                    from skimage.morphology import skeletonize
                    from skimage.util import img_as_bool, img_as_ubyte
                    rotated = sdrv.apply_driver_morph(rotated, [2, 1, 1], quiet_in=True)
                    rotated = img_as_ubyte(skeletonize(img_as_bool(rotated)))

            rot_h, rot_w = rotated.shape

            for row_idx in range(p.row_scan_start, rot_h, p.line_spacing):
                pixel_arr = rotated[row_idx, :]
                segments = gsz.find_intersections(pixel_arr)
                if len(segments) == 0:
                    continue

                # Build line coord array for measure_line_dist: shape (width, 2) as [row, col]
                line_coords = np.column_stack([
                    np.full(rot_w, row_idx, dtype=np.int32),
                    np.arange(rot_w, dtype=np.int32),
                ])
                distances = gsz.measure_line_dist(segments, line_coords)
                all_chord_lengths.extend(distances.tolist())

        chord_ids = list(range(1, len(all_chord_lengths) + 1))

        if p.pixels_per_um is not None:
            lengths_um: list[float | None] = [l / p.pixels_per_um for l in all_chord_lengths]
        else:
            lengths_um = [None] * len(all_chord_lengths)

        self.chord_df = pl.DataFrame(
            {
                "chord_id": chord_ids,
                "length_pixels": all_chord_lengths,
                "length_um": lengths_um,
            },
            schema={
                "chord_id": pl.Int64,
                "length_pixels": pl.Float64,
                "length_um": pl.Float64,
            },
        )
        return self.chord_df

    def measure_grain_areas(self) -> pl.DataFrame:
        """Track B: Watershed → regionprops → per-grain area DataFrame."""
        if self.binary_image is None:
            raise RuntimeError("segment_image() を先に呼び出してください。")

        p = self.params

        # GSAT binary: 255=boundary → invert so grain interior=True for distance transform
        binary_grains = self.binary_image == 0  # True where grain interior

        distance = ndimage.distance_transform_edt(binary_grains)

        # One marker per connected interior component — guarantees no grain is
        # ever split by watershed regardless of grain size or shape.
        labeled_components = measure.label(binary_grains)
        markers_labeled = np.zeros_like(labeled_components)
        for cid in range(1, labeled_components.max() + 1):
            component_mask = labeled_components == cid
            local_dist = distance * component_mask
            if local_dist.max() > 0:
                peak = np.unravel_index(local_dist.argmax(), local_dist.shape)
                markers_labeled[peak] = cid

        self.labeled_grains = segmentation.watershed(-distance, markers_labeled, mask=binary_grains)

        height, width = self.labeled_grains.shape
        properties = measure.regionprops(self.labeled_grains)

        grain_data: list[dict] = []
        for prop in properties:
            if prop.area < p.min_grain_area:
                continue
            if p.exclude_edge_grains:
                min_row, min_col, max_row, max_col = prop.bbox
                if (
                    min_row <= p.edge_buffer
                    or min_col <= p.edge_buffer
                    or max_row >= height - p.edge_buffer
                    or max_col >= width - p.edge_buffer
                ):
                    continue
            if p.grain_roi is not None:
                rx, ry, rw, rh = p.grain_roi
                cy, cx = prop.centroid
                if not (rx <= cx < rx + rw and ry <= cy < ry + rh):
                    continue
            grain_data.append({
                "grain_id": prop.label,
                "area_pixels": prop.area,
                "equivalent_diameter_pixels": float(prop.equivalent_diameter_area),
                "centroid_x": float(prop.centroid[1]),
                "centroid_y": float(prop.centroid[0]),
                "eccentricity": float(prop.eccentricity),
                "solidity": float(prop.solidity),
            })

        schema = {
            "grain_id": pl.Int64,
            "area_pixels": pl.Int64,
            "equivalent_diameter_pixels": pl.Float64,
            "centroid_x": pl.Float64,
            "centroid_y": pl.Float64,
            "eccentricity": pl.Float64,
            "solidity": pl.Float64,
        }
        df = pl.DataFrame(grain_data, schema=schema) if grain_data else pl.DataFrame(schema=schema)

        if p.pixels_per_um is not None and len(df) > 0:
            ppu = p.pixels_per_um
            df = df.with_columns([
                (pl.col("area_pixels") / (ppu ** 2)).alias("area_um2"),
                (pl.col("equivalent_diameter_pixels") / ppu).alias("equivalent_diameter_um"),
            ])
        else:
            df = df.with_columns([
                pl.lit(None, dtype=pl.Float64).alias("area_um2"),
                pl.lit(None, dtype=pl.Float64).alias("equivalent_diameter_um"),
            ])

        self.grain_df = df
        return df

    def get_chord_statistics(self) -> dict:
        """Chord length statistics + ASTM E112 grain size number G."""
        if self.chord_df is None or len(self.chord_df) == 0:
            return {}

        lengths = self.chord_df["length_pixels"]
        def _f(v) -> float | None:
            return float(v) if v is not None else None

        stats: dict = {
            "count": len(lengths),
            "mean_px": _f(lengths.mean()),
            "std_px": _f(lengths.std()),
            "min_px": _f(lengths.min()),
            "max_px": _f(lengths.max()),
            "mean_um": None,
            "std_um": None,
            "astm_grain_size_g": None,
        }

        p = self.params
        if p.pixels_per_um is not None:
            lengths_um = self.chord_df["length_um"].drop_nulls()
            if len(lengths_um) > 0:
                mean_um = float(lengths_um.mean())
                stats["mean_um"] = mean_um
                stats["std_um"] = _f(lengths_um.std())
                mean_mm = mean_um * 0.001
                if mean_mm > 0:
                    # ASTM E112: G = -6.6457 * log10(L_mm) - 3.298
                    stats["astm_grain_size_g"] = -6.6457 * math.log10(mean_mm) - 3.298

        return stats

    def get_grain_statistics(self) -> dict:
        """Per-grain area statistics."""
        if self.grain_df is None or len(self.grain_df) == 0:
            return {}

        areas = self.grain_df["area_pixels"]
        diams = self.grain_df["equivalent_diameter_pixels"]

        def _f(v) -> float | None:
            return float(v) if v is not None else None

        stats: dict = {
            "count": len(areas),
            "mean_area_px": _f(areas.mean()),
            "std_area_px": _f(areas.std()),
            "mean_diam_px": _f(diams.mean()),
            "std_diam_px": _f(diams.std()),
            "mean_area_um2": None,
            "std_area_um2": None,
            "mean_diam_um": None,
            "std_diam_um": None,
        }

        if "area_um2" in self.grain_df.columns:
            areas_um = self.grain_df["area_um2"].drop_nulls()
            diams_um = self.grain_df["equivalent_diameter_um"].drop_nulls()
            if len(areas_um) > 0:
                stats["mean_area_um2"] = _f(areas_um.mean())
                stats["std_area_um2"] = _f(areas_um.std())
            if len(diams_um) > 0:
                stats["mean_diam_um"] = _f(diams_um.mean())
                stats["std_diam_um"] = _f(diams_um.std())

        return stats

    _GRAIN_PALETTE = [
        [220,  80,  80],   # red
        [ 80, 160, 220],   # blue
        [ 80, 200,  80],   # green
        [220, 180,  60],   # yellow-orange
        [160,  80, 220],   # purple
    ]

    @staticmethod
    def _build_adjacency(labeled: np.ndarray) -> dict[int, set[int]]:
        """Build grain adjacency graph by Voronoi-expanding labels across boundaries.

        Watershed boundaries can be several pixels thick, so direct pixel-neighbour
        checks find nothing.  expand_labels floods each grain label into the zero-
        valued boundary region; after expansion, adjacent grains touch directly and
        a simple 1-step neighbour comparison finds all pairs.
        """
        from skimage.segmentation import expand_labels
        expanded = expand_labels(labeled, distance=20)
        adj: dict[int, set[int]] = {}
        for a, b in [
            (expanded[:-1, :], expanded[1:, :]),
            (expanded[:, :-1], expanded[:, 1:]),
        ]:
            diff = (a != b) & (a > 0) & (b > 0)
            pairs = np.column_stack((a[diff], b[diff]))
            for u, v in set(map(tuple, pairs.tolist())):
                adj.setdefault(u, set()).add(v)
                adj.setdefault(v, set()).add(u)
        return adj

    @staticmethod
    def _greedy_color(adj: dict[int, set[int]], grain_ids: list[int]) -> dict[int, int]:
        """Assign palette indices to grains so no two adjacent grains share a color.

        Uses Welsh-Powell heuristic: process grains in descending degree order.
        Falls back to color 0 if the palette is exhausted (should not happen for
        planar graphs with a 5-color palette).
        """
        sorted_ids = sorted(grain_ids, key=lambda g: len(adj.get(g, set())), reverse=True)
        color_map: dict[int, int] = {}
        n_colors = len(GrainAnalyzer._GRAIN_PALETTE)
        for g in sorted_ids:
            used = {color_map[nb] for nb in adj.get(g, set()) if nb in color_map}
            for c in range(n_colors):
                if c not in used:
                    color_map[g] = c
                    break
            else:
                color_map[g] = 0  # fallback if palette exhausted
        return color_map

    def render_overlay_image(self) -> np.ndarray:
        """Original image + per-grain colors + white boundaries + cyan scan lines."""
        if self.original_image is None or self.binary_image is None:
            raise RuntimeError("解析が完了していません。")

        if self.original_image.ndim == 2:
            gray = self.original_image
        else:
            gray = cv2.cvtColor(self.original_image, cv2.COLOR_BGR2GRAY)
        overlay = cv2.cvtColor(gray, cv2.COLOR_GRAY2RGB).copy()

        # Color only accepted grains (those in grain_df, i.e. within grain_roi and filters)
        if self.labeled_grains is not None and self.grain_df is not None:
            accepted_ids = self.grain_df["grain_id"].to_list()
            adj = self._build_adjacency(self.labeled_grains)
            color_map = self._greedy_color(adj, accepted_ids)
            for i, label_id in enumerate(sorted(accepted_ids)):
                palette_idx = color_map.get(label_id, i % len(self._GRAIN_PALETTE))
                color = np.array(self._GRAIN_PALETTE[palette_idx], dtype=np.float32)
                mask = self.labeled_grains == label_id
                overlay[mask] = (
                    overlay[mask].astype(np.float32) * 0.5 + color * 0.5
                ).astype(np.uint8)

        # Draw boundaries in white on top
        boundary_mask = self.binary_image > 0
        overlay[boundary_mask] = [255, 255, 255]

        # Draw horizontal line scan positions (at theta=0 for visual reference)
        if self.params is not None:
            height = overlay.shape[0]
            start_row = self.params.line_spacing // 2
            for row_idx in range(start_row, height, self.params.line_spacing):
                overlay[row_idx, :] = np.clip(
                    overlay[row_idx, :].astype(np.int32) + [0, 30, 30], 0, 255
                ).astype(np.uint8)

        # Draw grain number for every ~1% of total grain count (sorted top-left to bottom-right)
        if self.grain_df is not None and len(self.grain_df) > 0:
            sorted_grains = self.grain_df.sort(["centroid_y", "centroid_x"])
            total_grains = len(sorted_grains)
            label_interval = max(1, round(total_grains * 0.01))
            h, w = overlay.shape[:2]
            for grain_num, row in enumerate(sorted_grains.iter_rows(named=True), start=1):
                if grain_num % label_interval != 0:
                    continue
                cx = int(row["centroid_x"])
                cy = int(row["centroid_y"])
                if not (0 <= cx < w and 0 <= cy < h):
                    continue
                text = str(grain_num)
                font = cv2.FONT_HERSHEY_SIMPLEX
                font_scale = 0.3
                # Black outline for readability
                for dx, dy in [(-1, -1), (1, -1), (-1, 1), (1, 1)]:
                    cv2.putText(overlay, text, (cx + dx, cy + dy), font,
                                font_scale, (0, 0, 0), 1, cv2.LINE_AA)
                cv2.putText(overlay, text, (cx, cy), font,
                            font_scale, (255, 255, 255), 1, cv2.LINE_AA)

        return overlay

    def save_chord_csv(self, path: str | Path) -> None:
        if self.chord_df is None:
            raise RuntimeError("measure_intercepts() を先に呼び出してください。")
        self.chord_df.write_csv(str(path))

    def save_grain_csv(self, path: str | Path) -> None:
        if self.grain_df is None:
            raise RuntimeError("measure_grain_areas() を先に呼び出してください。")
        self.grain_df.write_csv(str(path))

    def save_result_csv(self, path: str | Path) -> None:
        """Save a combined summary CSV with chord and grain statistics."""
        chord_stats = self.get_chord_statistics()
        grain_stats = self.get_grain_statistics()

        rows = []
        for key, val in [
            ("chord_count", chord_stats.get("count")),
            ("chord_mean_length_um", chord_stats.get("mean_um")),
            ("chord_std_length_um", chord_stats.get("std_um")),
            ("astm_grain_size_g", chord_stats.get("astm_grain_size_g")),
            ("grain_count", grain_stats.get("count")),
            ("grain_mean_area_um2", grain_stats.get("mean_area_um2")),
            ("grain_std_area_um2", grain_stats.get("std_area_um2")),
            ("grain_mean_diameter_um", grain_stats.get("mean_diam_um")),
            ("grain_std_diameter_um", grain_stats.get("std_diam_um")),
        ]:
            rows.append({"metric": key, "value": str(val) if val is not None else ""})

        pl.DataFrame(rows).write_csv(str(path))

    def save_labeled_image(self, path: str | Path) -> None:
        overlay_rgb = self.render_overlay_image()
        overlay_bgr = cv2.cvtColor(overlay_rgb, cv2.COLOR_RGB2BGR)
        cv2.imwrite(str(path), overlay_bgr)

    def run_pipeline(self, params: AnalysisParams) -> tuple[pl.DataFrame, pl.DataFrame]:
        """Full pipeline: segment → intercept measurement + grain area measurement."""
        self.params = params
        self.segment_image()
        chord_df = self.measure_intercepts()
        grain_df = self.measure_grain_areas()
        return chord_df, grain_df
