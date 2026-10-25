from datetime import UTC, datetime

import pytest
from jaldrishti.domain.accessibility import (
    AccessibilitySnapshotRecord,
    RoadDisruptionRecord,
    SettlementAccessibilityRecord,
)
from jaldrishti.domain.events import FloodEventRecord
from jaldrishti_api.services import AccessibilityService

NOW = datetime(2026, 9, 25, 9, tzinfo=UTC)


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


class Accessibility:
    def __init__(self, available: bool = True) -> None:
        self.available = available

    async def get_latest(self, event_id: str):
        if not self.available:
            return None
        disruption = RoadDisruptionRecord(
            id="disruption-1",
            snapshot_id="access-1",
            event_id=event_id,
            flood_extent_id="extent-1",
            road_segment_id="road-1",
            name="NH 15",
            road_class="trunk",
            overlap_km=1.2,
            geometry={"type": "MultiLineString", "coordinates": [[[94, 27], [94.1, 27]]]},
            source="JalDrishti accessibility engine",
            source_record_id="road-1",
            observed_at=NOW,
            ingested_at=NOW,
            source_version="0.1.0",
            quality="model_derived",
            metadata={"interpretation": "Potentially affected"},
        )
        settlement = SettlementAccessibilityRecord(
            id="reachability-1",
            snapshot_id="access-1",
            event_id=event_id,
            flood_extent_id="extent-1",
            settlement_id="settlement-1",
            name="Test town",
            snapped_distance_m=100,
            major_road_reachable_before=True,
            major_road_reachable_after=False,
            hospital_reachable_before=True,
            hospital_reachable_after=False,
            nearest_major_road_km=None,
            nearest_hospital_km=None,
            potentially_isolated=True,
            assessment_status="assessed",
            geometry={"type": "Point", "coordinates": [94, 27]},
            source="JalDrishti accessibility engine",
            source_record_id="settlement-1",
            observed_at=NOW,
            ingested_at=NOW,
            source_version="0.1.0",
            quality="model_derived",
            metadata={"interpretation": "Modelled"},
        )
        return AccessibilitySnapshotRecord(
            id="access-1",
            event_id=event_id,
            flood_extent_id="extent-1",
            calculated_at=NOW,
            algorithm="jaldrishti-road-reachability-screening",
            algorithm_version="0.1.0",
            status="available",
            road_count=100,
            graph_node_count=200,
            graph_edge_count=250,
            potentially_affected_road_count=1,
            potentially_affected_road_km=1.2,
            assessed_settlement_count=1,
            potentially_isolated_settlement_count=1,
            coverage={"roads": {"status": "partial"}},
            metadata={"terminology": "Potential access disruption"},
            road_disruptions=(disruption,),
            settlements=(settlement,),
        )


@pytest.mark.asyncio
async def test_accessibility_contract_exposes_screening_not_closure():
    response = await AccessibilityService(
        events=Events(), accessibility=Accessibility()
    ).get_accessibility("event-dhemaji")

    assert response is not None
    assert response.status == "available"
    assert response.summary is not None
    assert response.summary.potentially_isolated_settlement_count == 1
    assert response.road_disruptions.features[0].properties.overlap_km == 1.2
    assert response.settlements.features[0].properties.potentially_isolated is True
    assert "not confirmed closures" in response.caveats[0]


@pytest.mark.asyncio
async def test_accessibility_before_satellite_extent_is_explicitly_unavailable():
    response = await AccessibilityService(
        events=Events(), accessibility=Accessibility(False)
    ).get_accessibility("event-dhemaji")

    assert response is not None
    assert response.status == "not_available"
    assert response.summary is None
