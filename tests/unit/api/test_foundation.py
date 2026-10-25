"""API contract tests that deliberately do not require PostGIS or Redis."""

from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime, timedelta
from typing import Any

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient, Response
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
from jaldrishti.domain.weather import OfficialWarningRecord, WeatherForecastSummaryRecord
from jaldrishti.persistence import metadata
from jaldrishti_api.config import Settings
from jaldrishti_api.dependencies import (
    _source_status,
    get_event_service,
    get_facility_service,
    get_geography_service,
    get_health_service,
    get_river_service,
    get_settlement_service,
    get_station_service,
    get_weather_service,
)
from jaldrishti_api.main import create_app
from jaldrishti_api.schemas import SourceStatus
from jaldrishti_api.services import (
    EventService,
    FacilityService,
    GeographyService,
    HealthService,
    RiverService,
    SettlementService,
    StationService,
    WeatherService,
)

NOW = datetime(2026, 9, 22, 6, 30, tzinfo=UTC)


class FakeRegions:
    async def list(self) -> list[GeographicRecord]:
        return [
            GeographicRecord(
                id="assam",
                code="AS",
                name="Assam",
                geometry={
                    "type": "MultiPolygon",
                    "coordinates": [[[[91.0, 26.0], [92.0, 26.0], [92.0, 27.0], [91.0, 26.0]]]],
                },
                source="geoBoundaries",
                source_url="https://www.geoboundaries.org/",
                source_version="6.0.0",
                quality="official",
                ingested_at=NOW,
            )
        ]


class FakeDistricts:
    def __init__(self) -> None:
        self.last_region_id: str | None = None

    async def list(self, *, region_id: str | None = None) -> list[GeographicRecord]:
        self.last_region_id = region_id
        return [self._district()] if region_id in {None, "assam"} else []

    async def get(self, district_id: str) -> GeographicRecord | None:
        return self._district() if district_id == "dhemaji" else None

    @staticmethod
    def _district() -> GeographicRecord:
        return GeographicRecord(
            id="dhemaji",
            code="DHEMAJI",
            name="Dhemaji",
            geometry={
                "type": "MultiPolygon",
                "coordinates": [[[[94.0, 27.0], [95.0, 27.0], [95.0, 28.0], [94.0, 27.0]]]],
            },
            source="data.gov.in",
            source_url="https://data.gov.in/",
            source_version="2026-09",
            quality="official",
            ingested_at=NOW,
        )


class FakeFacilities:
    def __init__(self) -> None:
        self.filters: tuple[str | None, str | None, str | None] | None = None

    async def list(
        self,
        *,
        region_id: str | None = None,
        district_id: str | None = None,
        category: str | None = None,
    ) -> list[FacilityRecord]:
        self.filters = (region_id, district_id, category)
        return [
            FacilityRecord(
                id="osm-node-1",
                code=None,
                name="District Hospital",
                geometry={"type": "Point", "coordinates": [94.57, 27.48]},
                source="OpenStreetMap",
                source_url="https://www.openstreetmap.org/node/1",
                source_version="2026-09-22",
                quality="official",
                ingested_at=NOW,
                category="healthcare",
                subcategory="hospital",
            )
        ]


class FakeSettlements:
    def __init__(self) -> None:
        self.filters: tuple[str | None, str | None, str | None] | None = None

    async def list(
        self,
        *,
        region_id: str | None = None,
        district_id: str | None = None,
        settlement_type: str | None = None,
    ) -> list[SettlementRecord]:
        self.filters = (region_id, district_id, settlement_type)
        return [
            SettlementRecord(
                id="osm-node-2",
                code=None,
                name="Dhemaji",
                geometry={"type": "Point", "coordinates": [94.58, 27.48]},
                source="OpenStreetMap contributors",
                source_url="https://www.openstreetmap.org/node/2",
                source_version="osm-api-2026-09-22",
                quality="community_data",
                ingested_at=NOW,
                settlement_type="town",
                population=12_000,
            )
        ]


class FakeRivers:
    def __init__(self) -> None:
        self.region_id: str | None = None

    async def list(self, *, region_id: str | None = None) -> list[RiverRecord]:
        self.region_id = region_id
        return [
            RiverRecord(
                id="assam-river-brahmaputra",
                code=None,
                name="Brahmaputra",
                geometry={
                    "type": "MultiLineString",
                    "coordinates": [[[91.0, 26.0], [92.0, 26.2]]],
                },
                source="OpenStreetMap contributors",
                source_url="https://www.openstreetmap.org/copyright",
                source_version="osm-2026-07-28",
                quality="community_data",
                ingested_at=NOW,
                river_class="major_context",
            )
        ]


