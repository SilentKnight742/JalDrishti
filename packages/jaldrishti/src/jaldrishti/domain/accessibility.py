"""Application-facing road-accessibility screening records."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from jaldrishti.domain.geography import GeoJSONMapping
from jaldrishti.domain.provenance import ProvenanceQuality


@dataclass(frozen=True, slots=True)
class RoadDisruptionRecord:
    id: str
    snapshot_id: str
    event_id: str
    flood_extent_id: str
    road_segment_id: str | None
    name: str
    road_class: str
    overlap_km: float
    geometry: GeoJSONMapping
    source: str
    source_record_id: str | None
    observed_at: datetime | None
    ingested_at: datetime
    source_version: str | None
    quality: ProvenanceQuality | str
    metadata: dict[str, Any]


@dataclass(frozen=True, slots=True)
class SettlementAccessibilityRecord:
    id: str
    snapshot_id: str
    event_id: str
    flood_extent_id: str
    settlement_id: str | None
    name: str
    snapped_distance_m: float | None
    major_road_reachable_before: bool
    major_road_reachable_after: bool
    hospital_reachable_before: bool
    hospital_reachable_after: bool
    nearest_major_road_km: float | None
    nearest_hospital_km: float | None
    potentially_isolated: bool
    assessment_status: str
    geometry: GeoJSONMapping
    source: str
    source_record_id: str | None
    observed_at: datetime | None
    ingested_at: datetime
    source_version: str | None
    quality: ProvenanceQuality | str
    metadata: dict[str, Any]


@dataclass(frozen=True, slots=True)
class AccessibilitySnapshotRecord:
    id: str
    event_id: str
    flood_extent_id: str
    calculated_at: datetime
    algorithm: str
    algorithm_version: str
    status: str
    road_count: int
    graph_node_count: int
    graph_edge_count: int
    potentially_affected_road_count: int
    potentially_affected_road_km: float
    assessed_settlement_count: int
    potentially_isolated_settlement_count: int
    coverage: dict[str, Any]
    metadata: dict[str, Any]
    road_disruptions: tuple[RoadDisruptionRecord, ...]
    settlements: tuple[SettlementAccessibilityRecord, ...]
