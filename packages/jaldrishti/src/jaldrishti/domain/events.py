"""Storage-independent flood-event and evidence records."""

from dataclasses import dataclass
from datetime import datetime

from jaldrishti.domain.geography import GeoJSONMapping
from jaldrishti.domain.provenance import ProvenanceQuality


@dataclass(frozen=True, slots=True)
class FloodEventRecord:
    id: str
    region_id: str
    primary_district_id: str | None
    name: str
    geometry: GeoJSONMapping
    started_at: datetime
    last_updated_at: datetime
    state_changed_at: datetime
    ended_at: datetime | None
    state: str
    trigger_summary: str
    rainfall_status: str
    river_status: str
    warning_status: str
    satellite_status: str
    created_by: str
    rule_version: str
    rationale: list[str]


@dataclass(frozen=True, slots=True)
class EventEvidenceRecord:
    id: str
    event_id: str
    evidence_type: str
    title: str
    summary: str
    geometry: GeoJSONMapping | None
    source: str
    source_record_id: str | None
    observed_at: datetime | None
    published_at: datetime | None
    ingested_at: datetime
    source_url: str | None
    source_version: str | None
    quality: ProvenanceQuality | str
    metadata: dict[str, object]


@dataclass(frozen=True, slots=True)
class EventTimelineRecord:
    id: str
    event_id: str
    evidence_id: str | None
    occurred_at: datetime
    category: str
    state_from: str | None
    state_to: str | None
    summary: str
    metadata: dict[str, object]