class FakeStations:
    def __init__(self) -> None:
        self.region_id: str | None = None
        self.observation_request: tuple[str, int] | None = None

    async def list(self, *, region_id: str | None = None) -> list[StationRecord]:
        self.region_id = region_id
        return [
            StationRecord(
                id="nwdp-test-station",
                region_id="assam",
                district_id="darrang",
                external_id=None,
                name="NH15 Crossing Fakirpara Tangni",
                geometry={"type": "Point", "coordinates": [92.11638889, 26.50833333]},
                river_name=None,
                basin_name=None,
                warning_level_m=None,
                danger_level_m=None,
                datum=None,
                time_zone=None,
                operational_status="pilot",
                coverage_status="incomplete_public_feed",
                source="Assam WRD / National Water Data Portal",
                source_url="https://nwdp.nwic.gov.in/dataset/example",
                source_version="nwdp-test",
                quality="official",
                ingested_at=NOW,
            )
        ]

    async def list_observations(
        self,
        station_id: str,
        *,
        limit: int = 168,
    ) -> list[StationObservationRecord]:
        self.observation_request = (station_id, limit)
        return [
            StationObservationRecord(
                id="nwdp-rwl-test",
                station_id=station_id,
                source_observed_at="22-09-2026 23:00",
                observed_at=None,
                water_level_m=61.083,
                unit="m",
                quality_flag="source_time_zone_unverified",
                source="Assam WRD / National Water Data Portal",
                source_url="https://nwdp.nwic.gov.in/dataset/example",
                source_version="nwdp-test",
                quality="official",
                ingested_at=NOW,
            )
        ]


class FakeWeather:
    def __init__(self) -> None:
        self.forecast_request: tuple[str | None, int] | None = None
        self.warning_request: tuple[str | None, int] | None = None

    async def list_forecast_summaries(
        self,
        *,
        region_id: str | None = None,
        hours: int = 24,
    ) -> list[WeatherForecastSummaryRecord]:
        self.forecast_request = (region_id, hours)
        return [
            WeatherForecastSummaryRecord(
                district_id="assam-district-325",
                district_name="Darrang",
                geometry={"type": "Point", "coordinates": [92.03, 26.45]},
                precipitation_24h_mm=18.4,
                maximum_probability_pct=82,
                forecast_from=NOW,
                forecast_through=datetime(2026, 9, 23, 5, 30, tzinfo=UTC),
                model="ecmwf_ifs025",
                source="Open-Meteo / ECMWF IFS 0.25° model guidance",
                source_url="https://open-meteo.com/en/docs",
                source_version="open-meteo-test",
                quality="model_derived",
                ingested_at=NOW,
            )
        ]

    async def list_warnings(
        self,
        *,
        region_id: str | None = None,
        day_index: int = 1,
    ) -> list[OfficialWarningRecord]:
        self.warning_request = (region_id, day_index)
        return [
            OfficialWarningRecord(
                id="imd-warning-16-2026-09-22",
                district_id="assam-district-325",
                district_name="Darrang",
                geometry={
                    "type": "MultiPolygon",
                    "coordinates": [[[[92.0, 26.0], [92.5, 26.0], [92.5, 26.5], [92.0, 26.0]]]],
                },
                external_id="16",
                issue_at=NOW,
                valid_date=date(2026, 9, 22),
                day_index=1,
                severity="yellow",
                color_code=3,
                warning_codes=[2, 4],
                hazards=["Heavy rain", "Thunderstorm, lightning or squall"],
                description="Localized heavy rain",
                source="India Meteorological Department district warnings",
                source_url="https://mausam.imd.gov.in/responsive/districtWiseWarningGIS.php",
                source_version="imd-wfs-test",
                quality="official",
                ingested_at=NOW,
            )
        ]


