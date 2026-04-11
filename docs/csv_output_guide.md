# CSV Output Guide

grainsize_measure exports two separate CSV files after analysis:

| File | Content |
|---|---|
| `*_chords.csv` | One row per measured chord (Track A — intercept method) |
| `*_grains.csv` | One row per detected grain (Track B — area method) |

---

## Chords CSV (`*_chords.csv`)

Each row represents a single chord — the gap between two consecutive grain boundaries crossed by one scan line at one angle.

| Column | Type | Unit | Description |
|---|---|---|---|
| `chord_id` | integer | — | Sequential identifier, starting at 1. Assigned in the order chords are found (angle 0 first, then subsequent angles). |
| `length_pixels` | float | px | Chord length measured in pixels. This is the number of pixels between the two boundary crossings on the scan line. |
| `length_um` | float | µm | Chord length converted to micrometres: `length_pixels / pixels_per_um`. Empty (`null`) if no scale has been set. |

### How chords are calculated

1. The binary boundary image is scanned with horizontal lines spaced `line_spacing` pixels apart.
2. For each scan line, boundary pixel locations are found (pixels with value 255).
3. Each gap between two consecutive boundary crossings is one chord.
4. The image is rotated to each angle in `[theta_start … theta_end]` with `n_theta_steps` steps, and steps 1–3 are repeated at each angle.
5. All chords from all angles are concatenated into a single list.

### Derived statistics shown in the UI

| Statistic | Formula |
|---|---|
| Mean chord length (µm) | `mean(length_um)` |
| ASTM grain size number G | `G = -6.6457 × log₁₀(mean_mm) - 3.298` (ASTM E112 intercept method) |

---

## Grains CSV (`*_grains.csv`)

Each row represents one detected grain that passed all filters (minimum area, edge exclusion, ROI).

| Column | Type | Unit | Description |
|---|---|---|---|
| `grain_id` | integer | — | Label assigned by the watershed segmentation algorithm. Not necessarily sequential; gaps appear where grains were filtered out. |
| `area_pixels` | integer | px² | Number of pixels inside the grain region (grain interior, excluding boundary pixels). |
| `equivalent_diameter_pixels` | float | px | Diameter of a circle that has the same area: `2 × sqrt(area_pixels / π)`. Provides a single linear size metric comparable across grains. |
| `centroid_x` | float | px | Horizontal pixel coordinate of the grain's area-weighted centroid (column index, left = 0). |
| `centroid_y` | float | px | Vertical pixel coordinate of the grain's area-weighted centroid (row index, top = 0). |
| `eccentricity` | float | — | Elongation of the grain shape, modelled as an ellipse. **0** = perfect circle, **1** = a line segment. Values above 0.9 indicate strongly elongated grains. |
| `solidity` | float | — | Ratio of the grain area to its convex hull area: `area_pixels / convex_hull_area`. **1.0** = fully convex (no indentations). Values below 0.8 indicate highly irregular or concave grain shapes. |
| `area_um2` | float | µm² | Physical grain area: `area_pixels / pixels_per_um²`. Empty (`null`) if no scale has been set. |
| `equivalent_diameter_um` | float | µm | Physical equivalent diameter: `equivalent_diameter_pixels / pixels_per_um`. Empty (`null`) if no scale has been set. |

### How grains are detected

1. The binary boundary image is inverted so grain interiors are `True`.
2. A Euclidean distance transform is computed — each interior pixel gets its distance to the nearest boundary.
3. Local maxima of the distance map (peaks deeper inside each grain) become watershed markers.
4. The watershed algorithm floods outward from each marker, producing a labeled image where every pixel belongs to exactly one grain.
5. `skimage.measure.regionprops` computes shape properties for each labeled region.
6. Grains are then filtered by `min_grain_area`, `exclude_edge_grains` / `edge_buffer`, and `grain_roi`.

### Shape metric quick reference

| `eccentricity` | Shape |
|---|---|
| 0.0 – 0.3 | Near-circular |
| 0.3 – 0.7 | Moderately elongated |
| 0.7 – 0.9 | Strongly elongated |
| > 0.9 | Rod-like or nearly flat |

| `solidity` | Shape |
|---|---|
| 0.95 – 1.0 | Convex, compact |
| 0.8 – 0.95 | Slightly irregular |
| < 0.8 | Highly concave or branched |

---

## Notes on missing values (`null`)

Columns `length_um`, `area_um2`, and `equivalent_diameter_um` are `null` when `pixels_per_um` is not set (shown as `(未設定)` in the UI). Set the scale — either via **自動検出** or manually — before exporting if physical units are required.
