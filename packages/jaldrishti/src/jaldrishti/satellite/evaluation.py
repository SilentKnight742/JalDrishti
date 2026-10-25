"""Binary agreement metrics for satellite-derived extent masks.

Agreement with another mapped product is not automatically independent
validation or field-verified accuracy. Callers must retain the comparison
source, acquisition timing, and caveat so temporal or methodological
dependence remains visible to operators.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray
from pyproj import CRS, Transformer
from shapely import make_valid
from shapely.geometry.base import BaseGeometry
from shapely.ops import transform


class EvaluationInputError(ValueError):
    """Raised when binary masks or their spatial scale are invalid."""


@dataclass(frozen=True, slots=True)
class BinaryEvaluationMetrics:
    """Confusion counts, overlap scores, and area-aware comparison metrics."""

    label: str
    caveat: str
    acquired_at: str
    true_positive_pixels: int
    false_positive_pixels: int
    false_negative_pixels: int
    true_negative_pixels: int
    iou: float
    dice_f1: float
    precision: float
    recall: float
    false_positive_rate: float
    detected_area_km2: float
    reference_area_km2: float
    area_difference_km2: float
    valid_comparison_area_km2: float
    overlap_area_km2: float


@dataclass(frozen=True, slots=True)
class VectorEvaluationMetrics:
    """Area-based agreement between two WGS84 polygonal flood products."""

    analysis_crs: str
    detected_area_km2: float
    reference_area_km2: float
    overlap_area_km2: float
    union_area_km2: float
    area_difference_km2: float
    iou: float
    dice_f1: float
    precision: float
    recall: float


def binary_metrics(
    predicted: NDArray[np.generic],
    reference: NDArray[np.generic],
    valid: NDArray[np.generic],
    pixel_area_km2: float,
    *,
    label: str,
    caveat: str,
    acquired_at: str,
) -> BinaryEvaluationMetrics:
    """Compare two binary masks inside an explicit common-valid-data mask.

    Empty positive classes produce zero-valued ratios rather than undefined or
    misleading perfect scores. ``pixel_area_km2`` must come from the raster
    transform (or another justified grid specification), not merely a nominal
    product resolution when pixels may be non-square.
    """

    predicted_array = np.asarray(predicted, dtype=bool)
    reference_array = np.asarray(reference, dtype=bool)
    valid_array = np.asarray(valid, dtype=bool)
    if not (
        predicted_array.shape == reference_array.shape == valid_array.shape
        and predicted_array.ndim >= 1
    ):
        raise EvaluationInputError("predicted, reference, and valid masks must share one shape")
    if not valid_array.any():
        raise EvaluationInputError("valid mask must contain at least one comparison pixel")
    area = float(pixel_area_km2)
    if not np.isfinite(area) or area <= 0:
        raise EvaluationInputError("pixel_area_km2 must be finite and greater than zero")

    pred = predicted_array & valid_array
    ref = reference_array & valid_array
    true_positive = int(np.count_nonzero(pred & ref))
    false_positive = int(np.count_nonzero(pred & ~ref & valid_array))
    false_negative = int(np.count_nonzero(~pred & ref & valid_array))
    true_negative = int(np.count_nonzero(~pred & ~ref & valid_array))

    def ratio(numerator: int, denominator: int) -> float:
        return float(numerator / denominator) if denominator else 0.0

    detected_area = float(pred.sum() * area)
    reference_area = float(ref.sum() * area)
    return BinaryEvaluationMetrics(
        label=label,
        caveat=caveat,
        acquired_at=acquired_at,
        true_positive_pixels=true_positive,
        false_positive_pixels=false_positive,
        false_negative_pixels=false_negative,
        true_negative_pixels=true_negative,
        iou=ratio(true_positive, true_positive + false_positive + false_negative),
        dice_f1=ratio(
            2 * true_positive,
            2 * true_positive + false_positive + false_negative,
        ),
        precision=ratio(true_positive, true_positive + false_positive),
        recall=ratio(true_positive, true_positive + false_negative),
        false_positive_rate=ratio(false_positive, false_positive + true_negative),
        detected_area_km2=detected_area,
        reference_area_km2=reference_area,
        area_difference_km2=detected_area - reference_area,
        valid_comparison_area_km2=float(valid_array.sum() * area),
        overlap_area_km2=float(true_positive * area),
    )


def _utm_crs_for_geometry(geometry: BaseGeometry) -> CRS:
    centroid = geometry.centroid
    longitude = float(centroid.x)
    latitude = float(centroid.y)
    if not (math.isfinite(longitude) and math.isfinite(latitude)):
        raise EvaluationInputError("comparison geometry centroid must be finite")
    zone = max(1, min(60, int((longitude + 180) // 6) + 1))
    return CRS.from_epsg((32600 if latitude >= 0 else 32700) + zone)


def vector_metrics(
    detected_wgs84: BaseGeometry,
    reference_wgs84: BaseGeometry,
) -> VectorEvaluationMetrics:
    """Compare polygonal products in a locally appropriate metre CRS.

    The result measures geometric agreement only. It does not turn the
    reference product into field truth; source timing and methodological
    dependence must remain visible with the stored comparison.
    """

    if detected_wgs84 is None or detected_wgs84.is_empty:
        raise EvaluationInputError("detected geometry must be non-empty")
    if reference_wgs84 is None or reference_wgs84.is_empty:
        raise EvaluationInputError("reference geometry must be non-empty")
    detected = make_valid(detected_wgs84)
    reference = make_valid(reference_wgs84)
    if detected.geom_type not in {"Polygon", "MultiPolygon"}:
        raise EvaluationInputError("detected geometry must be polygonal")
    if reference.geom_type not in {"Polygon", "MultiPolygon"}:
        raise EvaluationInputError("reference geometry must be polygonal")
    analysis_crs = _utm_crs_for_geometry(detected.union(reference))
    projector = Transformer.from_crs("EPSG:4326", analysis_crs, always_xy=True).transform
    detected_metric = transform(projector, detected)
    reference_metric = transform(projector, reference)
    detected_area = float(detected_metric.area / 1_000_000)
    reference_area = float(reference_metric.area / 1_000_000)
    overlap_area = float(detected_metric.intersection(reference_metric).area / 1_000_000)
    union_area = float(detected_metric.union(reference_metric).area / 1_000_000)

    def ratio(numerator: float, denominator: float) -> float:
        return numerator / denominator if denominator > 0 else 0.0

    return VectorEvaluationMetrics(
        analysis_crs=analysis_crs.to_string(),
        detected_area_km2=detected_area,
        reference_area_km2=reference_area,
        overlap_area_km2=overlap_area,
        union_area_km2=union_area,
        area_difference_km2=detected_area - reference_area,
        iou=ratio(overlap_area, union_area),
        dice_f1=ratio(2 * overlap_area, detected_area + reference_area),
        precision=ratio(overlap_area, detected_area),
        recall=ratio(overlap_area, reference_area),
    )
