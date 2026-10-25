"""Repository ports consumed by application services."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol

from jaldrishti.domain.accessibility import AccessibilitySnapshotRecord
from jaldrishti.domain.events import (
    EventEvidenceRecord,
    EventTimelineRecord,
    FloodEventRecord,
)
from jaldrishti.domain.geography import (
    FacilityRecord,
    GeographicRecord,
    RiverRecord,
    SettlementRecord,
)
from jaldrishti.domain.hydrology import StationObservationRecord, StationRecord
from jaldrishti.domain.impact import ImpactSnapshotRecord
from jaldrishti.domain.incidents import IncidentCreateInput, IncidentReportRecord
from jaldrishti.domain.satellite import (
    FloodExtentRecord,
    SatelliteComparisonRecord,
    SatelliteJobRecord,
)
from jaldrishti.domain.weather import OfficialWarningRecord, WeatherForecastSummaryRecord


class RegionRepository(Protocol):
    async def list(self) -> list[GeographicRecord]: ...


class DistrictRepository(Protocol):
    async def list(self, *, region_id: str | None = None) -> list[GeographicRecord]: ...

    async def get(self, district_id: str) -> GeographicRecord | None: ...


class FacilityRepository(Protocol):
    async def list(
        self,
        *,
        region_id: str | None = None,
        district_id: str | None = None,
        category: str | None = None,
    ) -> list[FacilityRecord]: ...


class SettlementRepository(Protocol):
    async def list(
        self,
        *,
        region_id: str | None = None,
        district_id: str | None = None,
        settlement_type: str | None = None,
    ) -> list[SettlementRecord]: ...


class RiverRepository(Protocol):
    async def list(self, *, region_id: str | None = None) -> list[RiverRecord]: ...


class StationRepository(Protocol):
    async def list(self, *, region_id: str | None = None) -> list[StationRecord]: ...

    async def list_observations(
        self,
        station_id: str,
        *,
        limit: int = 168,
    ) -> list[StationObservationRecord]: ...


class WeatherRepository(Protocol):
    async def list_forecast_summaries(
        self,
        *,
        region_id: str | None = None,
        hours: int = 24,
    ) -> list[WeatherForecastSummaryRecord]: ...

    async def list_warnings(
        self,
        *,
        region_id: str | None = None,
        day_index: int = 1,
    ) -> list[OfficialWarningRecord]: ...


class EventRepository(Protocol):
    async def list(
        self,
        *,
        region_id: str | None = None,
        state: str | None = None,
        include_closed: bool = False,
    ) -> list[FloodEventRecord]: ...

    async def get(self, event_id: str) -> FloodEventRecord | None: ...

    async def list_evidence(self, event_id: str) -> list[EventEvidenceRecord]: ...

    async def list_timeline(self, event_id: str) -> list[EventTimelineRecord]: ...


class SatelliteRepository(Protocol):
    async def create_job(
        self,
        *,
        event_id: str,
        request_fingerprint: str,
        before_start: datetime,
        before_end: datetime,
        after_start: datetime,
        after_end: datetime,
        algorithm: str,
        parameters: dict[str, Any],
        catalog_source: str,
    ) -> tuple[SatelliteJobRecord, bool]: ...

    async def get_job(self, job_id: str) -> SatelliteJobRecord | None: ...

    async def list_jobs(self, event_id: str) -> list[SatelliteJobRecord]: ...

    async def list_extents(self, event_id: str) -> list[FloodExtentRecord]: ...

    async def list_comparisons(self, event_id: str) -> list[SatelliteComparisonRecord]: ...


class ImpactRepository(Protocol):
    async def get_latest(self, event_id: str) -> ImpactSnapshotRecord | None: ...


class AccessibilityRepository(Protocol):
    async def get_latest(self, event_id: str) -> AccessibilitySnapshotRecord | None: ...


class IncidentRepository(Protocol):
    async def get_by_submission_id(self, submission_id: str) -> IncidentReportRecord | None: ...

    async def find_matching_open_event(self, longitude: float, latitude: float) -> str | None: ...

    async def point_in_region(
        self, longitude: float, latitude: float, *, region_id: str
    ) -> bool: ...

    async def create(self, value: IncidentCreateInput) -> tuple[IncidentReportRecord, bool]: ...

    async def list_public(self, event_id: str) -> list[IncidentReportRecord]: ...
