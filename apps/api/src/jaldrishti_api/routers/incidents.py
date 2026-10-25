"""Privacy-safe community incident reporting endpoints."""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from pydantic import UUID4

from jaldrishti_api.config import Settings
from jaldrishti_api.dependencies import IncidentServiceDependency, get_request_settings
from jaldrishti_api.incident_security import InvalidIncidentImage
from jaldrishti_api.schemas import (
    GeoJSONFeatureCollection,
    IncidentProperties,
    IncidentReceipt,
    IncidentSubmissionRequest,
    IncidentType,
)
from jaldrishti_api.services import (
    IncidentOutsideCoverage,
    IncidentRateLimitExceeded,
    IncidentSubmissionConflict,
)

router = APIRouter(tags=["incidents"])


@router.post(
    "/incidents/report",
    response_model=IncidentReceipt,
    status_code=status.HTTP_201_CREATED,
)
async def submit_incident(
    request: Request,
    service: IncidentServiceDependency,
    settings: Annotated[Settings, Depends(get_request_settings)],
    submission_id: Annotated[UUID4, Form()],
    incident_type: Annotated[IncidentType, Form()],
    description: Annotated[str, Form(min_length=5, max_length=2_000)],
    latitude: Annotated[float, Form(ge=24.0, le=28.5)],
    longitude: Annotated[float, Form(ge=89.4, le=96.3)],
    location_method: Annotated[Literal["gps", "map"], Form()],
    privacy_consent: Annotated[bool, Form()],
    people_affected: Annotated[int | None, Form(ge=0, le=1_000_000)] = None,
    people_count_approximate: Annotated[bool, Form()] = True,
    location_accuracy_m: Annotated[float | None, Form(ge=0, le=100_000)] = None,
    contact: Annotated[str | None, Form(max_length=240)] = None,
    photo: Annotated[UploadFile | None, File()] = None,
) -> IncidentReceipt:
    if not privacy_consent:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Privacy consent is required",
        )
    submission = IncidentSubmissionRequest(
        submission_id=submission_id,
        incident_type=incident_type,
        people_affected=people_affected,
        people_count_approximate=people_count_approximate,
        description=description,
        latitude=latitude,
        longitude=longitude,
        location_accuracy_m=location_accuracy_m,
        location_method=location_method,
        contact=contact,
        privacy_consent=privacy_consent,
    )
    content = None
    if photo is not None:
        if photo.content_type not in {"image/jpeg", "image/png", "image/webp"}:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Photo must be JPEG, PNG or WebP",
            )
        content = await photo.read(settings.incident_media_max_bytes + 1)
        if len(content) > settings.incident_media_max_bytes:
            raise HTTPException(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                detail="Photo exceeds the upload limit",
            )
    client_key = request.headers.get("x-real-ip") or (
        request.client.host if request.client is not None else "unknown"
    )
    try:
        return await service.submit(submission, client_key=client_key, photo=content)
    except IncidentRateLimitExceeded as exc:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=str(exc)) from exc
    except IncidentSubmissionConflict as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except (IncidentOutsideCoverage, InvalidIncidentImage) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc


@router.get(
    "/events/{event_id}/incidents",
    response_model=GeoJSONFeatureCollection[IncidentProperties],
)
async def list_event_incidents(
    event_id: str,
    service: IncidentServiceDependency,
) -> GeoJSONFeatureCollection[IncidentProperties]:
    result = await service.list_event_incidents(event_id)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")
    return result
