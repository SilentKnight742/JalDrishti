"""Pure dual-polarisation SAR flood/change-evidence kernels.

These functions reproduce the classical RadarWatch/Valencia heuristic: low
post-event VV backscatter combined with before/after VV and VH decreases. The
result is *change evidence*, not a calibrated flood probability, semantic
segmentation, field validation, or confirmation that any asset is damaged.
Urban double bounce, wet soil, agriculture, vegetation, surface roughness, and
acquisition timing can all create false positives or false negatives.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

import numpy as np
from numpy.typing import NDArray
from skimage.filters import threshold_multiotsu
from skimage.morphology import (
    closing,
    footprint_rectangle,
    remove_small_holes,
    remove_small_objects,
)

type ThresholdMethod = Literal["config_override", "multi_otsu_3class_clamped"]


class DetectionInputError(ValueError):
    """Raised when arrays or detection parameters cannot support the heuristic."""


@dataclass(frozen=True, slots=True)
class ChangeThresholds:
    """Maximum dB changes that qualify as VV and VH backscatter decreases."""

    vv_drop_db: float
    vh_drop_db: float

    def __post_init__(self) -> None:
        if not np.isfinite(self.vv_drop_db) or not np.isfinite(self.vh_drop_db):
            raise DetectionInputError("VV and VH change thresholds must be finite")


@dataclass(frozen=True, slots=True)
class WaterThreshold:
    """Selected low-backscatter threshold and the transparent selection method."""

    value_db: float
    method: ThresholdMethod


@dataclass(frozen=True, slots=True)
class EvidenceClassification:
    """Per-pixel evidence classes and their combined binary detection mask.

    ``evidence`` uses 0 for no evidence, 1 for moderate evidence, and 2 for
    high evidence. Arrays remain mutable NumPy values even though the result
    container itself is frozen.
    """

    evidence: NDArray[np.uint8]
    detected: NDArray[np.bool_]


def derive_water_threshold(
    post_event_vv_db: NDArray[np.floating[Any]],
    bounds_db: tuple[float, float],
    override_db: float | None = None,
) -> WaterThreshold:
    """Derive a clamped three-class Multi-Otsu low-backscatter threshold.

    Multi-Otsu is an unsupervised image threshold, not a learned or calibrated
    flood model. Clamping guards against pathological values in land-dominated
    scenes but does not make the threshold universally transferable. An
    explicit override is reported and returned without clamping so callers do
    not mistake a configured scientific decision for an estimated value.
    """

    low, high = (float(value) for value in bounds_db)
    if not np.isfinite(low) or not np.isfinite(high) or low >= high:
        raise DetectionInputError("bounds_db must contain two finite increasing values")

    if override_db is not None:
        override = float(override_db)
        if not np.isfinite(override):
            raise DetectionInputError("override_db must be finite")
        return WaterThreshold(value_db=override, method="config_override")

    values = np.asarray(post_event_vv_db, dtype=np.float32)
    values = values[np.isfinite(values)]
    if values.size < 256 or np.unique(values).size < 3:
        raise DetectionInputError(
            "three-class Multi-Otsu requires at least 256 valid pixels and three distinct values"
        )
    try:
        threshold = float(threshold_multiotsu(values, classes=3)[0])
    except ValueError as exc:
        raise DetectionInputError(f"unable to derive a Multi-Otsu threshold: {exc}") from exc
    return WaterThreshold(
        value_db=float(np.clip(threshold, low, high)),
        method="multi_otsu_3class_clamped",
    )


def classify_evidence(
    post_event_vv_db: NDArray[np.floating[Any]],
    delta_vv_db: NDArray[np.floating[Any]],
    delta_vh_db: NDArray[np.floating[Any]],
    water_threshold_db: float,
    thresholds: ChangeThresholds,
    min_component_pixels: int,
) -> EvidenceClassification:
    """Classify moderate and high dual-polarisation change evidence.

    Moderate evidence requires low post-event VV and a VV *or* VH decrease;
    high evidence requires both decreases. A 3x3 closing and small-component
    filtering are applied, then the common finite-data mask is reapplied so
    morphology cannot create evidence in nodata cells.

    The output represents remotely sensed evidence only. It must not be
    described as confirmed inundation, damage, or road closure.
    """

    post = np.asarray(post_event_vv_db, dtype=np.float32)
    delta_vv = np.asarray(delta_vv_db, dtype=np.float32)
    delta_vh = np.asarray(delta_vh_db, dtype=np.float32)
    if post.shape != delta_vv.shape or post.shape != delta_vh.shape:
        raise DetectionInputError("post-event VV and VV/VH change arrays must share one shape")
    if post.ndim != 2:
        raise DetectionInputError("SAR evidence classification requires two-dimensional arrays")
    if min_component_pixels < 1:
        raise DetectionInputError("min_component_pixels must be at least 1")
    threshold = float(water_threshold_db)
    if not np.isfinite(threshold):
        raise DetectionInputError("water_threshold_db must be finite")

    valid = np.isfinite(post) & np.isfinite(delta_vv) & np.isfinite(delta_vh)
    low_post = valid & (post <= threshold)
    vv_drop = valid & (delta_vv <= thresholds.vv_drop_db)
    vh_drop = valid & (delta_vh <= thresholds.vh_drop_db)
    high = low_post & vv_drop & vh_drop
    combined = low_post & (vv_drop | vh_drop)
    combined = closing(combined, footprint=footprint_rectangle((3, 3)))
    maximum_small_size = max(min_component_pixels - 1, 0)
    combined = remove_small_holes(combined, max_size=maximum_small_size)
    combined = remove_small_objects(combined, max_size=maximum_small_size)
    combined = np.asarray(combined, dtype=bool) & valid
    high &= combined

    evidence = np.zeros(post.shape, dtype=np.uint8)
    evidence[combined] = 1
    evidence[high] = 2
    return EvidenceClassification(evidence=evidence, detected=combined)