class FakeEvents:
    def __init__(self) -> None:
        self.filters: tuple[str | None, str | None, bool] | None = None

    @staticmethod
    def _event() -> FloodEventRecord:
        return FloodEventRecord(
            id="event-darrang",
            region_id="assam",
            primary_district_id="assam-district-325",
            name="Darrang flood watch",
            geometry={
                "type": "MultiPolygon",
                "coordinates": [[[[92.0, 26.0], [92.5, 26.0], [92.5, 26.5], [92.0, 26.0]]]],
            },
            started_at=NOW,
            last_updated_at=NOW,
            state_changed_at=NOW,
            ended_at=None,
            state="watch",
            trigger_summary="IMD yellow district warning: Heavy rain.",
            rainfall_status="model_guidance_available",
            river_status="pilot_unverified",
            warning_status="yellow",
            satellite_status="not_requested",
            created_by="auto",
            rule_version="test-rules-v1",
            rationale=["Official yellow maps to watch."],
        )

    async def list(
        self,
        *,
        region_id: str | None = None,
        state: str | None = None,
        include_closed: bool = False,
    ) -> list[FloodEventRecord]:
        self.filters = (region_id, state, include_closed)
        return [self._event()]

    async def get(self, event_id: str) -> FloodEventRecord | None:
        return self._event() if event_id == "event-darrang" else None

    async def list_evidence(self, event_id: str) -> list[EventEvidenceRecord]:
        return [
            EventEvidenceRecord(
                id="evidence-warning",
                event_id=event_id,
                evidence_type="official_warning",
                title="IMD yellow warning for Darrang",
                summary="Heavy rain.",
                geometry=self._event().geometry,
                source="India Meteorological Department district warnings",
                source_record_id="16/2026-09-22",
                observed_at=NOW,
                published_at=NOW,
                ingested_at=NOW,
                source_url="https://mausam.imd.gov.in/responsive/districtWiseWarningGIS.php",
                source_version="imd-wfs-test",
                quality="official",
                metadata={"severity": "yellow"},
            )
        ]

    async def list_timeline(self, event_id: str) -> list[EventTimelineRecord]:
        return [
            EventTimelineRecord(
                id="timeline-created",
                event_id=event_id,
                evidence_id="evidence-warning",
                occurred_at=NOW,
                category="event_created",
                state_from=None,
                state_to="watch",
                summary="IMD yellow district warning: Heavy rain.",
                metadata={"rule_id": "test-rules-v1:official-warning-yellow"},
            )
        ]


class PassingProbe:
    def __init__(self, name: str) -> None:
        self.name = name

    async def ping(self) -> None:
        return None


class FailingProbe(PassingProbe):
    async def ping(self) -> None:
        raise ConnectionError("service is intentionally absent in this test")


def _application() -> tuple[
    FastAPI,
    FakeDistricts,
    FakeFacilities,
    FakeSettlements,
    FakeRivers,
]:
    districts = FakeDistricts()
    facilities = FakeFacilities()
    settlements = FakeSettlements()
    rivers = FakeRivers()
    stations = FakeStations()
    weather = FakeWeather()
    events = FakeEvents()
    geography_service = GeographyService(regions=FakeRegions(), districts=districts)
    facility_service = FacilityService(facilities=facilities)
    settlement_service = SettlementService(settlements=settlements)
    river_service = RiverService(rivers=rivers)
    station_service = StationService(stations=stations)
    weather_service = WeatherService(weather=weather)
    event_service = EventService(events=events)
    health_service = HealthService(
        service="jaldrishti-api",
        version="0.1.0",
        database=PassingProbe("database"),
        redis=FailingProbe("redis"),
        sources=[
            SourceStatus(
                id="boundaries",
                name="Administrative boundaries",
                status="ok",
                last_updated_at=NOW,
            )
        ],
    )
    application = create_app(Settings(cors_origins=[]))

    async def geography_override() -> GeographyService:
        return geography_service

    async def facility_override() -> FacilityService:
        return facility_service

    async def settlement_override() -> SettlementService:
        return settlement_service

    async def river_override() -> RiverService:
        return river_service

    async def station_override() -> StationService:
        return station_service

    async def weather_override() -> WeatherService:
        return weather_service

    async def event_override() -> EventService:
        return event_service

    async def health_override() -> HealthService:
        return health_service

    application.dependency_overrides[get_geography_service] = geography_override
    application.dependency_overrides[get_facility_service] = facility_override
    application.dependency_overrides[get_settlement_service] = settlement_override
    application.dependency_overrides[get_river_service] = river_override
    application.dependency_overrides[get_station_service] = station_override
    application.dependency_overrides[get_weather_service] = weather_override
    application.dependency_overrides[get_event_service] = event_override
    application.dependency_overrides[get_health_service] = health_override
    application.state.fake_stations = stations
    application.state.fake_weather = weather
    application.state.fake_events = events
    return application, districts, facilities, settlements, rivers


async def _async_request(
    application: FastAPI,
    path: str,
    *,
    params: dict[str, Any] | None = None,
) -> Response:
    async with AsyncClient(
        transport=ASGITransport(app=application),
        base_url="http://testserver",
    ) as client:
        return await client.get(path, params=params)


def _get(
    application: FastAPI,
    path: str,
    *,
    params: dict[str, Any] | None = None,
) -> Response:
    return asyncio.run(_async_request(application, path, params=params))


