"""Storage-independent hydrology records.

The first Assam telemetry feed does not publish a timezone, stable station ID,
datum, or alert thresholds.  These contracts keep those fields nullable so the
rest of JalDrishti cannot accidentally manufacture operational certainty.
"""

from dataclasses import dataclass
from datetime import datetime

from jaldrishti.domain.geography import GeoJSONMapping
from jaldrishti.domain.provenance import ProvenanceQuality


@dataclass(frozen=True, slots=True)
class StationRecord:
    """A monitoring location with explicit operational limitations."""

    id: str
    region_id: str
    district_id: str | None
    external_id: str | None
    name: str
    geometry: GeoJSONMapping
    river_name: str | None
    basin_name: str | None
    warning_level_m: float | None
    danger_level_m: float | None
    datum: str | None
    time_zone: str | None
    operational_status: str
    coverage_status: str
    source: str
    source_url: str | None
    source_version: str | None
    quality: ProvenanceQuality | str
    ingested_at: datetime


@dataclass(frozen=True, slots=True)
class StationObservationRecord:
    """One water-level observation preserving the source-local timestamp."""

    id: str
    station_id: str
    source_observed_at: str
    observed_at: datetime | None
    water_level_m: float
    unit: str
    quality_flag: str
    source: str
    source_url: str | None
    source_version: str | None
    quality: ProvenanceQuality | str
    ingested_at: datetime
