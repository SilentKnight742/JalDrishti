"""Event-scoped potential-exposure endpoint."""

from fastapi import APIRouter, HTTPException, status

from jaldrishti_api.dependencies import ImpactServiceDependency
from jaldrishti_api.schemas import ImpactResponse

router = APIRouter(tags=["impact"])


@router.get("/events/{event_id}/impact", response_model=ImpactResponse)
async def get_event_impact(
    event_id: str,
    service: ImpactServiceDependency,
) -> ImpactResponse:
    response = await service.get_impact(event_id)
    if response is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")
    return response