def test_regions_returns_geojson_feature_collection() -> None:
    application, _, _, _, _ = _application()

    response = _get(application, "/api/v1/regions")

    assert response.status_code == 200
    payload = response.json()
    assert payload["type"] == "FeatureCollection"
    assert payload["features"][0]["geometry"]["type"] == "MultiPolygon"
    assert payload["features"][0]["properties"] == {
        "id": "assam",
        "code": "AS",
        "name": "Assam",
        "source": "geoBoundaries",
        "source_url": "https://www.geoboundaries.org/",
        "source_version": "6.0.0",
        "quality": "official",
        "ingested_at": "2026-09-22T06:30:00Z",
    }


def test_districts_filters_by_region_and_detail_is_a_feature() -> None:
    application, districts, _, _, _ = _application()

    collection = _get(application, "/api/v1/districts", params={"region_id": "assam"})
    detail = _get(application, "/api/v1/districts/dhemaji")

    assert collection.status_code == 200
    assert collection.json()["type"] == "FeatureCollection"
    assert districts.last_region_id == "assam"
    assert detail.status_code == 200
    assert detail.json()["type"] == "Feature"
    assert detail.json()["properties"]["id"] == "dhemaji"


def test_missing_district_is_404() -> None:
    application, _, _, _, _ = _application()

    response = _get(application, "/api/v1/districts/unknown")

    assert response.status_code == 404
    assert response.json() == {"detail": "District not found"}


def test_facilities_include_classification_and_forward_filters() -> None:
    application, _, facilities, _, _ = _application()

    response = _get(
        application,
        "/api/v1/facilities",
        params={"region_id": "assam", "district_id": "dhemaji", "category": "healthcare"},
    )

    assert response.status_code == 200
    properties = response.json()["features"][0]["properties"]
    assert properties["category"] == "healthcare"
    assert properties["subcategory"] == "hospital"
    assert facilities.filters == ("assam", "dhemaji", "healthcare")


def test_settlements_and_rivers_return_api_backed_context_layers() -> None:
    application, _, _, settlements, rivers = _application()

    settlement_response = _get(
        application,
        "/api/v1/settlements",
        params={"region_id": "assam", "settlement_type": "town"},
    )
    river_response = _get(application, "/api/v1/rivers", params={"region_id": "assam"})

    assert settlement_response.status_code == 200
    assert settlement_response.json()["features"][0]["properties"]["population"] == 12_000
    assert settlements.filters == ("assam", None, "town")
    assert river_response.status_code == 200
    assert river_response.json()["features"][0]["geometry"]["type"] == "MultiLineString"
    assert river_response.json()["features"][0]["properties"]["river_class"] == "major_context"
    assert rivers.region_id == "assam"


def test_stations_and_observations_expose_pilot_limitations() -> None:
    application, _, _, _, _ = _application()

    stations_response = _get(application, "/api/v1/stations", params={"region_id": "assam"})
    observations_response = _get(
        application,
        "/api/v1/stations/nwdp-test-station/observations",
        params={"limit": 24},
    )

    assert stations_response.status_code == 200
    station = stations_response.json()["features"][0]
    assert station["geometry"] == {
        "type": "Point",
        "coordinates": [92.11638889, 26.50833333],
    }
    assert station["properties"]["operational_status"] == "pilot"
    assert station["properties"]["time_zone"] is None
    assert station["properties"]["danger_level_m"] is None
    assert application.state.fake_stations.region_id == "assam"

    assert observations_response.status_code == 200
    series = observations_response.json()
    assert series["coverage_status"] == "incomplete_public_feed"
    assert series["time_zone"] is None
    assert series["observations"][0]["observed_at"] is None
    assert series["observations"][0]["source_observed_at"] == "22-09-2026 23:00"
    assert series["observations"][0]["water_level_m"] == 61.083
    assert application.state.fake_stations.observation_request == ("nwdp-test-station", 24)


def test_weather_and_warning_endpoints_preserve_evidence_classification() -> None:
    application, _, _, _, _ = _application()

    forecast_response = _get(
        application,
        "/api/v1/weather/forecasts",
        params={"region_id": "assam", "hours": 24},
    )
    warning_response = _get(
        application,
        "/api/v1/warnings",
        params={"region_id": "assam", "day": 1},
    )

    assert forecast_response.status_code == 200
    forecast = forecast_response.json()["features"][0]
    assert forecast["properties"]["quality"] == "model_derived"
    assert forecast["properties"]["precipitation_24h_mm"] == 18.4
    assert forecast["properties"]["maximum_probability_pct"] == 82
    assert application.state.fake_weather.forecast_request == ("assam", 24)

    assert warning_response.status_code == 200
    warning = warning_response.json()["features"][0]
    assert warning["properties"]["quality"] == "official"
    assert warning["properties"]["severity"] == "yellow"
    assert warning["properties"]["warning_codes"] == [2, 4]
    assert application.state.fake_weather.warning_request == ("assam", 1)


