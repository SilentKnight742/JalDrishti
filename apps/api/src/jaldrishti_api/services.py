"""Application services orchestrating repositories and infrastructure checks."""

import asyncio
import hashlib
import json
import logging
from datetime import UTC, datetime, timedelta
from typing import ClassVar, Protocol
from uuid import uuid4

from jaldrishti.domain.geography import (
    FacilityRecord,
    GeographicRecord,
    RiverRecord,
    SettlementRecord,
)
from jaldrishti.domain.incidents import IncidentCreateInput, IncidentMediaInput
from jaldrishti.domain.repositories import (
    AccessibilityRepository,
    DistrictRepository,
    EventRepository,
    FacilityRepository,
    ImpactRepository,
    IncidentRepository,
    RegionRepository,
    RiverRepository,
    SatelliteRepository,
    SettlementRepository,
    StationRepository,
    WeatherRepository,
)
from jaldrishti.ingestion.nwdp import PILOT_CAVEATS

from jaldrishti_api.schemas import (
    AccessibilityResponse,
    AccessibilitySummary,
    DependencyStatus,
    DependencyStatuses,
    EventEvidenceProperties,
    EventProperties,
    EventTimelineItem,
    FacilityProperties,
    FeatureProperties,
    FloodExtentProperties,
    GeoJSONFeature,
    GeoJSONFeatureCollection,
    ImpactResponse,
    ImpactSummary,
    IncidentProperties,
    IncidentReceipt,
    IncidentSubmissionRequest,
    PotentialExposureProperties,
    RiverProperties,
    RoadDisruptionProperties,
    SatelliteComparisonProperties,
    SatelliteJobItem,
    SatelliteJobRequest,
    ServiceStatus,
    SettlementAccessibilityProperties,
    SettlementProperties,
    SourceStatus,
    StationObservation,
    StationObservationSeries,
    StationProperties,
    WarningProperties,
    WeatherSummaryProperties,
)

logger = logging.getLogger(__name__)


class DependencyProbe(Protocol):
    name: str

    async def ping(self) -> None: ...


class SatelliteJobQueue(Protocol):
    def enqueue(self, job_id: str) -> None: ...


class IncidentRateLimiter(Protocol):
    async def allow(self, key: str, *, limit: int, window_seconds: int) -> bool: ...


class ContactCipher(Protocol):
    key_id: str

    def encrypt(self, value: str) -> bytes: ...


class IncidentMediaStore(Protocol):
    def store(self, *, report_id: str, media_id: str, content: bytes) -> IncidentMediaInput: ...

    def discard(self, media: IncidentMediaInput) -> None: ...


class IncidentRateLimitExceeded(RuntimeError):
    pass


class IncidentSubmissionConflict(RuntimeError):
    pass


class IncidentOutsideCoverage(RuntimeError):
    pass


def _properties(record: GeographicRecord) -> FeatureProperties:
    return FeatureProperties(
        id=record.id,
        code=record.code,
        name=record.name,
        source=record.source,
        source_url=record.source_url,
        source_version=record.source_version,
        quality=record.quality,
        ingested_at=record.ingested_at,
    )


def _feature(record: GeographicRecord) -> GeoJSONFeature[FeatureProperties]:
    return GeoJSONFeature[FeatureProperties](
        geometry=record.geometry,
        properties=_properties(record),
    )


def _facility_feature(record: FacilityRecord) -> GeoJSONFeature[FacilityProperties]:
    return GeoJSONFeature[FacilityProperties](
        geometry=record.geometry,
        properties=FacilityProperties(
            **_properties(record).model_dump(),
            category=record.category,
            subcategory=record.subcategory,
        ),
    )


def _settlement_feature(record: SettlementRecord) -> GeoJSONFeature[SettlementProperties]:
    return GeoJSONFeature[SettlementProperties](
        geometry=record.geometry,
        properties=SettlementProperties(
            **_properties(record).model_dump(),
            settlement_type=record.settlement_type,
            population=record.population,
        ),
    )


def _river_feature(record: RiverRecord) -> GeoJSONFeature[RiverProperties]:
    return GeoJSONFeature[RiverProperties](
        geometry=record.geometry,
        properties=RiverProperties(
            **_properties(record).model_dump(),
            river_class=record.river_class,
        ),
    )


