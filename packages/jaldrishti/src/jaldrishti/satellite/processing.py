"""Event-scoped OPERA RTC preparation, change detection, and vectorisation.

The output is satellite-observed *change evidence*.  Low backscatter can also
be caused by smooth non-flood surfaces, acquisition geometry, wet soil, or
agriculture.  Callers must retain the algorithm parameters and must not label
the result confirmed damage or a field-validated flood boundary.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import rasterio
from pyproj import Transformer
from rasterio.enums import Resampling
from rasterio.features import rasterize, shapes
from rasterio.transform import Affine, from_origin
from rasterio.warp import reproject, transform_bounds
from scipy.ndimage import generic_filter
from shapely.geometry import MultiPolygon, shape
from shapely.geometry.base import BaseGeometry
from shapely.ops import transform, unary_union

from jaldrishti.provenance.artifacts import file_record
from jaldrishti.satellite.detection import (
    ChangeThresholds,
    classify_evidence,
    derive_water_threshold,
)


class SatelliteProcessingError(ValueError):
    """Raised when source coverage or raster metadata cannot support analysis."""


class NoChangeEvidence(SatelliteProcessingError):
    """Raised when valid inputs produce no pixels meeting the configured rule."""


@dataclass(frozen=True, slots=True)
class SarRasterSet:
    product_id: str
    vv: Path
    vh: Path
    mask: Path


@dataclass(frozen=True, slots=True)
class FloodExtentProduct:
    geometry_wgs84: MultiPolygon
    area_km2: float
    high_evidence_area_km2: float
    valid_coverage_fraction: float
    water_threshold_db: float
    water_threshold_method: str
    analysis_crs: str
    resolution_m: float
    raster_path: Path
    raster_record: dict[str, Any]
    parameters: dict[str, Any]


def analysis_crs_for_geometry(geometry_wgs84: BaseGeometry) -> str:
    """Choose the local WGS84 UTM zone for an event-scoped AOI."""

    if geometry_wgs84.is_empty:
        raise SatelliteProcessingError("analysis geometry must not be empty")
    longitude = float(geometry_wgs84.centroid.x)
    latitude = float(geometry_wgs84.centroid.y)
    if not (-180 <= longitude <= 180 and -80 <= latitude <= 84):
        raise SatelliteProcessingError("analysis geometry is outside UTM coverage")
    zone = min(60, max(1, math.floor((longitude + 180) / 6) + 1))
    epsg = 32600 + zone if latitude >= 0 else 32700 + zone
    return f"EPSG:{epsg}"


def _target_grid(
    geometry_wgs84: BaseGeometry,
    analysis_crs: str,
    resolution_m: float,
) -> tuple[Affine, int, int]:
    west, south, east, north = transform_bounds(
        "EPSG:4326",
        analysis_crs,
        *geometry_wgs84.bounds,
        densify_pts=21,
    )
    left = math.floor(west / resolution_m) * resolution_m
    bottom = math.floor(south / resolution_m) * resolution_m
    right = math.ceil(east / resolution_m) * resolution_m
    top = math.ceil(north / resolution_m) * resolution_m
    width = round((right - left) / resolution_m)
    height = round((top - bottom) / resolution_m)
    if width < 1 or height < 1:
        raise SatelliteProcessingError("analysis geometry produced an empty raster grid")
    return from_origin(left, top, resolution_m, resolution_m), width, height


def _reproject_asset(
    data_path: Path,
    mask_path: Path,
    *,
    transform_: Affine,
    crs: str,
    width: int,
    height: int,
) -> tuple[np.ndarray, np.ndarray]:
    destination = np.full((height, width), np.nan, dtype=np.float32)
    mask_destination = np.full((height, width), 255, dtype=np.uint8)
    try:
        with rasterio.open(data_path) as source:
            if source.crs is None:
                raise SatelliteProcessingError(f"source raster has no CRS: {data_path}")
            reproject(
                source=source.read(1),
                destination=destination,
                src_transform=source.transform,
                src_crs=source.crs,
                src_nodata=source.nodata,
                dst_transform=transform_,
                dst_crs=crs,
                dst_nodata=np.nan,
                resampling=Resampling.bilinear,
            )
        with rasterio.open(mask_path) as source:
            if source.crs is None:
                raise SatelliteProcessingError(f"source mask has no CRS: {mask_path}")
            reproject(
                source=source.read(1),
                destination=mask_destination,
                src_transform=source.transform,
                src_crs=source.crs,
                src_nodata=source.nodata,
                dst_transform=transform_,
                dst_crs=crs,
                dst_nodata=255,
                resampling=Resampling.nearest,
            )
    except rasterio.RasterioError as exc:
        raise SatelliteProcessingError(f"unable to read OPERA raster: {exc}") from exc
    valid = np.isfinite(destination) & (destination > 0) & (mask_destination == 0)
    return destination, valid


def _mosaic(
    sources: Sequence[SarRasterSet],
    polarization: str,
    *,
    transform_: Affine,
    crs: str,
    width: int,
    height: int,
) -> tuple[np.ndarray, np.ndarray]:
    if not sources:
        raise SatelliteProcessingError("at least one OPERA source is required")
    total = np.zeros((height, width), dtype=np.float64)
    count = np.zeros((height, width), dtype=np.uint16)
    for item in sources:
        data, valid = _reproject_asset(
            getattr(item, polarization),
            item.mask,
            transform_=transform_,
            crs=crs,
            width=width,
            height=height,
        )
        total[valid] += data[valid]
        count[valid] += 1
    valid = count > 0
    mosaic = np.full((height, width), np.nan, dtype=np.float32)
    mosaic[valid] = (total[valid] / count[valid]).astype(np.float32)
    return mosaic, valid


def _linear_to_db(values: np.ndarray, valid: np.ndarray) -> np.ndarray:
    result = np.full(values.shape, np.nan, dtype=np.float32)
    usable = valid & np.isfinite(values) & (values > 0)
    result[usable] = 10 * np.log10(values[usable])
    return result


def _masked_median(values: np.ndarray, size: int) -> np.ndarray:
    if size == 1:
        return values.copy()

    def nan_median(window: np.ndarray) -> float:
        finite = window[np.isfinite(window)]
        return float(np.median(finite)) if finite.size else np.nan

    result = generic_filter(values, nan_median, size=size, mode="nearest").astype(np.float32)
    result[~np.isfinite(values)] = np.nan
    return result


def _write_evidence_raster(
    path: Path,
    evidence: np.ndarray,
    *,
    transform_: Affine,
    crs: str,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    profile = {
        "driver": "COG",
        "height": evidence.shape[0],
        "width": evidence.shape[1],
        "count": 1,
        "dtype": "uint8",
        "crs": crs,
        "transform": transform_,
        "nodata": 0,
        "compress": "deflate",
        "blocksize": 256,
        "overview_resampling": "nearest",
    }
    try:
        with rasterio.open(path, "w", **profile) as dataset:
            dataset.write(evidence.astype(np.uint8), 1)
    except rasterio.RasterioError as exc:
        path.unlink(missing_ok=True)
        raise SatelliteProcessingError(f"unable to write evidence COG: {exc}") from exc


def _vectorize(
    evidence: np.ndarray,
    *,
    transform_: Affine,
    analysis_crs: str,
    aoi_projected: BaseGeometry,
) -> MultiPolygon:
    detected = evidence > 0
    polygons = [
        shape(geometry)
        for geometry, value in shapes(
            detected.astype(np.uint8),
            mask=detected,
            transform=transform_,
        )
        if int(value) == 1
    ]
    if not polygons:
        raise SatelliteProcessingError("detection produced no change-evidence polygons")
    combined = unary_union(polygons).intersection(aoi_projected)
    if combined.is_empty:
        raise SatelliteProcessingError("detected evidence does not intersect the event AOI")
    if combined.geom_type == "Polygon":
        combined = MultiPolygon([combined])
    elif combined.geom_type != "MultiPolygon":
        polygon_parts = [part for part in combined.geoms if part.geom_type == "Polygon"]
        combined = MultiPolygon(polygon_parts)
    transformer = Transformer.from_crs(analysis_crs, "EPSG:4326", always_xy=True)
    web_geometry = transform(transformer.transform, combined)
    return web_geometry if isinstance(web_geometry, MultiPolygon) else MultiPolygon([web_geometry])


def process_opera_rtc_change(
    *,
    before: Sequence[SarRasterSet],
    after: Sequence[SarRasterSet],
    geometry_wgs84: BaseGeometry,
    output_path: Path,
    resolution_m: float = 30,
    median_kernel: int = 3,
    minimum_valid_coverage: float = 0.8,
    water_threshold_bounds_db: tuple[float, float] = (-20, -12),
    water_threshold_override_db: float | None = None,
    vv_drop_db: float = -3,
    vh_drop_db: float = -2,
    min_component_pixels: int = 10,
) -> FloodExtentProduct:
    """Produce one vector flood/change-evidence extent and its classified COG."""

    if geometry_wgs84.is_empty or not geometry_wgs84.is_valid:
        raise SatelliteProcessingError("event AOI must be a non-empty valid geometry")
    if resolution_m <= 0 or not math.isfinite(resolution_m):
        raise SatelliteProcessingError("resolution_m must be finite and positive")
    if median_kernel < 1 or median_kernel % 2 == 0:
        raise SatelliteProcessingError("median_kernel must be a positive odd integer")
    if not 0 < minimum_valid_coverage <= 1:
        raise SatelliteProcessingError("minimum_valid_coverage must be in (0, 1]")

    analysis_crs = analysis_crs_for_geometry(geometry_wgs84)
    grid_transform, width, height = _target_grid(
        geometry_wgs84,
        analysis_crs,
        float(resolution_m),
    )
    to_projected = Transformer.from_crs("EPSG:4326", analysis_crs, always_xy=True)
    aoi_projected = transform(to_projected.transform, geometry_wgs84)
    aoi_mask = rasterize(
        [(aoi_projected, 1)],
        out_shape=(height, width),
        transform=grid_transform,
        fill=0,
        dtype="uint8",
    ).astype(bool)
    if not aoi_mask.any():
        raise SatelliteProcessingError("event AOI did not rasterize onto the analysis grid")

    arrays: dict[str, np.ndarray] = {}
    validity: list[np.ndarray] = []
    for role, sources_ in (("before", before), ("after", after)):
        for polarization in ("vv", "vh"):
            linear, valid = _mosaic(
                sources_,
                polarization,
                transform_=grid_transform,
                crs=analysis_crs,
                width=width,
                height=height,
            )
            arrays[f"{role}_{polarization}"] = _masked_median(
                _linear_to_db(linear, valid),
                median_kernel,
            )
            validity.append(valid)

    common_valid = np.logical_and.reduce(validity) & aoi_mask
    coverage = float(common_valid.sum() / aoi_mask.sum())
    if coverage < minimum_valid_coverage:
        raise SatelliteProcessingError(
            f"common valid SAR coverage is {coverage:.1%}; "
            f"at least {minimum_valid_coverage:.1%} is required"
        )
    for array in arrays.values():
        array[~common_valid] = np.nan

    delta_vv = arrays["after_vv"] - arrays["before_vv"]
    delta_vh = arrays["after_vh"] - arrays["before_vh"]
    threshold = derive_water_threshold(
        arrays["after_vv"],
        water_threshold_bounds_db,
        water_threshold_override_db,
    )
    classified = classify_evidence(
        arrays["after_vv"],
        delta_vv,
        delta_vh,
        threshold.value_db,
        ChangeThresholds(vv_drop_db=vv_drop_db, vh_drop_db=vh_drop_db),
        min_component_pixels,
    )
    evidence = classified.evidence.copy()
    evidence[~common_valid] = 0
    if not classified.detected.any():
        raise NoChangeEvidence("detection produced no flood/change evidence")
    _write_evidence_raster(
        output_path,
        evidence,
        transform_=grid_transform,
        crs=analysis_crs,
    )
    geometry = _vectorize(
        evidence,
        transform_=grid_transform,
        analysis_crs=analysis_crs,
        aoi_projected=aoi_projected,
    )
    pixel_area_km2 = abs(grid_transform.a * grid_transform.e) / 1_000_000
    parameters = {
        "method": "low post-event VV plus dual-polarisation backscatter decrease",
        "water_threshold_db": threshold.value_db,
        "water_threshold_method": threshold.method,
        "water_threshold_bounds_db": list(water_threshold_bounds_db),
        "vv_drop_db": vv_drop_db,
        "vh_drop_db": vh_drop_db,
        "median_kernel": median_kernel,
        "min_component_pixels": min_component_pixels,
        "minimum_valid_coverage": minimum_valid_coverage,
        "terminology": "satellite-observed change evidence; not confirmed inundation or damage",
    }
    return FloodExtentProduct(
        geometry_wgs84=geometry,
        area_km2=float(classified.detected.sum() * pixel_area_km2),
        high_evidence_area_km2=float((evidence == 2).sum() * pixel_area_km2),
        valid_coverage_fraction=coverage,
        water_threshold_db=threshold.value_db,
        water_threshold_method=threshold.method,
        analysis_crs=analysis_crs,
        resolution_m=float(resolution_m),
        raster_path=output_path,
        raster_record=dict(file_record(output_path, output_path.parent)),
        parameters=parameters,
    )
