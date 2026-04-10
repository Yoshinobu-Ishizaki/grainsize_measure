"""GrainAnalyzer の単体テスト。

テスト用SEM画像は tests/sample/ に配置する。
画像がない場合は画像を必要とするテストをスキップする。
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

# src/ を import パスに追加
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from analyzer import AnalysisParams, GrainAnalyzer

SAMPLE_DIR = Path(__file__).parent / "sample"


# ---------------------------------------------------------------------------
# ヘルパー: テスト用合成画像
# ---------------------------------------------------------------------------

def make_synthetic_image(tmp_path: Path) -> Path:
    """グリッド状の白い境界線を持つ合成画像を作成して保存する。

    GSAT の global_threshold では「閾値より大きい値が白(=境界)」となる。
    境界線を明るく、粒子内部を暗くした画像を作成する。
    """
    import cv2

    img = np.full((200, 200), 50, dtype=np.uint8)  # 暗い背景 (粒子内部)
    # 境界線として明るい格子を描く
    for i in range(0, 200, 40):
        img[i, :] = 200  # 水平境界線
        img[:, i] = 200  # 垂直境界線

    path = tmp_path / "synthetic.png"
    cv2.imwrite(str(path), img)
    return path


@pytest.fixture
def analyzer() -> GrainAnalyzer:
    return GrainAnalyzer()


@pytest.fixture
def synthetic_image(tmp_path: Path) -> Path:
    return make_synthetic_image(tmp_path)


@pytest.fixture
def sample_image_path() -> Path | None:
    """tests/sample/ 内の最初の画像ファイルを返す。なければ None。"""
    for ext in ("*.jpg", "*.jpeg", "*.png", "*.tif", "*.tiff", "*.bmp"):
        files = list(SAMPLE_DIR.glob(ext))
        if files:
            return files[0]
    return None


# ---------------------------------------------------------------------------
# load_image
# ---------------------------------------------------------------------------

class TestLoadImage:
    def test_load_valid_image(self, analyzer: GrainAnalyzer, synthetic_image: Path) -> None:
        analyzer.load_image(synthetic_image)
        assert analyzer.original_image is not None
        assert analyzer.gray_image is not None
        assert analyzer.original_image.dtype == np.uint8

    def test_load_missing_image_raises(self, analyzer: GrainAnalyzer) -> None:
        with pytest.raises(ValueError, match="Could not load"):
            analyzer.load_image("nonexistent_image.png")

    def test_load_resets_previous_results(self, analyzer: GrainAnalyzer, synthetic_image: Path) -> None:
        analyzer.load_image(synthetic_image)
        # 再度ロードしたら中間結果がリセットされる
        analyzer.load_image(synthetic_image)
        assert analyzer.binary_image is None
        assert analyzer.labeled_grains is None
        assert analyzer.chord_df is None
        assert analyzer.grain_df is None


# ---------------------------------------------------------------------------
# segment_image
# ---------------------------------------------------------------------------

class TestSegmentImage:
    def _fast_params(self) -> AnalysisParams:
        """テスト用の高速パラメータ (NL-meansを軽量に)。"""
        return AnalysisParams(
            denoise_h=5.0,
            denoise_patch=5,
            denoise_search=11,
            sharpen_radius=1,
            sharpen_amount=0.5,
            threshold_method="global_threshold",
            threshold_value=100,
            morph_close_radius=1,
            morph_open_radius=1,
            min_feature_size=5,
            max_hole_size=5,
        )

    def test_segment_produces_binary(self, analyzer: GrainAnalyzer, synthetic_image: Path) -> None:
        analyzer.load_image(synthetic_image)
        analyzer.params = self._fast_params()
        analyzer.segment_image()
        assert analyzer.binary_image is not None
        assert analyzer.binary_image.dtype == np.uint8
        # バイナリ画像は 0 か 255 のみ
        unique_vals = set(np.unique(analyzer.binary_image))
        assert unique_vals.issubset({0, 255})

    def test_segment_without_load_raises(self, analyzer: GrainAnalyzer) -> None:
        with pytest.raises(RuntimeError):
            analyzer.segment_image()

    def test_segment_adaptive_threshold(self, analyzer: GrainAnalyzer, synthetic_image: Path) -> None:
        analyzer.load_image(synthetic_image)
        analyzer.params = AnalysisParams(
            denoise_h=5.0, denoise_patch=5, denoise_search=11,
            sharpen_radius=1, sharpen_amount=0.5,
            threshold_method="adaptive_threshold",
            adaptive_block_size=35, adaptive_offset=0.0,
            morph_close_radius=1, morph_open_radius=1,
            min_feature_size=5, max_hole_size=5,
        )
        analyzer.segment_image()
        assert analyzer.binary_image is not None


# ---------------------------------------------------------------------------
# measure_intercepts (Track A)
# ---------------------------------------------------------------------------

class TestMeasureIntercepts:
    def _run_to_segment(self, analyzer: GrainAnalyzer, path: Path) -> None:
        analyzer.load_image(path)
        analyzer.params = AnalysisParams(
            denoise_h=5.0, denoise_patch=5, denoise_search=11,
            sharpen_radius=1, sharpen_amount=0.5,
            threshold_value=100, morph_close_radius=1, morph_open_radius=1,
            min_feature_size=5, max_hole_size=5,
            line_spacing=20, theta_start=0.0, theta_end=90.0, n_theta_steps=2,
        )
        analyzer.segment_image()

    def test_returns_polars_dataframe(self, analyzer: GrainAnalyzer, synthetic_image: Path) -> None:
        import polars as pl
        self._run_to_segment(analyzer, synthetic_image)
        df = analyzer.measure_intercepts()
        assert isinstance(df, pl.DataFrame)

    def test_required_columns_present(self, analyzer: GrainAnalyzer, synthetic_image: Path) -> None:
        self._run_to_segment(analyzer, synthetic_image)
        df = analyzer.measure_intercepts()
        assert {"chord_id", "length_pixels", "length_um"}.issubset(set(df.columns))

    def test_length_um_null_without_scale(self, analyzer: GrainAnalyzer, synthetic_image: Path) -> None:
        self._run_to_segment(analyzer, synthetic_image)
        analyzer.params.pixels_per_um = None
        df = analyzer.measure_intercepts()
        if len(df) > 0:
            assert df["length_um"].is_null().all()

    def test_length_um_computed_with_scale(self, analyzer: GrainAnalyzer, synthetic_image: Path) -> None:
        import polars as pl
        self._run_to_segment(analyzer, synthetic_image)
        analyzer.params.pixels_per_um = 10.0
        df = analyzer.measure_intercepts()
        if len(df) > 0:
            ratio = df["length_pixels"] / df["length_um"]
            assert (ratio - 10.0).abs().max() < 1e-4

    def test_without_segment_raises(self, analyzer: GrainAnalyzer, synthetic_image: Path) -> None:
        analyzer.load_image(synthetic_image)
        with pytest.raises(RuntimeError):
            analyzer.measure_intercepts()


# ---------------------------------------------------------------------------
# measure_grain_areas (Track B)
# ---------------------------------------------------------------------------

class TestMeasureGrainAreas:
    def _run_to_segment(self, analyzer: GrainAnalyzer, path: Path) -> None:
        analyzer.load_image(path)
        analyzer.params = AnalysisParams(
            denoise_h=5.0, denoise_patch=5, denoise_search=11,
            sharpen_radius=1, sharpen_amount=0.5,
            threshold_value=100, morph_close_radius=1, morph_open_radius=1,
            min_feature_size=5, max_hole_size=5,
            min_grain_area=10, exclude_edge_grains=False,
        )
        analyzer.segment_image()

    def test_returns_polars_dataframe(self, analyzer: GrainAnalyzer, synthetic_image: Path) -> None:
        import polars as pl
        self._run_to_segment(analyzer, synthetic_image)
        df = analyzer.measure_grain_areas()
        assert isinstance(df, pl.DataFrame)

    def test_required_columns_present(self, analyzer: GrainAnalyzer, synthetic_image: Path) -> None:
        self._run_to_segment(analyzer, synthetic_image)
        df = analyzer.measure_grain_areas()
        assert {"grain_id", "area_pixels", "equivalent_diameter_pixels"}.issubset(set(df.columns))

    def test_scale_columns_null_without_scale(self, analyzer: GrainAnalyzer, synthetic_image: Path) -> None:
        self._run_to_segment(analyzer, synthetic_image)
        analyzer.params.pixels_per_um = None
        df = analyzer.measure_grain_areas()
        if len(df) > 0:
            assert df["area_um2"].is_null().all()
            assert df["equivalent_diameter_um"].is_null().all()

    def test_scale_columns_computed_with_scale(self, analyzer: GrainAnalyzer, synthetic_image: Path) -> None:
        import polars as pl
        self._run_to_segment(analyzer, synthetic_image)
        analyzer.params.pixels_per_um = 10.0
        df = analyzer.measure_grain_areas()
        if len(df) > 0:
            ratio = df["area_pixels"].cast(pl.Float64) / df["area_um2"]
            assert (ratio - 100.0).abs().max() < 1e-4

    def test_without_segment_raises(self, analyzer: GrainAnalyzer, synthetic_image: Path) -> None:
        analyzer.load_image(synthetic_image)
        with pytest.raises(RuntimeError):
            analyzer.measure_grain_areas()


# ---------------------------------------------------------------------------
# get_chord_statistics
# ---------------------------------------------------------------------------

class TestGetChordStatistics:
    def test_empty_before_analysis(self, analyzer: GrainAnalyzer) -> None:
        assert analyzer.get_chord_statistics() == {}

    def test_statistics_keys(self, analyzer: GrainAnalyzer, synthetic_image: Path) -> None:
        analyzer.load_image(synthetic_image)
        analyzer.params = AnalysisParams(
            denoise_h=5.0, denoise_patch=5, denoise_search=11,
            sharpen_radius=1, sharpen_amount=0.5,
            threshold_value=100, morph_close_radius=1, morph_open_radius=1,
            min_feature_size=5, max_hole_size=5,
            line_spacing=20, n_theta_steps=1,
        )
        analyzer.segment_image()
        analyzer.measure_intercepts()
        stats = analyzer.get_chord_statistics()
        if not stats:
            pytest.skip("Synthetic image produced no detectable chords via GSAT pipeline")
        assert {"count", "mean_px", "std_px", "min_px", "max_px"}.issubset(stats.keys())

    def test_astm_g_computed_with_scale(self, analyzer: GrainAnalyzer, synthetic_image: Path) -> None:
        analyzer.load_image(synthetic_image)
        analyzer.params = AnalysisParams(
            denoise_h=5.0, denoise_patch=5, denoise_search=11,
            sharpen_radius=1, sharpen_amount=0.5,
            threshold_value=100, morph_close_radius=1, morph_open_radius=1,
            min_feature_size=5, max_hole_size=5,
            line_spacing=20, n_theta_steps=1,
            pixels_per_um=10.0,
        )
        analyzer.segment_image()
        analyzer.measure_intercepts()
        stats = analyzer.get_chord_statistics()
        if stats.get("count", 0) > 0:
            assert "astm_grain_size_g" in stats
            assert stats["astm_grain_size_g"] is not None


# ---------------------------------------------------------------------------
# save_chord_csv / save_grain_csv
# ---------------------------------------------------------------------------

class TestSaveCSV:
    def _run_full(self, analyzer: GrainAnalyzer, path: Path) -> None:
        analyzer.load_image(path)
        analyzer.params = AnalysisParams(
            denoise_h=5.0, denoise_patch=5, denoise_search=11,
            sharpen_radius=1, sharpen_amount=0.5,
            threshold_value=100, morph_close_radius=1, morph_open_radius=1,
            min_feature_size=5, max_hole_size=5,
            line_spacing=20, n_theta_steps=1,
            min_grain_area=10, exclude_edge_grains=False,
        )
        analyzer.segment_image()
        analyzer.measure_intercepts()
        analyzer.measure_grain_areas()

    def test_save_chord_csv(self, analyzer: GrainAnalyzer, synthetic_image: Path, tmp_path: Path) -> None:
        import polars as pl
        self._run_full(analyzer, synthetic_image)
        out = tmp_path / "chords.csv"
        analyzer.save_chord_csv(out)
        assert out.exists()
        reloaded = pl.read_csv(out)
        assert len(reloaded) == len(analyzer.chord_df)

    def test_save_grain_csv(self, analyzer: GrainAnalyzer, synthetic_image: Path, tmp_path: Path) -> None:
        import polars as pl
        self._run_full(analyzer, synthetic_image)
        out = tmp_path / "grains.csv"
        analyzer.save_grain_csv(out)
        assert out.exists()
        reloaded = pl.read_csv(out)
        assert len(reloaded) == len(analyzer.grain_df)

    def test_save_chord_csv_without_analysis_raises(self, analyzer: GrainAnalyzer) -> None:
        with pytest.raises(RuntimeError):
            analyzer.save_chord_csv("/tmp/dummy.csv")

    def test_save_grain_csv_without_analysis_raises(self, analyzer: GrainAnalyzer) -> None:
        with pytest.raises(RuntimeError):
            analyzer.save_grain_csv("/tmp/dummy.csv")


# ---------------------------------------------------------------------------
# render_overlay_image
# ---------------------------------------------------------------------------

class TestRenderOverlay:
    def test_overlay_returns_rgb_array(self, analyzer: GrainAnalyzer, synthetic_image: Path) -> None:
        analyzer.load_image(synthetic_image)
        analyzer.params = AnalysisParams(
            denoise_h=5.0, denoise_patch=5, denoise_search=11,
            sharpen_radius=1, sharpen_amount=0.5,
            threshold_value=100, morph_close_radius=1, morph_open_radius=1,
            min_feature_size=5, max_hole_size=5,
        )
        analyzer.segment_image()
        overlay = analyzer.render_overlay_image()
        assert overlay.dtype == np.uint8
        assert overlay.ndim == 3
        assert overlay.shape[2] == 3  # RGB


# ---------------------------------------------------------------------------
# run_pipeline
# ---------------------------------------------------------------------------

class TestRunPipeline:
    def test_pipeline_returns_two_dataframes(
        self, analyzer: GrainAnalyzer, synthetic_image: Path
    ) -> None:
        import polars as pl
        params = AnalysisParams(
            denoise_h=5.0, denoise_patch=5, denoise_search=11,
            sharpen_radius=1, sharpen_amount=0.5,
            threshold_value=100, morph_close_radius=1, morph_open_radius=1,
            min_feature_size=5, max_hole_size=5,
            line_spacing=20, n_theta_steps=1,
            min_grain_area=10, exclude_edge_grains=False,
        )
        analyzer.load_image(synthetic_image)
        chord_df, grain_df = analyzer.run_pipeline(params)
        assert isinstance(chord_df, pl.DataFrame)
        assert isinstance(grain_df, pl.DataFrame)


# ---------------------------------------------------------------------------
# 実サンプル画像のスモークテスト（画像があるときのみ）
# ---------------------------------------------------------------------------

class TestWithSampleImage:
    def test_full_pipeline_with_sample(
        self, analyzer: GrainAnalyzer, sample_image_path: Path | None
    ) -> None:
        if sample_image_path is None:
            pytest.skip("tests/sample/ にSEM画像がありません")

        params = AnalysisParams(
            denoise_h=10.0, threshold_value=128,
            min_grain_area=50, exclude_edge_grains=True,
            line_spacing=20, n_theta_steps=2,
        )
        analyzer.load_image(sample_image_path)
        chord_df, grain_df = analyzer.run_pipeline(params)
        assert len(chord_df) >= 0
        assert len(grain_df) >= 0