class GeographyService:
    def __init__(
        self,
        *,
        regions: RegionRepository,
        districts: DistrictRepository,
    ) -> None:
        self._regions = regions
        self._districts = districts

    async def list_regions(self) -> GeoJSONFeatureCollection[FeatureProperties]:
        records = await self._regions.list()
        return GeoJSONFeatureCollection[FeatureProperties](
            features=[_feature(item) for item in records]
        )

    async def list_districts(
        self,
        *,
        region_id: str | None,
    ) -> GeoJSONFeatureCollection[FeatureProperties]:
        records = await self._districts.list(region_id=region_id)
        return GeoJSONFeatureCollection[FeatureProperties](
            features=[_feature(item) for item in records]
        )

    async def get_district(
        self,
        district_id: str,
    ) -> GeoJSONFeature[FeatureProperties] | None:
        record = await self._districts.get(district_id)
        return None if record is None else _feature(record)


class FacilityService:
    def __init__(self, *, facilities: FacilityRepository) -> None:
        self._facilities = facilities

    async def list_facilities(
        self,
        *,
        region_id: str | None,
        district_id: str | None,
        category: str | None,
    ) -> GeoJSONFeatureCollection[FacilityProperties]:
        records = await self._facilities.list(
            region_id=region_id,
            district_id=district_id,
            category=category,
        )
        return GeoJSONFeatureCollection[FacilityProperties](
            features=[_facility_feature(item) for item in records]
        )


class SettlementService:
    def __init__(self, *, settlements: SettlementRepository) -> None:
        self._settlements = settlements

    async def list_settlements(
        self,
        *,
        region_id: str | None,
        district_id: str | None,
        settlement_type: str | None,
    ) -> GeoJSONFeatureCollection[SettlementProperties]:
        records = await self._settlements.list(
            region_id=region_id,
            district_id=district_id,
            settlement_type=settlement_type,
        )
        return GeoJSONFeatureCollection[SettlementProperties](
            features=[_settlement_feature(item) for item in records]
        )


class RiverService:
    def __init__(self, *, rivers: RiverRepository) -> None:
        self._rivers = rivers

    async def list_rivers(
        self,
        *,
        region_id: str | None,
    ) -> GeoJSONFeatureCollection[RiverProperties]:
        records = await self._rivers.list(region_id=region_id)
        return GeoJSONFeatureCollection[RiverProperties](
            features=[_river_feature(item) for item in records]
        )


class StationService:
    def __init__(self, *, stations: StationRepository) -> None:
        self._stations = stations

    async def list_stations(
        self,
        *,
        region_id: str | None,
    ) -> GeoJSONFeatureCollection[StationProperties]:
        records = await self._stations.list(region_id=region_id)
        return GeoJSONFeatureCollection[StationProperties](
            features=[
                GeoJSONFeature[StationProperties](
                    geometry=record.geometry,
                    properties=StationProperties(
                        id=record.id,
                        code=record.external_id,
                        name=record.name,
                        source=record.source,
                        source_url=record.source_url,
                        source_version=record.source_version,
                        quality=record.quality,
                        ingested_at=record.ingested_at,
                        region_id=record.region_id,
                        district_id=record.district_id,
                        external_id=record.external_id,
                        river_name=record.river_name,
                        basin_name=record.basin_name,
                        warning_level_m=record.warning_level_m,
                        danger_level_m=record.danger_level_m,
                        datum=record.datum,
                        time_zone=record.time_zone,
                        operational_status=record.operational_status,
                        coverage_status=record.coverage_status,
                    ),
                )
                for record in records
            ]
        )

    async def list_observations(
        self,
        station_id: str,
        *,
        limit: int,
    ) -> StationObservationSeries:
        records = await self._stations.list_observations(station_id, limit=limit)
        return StationObservationSeries(
            station_id=station_id,
            caveats=list(PILOT_CAVEATS),
            observations=[
                StationObservation(
                    id=record.id,
                    station_id=record.station_id,
                    source_observed_at=record.source_observed_at,
                    observed_at=record.observed_at,
                    water_level_m=record.water_level_m,
                    unit=record.unit,
                    quality_flag=record.quality_flag,
                    source=record.source,
                    source_url=record.source_url,
                    source_version=record.source_version,
                    quality=record.quality,
                    ingested_at=record.ingested_at,
                )
                for record in records
            ],
        )


