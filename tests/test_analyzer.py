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
# ヘルパー: テスト用合成画像（暗い背景に明るい粒子を散在）
# ---------------------------------------------------------------------------

def make_synthetic_image(tmp_path: Path) -> Path:
    """境界が明確な合成SEM画像を作成して保存する。"""
    import cv2

    img = np.zeros((200, 200), dtype=np.uint8)
    # 9個の白い円（粒子相当）を配置
    for row in range(3):
        for col in range(3):
            cx, cy = 30 + col * 70, 30 + row * 70
            cv2.circle(img, (cx, cy), 20, 200, -1)

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
        analyzer.preprocess_image()
        analyzer.segment_grains()
        # 再度ロードしたら中間結果がリセットされる
        analyzer.load_image(synthetic_image)
        assert analyzer.processed_image is None
        assert analyzer.labeled_grains is None
        assert analyzer.grain_properties is None


# ---------------------------------------------------------------------------
# preprocess_image
# ---------------------------------------------------------------------------

class TestPreprocessImage:
    def test_preprocess_changes_image(self, analyzer: GrainAnalyzer, synthetic_image: Path) -> None:
        analyzer.load_image(synthetic_image)
        before = analyzer.gray_image.copy()
        analyzer.preprocess_image()
        assert analyzer.processed_image is not None
        assert not np.array_equal(analyzer.processed_image, before)

    def test_preprocess_output_is_uint8(self, analyzer: GrainAnalyzer, synthetic_image: Path) -> None:
        analyzer.load_image(synthetic_image)
        analyzer.preprocess_image()
        assert analyzer.processed_image.dtype == np.uint8

    def test_preprocess_without_load_raises(self, analyzer: GrainAnalyzer) -> None:
        with pytest.raises(RuntimeError):
            analyzer.preprocess_image()


# ---------------------------------------------------------------------------
# segment_grains
# ---------------------------------------------------------------------------

class TestSegmentGrains:
    @pytest.mark.parametrize("method", ["otsu", "adaptive", "manual"])
    def test_segment_produces_labels(
        self, analyzer: GrainAnalyzer, synthetic_image: Path, method: str
    ) -> None:
        analyzer.load_image(synthetic_image)
        analyzer.params = AnalysisParams(threshold_method=method, min_distance=5)
        analyzer.preprocess_image()
        analyzer.segment_grains()
        assert analyzer.labeled_grains is not None
        n_labels = len(np.unique(analyzer.labeled_grains)) - 1  # 0=背景を除く
        assert n_labels > 0

    def test_segment_without_preprocess_raises(
        self, analyzer: GrainAnalyzer, synthetic_image: Path
    ) -> None:
        analyzer.load_image(synthetic_image)
        with pytest.raises(RuntimeError):
            analyzer.segment_grains()


# ---------------------------------------------------------------------------
# calculate_grain_properties
# ---------------------------------------------------------------------------

class TestCalculateGrainProperties:
    def _run_up_to_segment(self, analyzer: GrainAnalyzer, path: Path) -> None:
        analyzer.load_image(path)
        analyzer.preprocess_image()
        analyzer.segment_grains()

    def test_returns_polars_dataframe(
        self, analyzer: GrainAnalyzer, synthetic_image: Path
    ) -> None:
        import polars as pl
        self._run_up_to_segment(analyzer, synthetic_image)
        df = analyzer.calculate_grain_properties()
        assert isinstance(df, pl.DataFrame)

    def test_required_columns_present(
        self, analyzer: GrainAnalyzer, synthetic_image: Path
    ) -> None:
        self._run_up_to_segment(analyzer, synthetic_image)
        df = analyzer.calculate_grain_properties()
        required = {"grain_id", "area_pixels", "equivalent_diameter_pixels"}
        assert required.issubset(set(df.columns))

    def test_scale_columns_null_when_no_scale(
        self, analyzer: GrainAnalyzer, synthetic_image: Path
    ) -> None:
        analyzer.params = AnalysisParams(pixels_per_um=None)
        self._run_up_to_segment(analyzer, synthetic_image)
        df = analyzer.calculate_grain_properties()
        if len(df) > 0:
            assert df["area_um2"].is_null().all()
            assert df["equivalent_diameter_um"].is_null().all()

    def test_scale_columns_computed_when_scale_set(
        self, analyzer: GrainAnalyzer, synthetic_image: Path
    ) -> None:
        import polars as pl
        analyzer.params = AnalysisParams(pixels_per_um=10.0, min_area=10, exclude_edge_grains=False)
        self._run_up_to_segment(analyzer, synthetic_image)
        df = analyzer.calculate_grain_properties()
        if len(df) > 0:
            assert not df["area_um2"].is_null().any()
            ratio = df["area_pixels"].cast(pl.Float64) / df["area_um2"]
            assert (ratio - 100.0).abs().max() < 1e-4

    def test_without_segment_raises(
        self, analyzer: GrainAnalyzer, synthetic_image: Path
    ) -> None:
        analyzer.load_image(synthetic_image)
        with pytest.raises(RuntimeError):
            analyzer.calculate_grain_properties()


