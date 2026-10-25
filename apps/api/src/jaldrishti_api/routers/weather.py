"""Weather-model guidance and official warning endpoints."""

from fastapi import APIRouter, Query

from jaldrishti_api.dependencies import WeatherServiceDependency
from jaldrishti_api.schemas import (
    GeoJSONFeatureCollection,
    WarningProperties,
    WeatherSummaryProperties,
)

router = APIRouter(tags=["weather"])


@router.get(
    "/weather/forecasts",
    response_model=GeoJSONFeatureCollection[WeatherSummaryProperties],
)
async def list_weather_forecast_summaries(
    service: WeatherServiceDependency,
    region_id: str | None = Query(default=None, min_length=1, max_length=64),
    hours: int = Query(default=24, ge=1, le=72),
) -> GeoJSONFeatureCollection[WeatherSummaryProperties]:
    return await service.list_forecast_summaries(region_id=region_id, hours=hours)


@router.get(
    "/warnings",
    response_model=GeoJSONFeatureCollection[WarningProperties],
)
async def list_official_warnings(
    service: WeatherServiceDependency,
    region_id: str | None = Query(default=None, min_length=1, max_length=64),
    day: int = Query(default=1, ge=1, le=5),
) -> GeoJSONFeatureCollection[WarningProperties]:
    return await service.list_warnings(region_id=region_id, day_index=day)
