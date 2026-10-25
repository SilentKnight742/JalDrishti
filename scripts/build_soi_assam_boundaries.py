"""Normalize Survey of India ABDB boundaries for the Assam bootstrap.

The source archive is intentionally not committed.  This utility reads the
official state and district shapefiles from an extracted ABDB archive, validates
the current Assam district coverage, simplifies it in the source metre-based
CRS, and writes web-ready EPSG:4326 GeoJSON. It also clips the independently
attributed OSM facilities to the normalized official district coverage so
every operational facility has an unambiguous Assam district assignment.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import geopandas as gpd
import shapely
from shapely.geometry import MultiPolygon, Polygon, mapping, shape
from shapely.geometry.base import BaseGeometry

ABDB_NAME = "Survey of India Administrative Boundary Data Base (ABDB)"
ABDB_PAGE_URL = "https://surveyofindia.gov.in/pages/administrative-boundary-data-base-abdb-"
ABDB_DOWNLOAD_URL = (
    "https://surveyofindia.gov.in/documents/State_District_Subdistrict_PAN%20INDIA.rar"
)
OSM_COPYRIGHT_URL = "https://www.openstreetmap.org/copyright"
OVERPASS_URL = "https://overpass.private.coffee/api/interpreter"
COORDINATE_DECIMAL_PLACES = 7

# Current code/name pairs in the 2026-05-07 ABDB District Boundary layer.  The
# raw spelling is checked separately and retained in feature metadata so a
# cleaned display label never obscures what the source actually published.
ASSAM_DISTRICTS: dict[str, tuple[str, str]] = {
    "300": ("KOKRAJHAR", "Kokrajhar"),
    "301": ("DHUBRI", "Dhubri"),
    "302": ("GOALPARA", "Goalpara"),
    "303": ("BARPETA", "Barpeta"),
    "304": ("MARIGAON", "Marigaon"),
    "305": ("NAGAON", "Nagaon"),
    "306": ("SONITPUR", "Sonitpur"),
    "307": ("LAKHIMPUR", "Lakhimpur"),
    "308": ("DHEMAJI", "Dhemaji"),
    "309": ("TINSUKIA", "Tinsukia"),
    "310": ("DIBRUGARH", "Dibrugarh"),
    "311": ("SIBSAGAR", "Sivasagar"),
    "312": ("JORHAT", "Jorhat"),
    "313": ("GOLAGHAT", "Golaghat"),
    "314": ("KARBI ANGLONG", "Karbi Anglong"),
    "315": ("DIMA HASAO", "Dima Hasao"),
    "316": ("CACHAR", "Cachar"),
    "317": ("SRIBHUMI", "Sribhumi"),
    "318": ("HAILAKANDI", "Hailakandi"),
    "319": ("BONGAIGAON", "Bongaigaon"),
    "320": ("CHIRANG", "Chirang"),
    "321": ("KAMRUP RURAL", "Kamrup"),
    "322": ("KAMRUP METRO", "Kamrup Metropolitan"),
    "323": ("NALBARI", "Nalbari"),
    "324": ("BAKSA", "Baksa"),
    "325": ("DARANG", "Darrang"),
    "326": ("UDALGURI", "Udalguri"),
    "664": ("SOUTH SALMARA", "South Salmara-Mankachar"),
    "704": ("CHARAIDEO", "Charaideo"),
    "707": ("MAJULI", "Majuli"),
    "720": ("HOJAI", "Hojai"),
    "734": ("BISWANATH", "Biswanath"),
    "752": ("WEST KARBI ANAGLONG", "West Karbi Anglong"),
    "766": ("TAMULPUR", "Tamulpur"),
    "771": ("BAJALI", "Bajali"),
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _normalized_raw_name(value: object) -> str:
    return " ".join(str(value).split()).upper()


def _normalized_code(value: object) -> str:
    text = str(value).strip()
    return text[:-2] if text.endswith(".0") else text


def _validate_columns(frame: gpd.GeoDataFrame, required: set[str], *, layer: str) -> None:
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"{layer} is missing required fields: {sorted(missing)}")
    if frame.crs is None:
        raise ValueError(f"{layer} has no CRS")
    axis_units = {axis.unit_name.lower() for axis in frame.crs.axis_info if axis.unit_name}
    if not axis_units or not axis_units <= {"metre", "meter"}:
        raise ValueError(f"{layer} must use a metre-based source CRS, got {frame.crs}")


def _multi_polygon(geometry: BaseGeometry) -> MultiPolygon:
    if isinstance(geometry, MultiPolygon):
        return geometry
    if isinstance(geometry, Polygon):
        return MultiPolygon([geometry])
    raise ValueError(f"Expected Polygon or MultiPolygon, got {geometry.geom_type}")


def _geojson_geometry(geometry: BaseGeometry) -> dict[str, Any]:
    """Serialize at centimetre-scale precision after metre-based simplification."""

    def _round_coordinates(value: Any) -> Any:
        if isinstance(value, (list, tuple)):
            return [_round_coordinates(item) for item in value]
        if isinstance(value, float):
            return round(value, COORDINATE_DECIMAL_PLACES)
        return value

    # The ABDB shapefiles carry a zero-valued Z ordinate. JalDrishti stores
    # operational map geometry in a 2D EPSG:4326 PostGIS column, so remove the
    # non-semantic ordinate explicitly instead of relying on driver behavior.
    payload = mapping(shapely.force_2d(_multi_polygon(geometry)))
    payload["coordinates"] = _round_coordinates(payload["coordinates"])
    rounded = shape(payload)
    if rounded.is_empty or not rounded.is_valid or shapely.has_z(rounded):
        raise ValueError("Coordinate rounding produced invalid boundary geometry")
    return payload


def _validate_geometries(geometries: gpd.GeoSeries, *, layer: str) -> None:
    if geometries.is_empty.any():
        raise ValueError(f"{layer} contains empty geometry")
    if not geometries.is_valid.all():
        invalid = geometries.index[~geometries.is_valid].tolist()
        raise ValueError(f"{layer} contains invalid geometries at rows {invalid}")
    unexpected = set(geometries.geom_type).difference({"Polygon", "MultiPolygon"})
    if unexpected:
        raise ValueError(f"{layer} contains unsupported geometry types: {sorted(unexpected)}")


def _source_properties(*, record_id: str, source_version: str) -> dict[str, Any]:
    return {
        "source": ABDB_NAME,
        "source_record_id": record_id,
        "source_url": ABDB_PAGE_URL,
        "source_version": source_version,
        "quality": "official",
    }


def _feature_collection(features: list[dict[str, Any]]) -> dict[str, Any]:
    return {"type": "FeatureCollection", "features": features}


def _read_official_boundaries(
    state_path: Path,
    district_path: Path,
    *,
    simplify_metres: float,
    source_version: str,
) -> tuple[dict[str, Any], dict[str, Any], str]:
    states = gpd.read_file(state_path)
    districts = gpd.read_file(district_path)
    _validate_columns(
        states,
        {"OBJECTID", "STATE", "geometry"},
        layer="ABDB State Boundary",
    )
    _validate_columns(
        districts,
        {"OBJECTID", "STATE_UT", "STATE_LGD", "DISTRICT", "DIST_LGD", "geometry"},
        layer="ABDB District Boundary",
    )
    if states.crs != districts.crs:
        raise ValueError("ABDB state and district layers use different source CRSs")

    assam_states = states[states["STATE"].map(_normalized_raw_name).eq("ASSAM")].copy()
    assam_districts = districts[districts["STATE_LGD"].map(_normalized_code).eq("18")].copy()
    if len(assam_states) != 1:
        raise ValueError(f"Expected one Assam state feature, received {len(assam_states)}")
    if len(assam_districts) != 35:
        raise ValueError(f"Expected 35 Assam districts, received {len(assam_districts)}")

    assam_districts["_code"] = assam_districts["DIST_LGD"].map(_normalized_code)
    observed_codes = set(assam_districts["_code"])
    expected_codes = set(ASSAM_DISTRICTS)
    if observed_codes != expected_codes:
        raise ValueError(
            "ABDB Assam LGD codes differ from the reviewed snapshot; "
            f"missing={sorted(expected_codes - observed_codes)}, "
            f"unexpected={sorted(observed_codes - expected_codes)}"
        )
    if assam_districts["_code"].duplicated().any():
        raise ValueError("ABDB Assam district LGD codes are not unique")
    for _, row in assam_districts.iterrows():
        code = row["_code"]
        expected_raw_name = ASSAM_DISTRICTS[code][0]
        actual_raw_name = _normalized_raw_name(row["DISTRICT"])
        if actual_raw_name != expected_raw_name:
            raise ValueError(
                f"ABDB district {code} raw name changed: "
                f"expected {expected_raw_name!r}, received {actual_raw_name!r}"
            )

    _validate_geometries(assam_states.geometry, layer="ABDB Assam state")
    _validate_geometries(assam_districts.geometry, layer="ABDB Assam districts")
    if not shapely.coverage_is_valid(assam_districts.geometry.array):
        raise ValueError("ABDB Assam districts do not form a valid coverage")
    state_geometry = assam_states.geometry.iloc[0]
    district_union = shapely.union_all(assam_districts.geometry.array)
    mismatch_ratio = state_geometry.symmetric_difference(district_union).area / state_geometry.area
    if mismatch_ratio > 1e-6:
        raise ValueError(
            f"ABDB Assam state/district boundaries disagree by {mismatch_ratio:.3%} of state area"
        )

    simplified_state = state_geometry.simplify(simplify_metres, preserve_topology=True)
    simplified_districts = shapely.coverage_simplify(
        assam_districts.geometry.array,
        simplify_metres,
    )
    if not shapely.coverage_is_valid(simplified_districts):
        raise ValueError("Simplified Assam districts no longer form a valid coverage")
    simplified_district_series = gpd.GeoSeries(
        simplified_districts,
        index=assam_districts.index,
        crs=assam_districts.crs,
    )
    simplified_state_series = gpd.GeoSeries([simplified_state], crs=states.crs)
    _validate_geometries(simplified_state_series, layer="simplified Assam state")
    _validate_geometries(simplified_district_series, layer="simplified Assam districts")

    state_wgs84 = simplified_state_series.to_crs("EPSG:4326").iloc[0]
    districts_wgs84 = simplified_district_series.to_crs("EPSG:4326")
    _validate_geometries(gpd.GeoSeries([state_wgs84], crs="EPSG:4326"), layer="Assam state")
    _validate_geometries(districts_wgs84, layer="Assam districts")
    source_crs_name = states.crs.name

    state_row = assam_states.iloc[0]
    region = _feature_collection(
        [
            {
                "type": "Feature",
                "id": "assam",
                "geometry": _geojson_geometry(state_wgs84),
                "properties": {
                    "id": "assam",
                    "code": "18",
                    "name": "Assam",
                    "iso_3166_2": "IN-AS",
                    **_source_properties(
                        record_id=f"state-boundary/objectid/{int(state_row['OBJECTID'])}",
                        source_version=source_version,
                    ),
                    "metadata": {
                        "source_layer": "State Boundary",
                        "source_object_id": int(state_row["OBJECTID"]),
                        "source_raw_name": str(state_row["STATE"]),
                        "source_crs": source_crs_name,
                        "simplification_tolerance_metres": simplify_metres,
                        "coordinate_decimal_places": COORDINATE_DECIMAL_PLACES,
                    },
                },
            }
        ]
    )

    district_features: list[dict[str, Any]] = []
    for index, row in assam_districts.iterrows():
        code = row["_code"]
        display_name = ASSAM_DISTRICTS[code][1]
        district_features.append(
            {
                "type": "Feature",
                "id": f"assam-district-{code}",
                "geometry": _geojson_geometry(districts_wgs84.loc[index]),
                "properties": {
                    "id": f"assam-district-{code}",
                    "region_id": "assam",
                    "code": code,
                    "name": display_name,
                    **_source_properties(
                        record_id=f"district-boundary/objectid/{int(row['OBJECTID'])}",
                        source_version=source_version,
                    ),
                    "metadata": {
                        "source_layer": "District Boundary",
                        "source_object_id": int(row["OBJECTID"]),
                        "source_raw_name": str(row["DISTRICT"]),
                        "source_raw_state_name": str(row["STATE_UT"]),
                        "source_crs": source_crs_name,
                        "simplification_tolerance_metres": simplify_metres,
                        "coordinate_decimal_places": COORDINATE_DECIMAL_PLACES,
                    },
                },
            }
        )
    district_features.sort(key=lambda feature: (feature["properties"]["name"], feature["id"]))
    return region, _feature_collection(district_features), source_crs_name


def _read_facilities(
    path: Path,
    *,
    district_coverage: BaseGeometry,
) -> tuple[dict[str, Any], tuple[str, ...]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("type") != "FeatureCollection" or not isinstance(payload.get("features"), list):
        raise ValueError(f"{path} is not a GeoJSON FeatureCollection")
    features = payload["features"]
    if not features:
        raise ValueError("Facilities bootstrap is empty")
    retained_features: list[dict[str, Any]] = []
    for index, feature in enumerate(features):
        geometry = shape(feature.get("geometry"))
        if geometry.geom_type != "Point" or geometry.is_empty or not geometry.is_valid:
            raise ValueError(f"Facility feature {index} is not a valid Point")
        properties = feature.get("properties", {})
        if properties.get("source") != "OpenStreetMap contributors":
            raise ValueError(f"Facility feature {index} has unexpected source provenance")
        if district_coverage.covers(geometry):
            retained_features.append(feature)
    if not retained_features:
        raise ValueError("No facilities fall within the official Assam district coverage")
    versions = tuple(
        sorted({str(feature["properties"]["source_version"]) for feature in retained_features})
    )
    normalized_payload = {**payload, "features": retained_features}
    return normalized_payload, versions


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _utc_timestamp(value: str) -> str:
    instant = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if instant.tzinfo is None:
        instant = instant.replace(tzinfo=UTC)
    return instant.astimezone(UTC).isoformat()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state-boundary", type=Path, required=True)
    parser.add_argument("--district-boundary", type=Path, required=True)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source-version", required=True)
    parser.add_argument("--archive-http-last-modified", required=True)
    parser.add_argument("--retrieved-at", required=True)
    parser.add_argument("--simplify-metres", type=float, default=25.0)
    parser.add_argument("--expected-archive-sha256")
    args = parser.parse_args()

    if args.simplify_metres < 0:
        parser.error("--simplify-metres must not be negative")
    if not re.fullmatch(r"[0-9a-f]{64}", args.expected_archive_sha256 or "0" * 64):
        parser.error("--expected-archive-sha256 must be a lowercase SHA-256 digest")

    archive_sha256 = _sha256(args.archive)
    if args.expected_archive_sha256 and archive_sha256 != args.expected_archive_sha256:
        raise ValueError(
            f"Archive SHA-256 mismatch: expected {args.expected_archive_sha256}, "
            f"received {archive_sha256}"
        )
    retrieved_at = _utc_timestamp(args.retrieved_at)
    region, districts, source_crs = _read_official_boundaries(
        args.state_boundary,
        args.district_boundary,
        simplify_metres=args.simplify_metres,
        source_version=args.source_version,
    )
    district_coverage = shapely.union_all(
        [shape(feature["geometry"]) for feature in districts["features"]]
    )
    facilities, facility_versions = _read_facilities(
        args.output / "facilities.geojson",
        district_coverage=district_coverage,
    )

    _write_json(args.output / "regions.geojson", region)
    _write_json(args.output / "districts.geojson", districts)
    _write_json(args.output / "facilities.geojson", facilities)
    _write_json(
        args.output / "manifest.json",
        {
            "schema_version": "1.1",
            "retrieved_at": retrieved_at,
            "region_count": len(region["features"]),
            "district_count": len(districts["features"]),
            "facility_count": len(facilities["features"]),
            "sources": [
                {
                    "name": ABDB_NAME,
                    "url": ABDB_PAGE_URL,
                    "download_url": ABDB_DOWNLOAD_URL,
                    "source_version": args.source_version,
                    "archive_http_last_modified": args.archive_http_last_modified,
                    "archive_sha256": archive_sha256,
                    "scope": ["region", "districts"],
                    "quality": "official",
                },
                {
                    "name": "OpenStreetMap contributors",
                    "license": "ODbL-1.0",
                    "url": OSM_COPYRIGHT_URL,
                    "source_versions": list(facility_versions),
                    "scope": ["facilities"],
                    "quality": "community_data",
                },
                {
                    "name": "Overpass API",
                    "url": OVERPASS_URL,
                    "scope": ["facilities"],
                },
            ],
            "normalization": {
                "boundary_source_crs": source_crs,
                "boundary_target_crs": "EPSG:4326",
                "boundary_simplification_method": "Shapely coverage_simplify",
                "boundary_simplification_tolerance_metres": args.simplify_metres,
                "boundary_coordinate_decimal_places": COORDINATE_DECIMAL_PLACES,
                "facility_clip_boundary": "official normalized Assam district coverage",
            },
            "limitations": [
                "Boundary geometry is simplified for web-map delivery; use the upstream ABDB archive for survey-grade detail.",
                "Facility coverage and tags are community-maintained and may be incomplete or stale.",
                "The repository source-code licence does not relicense either upstream dataset.",
            ],
        },
    )


if __name__ == "__main__":
    main()
