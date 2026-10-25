"""Event-scoped SAR processing and satellite extent endpoints."""

from fastapi import APIRouter, HTTPException, status

from jaldrishti_api.dependencies import SatelliteServiceDependency
from jaldrishti_api.schemas import (
    FloodExtentProperties,
    GeoJSONFeatureCollection,
    SatelliteComparisonProperties,
    SatelliteJobItem,
    SatelliteJobRequest,
)

router = APIRouter(tags=["satellite"])


@router.post(
    "/events/{event_id}/satellite-jobs",
    response_model=SatelliteJobItem,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_satellite_job(
    event_id: str,
    request: SatelliteJobRequest,
    service: SatelliteServiceDependency,
) -> SatelliteJobItem:
    job = await service.create_job(event_id, request)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")
    return job


@router.get("/events/{event_id}/satellite-jobs", response_model=list[SatelliteJobItem])
async def list_satellite_jobs(
    event_id: str,
    service: SatelliteServiceDependency,
) -> list[SatelliteJobItem]:
    return await service.list_jobs(event_id)


@router.get("/satellite-jobs/{job_id}", response_model=SatelliteJobItem)
async def get_satellite_job(
    job_id: str,
    service: SatelliteServiceDependency,
) -> SatelliteJobItem:
    job = await service.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Satellite job not found")
    return job


@router.get(
    "/events/{event_id}/flood-extents",
    response_model=GeoJSONFeatureCollection[FloodExtentProperties],
)
async def list_flood_extents(
    event_id: str,
    service: SatelliteServiceDependency,
) -> GeoJSONFeatureCollection[FloodExtentProperties]:
    return await service.list_extents(event_id)


@router.get(
    "/events/{event_id}/satellite-comparisons",
    response_model=GeoJSONFeatureCollection[SatelliteComparisonProperties],
)
async def list_satellite_comparisons(
    event_id: str,
    service: SatelliteServiceDependency,
) -> GeoJSONFeatureCollection[SatelliteComparisonProperties]:
    return await service.list_comparisons(event_id)
