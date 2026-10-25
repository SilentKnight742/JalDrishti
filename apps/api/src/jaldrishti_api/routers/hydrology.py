"""Pilot hydrology endpoints with explicit coverage and timestamp caveats."""

from fastapi import APIRouter, Query

from jaldrishti_api.dependencies import StationServiceDependency
from jaldrishti_api.schemas import (
    GeoJSONFeatureCollection,
    StationObservationSeries,
    StationProperties,
)

router = APIRouter(tags=["hydrology"])


@router.get("/stations", response_model=GeoJSONFeatureCollection[StationProperties])
async def list_stations(
    service: StationServiceDependency,
    region_id: str | None = Query(default=None, min_length=1, max_length=64),
) -> GeoJSONFeatureCollection[StationProperties]:
    return await service.list_stations(region_id=region_id)


@router.get(
    "/stations/{station_id}/observations",
    response_model=StationObservationSeries,
)
async def list_station_observations(
    station_id: str,
    service: StationServiceDependency,
    limit: int = Query(default=168, ge=1, le=2_000),
) -> StationObservationSeries:
    return await service.list_observations(station_id, limit=limit)
