"""Projected-geometry infrastructure exposure screening.

Geometric intersection identifies potential exposure only. It does not prove
that a road is closed, a structure is damaged, or a facility is unusable.
Source completeness, positional error, flood-observation timing, and geometry
resolution must remain visible in downstream interpretation.
"""

from __future__ import annotations

import math
from typing import Any

import geopandas as gpd
from pyproj import CRS
from shapely.geometry.base import BaseGeometry


class CRSValidationError(ValueError):
    """Raised when exposure measurements would not be in comparable metres."""


def _metric_projected_crs(value: Any, *, label: str) -> CRS:
    if value is None:
        raise CRSValidationError(f"{label} CRS is required")
    try:
        crs = CRS.from_user_input(value)
    except Exception as exc:
        raise CRSValidationError(f"{label} CRS is invalid: {value!r}") from exc
    if not crs.is_projected:
        raise CRSValidationError(f"{label} CRS must be projected, not geographic")
    horizontal_axes = crs.axis_info[:2]
    if len(horizontal_axes) < 2 or any(
        axis.unit_conversion_factor is None
        or not math.isclose(float(axis.unit_conversion_factor), 1.0, rel_tol=0, abs_tol=1e-12)
        for axis in horizontal_axes
    ):
        raise CRSValidationError(f"{label} CRS horizontal units must be metres")
    return crs


def validate_shared_metric_crs(features: gpd.GeoDataFrame, flood_crs: Any) -> CRS:
    """Require feature and flood geometries to share a projected metre CRS."""

    feature_crs = _metric_projected_crs(features.crs, label="feature")
    extent_crs = _metric_projected_crs(flood_crs, label="flood extent")
    if feature_crs != extent_crs:
        raise CRSValidationError(
            f"feature CRS {feature_crs.to_string()} does not match "
            f"flood extent CRS {extent_crs.to_string()}"
        )
    return feature_crs


def _validate_extent(flood_geometry: BaseGeometry) -> None:
    if flood_geometry is None or flood_geometry.is_empty:
        raise ValueError("flood_geometry must be a non-empty geometry")


def line_exposure(
    lines: gpd.GeoDataFrame,
    flood_geometry: BaseGeometry,
    minimum_overlap_m: float,
    *,
    flood_crs: Any,
) -> gpd.GeoDataFrame:
    """Return line features whose centreline overlap meets a metre threshold.

    The returned ``overlap_m`` measures geometry intersection length. It is a
    screening quantity and must not be labelled observed damage or closure.
    Both datasets must explicitly use the same projected metre CRS.
    """

    validate_shared_metric_crs(lines, flood_crs)
    _validate_extent(flood_geometry)
    threshold = float(minimum_overlap_m)
    if not math.isfinite(threshold) or threshold < 0:
        raise ValueError("minimum_overlap_m must be finite and non-negative")

    result = lines.copy()
    result["overlap_m"] = [
        (
            float(geometry.intersection(flood_geometry).length)
            if geometry is not None and not geometry.is_empty
            else 0.0
        )
        for geometry in result.geometry
    ]
    return result[result["overlap_m"] >= threshold].copy()


def polygon_exposure(
    features: gpd.GeoDataFrame,
    flood_geometry: BaseGeometry,
    minimum_overlap_fraction: float,
    *,
    flood_crs: Any,
) -> gpd.GeoDataFrame:
    """Return footprints or point assets that meet an exposure rule.

    Polygonal features qualify when their centroid is within the observed
    extent or their intersected-area fraction reaches the configured minimum.
    Point and linear representations qualify on intersection and receive an
    ``overlap_fraction`` of one or zero for schema consistency. These are
    potential-exposure rules, not damage assessment.
    """

    validate_shared_metric_crs(features, flood_crs)
    _validate_extent(flood_geometry)
    threshold = float(minimum_overlap_fraction)
    if not math.isfinite(threshold) or not 0 < threshold <= 1:
        raise ValueError("minimum_overlap_fraction must be in the interval (0, 1]")

    def measurements(geometry: BaseGeometry | None) -> tuple[float, bool]:
        if geometry is None or geometry.is_empty:
            return 0.0, False
        if geometry.geom_type in {
            "Point",
            "MultiPoint",
            "LineString",
            "LinearRing",
            "MultiLineString",
        }:
            exposed = geometry.intersects(flood_geometry)
            return float(exposed), exposed
        area = float(geometry.area)
        overlap = float(geometry.intersection(flood_geometry).area)
        fraction = overlap / area if area else 0.0
        return fraction, geometry.centroid.within(flood_geometry) or fraction >= threshold

    result = features.copy()
    measured = [measurements(geometry) for geometry in result.geometry]
    result["overlap_fraction"] = [item[0] for item in measured]
    result["exposed"] = [item[1] for item in measured]
    return result[result["exposed"].astype(bool)].copy()
