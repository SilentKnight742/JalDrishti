"""Domain contracts shared by JalDrishti applications."""

from jaldrishti.domain.events import (
    EventEvidenceRecord,
    EventTimelineRecord,
    FloodEventRecord,
)
from jaldrishti.domain.geography import FacilityRecord, GeographicRecord
from jaldrishti.domain.hydrology import StationObservationRecord, StationRecord
from jaldrishti.domain.provenance import ProvenanceQuality
from jaldrishti.domain.repositories import (
    DistrictRepository,
    EventRepository,
    FacilityRepository,
    RegionRepository,
    StationRepository,
    WeatherRepository,
)
from jaldrishti.domain.weather import OfficialWarningRecord, WeatherForecastSummaryRecord

__all__ = [
    "DistrictRepository",
    "EventEvidenceRecord",
    "EventRepository",
    "EventTimelineRecord",
    "FacilityRecord",
    "FacilityRepository",
    "FloodEventRecord",
    "GeographicRecord",
    "OfficialWarningRecord",
    "ProvenanceQuality",
    "RegionRepository",
    "StationObservationRecord",
    "StationRecord",
    "StationRepository",
    "WeatherForecastSummaryRecord",
    "WeatherRepository",
]
