"""Flood-event, evidence, and timeline endpoints."""

from typing import Literal

from fastapi import APIRouter, HTTPException, Query, status

from jaldrishti_api.dependencies import EventServiceDependency
from jaldrishti_api.schemas import (
    EventEvidenceProperties,
    EventProperties,
    EventTimelineItem,
    GeoJSONFeature,
    GeoJSONFeatureCollection,
)

router = APIRouter(tags=["events"])


@router.get("/events", response_model=GeoJSONFeatureCollection[EventProperties])
async def list_events(
    service: EventServiceDependency,
    region_id: str | None = Query(default=None, min_length=1, max_length=64),
    state: Literal["watch", "warning", "severe", "recovery"] | None = None,
    include_closed: bool = False,
) -> GeoJSONFeatureCollection[EventProperties]:
    return await service.list_events(
        region_id=region_id,
        state=state,
        include_closed=include_closed,
    )


@router.get("/events/{event_id}", response_model=GeoJSONFeature[EventProperties])
async def get_event(
    event_id: str,
    service: EventServiceDependency,
) -> GeoJSONFeature[EventProperties]:
    event = await service.get_event(event_id)
    if event is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")
    return event


@router.get(
    "/events/{event_id}/evidence",
    response_model=GeoJSONFeatureCollection[EventEvidenceProperties],
)
async def list_event_evidence(
    event_id: str,
    service: EventServiceDependency,
) -> GeoJSONFeatureCollection[EventEvidenceProperties]:
    if await service.get_event(event_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")
    return await service.list_evidence(event_id)


@router.get("/events/{event_id}/timeline", response_model=list[EventTimelineItem])
async def list_event_timeline(
    event_id: str,
    service: EventServiceDependency,
) -> list[EventTimelineItem]:
    if await service.get_event(event_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")
    return await service.list_timeline(event_id)
