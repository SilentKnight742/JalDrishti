from jaldrishti.routing import RoadLine, SettlementPoint, analyse_accessibility
from shapely.geometry import LineString, Point, Polygon


def test_flooded_connector_creates_potential_isolation_without_claiming_closure():
    roads = [
        RoadLine("west", "secondary", LineString([(0, 0), (1, 0)])),
        RoadLine("connector", "secondary", LineString([(1, 0), (2, 0)])),
        RoadLine("major", "primary", LineString([(2, 0), (3, 0)])),
    ]
    flood = Polygon([(1.4, -0.1), (1.6, -0.1), (1.6, 0.1), (1.4, 0.1)])

    result = analyse_accessibility(
        roads,
        flood,
        [SettlementPoint("s1", "Village", Point(0, 0))],
        [Point(3, 0)],
        maximum_snap_distance_m=10_000,
    )

    settlement = result.settlements[0]
    assert result.potentially_affected_road_ids == ("connector",)
    assert settlement.major_road_reachable_before is True
    assert settlement.major_road_reachable_after is False
    assert settlement.hospital_reachable_before is True
    assert settlement.hospital_reachable_after is False
    assert settlement.potentially_isolated is True


def test_safe_alternative_route_retains_access():
    roads = [
        RoadLine("direct", "secondary", LineString([(0, 0), (1, 0), (2, 0)])),
        RoadLine("detour", "secondary", LineString([(0, 0), (0, 1), (2, 1), (2, 0)])),
        RoadLine("major", "primary", LineString([(2, 0), (3, 0)])),
    ]
    flood = Polygon([(0.9, -0.1), (1.1, -0.1), (1.1, 0.1), (0.9, 0.1)])

    result = analyse_accessibility(
        roads,
        flood,
        [SettlementPoint("s1", "Village", Point(0, 0))],
        [Point(3, 0)],
        maximum_snap_distance_m=10_000,
    )

    settlement = result.settlements[0]
    assert settlement.major_road_reachable_after is True
    assert settlement.hospital_reachable_after is True
    assert settlement.potentially_isolated is False
    assert settlement.nearest_hospital_km is not None


def test_settlement_too_far_from_network_is_unassessed():
    result = analyse_accessibility(
        [RoadLine("major", "primary", LineString([(0, 0), (1, 0)]))],
        Polygon([(0.4, -0.1), (0.6, -0.1), (0.6, 0.1), (0.4, 0.1)]),
        [SettlementPoint("s1", "Remote", Point(5, 5))],
        [],
        maximum_snap_distance_m=100,
    )

    assert result.settlements[0].assessment_status == "outside_network_snap_tolerance"
    assert result.settlements[0].potentially_isolated is False
