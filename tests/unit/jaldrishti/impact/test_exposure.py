import geopandas as gpd
import pytest
from jaldrishti.impact.exposure import (
    CRSValidationError,
    line_exposure,
    polygon_exposure,
)
from shapely.geometry import LineString, Point, box


def test_linear_and_polygon_rules_match_valencia_parity() -> None:
    flood = box(4, -1, 8, 4)
    roads = gpd.GeoDataFrame(
        {"name": ["long", "clear"]},
        geometry=[LineString([(0, 0), (10, 0)]), LineString([(0, 5), (10, 5)])],
        crs="EPSG:32630",
    )
    buildings = gpd.GeoDataFrame(
        {"name": ["exposed", "clear"]},
        geometry=[box(6, 1, 9, 3), box(20, 20, 22, 22)],
        crs="EPSG:32630",
    )

    exposed_roads = line_exposure(
        roads,
        flood,
        minimum_overlap_m=3,
        flood_crs="EPSG:32630",
    )
    exposed_buildings = polygon_exposure(
        buildings,
        flood,
        minimum_overlap_fraction=0.1,
        flood_crs="EPSG:32630",
    )

    assert exposed_roads["name"].tolist() == ["long"]
    assert exposed_roads.iloc[0]["overlap_m"] == 4
    assert exposed_buildings["name"].tolist() == ["exposed"]


def test_point_facility_intersection_matches_legacy_semantics() -> None:
    facilities = gpd.GeoDataFrame(
        {"name": ["inside", "outside"]},
        geometry=[Point(5, 1), Point(20, 20)],
        crs="EPSG:32630",
    )

    exposed = polygon_exposure(
        facilities,
        box(4, -1, 8, 4),
        minimum_overlap_fraction=0.1,
        flood_crs="EPSG:32630",
    )

    assert exposed["name"].tolist() == ["inside"]
    assert exposed.iloc[0]["overlap_fraction"] == 1.0


@pytest.mark.parametrize(
    ("feature_crs", "flood_crs", "message"),
    [
        (None, "EPSG:32630", "feature CRS is required"),
        ("EPSG:4326", "EPSG:4326", "must be projected"),
        ("EPSG:32630", "EPSG:3857", "does not match"),
        ("EPSG:2263", "EPSG:2263", "units must be metres"),
    ],
)
def test_line_exposure_rejects_unsafe_crs(
    feature_crs: str | None,
    flood_crs: str,
    message: str,
) -> None:
    lines = gpd.GeoDataFrame(
        {"name": ["road"]},
        geometry=[LineString([(0, 0), (10, 0)])],
        crs=feature_crs,
    )

    with pytest.raises(CRSValidationError, match=message):
        line_exposure(lines, box(4, -1, 8, 4), 3, flood_crs=flood_crs)
