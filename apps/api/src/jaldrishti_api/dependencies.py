"""FastAPI dependency graph kept separate for straightforward test overrides."""

from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import Depends, Request
from jaldrishti.persistence.models import (
    FloodExtent,
    OfficialWarning,
    SatelliteJob,
    StationObservation,
    WeatherForecast,
)
from jaldrishti.persistence.repositories import (
    SQLAlchemyAccessibilityRepository,
    SQLAlchemyDistrictRepository,
    SQLAlchemyEventRepository,
    SQLAlchemyFacilityRepository,
    SQLAlchemyImpactRepository,
    SQLAlchemyIncidentRepository,
    SQLAlchemyRegionRepository,
    SQLAlchemyRiverRepository,
    SQLAlchemySatelliteRepository,
    SQLAlchemySettlementRepository,
    SQLAlchemyStationRepository,
    SQLAlchemyWeatherRepository,
)
from redis.asyncio import Redis
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from jaldrishti_api.config import Settings
from jaldrishti_api.db.session import get_db_session, get_redis
from jaldrishti_api.incident_security import (
    FernetContactCipher,
    PrivateIncidentMediaStore,
    RedisIncidentRateLimiter,
)
from jaldrishti_api.satellite_queue import CelerySatelliteJobQueue
from jaldrishti_api.schemas import SourceStatus
from jaldrishti_api.services import (
    AccessibilityService,
    EventService,
    FacilityService,
    GeographyService,
    HealthService,
    ImpactService,
    IncidentService,
    RiverService,
    SatelliteService,
    SettlementService,
    StationService,
    WeatherService,
)


class DatabaseProbe:
    name = "database"

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def ping(self) -> None:
        await self._session.execute(text("SELECT 1"))


class RedisProbe:
    name = "redis"

    def __init__(self, client: Redis) -> None:
        self._client = client

    async def ping(self) -> None:
        await self._client.ping()


def _source_status(
    last_updated_at: datetime | None,
    *,
    stale_after: timedelta,
    failed_after: timedelta,
    healthy_status: str = "ok",
    now: datetime | None = None,
) -> str:
    """Apply one source's configured freshness window on the server."""

    if last_updated_at is None:
        return "not_configured"
    checked_at = now or datetime.now(UTC)
    updated_at = (
        last_updated_at.replace(tzinfo=UTC)
        if last_updated_at.tzinfo is None
        else last_updated_at.astimezone(UTC)
    )
    age = max(timedelta(0), checked_at - updated_at)
    if age <= stale_after:
        return healthy_status
    if age <= failed_after:
        return "stale"
    return "unavailable"


async def get_request_settings(request: Request) -> Settings:
    return request.app.state.settings