def test_event_endpoints_expose_rules_evidence_and_timeline() -> None:
    application, _, _, _, _ = _application()

    events_response = _get(
        application,
        "/api/v1/events",
        params={"region_id": "assam", "state": "watch"},
    )
    detail_response = _get(application, "/api/v1/events/event-darrang")
    evidence_response = _get(application, "/api/v1/events/event-darrang/evidence")
    timeline_response = _get(application, "/api/v1/events/event-darrang/timeline")

    assert events_response.status_code == 200
    event = events_response.json()["features"][0]
    assert event["properties"]["state"] == "watch"
    assert event["properties"]["quality"] == "model_derived"
    assert event["properties"]["rationale"] == ["Official yellow maps to watch."]
    assert application.state.fake_events.filters == ("assam", "watch", False)
    assert detail_response.status_code == 200
    assert evidence_response.json()["features"][0]["properties"]["quality"] == "official"
    assert timeline_response.json()[0]["state_to"] == "watch"

    missing = _get(application, "/api/v1/events/unknown")
    assert missing.status_code == 404


def test_status_reports_dependency_degradation_without_failing_request() -> None:
    application, _, _, _, _ = _application()

    response = _get(application, "/api/v1/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "degraded"
    assert payload["service"] == "jaldrishti-api"
    assert payload["dependencies"] == {
        "database": {"status": "ok"},
        "redis": {"status": "unavailable"},
    }
    assert payload["sources"][0]["id"] == "boundaries"
    assert "checked_at" in payload


def test_source_freshness_uses_source_specific_server_windows() -> None:
    now = datetime(2026, 9, 25, 12, tzinfo=UTC)

    assert (
        _source_status(
            None,
            stale_after=timedelta(hours=3),
            failed_after=timedelta(hours=12),
            now=now,
        )
        == "not_configured"
    )
    assert (
        _source_status(
            now - timedelta(hours=2),
            stale_after=timedelta(hours=3),
            failed_after=timedelta(hours=12),
            now=now,
        )
        == "ok"
    )
    assert (
        _source_status(
            now - timedelta(hours=5),
            stale_after=timedelta(hours=3),
            failed_after=timedelta(hours=12),
            now=now,
        )
        == "stale"
    )
    assert (
        _source_status(
            now - timedelta(hours=13),
            stale_after=timedelta(hours=3),
            failed_after=timedelta(hours=12),
            now=now,
        )
        == "unavailable"
    )
    assert (
        _source_status(
            now - timedelta(hours=1),
            stale_after=timedelta(hours=3),
            failed_after=timedelta(hours=12),
            healthy_status="degraded",
            now=now,
        )
        == "degraded"
    )


def test_metadata_exports_spatial_models_and_provenance_columns() -> None:
    assert {
        "regions",
        "districts",
        "settlements",
        "rivers",
        "facilities",
        "stations",
        "station_observations",
        "weather_observations",
        "weather_forecasts",
        "official_warnings",
        "flood_events",
        "flood_event_districts",
        "event_evidence",
        "event_timeline_entries",
    } <= set(metadata.tables)
    required_provenance = {
        "source",
        "source_record_id",
        "observed_at",
        "published_at",
        "ingested_at",
        "last_checked_at",
        "source_url",
        "source_version",
        "quality",
    }
    for table_name in (
        "regions",
        "districts",
        "settlements",
        "rivers",
        "facilities",
        "stations",
        "station_observations",
        "weather_observations",
        "weather_forecasts",
        "official_warnings",
        "event_evidence",
    ):
        assert required_provenance <= set(metadata.tables[table_name].columns.keys())
        if "geometry" in metadata.tables[table_name].columns:
            assert metadata.tables[table_name].columns["geometry"].type.srid == 4326


def test_snapshot_extent_uniqueness_matches_the_migrated_schema() -> None:
    for table_name in ("impact_snapshots", "accessibility_snapshots"):
        table = metadata.tables[table_name]
        expected_constraint = f"uq_{table_name}_flood_extent_id"
        assert expected_constraint in {constraint.name for constraint in table.constraints}

        index = next(
            index for index in table.indexes if index.name == f"ix_{table_name}_flood_extent_id"
        )
        assert index.unique is False