# ---------------------------------------------------------------------------
# get_area_statistics
# ---------------------------------------------------------------------------

class TestGetAreaStatistics:
    def test_statistics_keys(self, analyzer: GrainAnalyzer, synthetic_image: Path) -> None:
        analyzer.load_image(synthetic_image)
        analyzer.params = AnalysisParams(min_area=10, exclude_edge_grains=False)
        analyzer.preprocess_image()
        analyzer.segment_grains()
        analyzer.calculate_grain_properties()
        stats = analyzer.get_area_statistics()
        expected_keys = {"count", "mean", "median", "std", "min", "max", "q25", "q75"}
        assert expected_keys.issubset(stats.keys())

    def test_empty_properties_returns_empty_dict(self, analyzer: GrainAnalyzer) -> None:
        assert analyzer.get_area_statistics() == {}


# ---------------------------------------------------------------------------
# save_csv
# ---------------------------------------------------------------------------

class TestSaveCSV:
    def test_save_csv_creates_file(
        self, analyzer: GrainAnalyzer, synthetic_image: Path, tmp_path: Path
    ) -> None:
        import polars as pl
        analyzer.load_image(synthetic_image)
        analyzer.params = AnalysisParams(min_area=10, exclude_edge_grains=False)
        analyzer.preprocess_image()
        analyzer.segment_grains()
        analyzer.calculate_grain_properties()

        out = tmp_path / "results.csv"
        analyzer.save_csv(out)
        assert out.exists()

        reloaded = pl.read_csv(out)
        assert len(reloaded) == len(analyzer.grain_properties)

    def test_save_csv_without_analysis_raises(
        self, analyzer: GrainAnalyzer
    ) -> None:
        with pytest.raises(RuntimeError):
            analyzer.save_csv("/tmp/dummy.csv")


# ---------------------------------------------------------------------------
# render_overlay_image
# ---------------------------------------------------------------------------

class TestRenderOverlay:
    def test_overlay_returns_rgb_array(
        self, analyzer: GrainAnalyzer, synthetic_image: Path
    ) -> None:
        analyzer.load_image(synthetic_image)
        analyzer.params = AnalysisParams(min_area=10, exclude_edge_grains=False)
        analyzer.preprocess_image()
        analyzer.segment_grains()
        analyzer.calculate_grain_properties()
        overlay = analyzer.render_overlay_image()
        assert overlay.dtype == np.uint8
        assert overlay.ndim == 3
        assert overlay.shape[2] == 3  # RGB


# ---------------------------------------------------------------------------
# 実サンプル画像のスモークテスト（画像があるときのみ）
# ---------------------------------------------------------------------------

class TestWithSampleImage:
    def test_full_pipeline_with_sample(
        self, analyzer: GrainAnalyzer, sample_image_path: Path | None
    ) -> None:
        if sample_image_path is None:
            pytest.skip("tests/sample/ にSEM画像がありません")

        params = AnalysisParams(min_area=50, exclude_edge_grains=True)
        analyzer.load_image(sample_image_path)
        df = analyzer.run_pipeline(params)
        assert len(df) >= 0  # 粒子数は0以上
