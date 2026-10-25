"""Validation boundary for the network-independent Assam development dataset."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

type GeoJSONFeature = dict[str, Any]


@dataclass(frozen=True, slots=True)
class AssamBootstrap:
    """Normalized features safe to hand to a persistence adapter."""

    regions: tuple[GeoJSONFeature, ...]
    districts: tuple[GeoJSONFeature, ...]
    settlements: tuple[GeoJSONFeature, ...]
    rivers: tuple[GeoJSONFeature, ...]
    roads: tuple[GeoJSONFeature, ...]
    facilities: tuple[GeoJSONFeature, ...]
    manifest: dict[str, Any]


def _read_feature_collection(path: Path) -> tuple[GeoJSONFeature, ...]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("type") != "FeatureCollection" or not isinstance(payload.get("features"), list):
        raise ValueError(f"{path} is not a GeoJSON FeatureCollection")
    features = tuple(payload["features"])
    for index, feature in enumerate(features):
        if feature.get("type") != "Feature":
            raise ValueError(f"{path} feature {index} is not a GeoJSON Feature")
        if not feature.get("id") or not isinstance(feature.get("properties"), dict):
            raise ValueError(f"{path} feature {index} has no stable ID or properties")
        properties = feature["properties"]
        required = {
            "id",
            "name",
            "quality",
            "source",
            "source_record_id",
            "source_url",
            "source_version",
        }
        missing = required.difference(properties)
        if missing:
            raise ValueError(f"{path} feature {feature['id']} is missing {sorted(missing)}")
    return features


def load_assam_bootstrap(directory: str | Path) -> AssamBootstrap:
    """Load and cross-check a normalized Assam bootstrap directory."""

    root = Path(directory)
    regions = _read_feature_collection(root / "regions.geojson")
    districts = _read_feature_collection(root / "districts.geojson")
    settlements = _read_feature_collection(root / "settlements.geojson")
    rivers = _read_feature_collection(root / "rivers.geojson")
    roads = _read_feature_collection(root / "roads.geojson")
    facilities = _read_feature_collection(root / "facilities.geojson")
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))

    counts = {
        "region_count": len(regions),
        "district_count": len(districts),
        "settlement_count": len(settlements),
        "river_count": len(rivers),
        "road_count": len(roads),
        "facility_count": len(facilities),
    }
    for key, actual in counts.items():
        if manifest.get(key) != actual:
            raise ValueError(f"Bootstrap manifest {key}={manifest.get(key)!r}; loaded {actual}")
    if len(regions) != 1 or regions[0]["properties"]["id"] != "assam":
        raise ValueError("Bootstrap must contain exactly the Assam region")
    if len(districts) != 35:
        raise ValueError(f"Bootstrap must contain 35 Assam districts, received {len(districts)}")
    district_codes = {feature["properties"].get("code") for feature in districts}
    if None in district_codes or len(district_codes) != 35:
        raise ValueError("Bootstrap district LGD codes must be present and unique")
    if any(feature["geometry"].get("type") != "MultiPolygon" for feature in (*regions, *districts)):
        raise ValueError("Region and district geometries must be MultiPolygon")
    if any(feature["geometry"].get("type") != "Point" for feature in (*settlements, *facilities)):
        raise ValueError("Settlement and facility geometries must be Point")
    if any(feature["geometry"].get("type") != "MultiLineString" for feature in rivers):
        raise ValueError("River geometries must be MultiLineString")
    if any(feature["geometry"].get("type") != "MultiLineString" for feature in roads):
        raise ValueError("Road geometries must be MultiLineString")
    return AssamBootstrap(
        regions=regions,
        districts=districts,
        settlements=settlements,
        rivers=rivers,
        roads=roads,
        facilities=facilities,
        manifest=manifest,
    )
