"""Potential road-access disruption from observed flood/change geometry.

The network result is a screening model. An intersecting road edge is treated
as potentially affected for routing, never as a confirmed closure.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import pairwise
from math import isfinite

import networkx as nx
from pyproj import Geod
from shapely.geometry import LineString, MultiLineString, Point
from shapely.geometry.base import BaseGeometry
from shapely.strtree import STRtree

Node = tuple[float, float]
MAJOR_CLASSES = frozenset(
    {"motorway", "motorway_link", "trunk", "trunk_link", "primary", "primary_link"}
)
GEOD = Geod(ellps="WGS84")


@dataclass(frozen=True, slots=True)
class RoadLine:
    id: str
    road_class: str
    geometry: LineString | MultiLineString


@dataclass(frozen=True, slots=True)
class SettlementPoint:
    id: str
    name: str
    geometry: Point


@dataclass(frozen=True, slots=True)
class SettlementReachability:
    settlement_id: str
    name: str
    snapped_distance_m: float | None
    major_road_reachable_before: bool
    major_road_reachable_after: bool
    hospital_reachable_before: bool
    hospital_reachable_after: bool
    nearest_major_road_km: float | None
    nearest_hospital_km: float | None
    potentially_isolated: bool
    assessment_status: str


@dataclass(frozen=True, slots=True)
class AccessibilityResult:
    road_count: int
    graph_node_count: int
    graph_edge_count: int
    potentially_affected_road_ids: tuple[str, ...]
    assessed_settlement_count: int
    potentially_isolated_settlement_count: int
    settlements: tuple[SettlementReachability, ...]


def _lines(geometry: LineString | MultiLineString) -> tuple[LineString, ...]:
    if isinstance(geometry, LineString):
        return (geometry,)
    return tuple(geometry.geoms)


def _node(coordinate: tuple[float, ...]) -> Node:
    return round(float(coordinate[0]), 7), round(float(coordinate[1]), 7)


def _distance_m(first: Node, second: Node) -> float:
    _, _, distance = GEOD.inv(first[0], first[1], second[0], second[1])
    return max(0.0, float(distance))


def _build_graph(
    roads: tuple[RoadLine, ...],
    flood_geometry: BaseGeometry,
) -> tuple[nx.MultiGraph, nx.MultiGraph, set[str], set[Node]]:
    baseline = nx.MultiGraph()
    safe = nx.MultiGraph()
    affected: set[str] = set()
    major_nodes: set[Node] = set()
    for road in roads:
        if road.geometry.is_empty:
            continue
        road_affected = road.geometry.intersects(flood_geometry)
        if road_affected:
            affected.add(road.id)
        for part_index, part in enumerate(_lines(road.geometry)):
            coordinates = tuple(part.coords)
            for coordinate_index, (start_raw, end_raw) in enumerate(pairwise(coordinates)):
                start = _node(start_raw)
                end = _node(end_raw)
                if start == end:
                    continue
                length_m = _distance_m(start, end)
                if not isfinite(length_m) or length_m <= 0:
                    continue
                edge_geometry = LineString([start, end])
                edge_affected = edge_geometry.intersects(flood_geometry)
                key = f"{road.id}:{part_index}:{coordinate_index}"
                attributes = {
                    "road_id": road.id,
                    "road_class": road.road_class,
                    "length_m": length_m,
                }
                baseline.add_edge(start, end, key=key, **attributes)
                if not edge_affected:
                    safe.add_edge(start, end, key=key, **attributes)
                if road.road_class in MAJOR_CLASSES:
                    major_nodes.update((start, end))
    return baseline, safe, affected, major_nodes


def _nearest_nodes(points: tuple[Point, ...], nodes: tuple[Node, ...]) -> tuple[Node | None, ...]:
    if not nodes:
        return tuple(None for _ in points)
    node_points = [Point(node) for node in nodes]
    tree = STRtree(node_points)
    return tuple(nodes[int(tree.nearest(point))] for point in points)


def _distances(graph: nx.MultiGraph, targets: set[Node]) -> dict[Node, float]:
    available = targets.intersection(graph.nodes)
    if not available:
        return {}
    return dict(nx.multi_source_dijkstra_path_length(graph, available, weight="length_m"))


def analyse_accessibility(
    roads: list[RoadLine] | tuple[RoadLine, ...],
    flood_geometry: BaseGeometry,
    settlements: list[SettlementPoint] | tuple[SettlementPoint, ...],
    hospitals: list[Point] | tuple[Point, ...],
    *,
    maximum_snap_distance_m: float = 5_000,
) -> AccessibilityResult:
    """Compare settlement reachability before and after screening flooded edges."""

    road_records = tuple(roads)
    settlement_records = tuple(settlements)
    hospital_points = tuple(hospitals)
    if flood_geometry is None or flood_geometry.is_empty:
        raise ValueError("flood_geometry must be non-empty")
    if not isfinite(maximum_snap_distance_m) or maximum_snap_distance_m <= 0:
        raise ValueError("maximum_snap_distance_m must be finite and positive")
    baseline, safe, affected, major_nodes = _build_graph(road_records, flood_geometry)
    nodes = tuple(baseline.nodes)
    settlement_nodes = _nearest_nodes(tuple(item.geometry for item in settlement_records), nodes)
    hospital_nodes = set(_nearest_nodes(hospital_points, nodes)) - {None}
    baseline_major = _distances(baseline, major_nodes)
    safe_major = _distances(safe, major_nodes)
    baseline_hospital = _distances(baseline, hospital_nodes)
    safe_hospital = _distances(safe, hospital_nodes)

    results: list[SettlementReachability] = []
    for settlement, node in zip(settlement_records, settlement_nodes, strict=True):
        snap_distance = (
            _distance_m((settlement.geometry.x, settlement.geometry.y), node)
            if node is not None
            else None
        )
        assessed = (
            node is not None
            and snap_distance is not None
            and snap_distance <= maximum_snap_distance_m
        )
        major_before = bool(assessed and node in baseline_major)
        major_after = bool(assessed and node in safe_major)
        hospital_before = bool(assessed and node in baseline_hospital)
        hospital_after = bool(assessed and node in safe_hospital)
        potentially_isolated = (major_before and not major_after) or (
            hospital_before and not hospital_after
        )
        results.append(
            SettlementReachability(
                settlement_id=settlement.id,
                name=settlement.name,
                snapped_distance_m=snap_distance if assessed else None,
                major_road_reachable_before=major_before,
                major_road_reachable_after=major_after,
                hospital_reachable_before=hospital_before,
                hospital_reachable_after=hospital_after,
                nearest_major_road_km=(safe_major[node] / 1_000 if major_after else None),
                nearest_hospital_km=(safe_hospital[node] / 1_000 if hospital_after else None),
                potentially_isolated=potentially_isolated,
                assessment_status="assessed" if assessed else "outside_network_snap_tolerance",
            )
        )
    return AccessibilityResult(
        road_count=len(road_records),
        graph_node_count=baseline.number_of_nodes(),
        graph_edge_count=baseline.number_of_edges(),
        potentially_affected_road_ids=tuple(sorted(affected)),
        assessed_settlement_count=sum(item.assessment_status == "assessed" for item in results),
        potentially_isolated_settlement_count=sum(item.potentially_isolated for item in results),
        settlements=tuple(results),
    )