class WeatherService:
    def __init__(self, *, weather: WeatherRepository) -> None:
        self._weather = weather

    async def list_forecast_summaries(
        self,
        *,
        region_id: str | None,
        hours: int,
    ) -> GeoJSONFeatureCollection[WeatherSummaryProperties]:
        records = await self._weather.list_forecast_summaries(
            region_id=region_id,
            hours=hours,
        )
        return GeoJSONFeatureCollection[WeatherSummaryProperties](
            features=[
                GeoJSONFeature[WeatherSummaryProperties](
                    geometry=record.geometry,
                    properties=WeatherSummaryProperties(
                        id=f"weather-summary-{record.district_id}",
                        code=None,
                        name=record.district_name,
                        district_id=record.district_id,
                        precipitation_24h_mm=record.precipitation_24h_mm,
                        maximum_probability_pct=record.maximum_probability_pct,
                        forecast_from=record.forecast_from,
                        forecast_through=record.forecast_through,
                        model=record.model,
                        source=record.source,
                        source_url=record.source_url,
                        source_version=record.source_version,
                        quality=record.quality,
                        ingested_at=record.ingested_at,
                    ),
                )
                for record in records
            ]
        )

    async def list_warnings(
        self,
        *,
        region_id: str | None,
        day_index: int,
    ) -> GeoJSONFeatureCollection[WarningProperties]:
        records = await self._weather.list_warnings(
            region_id=region_id,
            day_index=day_index,
        )
        return GeoJSONFeatureCollection[WarningProperties](
            features=[
                GeoJSONFeature[WarningProperties](
                    geometry=record.geometry,
                    properties=WarningProperties(
                        id=record.id,
                        code=None,
                        name=record.district_name,
                        district_id=record.district_id,
                        external_id=record.external_id,
                        issue_at=record.issue_at,
                        valid_date=record.valid_date,
                        day_index=record.day_index,
                        severity=record.severity,
                        color_code=record.color_code,
                        warning_codes=record.warning_codes,
                        hazards=record.hazards,
                        description=record.description,
                        source=record.source,
                        source_url=record.source_url,
                        source_version=record.source_version,
                        quality=record.quality,
                        ingested_at=record.ingested_at,
                    ),
                )
                for record in records
            ]
        )


class EventService:
    def __init__(self, *, events: EventRepository) -> None:
        self._events = events

    @staticmethod
    def _feature(record) -> GeoJSONFeature[EventProperties]:
        return GeoJSONFeature[EventProperties](
            geometry=record.geometry,
            properties=EventProperties(
                id=record.id,
                code=None,
                name=record.name,
                source="JalDrishti transparent rule engine",
                source_url=None,
                source_version=record.rule_version,
                quality="model_derived",
                ingested_at=record.last_updated_at,
                region_id=record.region_id,
                primary_district_id=record.primary_district_id,
                state=record.state,
                started_at=record.started_at,
                last_updated_at=record.last_updated_at,
                state_changed_at=record.state_changed_at,
                ended_at=record.ended_at,
                trigger_summary=record.trigger_summary,
                rainfall_status=record.rainfall_status,
                river_status=record.river_status,
                warning_status=record.warning_status,
                satellite_status=record.satellite_status,
                created_by=record.created_by,
                rule_version=record.rule_version,
                rationale=record.rationale,
            ),
        )

    async def list_events(
        self,
        *,
        region_id: str | None,
        state: str | None,
        include_closed: bool,
    ) -> GeoJSONFeatureCollection[EventProperties]:
        records = await self._events.list(
            region_id=region_id,
            state=state,
            include_closed=include_closed,
        )
        return GeoJSONFeatureCollection[EventProperties](
            features=[self._feature(record) for record in records]
        )

    async def get_event(self, event_id: str) -> GeoJSONFeature[EventProperties] | None:
        record = await self._events.get(event_id)
        return None if record is None else self._feature(record)

    async def list_evidence(
        self,
        event_id: str,
    ) -> GeoJSONFeatureCollection[EventEvidenceProperties]:
        records = await self._events.list_evidence(event_id)
        return GeoJSONFeatureCollection[EventEvidenceProperties](
            features=[
                GeoJSONFeature[EventEvidenceProperties](
                    geometry=record.geometry,
                    properties=EventEvidenceProperties(
                        id=record.id,
                        code=None,
                        name=record.title,
                        source=record.source,
                        source_url=record.source_url,
                        source_version=record.source_version,
                        quality=record.quality,
                        ingested_at=record.ingested_at,
                        event_id=record.event_id,
                        evidence_type=record.evidence_type,
                        summary=record.summary,
                        source_record_id=record.source_record_id,
                        observed_at=record.observed_at,
                        published_at=record.published_at,
                        metadata=record.metadata,
                    ),
                )
                for record in records
            ]
        )

    async def list_timeline(self, event_id: str) -> list[EventTimelineItem]:
        return [
            EventTimelineItem(
                id=record.id,
                event_id=record.event_id,
                evidence_id=record.evidence_id,
                occurred_at=record.occurred_at,
                category=record.category,
                state_from=record.state_from,
                state_to=record.state_to,
                summary=record.summary,
                metadata=record.metadata,
            )
            for record in await self._events.list_timeline(event_id)
        ]


