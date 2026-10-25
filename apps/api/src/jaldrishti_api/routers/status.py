"""Liveness/readiness endpoint."""

from fastapi import APIRouter

from jaldrishti_api.dependencies import HealthServiceDependency
from jaldrishti_api.schemas import ServiceStatus

router = APIRouter(tags=["system"])


@router.get("/status", response_model=ServiceStatus)
async def get_status(service: HealthServiceDependency) -> ServiceStatus:
    return await service.status()
