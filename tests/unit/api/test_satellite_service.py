from datetime import UTC, datetime

import pytest
from jaldrishti.domain.events import FloodEventRecord
from jaldrishti.domain.satellite import (
    FloodExtentRecord,
    SatelliteComparisonRecord,
    SatelliteJobRecord,
)
from jaldrishti_api.schemas import SatelliteJobRequest
from jaldrishti_api.services import SatelliteService

NOW = datetime(2026, 9, 25, 6, tzinfo=UTC)


class Events:
    async def get(self, event_id: str):
        if event_id != "event-dhemaji":
            return None
        return FloodEventRecord(
            id=event_id,
            region_id="assam",
            primary_district_id="dhemaji",
            name="Dhemaji flood watch",
            geometry={
                "type": "MultiPolygon",
                "coordinates": [[[[94, 27], [95, 27], [95, 28], [94, 27]]]],
            },
            started_at=NOW,
            last_updated_at=NOW,
            state_changed_at=NOW,
            ended_at=None,
            state="watch",
            trigger_summary="Official warning",
            rainfall_status="supporting",
            river_status="not_available",
            warning_status="yellow",
            satellite_status="not_requested",
            created_by="auto",
            rule_version="test-v1",
            rationale=[],
        )


class Satellite:
    def __init__(self) -> None:
        self.job = None
        self.create_count = 0

    async def create_job(self, **values):
        self.create_count += 1
        created = self.job is None
        if created:
            self.job = SatelliteJobRecord(
                id=f"satjob-{values['request_fingerprint'][:32]}",
                event_id=values["event_id"],
                status="queued",
                requested_at=NOW,
                started_at=None,
                completed_at=None,
                before_start=values["before_start"],
                before_end=values["before_end"],
                after_start=values["after_start"],
                after_end=values["after_end"],
                algorithm=values["algorithm"],
                parameters=values["parameters"],
                error_code=None,
                error_message=None,
                catalog_source=values["catalog_source"],
                catalog_url=None,
                scene_count=0,
            )
        return self.job, created

    async def get_job(self, job_id: str):
        return self.job if self.job and self.job.id == job_id else None

    async def list_jobs(self, event_id: str):
        return [self.job] if self.job and self.job.event_id == event_id else []

    async def list_extents(self, event_id: str):
        if event_id != "event-dhemaji":
            return []
        return [
            FloodExtentRecord(
                id="extent-1",
                event_id=event_id,
                job_id="satjob-1",
                acquired_at=NOW,
                algorithm="jaldrishti-opera-rtc-change",
                algorithm_version="0.1.0",
                parameters={"vv_drop_db": -3},
                area_km2=12.5,
                high_evidence_area_km2=8.2,
                valid_coverage_fraction=0.93,
                resolution_m=30,
                analysis_crs="EPSG:32646",
                raster_uri="artifact://satellite/satjob-1/evidence.tif",
                geometry={
                    "type": "MultiPolygon",
                    "coordinates": [[[[94, 27], [94.1, 27], [94.1, 27.1], [94, 27]]]],
                },
                source="NASA/JPL OPERA RTC-S1 via ASF DAAC",
                source_record_id="OPERA_TEST",
                observed_at=NOW,
                published_at=None,
                ingested_at=NOW,
                source_url="https://api.daac.asf.alaska.edu",
                source_version="1.0",
                quality="satellite_observed",
                metadata={"caveat": "not confirmed damage"},
            )
        ]

    async def list_comparisons(self, event_id: str):
        if event_id != "event-dhemaji":
            return []
        return [
            SatelliteComparisonRecord(
                id="comparison-1",
                event_id=event_id,
                flood_extent_id="extent-1",
                reference_name="Independent reference product",
                reference_acquired_at=NOW,
                compared_at=NOW,
                analysis_crs="EPSG:32646",
                iou=0.5,
                dice_f1=2 / 3,
                precision=0.75,
                recall=0.6,
                detected_area_km2=12.5,
                reference_area_km2=14,
                overlap_area_km2=8,
                union_area_km2=18.5,
                area_difference_km2=-1.5,
                temporal_offset_hours=2,
                caveat="Independent mapped product, not field truth.",
                geometry={
                    "type": "MultiPolygon",
                    "coordinates": [[[[94, 27], [94.1, 27], [94.1, 27.1], [94, 27]]]],
                },
                source="Reference provider",
                source_record_id="reference-1",
                observed_at=NOW,
                published_at=NOW,
                ingested_at=NOW,
                source_url="https://example.invalid/reference-1",
                source_version="2026-09-25",
                quality="official",
                metadata={"independence": "external"},
            )
        ]


class Queue:
    def __init__(self) -> None:
        self.ids = []

    def enqueue(self, job_id: str) -> None:
        self.ids.append(job_id)


@pytest.mark.asyncio
async def test_satellite_job_request_is_idempotent_and_enqueued_once():
    satellite = Satellite()
    queue = Queue()
    service = SatelliteService(events=Events(), satellite=satellite, queue=queue)
    request = SatelliteJobRequest()

    first = await service.create_job("event-dhemaji", request)
    second = await service.create_job("event-dhemaji", request)

    assert first == second
    assert first is not None
    assert first.before_start == datetime(2026, 9, 1, 6, tzinfo=UTC)
    assert first.after_end == datetime(2026, 10, 7, 6, tzinfo=UTC)
    assert queue.ids == [first.id]
    assert satellite.create_count == 2


@pytest.mark.asyncio
async def test_satellite_extent_contract_keeps_observation_and_caveat():
    service = SatelliteService(events=Events(), satellite=Satellite(), queue=Queue())

    response = await service.list_extents("event-dhemaji")

    assert len(response.features) == 1
    properties = response.features[0].properties
    assert properties.quality == "satellite_observed"
    assert properties.area_km2 == 12.5
    assert properties.metadata["caveat"] == "not confirmed damage"


@pytest.mark.asyncio
async def test_satellite_comparison_contract_keeps_metrics_timing_and_caveat():
    service = SatelliteService(events=Events(), satellite=Satellite(), queue=Queue())

    response = await service.list_comparisons("event-dhemaji")

    assert len(response.features) == 1
    properties = response.features[0].properties
    assert properties.iou == 0.5
    assert properties.temporal_offset_hours == 2
    assert properties.caveat == "Independent mapped product, not field truth."
