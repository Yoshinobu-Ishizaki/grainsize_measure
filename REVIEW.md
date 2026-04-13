# Code Review & Improvement Plan

**Date**: 2026-04-13  
**Reviewer**: Claude Opus 4.6  
**Version**: 0.24.2

---

## Executive Summary

The codebase is well-architected overall with clean separation between the GSAT library, the analyzer engine, and the GUI layer. The watershed-based grain detection algorithm is sound. The main opportunities are: (1) vectorizing hot-path Python loops in GSAT functions, (2) reducing unnecessary memory copies in image processing, (3) expanding test coverage, and (4) cleaning up dependencies.

---

## Part 1: Performance Issues

### P1. `grain_size_functions.py:measure_line_dist()` — Loop can be vectorized

**File**: `src/gsat/grain_size_functions.py:223-238`  
**Impact**: Medium — called once per scan angle per image, but each call iterates all segments  

The Python `for` loop computes Euclidean distances one segment at a time. This can be replaced with a single NumPy operation:

```python
# Current (loop)
for m, cur_seg in enumerate(segs_local_arr_in):
    ...
    seg_dist_arr_out[m] = np.sqrt(...)

# Vectorized replacement
starts = segs_local_arr_in[:, 0]
ends = segs_local_arr_in[:, 1]
seg_dist_arr_out = np.hypot(
    line_global_r[ends] - line_global_r[starts],
    line_global_c[ends] - line_global_c[starts],
)
```

### P2. `grain_size_functions.py:measure_circular_dist()` — Same loop pattern

**File**: `src/gsat/grain_size_functions.py:274-306`  
**Impact**: Medium — same pattern, vectorizable with batch radial vectors and `np.arccos`  

```python
starts = segs_local_arr_in[:, 0]
ends = segs_local_arr_in[:, 1]
vec_a = circ_global_arr_in[starts] - circ_center  # shape (N, 2)
vec_b = circ_global_arr_in[ends] - circ_center
mag_a = np.linalg.norm(vec_a, axis=1)
mag_b = np.linalg.norm(vec_b, axis=1)
unit_a = vec_a / mag_a[:, None]
unit_b = vec_b / mag_b[:, None]
dots = np.clip(np.sum(unit_a * unit_b, axis=1), -1, 1)
thetas = np.abs(np.arccos(dots))
radii = (mag_a + mag_b) / 2.0
seg_dist_arr_out = radii * thetas
```

### P3. `grain_size_functions.py:find_intersections()` — `np.arange` in Python loop

**File**: `src/gsat/grain_size_functions.py:32`  
**Impact**: Low-medium — `np.arange()` creates a NumPy array for a simple range iteration. Replace with `range()`. The entire function could be vectorized with `np.diff()` to find transitions, but this touches GSAT original code and needs careful validation.

### P4. `grain_size_functions.py:make_continuous_line()` — O(N²) distance matrix

**File**: `src/gsat/grain_size_functions.py:93`  
**Impact**: Low — N is typically small (boundary pixels in a single scan line), but `squareform(pdist(...))` creates a full NxN matrix just to find one endpoint. Could use `np.partition` instead of full sort at line 98.

### P5. `image_viewer.py:337` — Double pixmap copy

**File**: `src/gui/image_viewer.py:337`  
**Impact**: Medium — `QPixmap.fromImage(q_img.copy())` creates two copies. Remove the `.copy()`.

### P6. `settings_dialog.py:1360` — Color conversion on UI thread

**File**: `src/gui/settings_dialog.py` (around line 1360)  
**Impact**: Medium — `cv2.cvtColor(binary, cv2.COLOR_GRAY2RGB)` blocks the UI. Should be done inside the worker thread before emitting `finished`.

### P7. Excessive `.copy()` in GSAT wrappers

**Files**: `src/gsat/cv_processing_wrappers.py:47+`, `src/gsat/cv_driver_functions.py:149+`  
**Impact**: Low — nearly every function copies the entire image on entry. For large images this doubles memory per pipeline step. Where the caller discards the input, in-place would be safe.

---

## Part 2: Algorithm Improvements

### A1. Consider connected-component–based grain detection as alternative

The current approach (threshold → watershed) is solid. An alternative for polished-section images with clear boundaries is:

1. Threshold to get binary boundary image (existing step)
2. Morphological close to seal small gaps (existing step)
3. `ndimage.label()` on the inverted binary to get connected components directly
4. Skip watershed entirely

This would be faster for images where boundaries are already well-closed. Could be offered as a "fast mode" option.

### A2. Adaptive CLAHE tile size

Currently `clahe_tile_size` is a fixed user parameter. It could be auto-set to approximately 1 grain diameter (estimated from a quick coarse segmentation pass), making CLAHE more effective without manual tuning.

### A3. Skeletonize boundary before watershed

For images with thick grain boundaries, skeletonizing the boundary image before watershed would produce more accurate grain areas (boundaries consume fewer pixels). The `skeletonize` option already exists but is applied in a specific context — consider making it a standard pipeline step for thick-boundary images.

