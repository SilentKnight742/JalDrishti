"""Application-facing records for SAR jobs and flood/change extents."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from jaldrishti.domain.geography import GeoJSONMapping
from jaldrishti.domain.provenance import ProvenanceQuality


@dataclass(frozen=True, slots=True)
class SatelliteJobRecord:
    id: str
    event_id: str
    status: str
    requested_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    before_start: datetime
    before_end: datetime
    after_start: datetime
    after_end: datetime
    algorithm: str
    parameters: dict[str, Any]
    error_code: str | None
    error_message: str | None
    catalog_source: str
    catalog_url: str | None
    scene_count: int


@dataclass(frozen=True, slots=True)
class FloodExtentRecord:
    id: str
    event_id: str
    job_id: str
    acquired_at: datetime
    algorithm: str
    algorithm_version: str
    parameters: dict[str, Any]
    area_km2: float
    high_evidence_area_km2: float
    valid_coverage_fraction: float
    resolution_m: float
    analysis_crs: str
    raster_uri: str
    geometry: GeoJSONMapping
    source: str
    source_record_id: str | None
    observed_at: datetime | None
    published_at: datetime | None
    ingested_at: datetime
    source_url: str | None
    source_version: str | None
    quality: ProvenanceQuality | str
    metadata: dict[str, Any]


@dataclass(frozen=True, slots=True)
class SatelliteComparisonRecord:
    id: str
    event_id: str
    flood_extent_id: str
    reference_name: str
    reference_acquired_at: datetime | None
    compared_at: datetime
    analysis_crs: str
    iou: float
    dice_f1: float
    precision: float
    recall: float
    detected_area_km2: float
    reference_area_km2: float
    overlap_area_km2: float
    union_area_km2: float
    area_difference_km2: float
    temporal_offset_hours: float | None
    caveat: str
    geometry: GeoJSONMapping
    source: str
    source_record_id: str | None
    observed_at: datetime | None
    published_at: datetime | None
    ingested_at: datetime
    source_url: str | None
    source_version: str | None
    quality: ProvenanceQuality | str
    metadata: dict[str, Any]
