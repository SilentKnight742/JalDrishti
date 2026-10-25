"""Event-scoped road accessibility screening endpoint."""

from fastapi import APIRouter, HTTPException, status

from jaldrishti_api.dependencies import AccessibilityServiceDependency
from jaldrishti_api.schemas import AccessibilityResponse

router = APIRouter(tags=["accessibility"])


@router.get("/events/{event_id}/accessibility", response_model=AccessibilityResponse)
async def get_event_accessibility(
    event_id: str,
    service: AccessibilityServiceDependency,
) -> AccessibilityResponse:
    response = await service.get_accessibility(event_id)
    if response is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")
    return response