async def get_geography_service(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> GeographyService:
    return GeographyService(
        regions=SQLAlchemyRegionRepository(session),
        districts=SQLAlchemyDistrictRepository(session),
    )


async def get_facility_service(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> FacilityService:
    return FacilityService(facilities=SQLAlchemyFacilityRepository(session))


async def get_settlement_service(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> SettlementService:
    return SettlementService(settlements=SQLAlchemySettlementRepository(session))


async def get_river_service(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> RiverService:
    return RiverService(rivers=SQLAlchemyRiverRepository(session))


async def get_station_service(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> StationService:
    return StationService(stations=SQLAlchemyStationRepository(session))


async def get_weather_service(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> WeatherService:
    return WeatherService(weather=SQLAlchemyWeatherRepository(session))


async def get_event_service(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> EventService:
    return EventService(events=SQLAlchemyEventRepository(session))


async def get_satellite_service(
    settings: Annotated[Settings, Depends(get_request_settings)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> SatelliteService:
    return SatelliteService(
        events=SQLAlchemyEventRepository(session),
        satellite=SQLAlchemySatelliteRepository(session),
        queue=CelerySatelliteJobQueue(settings.redis_url),
    )


async def get_impact_service(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ImpactService:
    return ImpactService(
        events=SQLAlchemyEventRepository(session),
        impact=SQLAlchemyImpactRepository(session),
    )


async def get_accessibility_service(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> AccessibilityService:
    return AccessibilityService(
        events=SQLAlchemyEventRepository(session),
        accessibility=SQLAlchemyAccessibilityRepository(session),
    )


async def get_incident_service(
    settings: Annotated[Settings, Depends(get_request_settings)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    redis: Annotated[Redis, Depends(get_redis)],
) -> IncidentService:
    return IncidentService(
        events=SQLAlchemyEventRepository(session),
        incidents=SQLAlchemyIncidentRepository(session),
        limiter=RedisIncidentRateLimiter(redis),
        cipher=FernetContactCipher(
            settings.contact_encryption_key,
            settings.contact_encryption_key_id,
        ),
        media_store=PrivateIncidentMediaStore(
            settings.incident_media_directory,
            settings.incident_media_max_bytes,
        ),
        rate_limit_per_hour=settings.incident_rate_limit_per_hour,
    )


async def get_health_service(
    settings: Annotated[Settings, Depends(get_request_settings)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    redis: Annotated[Redis, Depends(get_redis)],
) -> HealthService:
    checked_at = datetime.now(UTC)
    telemetry_checked_at = await session.scalar(select(func.max(StationObservation.ingested_at)))
    warnings_checked_at = await session.scalar(select(func.max(OfficialWarning.ingested_at)))
    forecast_checked_at = await session.scalar(select(func.max(WeatherForecast.ingested_at)))
    satellite_checked_at = await session.scalar(select(func.max(FloodExtent.ingested_at)))
    latest_satellite_job = await session.scalar(
        select(SatelliteJob).order_by(SatelliteJob.requested_at.desc()).limit(1)
    )
    boundary_updated_at = datetime(2026, 5, 12, 8, 51, 34, tzinfo=UTC)
    facility_updated_at = datetime(2026, 5, 6, 3, 25, tzinfo=UTC)
    settlement_updated_at = datetime(2026, 9, 22, 3, 30, tzinfo=UTC)
    river_updated_at = datetime(2026, 7, 28, 2, 16, 18, tzinfo=UTC)
    satellite_status = "not_configured"
    satellite_detail = (
        "No event-scoped satellite observation has been requested. Public catalogue search "
        "does not require credentials; OPERA asset downloads require NASA Earthdata access."
    )
    satellite_updated_at = satellite_checked_at
    if latest_satellite_job is not None:
        satellite_updated_at = (
            satellite_checked_at
            or latest_satellite_job.completed_at
            or latest_satellite_job.requested_at
        )
        if satellite_checked_at is not None:
            satellite_status = "ok"
            satellite_detail = "At least one processed satellite change extent is available."
        elif latest_satellite_job.status == "awaiting_credentials":
            satellite_status = "not_configured"
            satellite_detail = latest_satellite_job.error_message
        elif latest_satellite_job.status in {"failed", "no_scenes", "completed_no_extent"}:
            satellite_status = "degraded"
            satellite_detail = latest_satellite_job.error_message
        else:
            satellite_status = "ok"
            satellite_detail = (
                f"Latest event-scoped satellite job is {latest_satellite_job.status}."
            )
    return HealthService(
        service=settings.service_id,
        version=settings.version,
        database=DatabaseProbe(session),
        redis=RedisProbe(redis),
        sources=[
            SourceStatus(
                id="assam-boundaries-bootstrap",
                name="Assam administrative boundaries",
                status=_source_status(
                    boundary_updated_at,
                    stale_after=timedelta(days=120),
                    failed_after=timedelta(days=365),
                    now=checked_at,
                ),
                last_updated_at=boundary_updated_at,
            ),
            SourceStatus(
                id="osm-facilities-bootstrap",
                name="OSM facilities",
                status=_source_status(
                    facility_updated_at,
                    stale_after=timedelta(days=30),
                    failed_after=timedelta(days=90),
                    now=checked_at,
                ),
                last_updated_at=facility_updated_at,
            ),
            SourceStatus(
                id="osm-settlements-bootstrap",
                name="OSM settlements",
                status=_source_status(
                    settlement_updated_at,
                    stale_after=timedelta(days=30),
                    failed_after=timedelta(days=90),
                    now=checked_at,
                ),
                last_updated_at=settlement_updated_at,
            ),
            SourceStatus(
                id="osm-rivers-bootstrap",
                name="OSM major-river context",
                status=_source_status(
                    river_updated_at,
                    stale_after=timedelta(days=30),
                    failed_after=timedelta(days=90),
                    now=checked_at,
                ),
                last_updated_at=river_updated_at,
            ),
            SourceStatus(
                id="assam-river-telemetry",
                name="Assam river telemetry",
                status=_source_status(
                    telemetry_checked_at,
                    stale_after=timedelta(hours=3),
                    failed_after=timedelta(hours=12),
                    healthy_status="degraded",
                    now=checked_at,
                ),
                last_updated_at=telemetry_checked_at,
                detail=(
                    "Pilot public feed with incomplete statewide coverage; source timezone, "
                    "datum and alert thresholds are not published."
                ),
            ),
            SourceStatus(
                id="imd-district-warnings",
                name="IMD district warnings",
                status=_source_status(
                    warnings_checked_at,
                    stale_after=timedelta(hours=3),
                    failed_after=timedelta(hours=12),
                    now=checked_at,
                ),
                last_updated_at=warnings_checked_at,
                detail="Official five-day district warnings from IMD's public WFS map layer.",
            ),
            SourceStatus(
                id="open-meteo-rainfall-guidance",
                name="Rainfall model guidance",
                status=_source_status(
                    forecast_checked_at,
                    stale_after=timedelta(hours=6),
                    failed_after=timedelta(hours=12),
                    now=checked_at,
                ),
                last_updated_at=forecast_checked_at,
                detail=(
                    "District-centroid ECMWF model guidance via Open-Meteo; "
                    "not a rain-gauge observation or official IMD forecast."
                ),
            ),
            SourceStatus(
                id="asf-opera-s1",
                name="OPERA Sentinel-1 satellite observation",
                status=satellite_status,
                last_updated_at=satellite_updated_at,
                detail=satellite_detail,
            ),
        ],
        timeout_seconds=settings.healthcheck_timeout_seconds,
    )


GeographyServiceDependency = Annotated[GeographyService, Depends(get_geography_service)]
FacilityServiceDependency = Annotated[FacilityService, Depends(get_facility_service)]
SettlementServiceDependency = Annotated[SettlementService, Depends(get_settlement_service)]
RiverServiceDependency = Annotated[RiverService, Depends(get_river_service)]
StationServiceDependency = Annotated[StationService, Depends(get_station_service)]
WeatherServiceDependency = Annotated[WeatherService, Depends(get_weather_service)]
EventServiceDependency = Annotated[EventService, Depends(get_event_service)]
SatelliteServiceDependency = Annotated[SatelliteService, Depends(get_satellite_service)]
ImpactServiceDependency = Annotated[ImpactService, Depends(get_impact_service)]
AccessibilityServiceDependency = Annotated[AccessibilityService, Depends(get_accessibility_service)]
IncidentServiceDependency = Annotated[IncidentService, Depends(get_incident_service)]
HealthServiceDependency = Annotated[HealthService, Depends(get_health_service)]
