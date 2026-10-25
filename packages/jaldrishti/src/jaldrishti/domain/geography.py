"""Read models returned by persistence adapters."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from jaldrishti.domain.provenance import ProvenanceQuality

type GeoJSONMapping = dict[str, Any]


@dataclass(frozen=True, slots=True)
class GeographicRecord:
    """Storage-independent representation of a geographic feature."""

    id: str
    code: str | None
    name: str
    geometry: GeoJSONMapping | None
    source: str
    source_url: str | None
    source_version: str | None
    quality: ProvenanceQuality | str
    ingested_at: datetime


@dataclass(frozen=True, slots=True)
class FacilityRecord(GeographicRecord):
    """A geographic feature with facility-specific classification."""

    category: str
    subcategory: str | None = None


@dataclass(frozen=True, slots=True)
class SettlementRecord(GeographicRecord):
    """A named population centre used as geographic context."""

    settlement_type: str | None = None
    population: int | None = None


@dataclass(frozen=True, slots=True)
class RiverRecord(GeographicRecord):
    """A named river backdrop; not a hydrological network model."""

    river_class: str | None = None
