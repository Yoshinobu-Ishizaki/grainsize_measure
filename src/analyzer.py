from __future__ import annotations

import cv2
import numpy as np
import polars as pl
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from skimage import filters, segmentation, measure, morphology
from skimage.feature import peak_local_max
from skimage.util import img_as_ubyte
from scipy import ndimage


@dataclass
class AnalysisParams:
    gaussian_sigma: float = 1.0
    contrast_factor: float = 1.2
    threshold_method: Literal["otsu", "adaptive", "manual"] = "otsu"
    manual_threshold: int = 128
    min_distance: int = 10
    min_area: int = 50
    exclude_edge_grains: bool = True
    edge_buffer: int = 5
    pixels_per_um: float | None = None  # None = ピクセル単位のみ


class GrainAnalyzer:
    def __init__(self) -> None:
        self.image_path: Path | None = None
        self.original_image: np.ndarray | None = None   # BGR, uint8
        self.gray_image: np.ndarray | None = None       # グレースケール, uint8
        self.processed_image: np.ndarray | None = None  # 前処理済みグレースケール, uint8
        self.labeled_grains: np.ndarray | None = None   # int32 ラベルマップ
        self.grain_properties: pl.DataFrame | None = None
        self.params: AnalysisParams = AnalysisParams()

    def load_image(self, path: str | Path) -> None:
        """画像を読み込んでグレースケールに変換する。"""
        self.image_path = Path(path)
        self.original_image = cv2.imread(str(self.image_path))
        if self.original_image is None:
            raise ValueError(f"Could not load image from {self.image_path}")

        if len(self.original_image.shape) == 3:
            self.gray_image = cv2.cvtColor(self.original_image, cv2.COLOR_BGR2GRAY)
        else:
            self.gray_image = self.original_image.copy()

        self.processed_image = None
        self.labeled_grains = None
        self.grain_properties = None

    def preprocess_image(self) -> None:
        """ガウシアンブラーとコントラスト強調でセグメント精度を上げる。"""
        if self.gray_image is None:
            raise RuntimeError("load_image() を先に呼び出してください。")

        p = self.params

        # filters.gaussian は float64 の [0,1] 範囲を返すため img_as_ubyte で uint8 に戻す
        blurred = filters.gaussian(self.gray_image, sigma=p.gaussian_sigma)
        blurred_u8 = img_as_ubyte(blurred)

        # コントラスト強調
        enhanced = np.clip(blurred_u8.astype(np.float32) * p.contrast_factor, 0, 255).astype(np.uint8)

        # ヒストグラム平坦化
        self.processed_image = cv2.equalizeHist(enhanced)

    def segment_grains(self) -> None:
        """Watershedアルゴリズムで粒子をセグメントする。"""
        if self.processed_image is None:
            raise RuntimeError("preprocess_image() を先に呼び出してください。")

        p = self.params

        if p.threshold_method == "otsu":
            threshold = filters.threshold_otsu(self.processed_image)
            binary = self.processed_image > threshold
        elif p.threshold_method == "adaptive":
            adaptive_thresh = filters.threshold_local(self.processed_image, block_size=35, offset=10)
            binary = self.processed_image > adaptive_thresh
        else:  # manual
            binary = self.processed_image > p.manual_threshold

        binary = morphology.closing(binary, morphology.disk(2))
        binary = morphology.opening(binary, morphology.disk(1))

        distance = ndimage.distance_transform_edt(binary)

        coordinates = peak_local_max(
            distance,
            min_distance=p.min_distance,
            threshold_abs=0.3 * distance.max() if distance.max() > 0 else 0,
        )
        markers = np.zeros_like(distance, dtype=bool)
        if len(coordinates) > 0:
            markers[tuple(coordinates.T)] = True
        markers = measure.label(markers)

        self.labeled_grains = segmentation.watershed(-distance, markers, mask=binary)

    def calculate_grain_properties(self) -> pl.DataFrame:
        """各粒子のプロパティを計算してDataFrameで返す。"""
        if self.labeled_grains is None:
            raise RuntimeError("segment_grains() を先に呼び出してください。")

        p = self.params
        properties = measure.regionprops(self.labeled_grains)
        height, width = self.labeled_grains.shape

        grain_data: list[dict] = []
        for prop in properties:
            if prop.area < p.min_area:
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

            grain_data.append({
                "grain_id": prop.label,
                "area_pixels": prop.area,
                "centroid_x": float(prop.centroid[1]),
                "centroid_y": float(prop.centroid[0]),
                "major_axis_length": float(prop.axis_major_length),
                "minor_axis_length": float(prop.axis_minor_length),
                "eccentricity": float(prop.eccentricity),
                "solidity": float(prop.solidity),
                "equivalent_diameter_pixels": float(prop.equivalent_diameter_area),
                "perimeter": float(prop.perimeter),
            })

        df = pl.DataFrame(grain_data) if grain_data else pl.DataFrame(schema={
            "grain_id": pl.Int64,
            "area_pixels": pl.Int64,
            "centroid_x": pl.Float64,
            "centroid_y": pl.Float64,
            "major_axis_length": pl.Float64,
            "minor_axis_length": pl.Float64,
            "eccentricity": pl.Float64,
            "solidity": pl.Float64,
            "equivalent_diameter_pixels": pl.Float64,
            "perimeter": pl.Float64,
        })

        # スケール設定がある場合は実寸列を追加
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

        self.grain_properties = df
        return df

    def get_area_statistics(self) -> dict:
        """面積分布の統計量を返す。"""
        if self.grain_properties is None or len(self.grain_properties) == 0:
            return {}

        areas = self.grain_properties["area_pixels"]
        return {
            "count": len(areas),
            "mean": float(areas.mean()),
            "median": float(areas.median()),
            "std": float(areas.std()),
            "min": float(areas.min()),
            "max": float(areas.max()),
            "q25": float(areas.quantile(0.25, interpolation="nearest")),
            "q75": float(areas.quantile(0.75, interpolation="nearest")),
        }

    def render_overlay_image(self) -> np.ndarray:
        """元画像に粒子境界と粒子IDを重ねたRGB画像を返す。"""
        if self.original_image is None or self.labeled_grains is None or self.grain_properties is None:
            raise RuntimeError("解析が完了していません。")

        # BGR → RGB
        overlay = cv2.cvtColor(self.original_image, cv2.COLOR_BGR2RGB).copy()

        # 粒子境界を緑色で描画
        boundary_mask = segmentation.find_boundaries(self.labeled_grains, mode="outer")
        overlay[boundary_mask] = [0, 220, 0]

        # 採用された粒子のcentroidにIDをテキスト注釈
        accepted_ids = set(self.grain_properties["grain_id"].to_list())
        for prop in measure.regionprops(self.labeled_grains):
            if prop.label in accepted_ids:
                cy, cx = int(prop.centroid[0]), int(prop.centroid[1])
                cv2.putText(
                    overlay,
                    str(prop.label),
                    (cx, cy),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.35,
                    (255, 255, 0),
                    1,
                    cv2.LINE_AA,
                )

        return overlay

    def save_csv(self, path: str | Path) -> None:
        """粒子プロパティをCSVに保存する。"""
        if self.grain_properties is None:
            raise RuntimeError("calculate_grain_properties() を先に呼び出してください。")
        self.grain_properties.write_csv(str(path))

    def save_labeled_image(self, path: str | Path) -> None:
        """overlay画像をファイルに保存する。"""
        overlay_rgb = self.render_overlay_image()
        # OpenCV は BGR で保存する
        overlay_bgr = cv2.cvtColor(overlay_rgb, cv2.COLOR_RGB2BGR)
        cv2.imwrite(str(path), overlay_bgr)

    def run_pipeline(self, params: AnalysisParams) -> pl.DataFrame:
        """前処理→セグメント→プロパティ計算を一括実行する。"""
        self.params = params
        self.preprocess_image()
        self.segment_grains()
        return self.calculate_grain_properties()
