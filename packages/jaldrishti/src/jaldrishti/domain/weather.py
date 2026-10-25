"""Storage-independent weather and warning records."""

from dataclasses import dataclass
from datetime import date, datetime

from jaldrishti.domain.geography import GeoJSONMapping
from jaldrishti.domain.provenance import ProvenanceQuality


@dataclass(frozen=True, slots=True)
class WeatherForecastSummaryRecord:
    """District-centroid model guidance aggregated over the next 24 hours."""

    district_id: str
    district_name: str
    geometry: GeoJSONMapping
    precipitation_24h_mm: float
    maximum_probability_pct: float | None
    forecast_from: datetime
    forecast_through: datetime
    model: str
    source: str
    source_url: str | None
    source_version: str | None
    quality: ProvenanceQuality | str
    ingested_at: datetime


@dataclass(frozen=True, slots=True)
class OfficialWarningRecord:
    """One official district warning for a forecast day."""

    id: str
    district_id: str
    district_name: str
    geometry: GeoJSONMapping
    external_id: str
    issue_at: datetime
    valid_date: date
    day_index: int
    severity: str
    color_code: int
    warning_codes: list[int]
    hazards: list[str]
    description: str | None
    source: str
    source_url: str | None
    source_version: str | None
    quality: ProvenanceQuality | str
    ingested_at: datetime
