"""SQLAlchemy implementations of the geography repository ports."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from typing import Any

from geoalchemy2.shape import from_shape, to_shape
from shapely.geometry import Point, mapping
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from jaldrishti.domain.accessibility import (
    AccessibilitySnapshotRecord,
    RoadDisruptionRecord,
    SettlementAccessibilityRecord,
)
from jaldrishti.domain.events import (
    EventEvidenceRecord,
    EventTimelineRecord,
    FloodEventRecord,
)
from jaldrishti.domain.geography import (
    FacilityRecord,
    GeographicRecord,
    GeoJSONMapping,
    RiverRecord,
    SettlementRecord,
)
from jaldrishti.domain.hydrology import StationObservationRecord, StationRecord
from jaldrishti.domain.impact import ImpactSnapshotRecord, PotentialExposureRecord
from jaldrishti.domain.incidents import IncidentCreateInput, IncidentReportRecord
from jaldrishti.domain.provenance import ProvenanceQuality
from jaldrishti.domain.satellite import (
    FloodExtentRecord,
    SatelliteComparisonRecord,
    SatelliteJobRecord,
)
from jaldrishti.domain.weather import OfficialWarningRecord, WeatherForecastSummaryRecord
from jaldrishti.persistence.models import (
    AccessibilitySnapshot,
    District,
    EventEvidence,
    EventTimelineEntry,
    Facility,
    FloodEvent,
    FloodExtent,
    ImpactSnapshot,
    IncidentContact,
    IncidentMedia,
    IncidentReport,
    OfficialWarning,
    PotentialExposure,
    Region,
    River,
    RoadDisruption,
    SatelliteComparison,
    SatelliteJob,
    SatelliteScene,
    Settlement,
    SettlementAccessibility,
    Station,
    StationObservation,
    WeatherForecast,
)


def _as_geojson(value: Any) -> GeoJSONMapping | None:
    if value is None:
        return None
    if isinstance(value, Mapping):
        return dict(value)
    if hasattr(value, "__geo_interface__"):
        return dict(value.__geo_interface__)
    return dict(mapping(to_shape(value)))


def _geographic_record(row: Region | District) -> GeographicRecord:
    return GeographicRecord(
        id=row.id,
        code=row.code,
        name=row.name,
        geometry=_as_geojson(row.geometry),
        source=row.source,
        source_url=row.source_url,
        source_version=row.source_version,
        quality=row.quality,
        ingested_at=row.ingested_at,
    )


def _event_record(row: FloodEvent) -> FloodEventRecord:
    raw_rationale = row.metadata_.get("rationale", [])
    rationale = [str(item) for item in raw_rationale] if isinstance(raw_rationale, list) else []
    return FloodEventRecord(
        id=row.id,
        region_id=row.region_id,
        primary_district_id=row.primary_district_id,
        name=row.name,
        geometry=_as_geojson(row.geometry) or {"type": "MultiPolygon", "coordinates": []},
        started_at=row.started_at,
        last_updated_at=row.last_updated_at,
        state_changed_at=row.state_changed_at,
        ended_at=row.ended_at,
        state=row.state,
        trigger_summary=row.trigger_summary,
        rainfall_status=row.rainfall_status,
        river_status=row.river_status,
        warning_status=row.warning_status,
        satellite_status=row.satellite_status,
        created_by=row.created_by,
        rule_version=row.rule_version,
        rationale=rationale,
    )


class SQLAlchemyRegionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list(self) -> list[GeographicRecord]:
        rows = (await self._session.scalars(select(Region).order_by(Region.name))).all()
        return [_geographic_record(row) for row in rows]


class SQLAlchemyDistrictRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list(self, *, region_id: str | None = None) -> list[GeographicRecord]:
        statement = select(District)
        if region_id is not None:
            statement = statement.where(District.region_id == region_id)
        rows = (await self._session.scalars(statement.order_by(District.name))).all()
        return [_geographic_record(row) for row in rows]

    async def get(self, district_id: str) -> GeographicRecord | None:
        row = await self._session.get(District, district_id)
        return None if row is None else _geographic_record(row)


class SQLAlchemyFacilityRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list(
        self,
        *,
        region_id: str | None = None,
        district_id: str | None = None,
        category: str | None = None,
    ) -> list[FacilityRecord]:
        statement = select(Facility)
        if region_id is not None:
            statement = statement.where(Facility.region_id == region_id)
        if district_id is not None:
            statement = statement.where(Facility.district_id == district_id)
        if category is not None:
            statement = statement.where(Facility.category == category)
        rows = (await self._session.scalars(statement.order_by(Facility.name))).all()
        return [
            FacilityRecord(
                id=row.id,
                code=row.code,
                name=row.name,
                geometry=_as_geojson(row.geometry),
                source=row.source,
                source_url=row.source_url,
                source_version=row.source_version,
                quality=row.quality,
                ingested_at=row.ingested_at,
                category=row.category,
                subcategory=row.subcategory,
            )
            for row in rows
        ]


class SQLAlchemySettlementRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list(
        self,
        *,
        region_id: str | None = None,
        district_id: str | None = None,
        settlement_type: str | None = None,
    ) -> list[SettlementRecord]:
        statement = select(Settlement)
        if region_id is not None:
            statement = statement.where(Settlement.region_id == region_id)
        if district_id is not None:
            statement = statement.where(Settlement.district_id == district_id)
        if settlement_type is not None:
            statement = statement.where(Settlement.settlement_type == settlement_type)
        rows = (await self._session.scalars(statement.order_by(Settlement.name))).all()
        return [
            SettlementRecord(
                id=row.id,
                code=row.code,
                name=row.name,
                geometry=_as_geojson(row.geometry),
                source=row.source,
                source_url=row.source_url,
                source_version=row.source_version,
                quality=row.quality,
                ingested_at=row.ingested_at,
                settlement_type=row.settlement_type,
                population=row.population,
            )
            for row in rows
        ]


class SQLAlchemyRiverRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list(self, *, region_id: str | None = None) -> list[RiverRecord]:
        statement = select(River)
        if region_id is not None:
            statement = statement.where(River.region_id == region_id)
        rows = (await self._session.scalars(statement.order_by(River.name))).all()
        return [
            RiverRecord(
                id=row.id,
                code=row.code,
                name=row.name,
                geometry=_as_geojson(row.geometry),
                source=row.source,
                source_url=row.source_url,
                source_version=row.source_version,
                quality=row.quality,
                ingested_at=row.ingested_at,
                river_class=row.river_class,
            )
            for row in rows
        ]


class SQLAlchemyStationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list(self, *, region_id: str | None = None) -> list[StationRecord]:
        statement = select(Station)
        if region_id is not None:
            statement = statement.where(Station.region_id == region_id)
        rows = (await self._session.scalars(statement.order_by(Station.name))).all()
        return [
            StationRecord(
                id=row.id,
                region_id=row.region_id,
                district_id=row.district_id,
                external_id=row.external_id,
                name=row.name,
                geometry=_as_geojson(row.geometry) or {"type": "Point", "coordinates": []},
                river_name=row.river_name,
                basin_name=row.basin_name,
                warning_level_m=row.warning_level_m,
                danger_level_m=row.danger_level_m,
                datum=row.datum,
                time_zone=row.time_zone,
                operational_status=row.operational_status,
                coverage_status=row.coverage_status,
                source=row.source,
                source_url=row.source_url,
                source_version=row.source_version,
                quality=row.quality,
                ingested_at=row.ingested_at,
            )
            for row in rows
        ]

    async def list_observations(
        self,
        station_id: str,
        *,
        limit: int = 168,
    ) -> list[StationObservationRecord]:
        statement = (
            select(StationObservation)
            .where(StationObservation.station_id == station_id)
            .order_by(StationObservation.source_observed_at_local.desc())
            .limit(limit)
        )
        rows = (await self._session.scalars(statement)).all()
        return [
            StationObservationRecord(
                id=row.id,
                station_id=row.station_id,
                source_observed_at=row.source_observed_at,
                observed_at=row.observed_at,
                water_level_m=row.water_level_m,
                unit=row.unit,
                quality_flag=row.quality_flag,
                source=row.source,
                source_url=row.source_url,
                source_version=row.source_version,
                quality=row.quality,
                ingested_at=row.ingested_at,
            )
            for row in rows
        ]


class SQLAlchemyWeatherRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_forecast_summaries(
        self,
        *,
        region_id: str | None = None,
        hours: int = 24,
    ) -> list[WeatherForecastSummaryRecord]:
        starts_at = datetime.now(UTC).replace(minute=0, second=0, microsecond=0)
        ends_at = starts_at + timedelta(hours=hours)
        statement = (
            select(WeatherForecast, District)
            .join(District, District.id == WeatherForecast.district_id)
            .where(
                WeatherForecast.valid_at >= starts_at,
                WeatherForecast.valid_at < ends_at,
            )
            .order_by(WeatherForecast.district_id, WeatherForecast.valid_at)
        )
        if region_id is not None:
            statement = statement.where(WeatherForecast.region_id == region_id)
        rows = (await self._session.execute(statement)).all()
        grouped: dict[str, list[tuple[WeatherForecast, District]]] = {}
        for forecast, district in rows:
            grouped.setdefault(forecast.district_id, []).append((forecast, district))

        summaries: list[WeatherForecastSummaryRecord] = []
        for district_rows in grouped.values():
            forecasts = [item[0] for item in district_rows]
            district = district_rows[0][1]
            probabilities = [
                item.precipitation_probability_pct
                for item in forecasts
                if item.precipitation_probability_pct is not None
            ]
            latest = max(forecasts, key=lambda item: item.ingested_at)
            summaries.append(
                WeatherForecastSummaryRecord(
                    district_id=district.id,
                    district_name=district.name,
                    geometry=_as_geojson(latest.geometry) or {"type": "Point", "coordinates": []},
                    precipitation_24h_mm=round(sum(item.precipitation_mm for item in forecasts), 2),
                    maximum_probability_pct=max(probabilities) if probabilities else None,
                    forecast_from=min(item.valid_at for item in forecasts),
                    forecast_through=max(item.valid_at for item in forecasts),
                    model=latest.model,
                    source=latest.source,
                    source_url=latest.source_url,
                    source_version=latest.source_version,
                    quality=latest.quality,
                    ingested_at=latest.ingested_at,
                )
            )
        return sorted(summaries, key=lambda item: item.district_name)

    async def list_warnings(
        self,
        *,
        region_id: str | None = None,
        day_index: int = 1,
    ) -> list[OfficialWarningRecord]:
        statement = (
            select(OfficialWarning, District)
            .join(District, District.id == OfficialWarning.district_id)
            .where(OfficialWarning.day_index == day_index)
            .order_by(
                OfficialWarning.district_id,
                OfficialWarning.issue_at.desc(),
                OfficialWarning.ingested_at.desc(),
            )
        )
        if region_id is not None:
            statement = statement.where(OfficialWarning.region_id == region_id)
        rows = (await self._session.execute(statement)).all()
        latest_by_district: dict[str, tuple[OfficialWarning, District]] = {}
        for warning, district in rows:
            latest_by_district.setdefault(warning.district_id, (warning, district))

        records = []
        for warning, district in latest_by_district.values():
            records.append(
                OfficialWarningRecord(
                    id=warning.id,
                    district_id=district.id,
                    district_name=district.name,
                    geometry=_as_geojson(district.geometry)
                    or {"type": "MultiPolygon", "coordinates": []},
                    external_id=warning.external_id,
                    issue_at=warning.issue_at,
                    valid_date=warning.valid_date,
                    day_index=warning.day_index,
                    severity=warning.severity,
                    color_code=warning.color_code,
                    warning_codes=list(warning.warning_codes),
                    hazards=list(warning.hazards),
                    description=warning.description,
                    source=warning.source,
                    source_url=warning.source_url,
                    source_version=warning.source_version,
                    quality=warning.quality,
                    ingested_at=warning.ingested_at,
                )
            )
        return sorted(records, key=lambda item: item.district_name)


class SQLAlchemyEventRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list(
        self,
        *,
        region_id: str | None = None,
        state: str | None = None,
        include_closed: bool = False,
    ) -> list[FloodEventRecord]:
        statement = select(FloodEvent)
        if region_id is not None:
            statement = statement.where(FloodEvent.region_id == region_id)
        if state is not None:
            statement = statement.where(FloodEvent.state == state)
        if not include_closed:
            statement = statement.where(FloodEvent.ended_at.is_(None))
        rows = (
            await self._session.scalars(
                statement.order_by(FloodEvent.last_updated_at.desc(), FloodEvent.name)
            )
        ).all()
        return [_event_record(row) for row in rows]

    async def get(self, event_id: str) -> FloodEventRecord | None:
        row = await self._session.get(FloodEvent, event_id)
        return None if row is None else _event_record(row)

    async def list_evidence(self, event_id: str) -> list[EventEvidenceRecord]:
        rows = (
            await self._session.scalars(
                select(EventEvidence)
                .where(EventEvidence.event_id == event_id)
                .order_by(EventEvidence.ingested_at.desc(), EventEvidence.title)
            )
        ).all()
        return [
            EventEvidenceRecord(
                id=row.id,
                event_id=row.event_id,
                evidence_type=row.evidence_type,
                title=row.title,
                summary=row.summary,
                geometry=_as_geojson(row.geometry),
                source=row.source,
                source_record_id=row.source_record_id,
                observed_at=row.observed_at,
                published_at=row.published_at,
                ingested_at=row.ingested_at,
                source_url=row.source_url,
                source_version=row.source_version,
                quality=row.quality,
                metadata=dict(row.metadata_),
            )
            for row in rows
        ]

    async def list_timeline(self, event_id: str) -> list[EventTimelineRecord]:
        rows = (
            await self._session.scalars(
                select(EventTimelineEntry)
                .where(EventTimelineEntry.event_id == event_id)
                .order_by(EventTimelineEntry.occurred_at, EventTimelineEntry.id)
            )
        ).all()
        return [
            EventTimelineRecord(
                id=row.id,
                event_id=row.event_id,
                evidence_id=row.evidence_id,
                occurred_at=row.occurred_at,
                category=row.category,
                state_from=row.state_from,
                state_to=row.state_to,
                summary=row.summary,
                metadata=dict(row.metadata_),
            )
            for row in rows
        ]


def _satellite_job_record(row: SatelliteJob, scene_count: int) -> SatelliteJobRecord:
    return SatelliteJobRecord(
        id=row.id,
        event_id=row.event_id,
        status=row.status,
        requested_at=row.requested_at,
        started_at=row.started_at,
        completed_at=row.completed_at,
        before_start=row.before_start,
        before_end=row.before_end,
        after_start=row.after_start,
        after_end=row.after_end,
        algorithm=row.algorithm,
        parameters=dict(row.parameters),
        error_code=row.error_code,
        error_message=row.error_message,
        catalog_source=row.catalog_source,
        catalog_url=row.catalog_url,
        scene_count=scene_count,
    )


class SQLAlchemySatelliteRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def _record(self, row: SatelliteJob) -> SatelliteJobRecord:
        count = await self._session.scalar(
            select(func.count(SatelliteScene.id)).where(SatelliteScene.job_id == row.id)
        )
        return _satellite_job_record(row, int(count or 0))

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
    ) -> tuple[SatelliteJobRecord, bool]:
        existing = await self._session.scalar(
            select(SatelliteJob).where(
                SatelliteJob.event_id == event_id,
                SatelliteJob.request_fingerprint == request_fingerprint,
            )
        )
        if existing is not None:
            return await self._record(existing), False
        row = SatelliteJob(
            id=f"satjob-{request_fingerprint[:32]}",
            event_id=event_id,
            request_fingerprint=request_fingerprint,
            status="queued",
            requested_at=datetime.now(UTC),
            before_start=before_start,
            before_end=before_end,
            after_start=after_start,
            after_end=after_end,
            algorithm=algorithm,
            parameters=parameters,
            catalog_source=catalog_source,
            metadata_={},
        )
        self._session.add(row)
        try:
            await self._session.commit()
        except IntegrityError:
            await self._session.rollback()
            concurrent = await self._session.scalar(
                select(SatelliteJob).where(
                    SatelliteJob.event_id == event_id,
                    SatelliteJob.request_fingerprint == request_fingerprint,
                )
            )
            if concurrent is None:
                raise
            return await self._record(concurrent), False
        await self._session.refresh(row)
        return await self._record(row), True

    async def get_job(self, job_id: str) -> SatelliteJobRecord | None:
        row = await self._session.get(SatelliteJob, job_id)
        return None if row is None else await self._record(row)

    async def list_jobs(self, event_id: str) -> list[SatelliteJobRecord]:
        rows = (
            await self._session.scalars(
                select(SatelliteJob)
                .where(SatelliteJob.event_id == event_id)
                .order_by(SatelliteJob.requested_at.desc())
            )
        ).all()
        return [await self._record(row) for row in rows]

    async def list_extents(self, event_id: str) -> list[FloodExtentRecord]:
        rows = (
            await self._session.scalars(
                select(FloodExtent)
                .where(FloodExtent.event_id == event_id)
                .order_by(FloodExtent.acquired_at.desc())
            )
        ).all()
        return [
            FloodExtentRecord(
                id=row.id,
                event_id=row.event_id,
                job_id=row.job_id,
                acquired_at=row.acquired_at,
                algorithm=row.algorithm,
                algorithm_version=row.algorithm_version,
                parameters=dict(row.parameters),
                area_km2=row.area_km2,
                high_evidence_area_km2=row.high_evidence_area_km2,
                valid_coverage_fraction=row.valid_coverage_fraction,
                resolution_m=row.resolution_m,
                analysis_crs=row.analysis_crs,
                raster_uri=row.raster_uri,
                geometry=_as_geojson(row.geometry) or {"type": "MultiPolygon", "coordinates": []},
                source=row.source,
                source_record_id=row.source_record_id,
                observed_at=row.observed_at,
                published_at=row.published_at,
                ingested_at=row.ingested_at,
                source_url=row.source_url,
                source_version=row.source_version,
                quality=row.quality,
                metadata=dict(row.metadata_),
            )
            for row in rows
        ]

    async def list_comparisons(self, event_id: str) -> list[SatelliteComparisonRecord]:
        rows = (
            await self._session.scalars(
                select(SatelliteComparison)
                .where(SatelliteComparison.event_id == event_id)
                .order_by(SatelliteComparison.compared_at.desc())
            )
        ).all()
        return [
            SatelliteComparisonRecord(
                id=row.id,
                event_id=row.event_id,
                flood_extent_id=row.flood_extent_id,
                reference_name=row.reference_name,
                reference_acquired_at=row.reference_acquired_at,
                compared_at=row.compared_at,
                analysis_crs=row.analysis_crs,
                iou=row.iou,
                dice_f1=row.dice_f1,
                precision=row.precision,
                recall=row.recall,
                detected_area_km2=row.detected_area_km2,
                reference_area_km2=row.reference_area_km2,
                overlap_area_km2=row.overlap_area_km2,
                union_area_km2=row.union_area_km2,
                area_difference_km2=row.area_difference_km2,
                temporal_offset_hours=row.temporal_offset_hours,
                caveat=row.caveat,
                geometry=_as_geojson(row.geometry) or {"type": "MultiPolygon", "coordinates": []},
                source=row.source,
                source_record_id=row.source_record_id,
                observed_at=row.observed_at,
                published_at=row.published_at,
                ingested_at=row.ingested_at,
                source_url=row.source_url,
                source_version=row.source_version,
                quality=row.quality,
                metadata=dict(row.metadata_),
            )
            for row in rows
        ]


class SQLAlchemyImpactRepository:
    """Read the latest reproducible exposure snapshot for one event."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_latest(self, event_id: str) -> ImpactSnapshotRecord | None:
        snapshot = await self._session.scalar(
            select(ImpactSnapshot)
            .where(ImpactSnapshot.event_id == event_id)
            .order_by(ImpactSnapshot.calculated_at.desc(), ImpactSnapshot.id.desc())
            .limit(1)
        )
        if snapshot is None:
            return None
        rows = (
            await self._session.scalars(
                select(PotentialExposure)
                .where(PotentialExposure.snapshot_id == snapshot.id)
                .order_by(
                    PotentialExposure.asset_type,
                    PotentialExposure.name,
                    PotentialExposure.id,
                )
            )
        ).all()
        exposures = tuple(
            PotentialExposureRecord(
                id=row.id,
                snapshot_id=row.snapshot_id,
                event_id=row.event_id,
                flood_extent_id=row.flood_extent_id,
                asset_type=row.asset_type,
                asset_id=row.asset_id,
                name=row.name,
                metric_type=row.metric_type,
                metric_value=row.metric_value,
                unit=row.unit,
                geometry=_as_geojson(row.geometry) or {"type": "Point", "coordinates": []},
                source=row.source,
                source_record_id=row.source_record_id,
                observed_at=row.observed_at,
                published_at=row.published_at,
                ingested_at=row.ingested_at,
                source_url=row.source_url,
                source_version=row.source_version,
                quality=row.quality,
                metadata=dict(row.metadata_),
            )
            for row in rows
        )
        return ImpactSnapshotRecord(
            id=snapshot.id,
            event_id=snapshot.event_id,
            flood_extent_id=snapshot.flood_extent_id,
            calculated_at=snapshot.calculated_at,
            algorithm=snapshot.algorithm,
            algorithm_version=snapshot.algorithm_version,
            inundated_area_km2=snapshot.inundated_area_km2,
            settlement_count=snapshot.settlement_count,
            facility_count=snapshot.facility_count,
            population_potentially_exposed=snapshot.population_potentially_exposed,
            population_record_count=snapshot.population_record_count,
            road_overlap_km=snapshot.road_overlap_km,
            building_count=snapshot.building_count,
            coverage=dict(snapshot.coverage),
            metadata=dict(snapshot.metadata_),
            exposures=exposures,
        )


