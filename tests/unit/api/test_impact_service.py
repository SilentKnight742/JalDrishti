from datetime import UTC, datetime

import pytest
from jaldrishti.domain.events import FloodEventRecord
from jaldrishti.domain.impact import ImpactSnapshotRecord, PotentialExposureRecord
from jaldrishti_api.services import ImpactService

NOW = datetime(2026, 9, 25, 8, tzinfo=UTC)


class Events:
    async def get(self, event_id: str):
        if event_id != "event-dhemaji":
            return None
        return FloodEventRecord(
            id=event_id,
            region_id="assam",
            primary_district_id="dhemaji",
            name="Dhemaji flood warning",
            geometry={"type": "MultiPolygon", "coordinates": []},
            started_at=NOW,
            last_updated_at=NOW,
            state_changed_at=NOW,
            ended_at=None,
            state="warning",
            trigger_summary="Official warning",
            rainfall_status="supporting",
            river_status="not_available",
            warning_status="orange",
            satellite_status="observed_extent_available",
            created_by="auto",
            rule_version="test-v1",
            rationale=[],
        )


class Impact:
    def __init__(self, available: bool = True) -> None:
        self.available = available

    async def get_latest(self, event_id: str):
        if not self.available:
            return None
        exposure = PotentialExposureRecord(
            id="exposure-1",
            snapshot_id="impact-1",
            event_id=event_id,
            flood_extent_id="extent-1",
            asset_type="facility",
            asset_id="facility-1",
            name="District Hospital",
            metric_type="intersects",
            metric_value=1,
            unit="boolean",
            geometry={"type": "Point", "coordinates": [94.5, 27.5]},
            source="JalDrishti impact engine",
            source_record_id="facility-1",
            observed_at=NOW,
            published_at=None,
            ingested_at=NOW,
            source_url=None,
            source_version="0.1.0",
            quality="model_derived",
            metadata={"asset_source": "OpenStreetMap contributors"},
        )
        return ImpactSnapshotRecord(
            id="impact-1",
            event_id=event_id,
            flood_extent_id="extent-1",
            calculated_at=NOW,
            algorithm="jaldrishti-point-intersection-exposure",
            algorithm_version="0.1.0",
            inundated_area_km2=12.5,
            settlement_count=2,
            facility_count=1,
            population_potentially_exposed=None,
            population_record_count=0,
            road_overlap_km=None,
            building_count=None,
            coverage={"roads": {"status": "not_configured"}},
            metadata={"terminology": "Potential exposure"},
            exposures=(exposure,),
        )


@pytest.mark.asyncio
async def test_impact_response_preserves_null_unknowns_and_provenance():
    response = await ImpactService(events=Events(), impact=Impact()).get_impact("event-dhemaji")

    assert response is not None
    assert response.status == "available"
    assert response.summary is not None
    assert response.summary.population_potentially_exposed is None
    assert response.summary.road_overlap_km is None
    assert response.exposures.features[0].properties.quality == "model_derived"
    assert "not observed damage" in response.caveats[0]


@pytest.mark.asyncio
async def test_known_event_without_extent_has_explicit_unavailable_response():
    response = await ImpactService(events=Events(), impact=Impact(False)).get_impact(
        "event-dhemaji"
    )

    assert response is not None
    assert response.status == "not_available"
    assert response.summary is None
    assert response.exposures.features == []


@pytest.mark.asyncio
async def test_unknown_event_is_not_conflated_with_missing_impact():
    response = await ImpactService(events=Events(), impact=Impact()).get_impact("missing")

    assert response is None
