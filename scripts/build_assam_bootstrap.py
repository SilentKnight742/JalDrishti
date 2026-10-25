"""Normalize attributed OSM/Nominatim exports into the Phase 1 bootstrap schema.

This is a reproducible build utility, not a live ingestion adapter. Its outputs
are committed under ``data/bootstrap/assam`` so ``docker compose up`` remains
network-independent. Production refreshes should use the bulk Geofabrik source
configured in ``configs/assam.yaml`` and retain the same provenance fields.
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

OSM_COPYRIGHT_URL = "https://www.openstreetmap.org/copyright"
NOMINATIM_URL = "https://nominatim.openstreetmap.org/"
OVERPASS_URL = "https://overpass.private.coffee/api/interpreter"


def _multi_polygon(geometry: dict[str, Any]) -> dict[str, Any]:
    if geometry["type"] == "MultiPolygon":
        return geometry
    if geometry["type"] != "Polygon":
        raise ValueError(f"Expected Polygon or MultiPolygon, got {geometry['type']}")
    return {"type": "MultiPolygon", "coordinates": [geometry["coordinates"]]}


def _feature_collection(features: list[dict[str, Any]]) -> dict[str, Any]:
    return {"type": "FeatureCollection", "features": features}


def _source_properties(*, osm_type: str, osm_id: int, version: str) -> dict[str, Any]:
    return {
        "source": "OpenStreetMap contributors",
        "source_record_id": f"{osm_type}/{osm_id}",
        "source_url": f"https://www.openstreetmap.org/{osm_type}/{osm_id}",
        "source_version": version,
        "quality": "community_data",
    }


def _normalize_region(payload: dict[str, Any], *, version: str) -> dict[str, Any]:
    source = payload["features"]
    if len(source) != 1:
        raise ValueError(f"Expected exactly one Assam region, received {len(source)}")
    feature = source[0]
    properties = feature["properties"]
    if properties.get("name") != "Assam":
        raise ValueError("Region source is not Assam")
    osm_id = int(properties["osm_id"])
    return _feature_collection(
        [
            {
                "type": "Feature",
                "id": "assam",
                "geometry": _multi_polygon(feature["geometry"]),
                "properties": {
                    "id": "assam",
                    "code": "18",
                    "name": "Assam",
                    "iso_3166_2": "IN-AS",
                    **_source_properties(osm_type="relation", osm_id=osm_id, version=version),
                    "metadata": {
                        "admin_level": "4",
                        "wikidata": properties.get("extratags", {}).get("wikidata"),
                    },
                },
            }
        ]
    )


def _normalize_districts(payload: dict[str, Any], *, version: str) -> dict[str, Any]:
    features: list[dict[str, Any]] = []
    for feature in payload["features"]:
        source = feature["properties"]
        extras = source.get("extratags", {})
        code = extras.get("ref:LGD:district")
        if not code:
            raise ValueError(f"District {source.get('name')} has no LGD code")
        name = str(source["name"]).removesuffix(" district")
        osm_id = int(source["osm_id"])
        features.append(
            {
                "type": "Feature",
                "id": f"assam-district-{code}",
                "geometry": _multi_polygon(feature["geometry"]),
                "properties": {
                    "id": f"assam-district-{code}",
                    "region_id": "assam",
                    "code": str(code),
                    "name": name,
                    **_source_properties(osm_type="relation", osm_id=osm_id, version=version),
                    "metadata": {
                        "admin_level": "5",
                        "wikidata": extras.get("wikidata"),
                    },
                },
            }
        )
    features.sort(key=lambda item: (item["properties"]["name"], item["id"]))
    if len(features) != 35:
        raise ValueError(f"Expected 35 Assam districts, received {len(features)}")
    if len({feature["properties"]["code"] for feature in features}) != 35:
        raise ValueError("Assam district LGD codes are not unique")
    return _feature_collection(features)


def _facility_point(element: dict[str, Any]) -> list[float] | None:
    if element["type"] == "node":
        latitude, longitude = element.get("lat"), element.get("lon")
    else:
        center = element.get("center", {})
        latitude, longitude = center.get("lat"), center.get("lon")
    if latitude is None or longitude is None:
        return None
    return [float(longitude), float(latitude)]


def _facility_category(amenity: str) -> str:
    if amenity in {"hospital", "clinic", "doctors"}:
        return "healthcare"
    if amenity == "school":
        return "education"
    return "emergency_service"


def _normalize_facilities(payload: dict[str, Any], *, version: str) -> dict[str, Any]:
    features: list[dict[str, Any]] = []
    for element in payload["elements"]:
        tags = element.get("tags", {})
        name = tags.get("name")
        amenity = tags.get("amenity")
        coordinates = _facility_point(element)
        if not name or not amenity or coordinates is None:
            continue
        osm_type = str(element["type"])
        osm_id = int(element["id"])
        record_id = f"osm-{osm_type}-{osm_id}"
        public_tags = {
            key: value
            for key, value in tags.items()
            if key
            in {
                "addr:city",
                "addr:district",
                "addr:postcode",
                "emergency",
                "healthcare",
                "operator",
                "operator:type",
                "opening_hours",
                "phone",
                "website",
            }
        }
        features.append(
            {
                "type": "Feature",
                "id": record_id,
                "geometry": {"type": "Point", "coordinates": coordinates},
                "properties": {
                    "id": record_id,
                    "region_id": "assam",
                    "district_id": None,
                    "code": None,
                    "name": str(name),
                    "category": _facility_category(str(amenity)),
                    "subcategory": str(amenity),
                    **_source_properties(osm_type=osm_type, osm_id=osm_id, version=version),
                    "metadata": public_tags,
                },
            }
        )
    features.sort(key=lambda item: (item["properties"]["name"], item["id"]))
    return _feature_collection(features)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--region", type=Path, required=True)
    parser.add_argument("--districts", type=Path, required=True)
    parser.add_argument("--facilities", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--retrieved-at", required=True)
    args = parser.parse_args()

    retrieved_at = datetime.fromisoformat(args.retrieved_at.replace("Z", "+00:00"))
    if retrieved_at.tzinfo is None:
        retrieved_at = retrieved_at.replace(tzinfo=UTC)
    version = f"osm-{retrieved_at.astimezone(UTC).date().isoformat()}"

    region = json.loads(args.region.read_text(encoding="utf-8"))
    districts = json.loads(args.districts.read_text(encoding="utf-8"))
    facilities = json.loads(args.facilities.read_text(encoding="utf-8"))
    normalized_region = _normalize_region(region, version=version)
    normalized_districts = _normalize_districts(districts, version=version)
    facility_version = (
        "osm-" + facilities.get("osm3s", {}).get("timestamp_osm_base", version).split("T", 1)[0]
    )
    normalized_facilities = _normalize_facilities(facilities, version=facility_version)

    _write_json(args.output / "regions.geojson", normalized_region)
    _write_json(args.output / "districts.geojson", normalized_districts)
    _write_json(args.output / "facilities.geojson", normalized_facilities)
    _write_json(
        args.output / "manifest.json",
        {
            "schema_version": "1.0",
            "retrieved_at": retrieved_at.astimezone(UTC).isoformat(),
            "region_count": len(normalized_region["features"]),
            "district_count": len(normalized_districts["features"]),
            "facility_count": len(normalized_facilities["features"]),
            "sources": [
                {
                    "name": "OpenStreetMap contributors",
                    "license": "ODbL-1.0",
                    "url": OSM_COPYRIGHT_URL,
                },
                {"name": "Nominatim", "url": NOMINATIM_URL},
                {"name": "Overpass API", "url": OVERPASS_URL},
            ],
            "limitations": [
                "Community-maintained development bootstrap, not an authoritative asset inventory.",
                "Facility coverage and tags may be incomplete or stale.",
                "Administrative boundaries are replaced by Survey of India ABDB when that adapter runs.",
            ],
        },
    )


if __name__ == "__main__":
    main()