class SQLAlchemyAccessibilityRepository:
    """Read the latest reachability screen and its traceable map records."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_latest(self, event_id: str) -> AccessibilitySnapshotRecord | None:
        snapshot = await self._session.scalar(
            select(AccessibilitySnapshot)
            .where(AccessibilitySnapshot.event_id == event_id)
            .order_by(
                AccessibilitySnapshot.calculated_at.desc(),
                AccessibilitySnapshot.id.desc(),
            )
            .limit(1)
        )
        if snapshot is None:
            return None
        disruption_rows = (
            await self._session.scalars(
                select(RoadDisruption)
                .where(RoadDisruption.snapshot_id == snapshot.id)
                .order_by(RoadDisruption.name, RoadDisruption.id)
            )
        ).all()
        settlement_rows = (
            await self._session.scalars(
                select(SettlementAccessibility)
                .where(SettlementAccessibility.snapshot_id == snapshot.id)
                .order_by(
                    SettlementAccessibility.potentially_isolated.desc(),
                    SettlementAccessibility.name,
                )
            )
        ).all()
        disruptions = tuple(
            RoadDisruptionRecord(
                id=row.id,
                snapshot_id=row.snapshot_id,
                event_id=row.event_id,
                flood_extent_id=row.flood_extent_id,
                road_segment_id=row.road_segment_id,
                name=row.name,
                road_class=row.road_class,
                overlap_km=row.overlap_km,
                geometry=_as_geojson(row.geometry)
                or {"type": "MultiLineString", "coordinates": []},
                source=row.source,
                source_record_id=row.source_record_id,
                observed_at=row.observed_at,
                ingested_at=row.ingested_at,
                source_version=row.source_version,
                quality=row.quality,
                metadata=dict(row.metadata_),
            )
            for row in disruption_rows
        )
        settlements = tuple(
            SettlementAccessibilityRecord(
                id=row.id,
                snapshot_id=row.snapshot_id,
                event_id=row.event_id,
                flood_extent_id=row.flood_extent_id,
                settlement_id=row.settlement_id,
                name=row.name,
                snapped_distance_m=row.snapped_distance_m,
                major_road_reachable_before=row.major_road_reachable_before,
                major_road_reachable_after=row.major_road_reachable_after,
                hospital_reachable_before=row.hospital_reachable_before,
                hospital_reachable_after=row.hospital_reachable_after,
                nearest_major_road_km=row.nearest_major_road_km,
                nearest_hospital_km=row.nearest_hospital_km,
                potentially_isolated=row.potentially_isolated,
                assessment_status=row.assessment_status,
                geometry=_as_geojson(row.geometry) or {"type": "Point", "coordinates": []},
                source=row.source,
                source_record_id=row.source_record_id,
                observed_at=row.observed_at,
                ingested_at=row.ingested_at,
                source_version=row.source_version,
                quality=row.quality,
                metadata=dict(row.metadata_),
            )
            for row in settlement_rows
        )
        return AccessibilitySnapshotRecord(
            id=snapshot.id,
            event_id=snapshot.event_id,
            flood_extent_id=snapshot.flood_extent_id,
            calculated_at=snapshot.calculated_at,
            algorithm=snapshot.algorithm,
            algorithm_version=snapshot.algorithm_version,
            status=snapshot.status,
            road_count=snapshot.road_count,
            graph_node_count=snapshot.graph_node_count,
            graph_edge_count=snapshot.graph_edge_count,
            potentially_affected_road_count=snapshot.potentially_affected_road_count,
            potentially_affected_road_km=snapshot.potentially_affected_road_km,
            assessed_settlement_count=snapshot.assessed_settlement_count,
            potentially_isolated_settlement_count=(snapshot.potentially_isolated_settlement_count),
            coverage=dict(snapshot.coverage),
            metadata=dict(snapshot.metadata_),
            road_disruptions=disruptions,
            settlements=settlements,
        )


def _incident_record(row: IncidentReport) -> IncidentReportRecord:
    return IncidentReportRecord(
        id=row.id,
        submission_id=row.submission_id,
        public_reference=row.public_reference,
        request_fingerprint=row.request_fingerprint,
        event_id=row.event_id,
        incident_type=row.incident_type,
        people_affected=row.people_affected,
        people_count_approximate=row.people_count_approximate,
        public_summary=row.public_summary,
        reported_at=row.reported_at,
        verification_state=row.verification_state,
        status=row.status,
        location_method=row.location_method,
        location_accuracy_m=row.location_accuracy_m,
        public_geometry=_as_geojson(row.public_geometry) or {"type": "Point", "coordinates": []},
        media_count=row.media_count,
        source=row.source,
        source_record_id=row.source_record_id,
        source_version=row.source_version,
        quality=row.quality,
        ingested_at=row.ingested_at,
        metadata=dict(row.metadata_),
    )


class SQLAlchemyIncidentRepository:
    """Persist private submissions while returning only public-safe records."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_submission_id(self, submission_id: str) -> IncidentReportRecord | None:
        row = await self._session.scalar(
            select(IncidentReport).where(IncidentReport.submission_id == submission_id)
        )
        return None if row is None else _incident_record(row)

    async def find_matching_open_event(self, longitude: float, latitude: float) -> str | None:
        point = func.ST_SetSRID(func.ST_MakePoint(longitude, latitude), 4326)
        return await self._session.scalar(
            select(FloodEvent.id)
            .where(FloodEvent.ended_at.is_(None), func.ST_Covers(FloodEvent.geometry, point))
            .order_by(FloodEvent.last_updated_at.desc())
            .limit(1)
        )

    async def point_in_region(self, longitude: float, latitude: float, *, region_id: str) -> bool:
        point = func.ST_SetSRID(func.ST_MakePoint(longitude, latitude), 4326)
        result = await self._session.scalar(
            select(func.ST_Covers(Region.geometry, point)).where(Region.id == region_id)
        )
        return bool(result)

    async def create(self, value: IncidentCreateInput) -> tuple[IncidentReportRecord, bool]:
        existing = await self.get_by_submission_id(value.submission_id)
        if existing is not None:
            return existing, False
        row = IncidentReport(
            id=value.id,
            submission_id=value.submission_id,
            public_reference=value.public_reference,
            request_fingerprint=value.request_fingerprint,
            event_id=value.event_id,
            incident_type=value.incident_type,
            people_affected=value.people_affected,
            people_count_approximate=value.people_count_approximate,
            description_private=value.description_private,
            public_summary=value.public_summary,
            reported_at=value.reported_at,
            verification_state="unverified",
            status="received",
            location_method=value.location_method,
            location_accuracy_m=value.location_accuracy_m,
            exact_geometry=from_shape(
                Point(value.exact_longitude, value.exact_latitude), srid=4326
            ),
            public_geometry=from_shape(
                Point(value.public_longitude, value.public_latitude), srid=4326
            ),
            media_count=1 if value.media else 0,
            privacy_consent_at=value.privacy_consent_at,
            metadata_=value.metadata,
            source="JalDrishti public incident report",
            source_record_id=value.public_reference,
            observed_at=value.reported_at,
            published_at=None,
            last_checked_at=None,
            source_url=None,
            source_version="0.1.0",
            quality=ProvenanceQuality.UNVERIFIED_REPORT,
        )
        self._session.add(row)
        if value.encrypted_contact is not None and value.encryption_key_id is not None:
            self._session.add(
                IncidentContact(
                    report_id=value.id,
                    encrypted_contact=value.encrypted_contact,
                    encryption_key_id=value.encryption_key_id,
                    created_at=value.reported_at,
                )
            )
        if value.media is not None:
            self._session.add(
                IncidentMedia(
                    id=value.media.id,
                    report_id=value.id,
                    private_uri=value.media.private_uri,
                    mime_type=value.media.mime_type,
                    size_bytes=value.media.size_bytes,
                    sha256=value.media.sha256,
                    normalization_status=value.media.normalization_status,
                    created_at=value.reported_at,
                )
            )
        if value.event_id is not None:
            evidence_id = f"evidence-{value.id}"
            self._session.add(
                EventEvidence(
                    id=evidence_id,
                    event_id=value.event_id,
                    evidence_type="public_incident_report",
                    title=value.public_summary,
                    summary=(
                        "Unverified public report linked by location; exact coordinates and "
                        "private report content are withheld."
                    ),
                    geometry=from_shape(
                        Point(value.public_longitude, value.public_latitude), srid=4326
                    ),
                    metadata_={
                        "incident_type": value.incident_type,
                        "public_reference": value.public_reference,
                        "verification_state": "unverified",
                    },
                    source="JalDrishti public incident report",
                    source_record_id=value.public_reference,
                    observed_at=value.reported_at,
                    published_at=None,
                    last_checked_at=None,
                    source_url=None,
                    source_version="0.1.0",
                    quality=ProvenanceQuality.UNVERIFIED_REPORT,
                )
            )
            self._session.add(
                EventTimelineEntry(
                    id=f"timeline-{value.id}",
                    event_id=value.event_id,
                    evidence_id=evidence_id,
                    occurred_at=value.reported_at,
                    category="public_report_received",
                    state_from=None,
                    state_to=None,
                    summary=(
                        f"Unverified {value.incident_type.replace('_', ' ')} report received."
                    ),
                    metadata_={"public_reference": value.public_reference},
                )
            )
        try:
            await self._session.commit()
        except IntegrityError:
            await self._session.rollback()
            concurrent = await self.get_by_submission_id(value.submission_id)
            if concurrent is None:
                raise
            return concurrent, False
        await self._session.refresh(row)
        return _incident_record(row), True

    async def list_public(self, event_id: str) -> list[IncidentReportRecord]:
        rows = (
            await self._session.scalars(
                select(IncidentReport)
                .where(IncidentReport.event_id == event_id)
                .order_by(IncidentReport.reported_at.desc(), IncidentReport.id)
            )
        ).all()
        return [_incident_record(row) for row in rows]
