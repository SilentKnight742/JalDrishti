"""Phase 1 geography endpoints."""

from fastapi import APIRouter, HTTPException, Query, status

from jaldrishti_api.dependencies import (
    FacilityServiceDependency,
    GeographyServiceDependency,
    RiverServiceDependency,
    SettlementServiceDependency,
)
from jaldrishti_api.schemas import (
    FacilityProperties,
    FeatureProperties,
    GeoJSONFeature,
    GeoJSONFeatureCollection,
    RiverProperties,
    SettlementProperties,
)

router = APIRouter(tags=["geography"])


@router.get("/regions", response_model=GeoJSONFeatureCollection[FeatureProperties])
async def list_regions(
    service: GeographyServiceDependency,
) -> GeoJSONFeatureCollection[FeatureProperties]:
    return await service.list_regions()


@router.get("/districts", response_model=GeoJSONFeatureCollection[FeatureProperties])
async def list_districts(
    service: GeographyServiceDependency,
    region_id: str | None = Query(default=None, min_length=1, max_length=64),
) -> GeoJSONFeatureCollection[FeatureProperties]:
    return await service.list_districts(region_id=region_id)


@router.get("/districts/{district_id}", response_model=GeoJSONFeature[FeatureProperties])
async def get_district(
    district_id: str,
    service: GeographyServiceDependency,
) -> GeoJSONFeature[FeatureProperties]:
    feature = await service.get_district(district_id)
    if feature is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="District not found",
        )
    return feature


@router.get("/facilities", response_model=GeoJSONFeatureCollection[FacilityProperties])
async def list_facilities(
    service: FacilityServiceDependency,
    region_id: str | None = Query(default=None, min_length=1, max_length=64),
    district_id: str | None = Query(default=None, min_length=1, max_length=64),
    category: str | None = Query(default=None, min_length=1, max_length=80),
) -> GeoJSONFeatureCollection[FacilityProperties]:
    return await service.list_facilities(
        region_id=region_id,
        district_id=district_id,
        category=category,
    )


@router.get("/settlements", response_model=GeoJSONFeatureCollection[SettlementProperties])
async def list_settlements(
    service: SettlementServiceDependency,
    region_id: str | None = Query(default=None, min_length=1, max_length=64),
    district_id: str | None = Query(default=None, min_length=1, max_length=64),
    settlement_type: str | None = Query(default=None, min_length=1, max_length=64),
) -> GeoJSONFeatureCollection[SettlementProperties]:
    return await service.list_settlements(
        region_id=region_id,
        district_id=district_id,
        settlement_type=settlement_type,
    )


@router.get("/rivers", response_model=GeoJSONFeatureCollection[RiverProperties])
async def list_rivers(
    service: RiverServiceDependency,
    region_id: str | None = Query(default=None, min_length=1, max_length=64),
) -> GeoJSONFeatureCollection[RiverProperties]:
    return await service.list_rivers(region_id=region_id)