class SatelliteService:
    """Create idempotent event-scoped SAR work and expose its evidence."""

    algorithm = "jaldrishti-opera-rtc-change"

    def __init__(
        self,
        *,
        events: EventRepository,
        satellite: SatelliteRepository,
        queue: SatelliteJobQueue,
    ) -> None:
        self._events = events
        self._satellite = satellite
        self._queue = queue

    @staticmethod
    def _job_item(record) -> SatelliteJobItem:
        return SatelliteJobItem(
            id=record.id,
            event_id=record.event_id,
            status=record.status,
            requested_at=record.requested_at,
            started_at=record.started_at,
            completed_at=record.completed_at,
            before_start=record.before_start,
            before_end=record.before_end,
            after_start=record.after_start,
            after_end=record.after_end,
            algorithm=record.algorithm,
            parameters=record.parameters,
            error_code=record.error_code,
            error_message=record.error_message,
            catalog_source=record.catalog_source,
            catalog_url=record.catalog_url,
            scene_count=record.scene_count,
        )

    async def create_job(
        self,
        event_id: str,
        request: SatelliteJobRequest,
    ) -> SatelliteJobItem | None:
        event = await self._events.get(event_id)
        if event is None:
            return None
        before_start = event.started_at - timedelta(days=request.before_days)
        before_end = event.started_at
        after_start = event.started_at
        after_end = event.started_at + timedelta(days=request.after_days)
        parameters = request.model_dump(mode="json")
        fingerprint_payload = {
            "event_id": event_id,
            "before_start": before_start.isoformat(),
            "before_end": before_end.isoformat(),
            "after_start": after_start.isoformat(),
            "after_end": after_end.isoformat(),
            "algorithm": self.algorithm,
            "parameters": parameters,
        }
        fingerprint = hashlib.sha256(
            json.dumps(fingerprint_payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        job, created = await self._satellite.create_job(
            event_id=event_id,
            request_fingerprint=fingerprint,
            before_start=before_start,
            before_end=before_end,
            after_start=after_start,
            after_end=after_end,
            algorithm=self.algorithm,
            parameters=parameters,
            catalog_source="NASA ASF DAAC OPERA-S1 catalogue",
        )
        if created:
            self._queue.enqueue(job.id)
        return self._job_item(job)

    async def get_job(self, job_id: str) -> SatelliteJobItem | None:
        job = await self._satellite.get_job(job_id)
        return None if job is None else self._job_item(job)

    async def list_jobs(self, event_id: str) -> list[SatelliteJobItem]:
        return [self._job_item(item) for item in await self._satellite.list_jobs(event_id)]

    async def list_extents(
        self,
        event_id: str,
    ) -> GeoJSONFeatureCollection[FloodExtentProperties]:
        records = await self._satellite.list_extents(event_id)
        return GeoJSONFeatureCollection[FloodExtentProperties](
            features=[
                GeoJSONFeature[FloodExtentProperties](
                    geometry=record.geometry,
                    properties=FloodExtentProperties(
                        id=record.id,
                        code=None,
                        name=f"Satellite change extent · {record.acquired_at.date().isoformat()}",
                        source=record.source,
                        source_url=record.source_url,
                        source_version=record.source_version,
                        quality=record.quality,
                        ingested_at=record.ingested_at,
                        event_id=record.event_id,
                        job_id=record.job_id,
                        acquired_at=record.acquired_at,
                        algorithm=record.algorithm,
                        algorithm_version=record.algorithm_version,
                        parameters=record.parameters,
                        area_km2=record.area_km2,
                        high_evidence_area_km2=record.high_evidence_area_km2,
                        valid_coverage_fraction=record.valid_coverage_fraction,
                        resolution_m=record.resolution_m,
                        analysis_crs=record.analysis_crs,
                        raster_uri=record.raster_uri,
                        metadata=record.metadata,
                    ),
                )
                for record in records
            ]
        )

    async def list_comparisons(
        self,
        event_id: str,
    ) -> GeoJSONFeatureCollection[SatelliteComparisonProperties]:
        records = await self._satellite.list_comparisons(event_id)
        return GeoJSONFeatureCollection[SatelliteComparisonProperties](
            features=[
                GeoJSONFeature[SatelliteComparisonProperties](
                    geometry=record.geometry,
                    properties=SatelliteComparisonProperties(
                        id=record.id,
                        code=None,
                        name=f"Comparison with {record.reference_name}",
                        source=record.source,
                        source_url=record.source_url,
                        source_version=record.source_version,
                        quality=record.quality,
                        ingested_at=record.ingested_at,
                        event_id=record.event_id,
                        flood_extent_id=record.flood_extent_id,
                        reference_name=record.reference_name,
                        reference_acquired_at=record.reference_acquired_at,
                        compared_at=record.compared_at,
                        analysis_crs=record.analysis_crs,
                        iou=record.iou,
                        dice_f1=record.dice_f1,
                        precision=record.precision,
                        recall=record.recall,
                        detected_area_km2=record.detected_area_km2,
                        reference_area_km2=record.reference_area_km2,
                        overlap_area_km2=record.overlap_area_km2,
                        union_area_km2=record.union_area_km2,
                        area_difference_km2=record.area_difference_km2,
                        temporal_offset_hours=record.temporal_offset_hours,
                        caveat=record.caveat,
                        source_record_id=record.source_record_id,
                        observed_at=record.observed_at,
                        published_at=record.published_at,
                        metadata=record.metadata,
                    ),
                )
                for record in records
            ]
        )


class ImpactService:
    """Expose potential exposure while retaining data-coverage limitations."""

    caveats: ClassVar[list[str]] = [
        "Geometric intersection indicates potential exposure, not observed damage or loss.",
        "Settlement, facility and population results inherit the completeness and positional limitations of their source datasets.",
        "Unavailable roads or buildings are returned as null, never as measured zero.",
    ]

    def __init__(self, *, events: EventRepository, impact: ImpactRepository) -> None:
        self._events = events
        self._impact = impact

    async def get_impact(self, event_id: str) -> ImpactResponse | None:
        if await self._events.get(event_id) is None:
            return None
        record = await self._impact.get_latest(event_id)
        if record is None:
            return ImpactResponse(
                status="not_available",
                summary=None,
                exposures=GeoJSONFeatureCollection[PotentialExposureProperties](features=[]),
                caveats=self.caveats,
            )
        exposures = GeoJSONFeatureCollection[PotentialExposureProperties](
            features=[
                GeoJSONFeature[PotentialExposureProperties](
                    geometry=item.geometry,
                    properties=PotentialExposureProperties(
                        id=item.id,
                        code=None,
                        name=item.name,
                        source=item.source,
                        source_url=item.source_url,
                        source_version=item.source_version,
                        quality=item.quality,
                        ingested_at=item.ingested_at,
                        snapshot_id=item.snapshot_id,
                        event_id=item.event_id,
                        flood_extent_id=item.flood_extent_id,
                        asset_type=item.asset_type,
                        asset_id=item.asset_id,
                        metric_type=item.metric_type,
                        metric_value=item.metric_value,
                        unit=item.unit,
                        source_record_id=item.source_record_id,
                        observed_at=item.observed_at,
                        published_at=item.published_at,
                        metadata=item.metadata,
                    ),
                )
                for item in record.exposures
            ]
        )
        return ImpactResponse(
            status="available",
            summary=ImpactSummary(
                id=record.id,
                event_id=record.event_id,
                flood_extent_id=record.flood_extent_id,
                calculated_at=record.calculated_at,
                algorithm=record.algorithm,
                algorithm_version=record.algorithm_version,
                inundated_area_km2=record.inundated_area_km2,
                settlement_count=record.settlement_count,
                facility_count=record.facility_count,
                population_potentially_exposed=record.population_potentially_exposed,
                population_record_count=record.population_record_count,
                road_overlap_km=record.road_overlap_km,
                building_count=record.building_count,
                coverage=record.coverage,
                metadata=record.metadata,
            ),
            exposures=exposures,
            caveats=self.caveats,
        )


class AccessibilityService:
    """Expose network screening without implying observed road conditions."""

    caveats: ClassVar[list[str]] = [
        "Road intersections are potential disruptions, not confirmed closures.",
        "Routes use a partial OSM backbone and are not safe-navigation instructions.",
        "A potentially isolated settlement requires baseline access that disappears in the screened network.",
    ]

    def __init__(
        self,
        *,
        events: EventRepository,
        accessibility: AccessibilityRepository,
    ) -> None:
        self._events = events
        self._accessibility = accessibility

    async def get_accessibility(self, event_id: str) -> AccessibilityResponse | None:
        if await self._events.get(event_id) is None:
            return None
        record = await self._accessibility.get_latest(event_id)
        if record is None:
            return AccessibilityResponse(
                status="not_available",
                summary=None,
                road_disruptions=GeoJSONFeatureCollection[RoadDisruptionProperties](features=[]),
                settlements=GeoJSONFeatureCollection[SettlementAccessibilityProperties](
                    features=[]
                ),
                caveats=self.caveats,
            )
        disruptions = GeoJSONFeatureCollection[RoadDisruptionProperties](
            features=[
                GeoJSONFeature[RoadDisruptionProperties](
                    geometry=item.geometry,
                    properties=RoadDisruptionProperties(
                        id=item.id,
                        code=None,
                        name=item.name,
                        source=item.source,
                        source_url=None,
                        source_version=item.source_version,
                        quality=item.quality,
                        ingested_at=item.ingested_at,
                        snapshot_id=item.snapshot_id,
                        event_id=item.event_id,
                        flood_extent_id=item.flood_extent_id,
                        road_segment_id=item.road_segment_id,
                        road_class=item.road_class,
                        overlap_km=item.overlap_km,
                        source_record_id=item.source_record_id,
                        observed_at=item.observed_at,
                        metadata=item.metadata,
                    ),
                )
                for item in record.road_disruptions
            ]
        )
        settlements = GeoJSONFeatureCollection[SettlementAccessibilityProperties](
            features=[
                GeoJSONFeature[SettlementAccessibilityProperties](
                    geometry=item.geometry,
                    properties=SettlementAccessibilityProperties(
                        id=item.id,
                        code=None,
                        name=item.name,
                        source=item.source,
                        source_url=None,
                        source_version=item.source_version,
                        quality=item.quality,
                        ingested_at=item.ingested_at,
                        snapshot_id=item.snapshot_id,
                        event_id=item.event_id,
                        flood_extent_id=item.flood_extent_id,
                        settlement_id=item.settlement_id,
                        snapped_distance_m=item.snapped_distance_m,
                        major_road_reachable_before=item.major_road_reachable_before,
                        major_road_reachable_after=item.major_road_reachable_after,
                        hospital_reachable_before=item.hospital_reachable_before,
                        hospital_reachable_after=item.hospital_reachable_after,
                        nearest_major_road_km=item.nearest_major_road_km,
                        nearest_hospital_km=item.nearest_hospital_km,
                        potentially_isolated=item.potentially_isolated,
                        assessment_status=item.assessment_status,
                        source_record_id=item.source_record_id,
                        observed_at=item.observed_at,
                        metadata=item.metadata,
                    ),
                )
                for item in record.settlements
            ]
        )
        return AccessibilityResponse(
            status=("available" if record.status == "available" else "not_configured"),
            summary=AccessibilitySummary(
                id=record.id,
                event_id=record.event_id,
                flood_extent_id=record.flood_extent_id,
                calculated_at=record.calculated_at,
                algorithm=record.algorithm,
                algorithm_version=record.algorithm_version,
                status=record.status,
                road_count=record.road_count,
                graph_node_count=record.graph_node_count,
                graph_edge_count=record.graph_edge_count,
                potentially_affected_road_count=record.potentially_affected_road_count,
                potentially_affected_road_km=record.potentially_affected_road_km,
                assessed_settlement_count=record.assessed_settlement_count,
                potentially_isolated_settlement_count=(
                    record.potentially_isolated_settlement_count
                ),
                coverage=record.coverage,
                metadata=record.metadata,
            ),
            road_disruptions=disruptions,
            settlements=settlements,
            caveats=self.caveats,
        )


class IncidentService:
    """Accept a report without leaking its exact location or private fields."""

    _labels: ClassVar[dict[str, str]] = {
        "stranded_people": "People potentially stranded",
        "medical_emergency": "Medical emergency reported",
        "road_flooded": "Road flooding reported",
        "bridge_damage": "Bridge damage reported",
        "building_flooding": "Building flooding reported",
        "embankment_issue": "Embankment issue reported",
        "other": "Flood-related incident reported",
    }

    def __init__(
        self,
        *,
        events: EventRepository,
        incidents: IncidentRepository,
        limiter: IncidentRateLimiter,
        cipher: ContactCipher,
        media_store: IncidentMediaStore,
        rate_limit_per_hour: int,
    ) -> None:
        self._events = events
        self._incidents = incidents
        self._limiter = limiter
        self._cipher = cipher
        self._media_store = media_store
        self._rate_limit_per_hour = rate_limit_per_hour

    @staticmethod
    def _fingerprint(request: IncidentSubmissionRequest, photo: bytes | None) -> str:
        payload = request.model_dump(mode="json")
        payload["photo_sha256"] = hashlib.sha256(photo).hexdigest() if photo else None
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()

    @staticmethod
    def _receipt(record, *, duplicate: bool) -> IncidentReceipt:
        return IncidentReceipt(
            public_reference=record.public_reference,
            event_id=record.event_id,
            status=record.status,
            verification_state=record.verification_state,
            reported_at=record.reported_at,
            public_location_precision="approximately 1 km; exact location withheld",
            duplicate=duplicate,
            message=(
                "Report received for review. It remains unverified and is not an emergency-service dispatch."
            ),
        )

    async def submit(
        self,
        request: IncidentSubmissionRequest,
        *,
        client_key: str,
        photo: bytes | None,
    ) -> IncidentReceipt:
        submission_id = str(request.submission_id)
        fingerprint = self._fingerprint(request, photo)
        existing = await self._incidents.get_by_submission_id(submission_id)
        if existing is not None:
            if existing.request_fingerprint != fingerprint:
                raise IncidentSubmissionConflict(
                    "That submission identifier was already used for different content"
                )
            return self._receipt(existing, duplicate=True)
        if not await self._limiter.allow(
            client_key,
            limit=self._rate_limit_per_hour,
            window_seconds=3600,
        ):
            raise IncidentRateLimitExceeded("Incident submission limit reached")
        if not await self._incidents.point_in_region(
            request.longitude, request.latitude, region_id="assam"
        ):
            raise IncidentOutsideCoverage("The selected location is outside Assam")

        reported_at = datetime.now(UTC)
        event_id = await self._incidents.find_matching_open_event(
            request.longitude, request.latitude
        )
        digest = hashlib.sha256(submission_id.encode("utf-8")).hexdigest()
        report_id = f"incident-{digest[:32]}"
        public_reference = f"JD-{digest[:10].upper()}"
        encrypted_contact = self._cipher.encrypt(request.contact) if request.contact else None
        media = None
        if photo:
            media = self._media_store.store(
                report_id=report_id,
                media_id=f"media-{uuid4().hex}",
                content=photo,
            )
        people_phrase = ""
        if request.people_affected is not None:
            qualifier = "approximately " if request.people_count_approximate else ""
            people_phrase = f"; {qualifier}{request.people_affected} people reported"
        value = IncidentCreateInput(
            id=report_id,
            submission_id=submission_id,
            public_reference=public_reference,
            request_fingerprint=fingerprint,
            event_id=event_id,
            incident_type=request.incident_type,
            people_affected=request.people_affected,
            people_count_approximate=request.people_count_approximate,
            description_private=request.description,
            public_summary=f"{self._labels[request.incident_type]}{people_phrase}",
            reported_at=reported_at,
            location_method=request.location_method,
            location_accuracy_m=request.location_accuracy_m,
            exact_longitude=request.longitude,
            exact_latitude=request.latitude,
            public_longitude=round(request.longitude, 2),
            public_latitude=round(request.latitude, 2),
            privacy_consent_at=reported_at,
            encrypted_contact=encrypted_contact,
            encryption_key_id=(self._cipher.key_id if encrypted_contact else None),
            media=media,
            metadata={
                "public_location_coarsening_degrees": 0.01,
                "verification_notice": "Unverified public report",
            },
        )
        try:
            record, created = await self._incidents.create(value)
        except Exception:
            if media is not None:
                self._media_store.discard(media)
            raise
        if not created and media is not None:
            self._media_store.discard(media)
        if record.request_fingerprint != fingerprint:
            raise IncidentSubmissionConflict(
                "That submission identifier was already used for different content"
            )
        return self._receipt(record, duplicate=not created)

    async def list_event_incidents(
        self, event_id: str
    ) -> GeoJSONFeatureCollection[IncidentProperties] | None:
        if await self._events.get(event_id) is None:
            return None
        records = await self._incidents.list_public(event_id)
        return GeoJSONFeatureCollection[IncidentProperties](
            features=[
                GeoJSONFeature[IncidentProperties](
                    geometry=item.public_geometry,
                    properties=IncidentProperties(
                        id=item.id,
                        code=None,
                        name=item.public_summary,
                        source=item.source,
                        source_url=None,
                        source_version=item.source_version,
                        quality=item.quality,
                        ingested_at=item.ingested_at,
                        event_id=item.event_id,
                        public_reference=item.public_reference,
                        incident_type=item.incident_type,
                        people_affected=item.people_affected,
                        people_count_approximate=item.people_count_approximate,
                        public_summary=item.public_summary,
                        reported_at=item.reported_at,
                        verification_state=item.verification_state,
                        status=item.status,
                        location_method=item.location_method,
                        location_accuracy_m=item.location_accuracy_m,
                        media_count=item.media_count,
                        source_record_id=item.source_record_id,
                        metadata=item.metadata,
                    ),
                )
                for item in records
            ]
        )


class HealthService:
    def __init__(
        self,
        *,
        service: str,
        version: str,
        database: DependencyProbe,
        redis: DependencyProbe,
        sources: list[SourceStatus] | None = None,
        timeout_seconds: float = 2.0,
    ) -> None:
        self._service = service
        self._version = version
        self._database = database
        self._redis = redis
        self._sources = sources or []
        self._timeout_seconds = timeout_seconds

    async def _check(self, probe: DependencyProbe) -> DependencyStatus:
        try:
            await asyncio.wait_for(probe.ping(), timeout=self._timeout_seconds)
        except Exception as exc:  # health must survive unknown driver failures
            logger.warning(
                "dependency health check failed",
                extra={"dependency": probe.name, "error_type": type(exc).__name__},
            )
            return DependencyStatus(status="unavailable")
        return DependencyStatus(status="ok")

    async def status(self) -> ServiceStatus:
        database, redis = await asyncio.gather(
            self._check(self._database),
            self._check(self._redis),
        )
        overall = "ok" if database.status == redis.status == "ok" else "degraded"
        return ServiceStatus(
            status=overall,
            service=self._service,
            version=self._version,
            checked_at=datetime.now(UTC),
            dependencies=DependencyStatuses(database=database, redis=redis),
            sources=self._sources,
        )
