"""Contract tests for the committed, attributed Assam bootstrap."""

from pathlib import Path

import shapely
from jaldrishti.ingestion import load_assam_bootstrap
from shapely.geometry import shape

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
CURRENT_ASSAM_LGD_CODES = {
    "300",
    "301",
    "302",
    "303",
    "304",
    "305",
    "306",
    "307",
    "308",
    "309",
    "310",
    "311",
    "312",
    "313",
    "314",
    "315",
    "316",
    "317",
    "318",
    "319",
    "320",
    "321",
    "322",
    "323",
    "324",
    "325",
    "326",
    "664",
    "704",
    "707",
    "720",
    "734",
    "752",
    "766",
    "771",
}


def test_assam_bootstrap_has_current_district_set_and_provenance() -> None:
    dataset = load_assam_bootstrap(REPOSITORY_ROOT / "data" / "bootstrap" / "assam")

    assert len(dataset.regions) == 1
    assert len(dataset.districts) == 35
    assert len(dataset.settlements) >= 100
    assert len(dataset.rivers) >= 10
    assert len(dataset.facilities) > 1_000
    assert len(dataset.roads) > 30_000
    names = {feature["properties"]["name"] for feature in dataset.districts}
    assert {"Bajali", "Biswanath", "Hojai", "Sribhumi", "Tamulpur"} <= names
    assert {feature["properties"]["code"] for feature in dataset.districts} == (
        CURRENT_ASSAM_LGD_CODES
    )
    assert all(feature["properties"]["quality"] == "official" for feature in dataset.districts)
    assert all(
        feature["properties"]["source"]
        == "Survey of India Administrative Boundary Data Base (ABDB)"
        for feature in (*dataset.regions, *dataset.districts)
    )
    assert all(
        feature["properties"]["metadata"]["source_raw_name"]
        for feature in (*dataset.regions, *dataset.districts)
    )
    assert all(feature["properties"]["source_record_id"] for feature in dataset.facilities)
    assert {"Brahmaputra", "Barak", "Subansiri"} <= {
        feature["properties"]["name"] for feature in dataset.rivers
    }
    assert {"Guwahati", "Silchar", "Dibrugarh"} <= {
        feature["properties"]["name"] for feature in dataset.settlements
    }
    assert all(
        feature["properties"]["quality"] == "community_data" for feature in dataset.facilities
    )
    assert all(
        feature["properties"]["quality"] == "community_data"
        for feature in (*dataset.settlements, *dataset.rivers, *dataset.roads)
    )


def test_assam_bootstrap_boundary_geometries_are_valid_coverage() -> None:
    dataset = load_assam_bootstrap(REPOSITORY_ROOT / "data" / "bootstrap" / "assam")

    region_geometry = shape(dataset.regions[0]["geometry"])
    district_geometries = [shape(feature["geometry"]) for feature in dataset.districts]
    assert region_geometry.is_valid
    assert all(geometry.is_valid for geometry in district_geometries)
    assert not shapely.has_z(region_geometry)
    assert not any(shapely.has_z(geometry) for geometry in district_geometries)
    assert shapely.coverage_is_valid(district_geometries)
    district_coverage = shapely.union_all(district_geometries)
    assert all(
        district_coverage.covers(shape(feature["geometry"])) for feature in dataset.facilities
    )


def test_assam_bootstrap_manifest_is_cross_checked() -> None:
    dataset = load_assam_bootstrap(REPOSITORY_ROOT / "data" / "bootstrap" / "assam")

    assert dataset.manifest["district_count"] == len(dataset.districts)
    assert dataset.manifest["settlement_count"] == len(dataset.settlements)
    assert dataset.manifest["river_count"] == len(dataset.rivers)
    assert dataset.manifest["facility_count"] == len(dataset.facilities)
    assert dataset.manifest["road_count"] == len(dataset.roads)
    assert dataset.manifest["schema_version"] == "1.3"
    assert dataset.manifest["sources"][0]["quality"] == "official"
    assert dataset.manifest["sources"][0]["archive_sha256"] == (
        "b8325e5d9dd0f04a6663d775363fe38cd2f23bd9dbae3fb7118b4e6e0ce0bcb7"
    )
    assert dataset.manifest["sources"][1]["license"] == "ODbL-1.0"
    assert dataset.manifest["normalization"]["boundary_simplification_tolerance_metres"] == 25
    assert dataset.manifest["sources"][-1]["archive_sha256"] == (
        "709da4cd1b81e8576885dd2cab7dfaf69db18372ce693fd5fea6a4ada4aa41f2"
    )