---

## Part 3: Code Quality Issues

### Q1. Unused dependency: PyWavelets

**File**: `pyproject.toml:16`  
**Action**: Remove `"PyWavelets>=1.6"` — grep confirms it's never imported anywhere in `src/`.

### Q2. Unused top-level import: `morphology`

**File**: `src/analyzer.py:11`  
**Action**: Change `from skimage import segmentation, measure, morphology` to `from skimage import segmentation, measure` — `morphology` is imported locally where needed (lines 191, 291).

### Q3. Duplicate easyocr in dependencies

**File**: `pyproject.toml`  
**Action**: `easyocr` appears in both core `dependencies` and `[project.optional-dependencies] ocr`. Remove from one location.

### Q4. Python version mismatch

**File**: `pyproject.toml:6`  
**Action**: `requires-python = ">=3.13"` but features used are compatible with 3.11+. Either relax to `>=3.11` or document why 3.13 is required.

### Q5. `settings_dialog.py` is 1710 lines

**Action**: Extract worker classes (lines 53-135) into `gui/workers.py`. Extract progress dialogs (lines 141-266) into `gui/dialogs.py`. This reduces the main file to ~1400 lines and improves navigability.

### Q6. Repetitive `_updating_roi` guard pattern

**File**: `src/gui/settings_dialog.py` (8 occurrences)  
**Action**: Replace with a context manager:
```python
@contextmanager
def _silent_update(self):
    self._updating_roi = True
    try:
        yield
    finally:
        self._updating_roi = False
```

### Q7. Missing stderr capture from optimizer subprocess

**File**: `src/gui/settings_dialog.py:1225`  
**Action**: Connect `_optimizer_proc.readyReadStandardError` to a handler that logs or displays errors.

---

## Part 4: Test Coverage Gaps

### T1. `segment_by_color()` — ZERO test coverage

**File**: `src/analyzer.py:199-232`  
**Impact**: HIGH — entire Felzenszwalb detection mode untested  
**Action**: Add tests using a synthetic color-grid image (e.g., 4 colored quadrants) to verify boundary detection and grain count.

### T2. `get_grain_statistics()` — untested

**File**: `src/analyzer.py:484-517`  
**Action**: Add test that runs full pipeline and verifies statistic keys and value ranges.

### T3. `run_segmentation()` / `run_measurement()` — untested dispatchers

**File**: `src/analyzer.py:234-248`  
**Action**: Add tests for both detection modes through these entry points.

### T4. Flaky test: `test_statistics_keys`

**File**: `tests/test_analyzer.py:259`  
**Action**: Fix synthetic image so it reliably produces detectable chords (currently skipped).

### T5. No scale_detector tests

**File**: `src/scale_detector.py`  
**Action**: Add tests using sample images with known scale bars.

---

## Part 5: Improvement Plan (for coder agents)

### Phase 1: Quick wins (no behavior change)

1. **Remove PyWavelets** from `pyproject.toml` dependencies
2. **Remove unused `morphology` import** from `analyzer.py:11`
3. **Fix double pixmap copy** in `image_viewer.py:337` — remove `.copy()`
4. **Fix `np.arange` → `range`** in `grain_size_functions.py:32`
5. **Consolidate easyocr** dependency definition in `pyproject.toml`

### Phase 2: Performance vectorization

6. **Vectorize `measure_line_dist()`** in `grain_size_functions.py:223-238` — replace Python loop with `np.hypot()` batch operation (see P1 above for exact code)
7. **Vectorize `measure_circular_dist()`** in `grain_size_functions.py:274-306` — replace loop with batch vector operations (see P2 above for exact code)
8. **Move `cv2.cvtColor` to worker thread** in `settings_dialog.py` — do gray→RGB conversion inside `_ImageProcessWorker.run()` before emitting result

### Phase 3: Test coverage

9. **Add `test_segment_by_color()`** — create synthetic 2x2 color grid, run `segment_by_color()`, assert 4 grains detected
10. **Add `test_get_grain_statistics()`** — run pipeline, verify keys `["mean_area_px", "std_area_px", "count", ...]` present and values > 0
11. **Add `test_run_segmentation_both_modes()`** — verify dispatcher routes to correct method
12. **Add `test_scale_detector()`** — use sample image with known scale bar, assert detected value within tolerance
13. **Fix `test_statistics_keys`** — adjust synthetic image to produce measurable chords

### Phase 4: Code organization

14. **Extract workers** from `settings_dialog.py` into `gui/workers.py`
15. **Extract progress dialogs** into `gui/dialogs.py`
16. **Add stderr handler** for optimizer subprocess
17. **Refactor `_updating_roi` pattern** to context manager

### Phase 5: Algorithm enhancements (optional)

18. **Add "fast mode"** — direct connected-component labeling when boundaries are well-closed, skipping watershed
19. **Auto-estimate CLAHE tile size** from coarse grain diameter estimation
20. **Add boundary skeletonization option** as standard pipeline step for thick-boundary images
