"""Application-facing records for reproducible potential-exposure results."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from jaldrishti.domain.geography import GeoJSONMapping
from jaldrishti.domain.provenance import ProvenanceQuality


@dataclass(frozen=True, slots=True)
class PotentialExposureRecord:
    id: str
    snapshot_id: str
    event_id: str
    flood_extent_id: str
    asset_type: str
    asset_id: str
    name: str
    metric_type: str
    metric_value: float
    unit: str
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
class ImpactSnapshotRecord:
    id: str
    event_id: str
    flood_extent_id: str
    calculated_at: datetime
    algorithm: str
    algorithm_version: str
    inundated_area_km2: float
    settlement_count: int
    facility_count: int
    population_potentially_exposed: int | None
    population_record_count: int
    road_overlap_km: float | None
    building_count: int | None
    coverage: dict[str, Any]
    metadata: dict[str, Any]
    exposures: tuple[PotentialExposureRecord, ...]
