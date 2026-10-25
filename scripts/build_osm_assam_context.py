"""Build attributed Assam settlement and major-river bootstrap layers.

The input files are frozen Overpass JSON responses.  This script clips every
record to the already-normalized official Assam boundary, writes deterministic
GeoJSON, and extends the existing bootstrap manifest without rewriting the
official administrative layers or the independently built facility layer.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from shapely.geometry import LineString, MultiLineString, Point, shape
from shapely.geometry.base import BaseGeometry
from shapely.ops import linemerge, unary_union

OSM_COPYRIGHT_URL = "https://www.openstreetmap.org/copyright"
OSM_API_URL = "https://api.openstreetmap.org/api/0.6/"
OVERPASS_URL = "https://overpass.private.coffee/api/interpreter"
RIVER_SELECTION = (
    "Brahmaputra|Barak|Subansiri|Lohit|Dibang|Manas|Beki|Dhansiri|Kopili|"
    "Jia Bharali|Kameng|Burhi Dihing|Dihing|Dikhow|Disang|Jhanji|Kulsi|Sankosh"
)


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} does not contain a JSON object")
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _source_version(payload: dict[str, Any]) -> str:
    if payload.get("_source_version"):
        return str(payload["_source_version"])
    timestamp = str(payload.get("osm3s", {}).get("timestamp_osm_base", ""))
    if not timestamp:
        raise ValueError("Overpass response has no osm3s.timestamp_osm_base")
    return f"osm-{timestamp.split('T', 1)[0]}"


def _merge_osm_payloads(paths: list[Path], *, source_version: str) -> dict[str, Any]:
    elements: list[dict[str, Any]] = []
    for path in paths:
        payload = _read_json(path)
        source_elements = payload.get("elements")
        if not isinstance(source_elements, list):
            raise ValueError(f"{path} has no OSM elements list")
        elements.extend(source_elements)
    return {"_source_version": source_version, "elements": elements}


def _region_geometry(path: Path) -> BaseGeometry:
    payload = _read_json(path)
    features = payload.get("features", [])
    if len(features) != 1 or features[0].get("properties", {}).get("id") != "assam":
        raise ValueError("Region file must contain exactly the normalized Assam feature")
    geometry = shape(features[0]["geometry"])
    if geometry.is_empty or not geometry.is_valid:
        raise ValueError("Normalized Assam boundary is empty or invalid")
    return geometry


def _osm_properties(*, element_type: str, element_id: int, version: str) -> dict[str, Any]:
    return {
        "source": "OpenStreetMap contributors",
        "source_record_id": f"{element_type}/{element_id}",
        "source_url": f"https://www.openstreetmap.org/{element_type}/{element_id}",
        "source_version": version,
        "quality": "community_data",
    }


def _population(value: object) -> int | None:
    if value is None:
        return None
    digits = re.sub(r"[^0-9]", "", str(value))
    return int(digits) if digits else None


def _settlements(payload: dict[str, Any], region: BaseGeometry) -> dict[str, Any]:
    version = _source_version(payload)
    features: list[dict[str, Any]] = []
    seen_ids: set[int] = set()
    for element in payload.get("elements", []):
        if element.get("type") != "node":
            continue
        tags = element.get("tags", {})
        raw_name = tags.get("name")
        name = tags.get("name:en") or raw_name
        settlement_type = tags.get("place")
        if not name or settlement_type not in {"city", "town"}:
            continue
        element_id = int(element["id"])
        if element_id in seen_ids:
            continue
        point = Point(float(element["lon"]), float(element["lat"]))
        if not region.covers(point):
            continue
        seen_ids.add(element_id)
        record_id = f"osm-node-{element_id}"
        metadata = {
            key: tags[key]
            for key in (
                "alt_name",
                "name:as",
                "name:en",
                "official_name",
                "population:date",
                "wikidata",
            )
            if tags.get(key)
        }
        if raw_name and raw_name != name:
            metadata["source_raw_name"] = raw_name
        features.append(
            {
                "type": "Feature",
                "id": record_id,
                "geometry": {"type": "Point", "coordinates": [point.x, point.y]},
                "properties": {
                    "id": record_id,
                    "region_id": "assam",
                    "district_id": None,
                    "code": None,
                    "name": str(name),
                    "settlement_type": settlement_type,
                    "population": _population(tags.get("population")),
                    **_osm_properties(
                        element_type="node",
                        element_id=element_id,
                        version=version,
                    ),
                    "metadata": metadata,
                },
            }
        )
    features.sort(key=lambda feature: (feature["properties"]["name"], feature["id"]))
    if len(features) < 25:
        raise ValueError(f"Expected at least 25 Assam cities/towns, received {len(features)}")
    return {"type": "FeatureCollection", "features": features}


def _canonical_river_name(name: str) -> str | None:
    normalized = " ".join(name.casefold().split())
    if "puraton brahmaputra" in normalized:
        return None
    rules = (
        (("brahmaputra",), "Brahmaputra"),
        (("barak",), "Barak"),
        (("subansiri",), "Subansiri"),
        (("lohit",), "Lohit"),
        (("dibang",), "Dibang"),
        (("manas",), "Manas"),
        (("beki",), "Beki"),
        (("mora dhansiri",), "Mora Dhansiri"),
        (("dhansiri",), "Dhansiri"),
        (("kopili",), "Kopili"),
        (("kameng", "jia bharali"), "Jia Bharali (Kameng)"),
        (("burhi dihing",), "Burhi Dihing"),
        (("noa dihing", "noa dehing", "diyun;dihing"), "Noa Dihing"),
        (("dikhow",), "Dikhow"),
        (("disang",), "Disang"),
        (("jhanji", "melak-jhanji"), "Jhanji"),
        (("kulsi",), "Kulsi"),
        (("sankosh",), "Sankosh"),
    )
    for needles, canonical in rules:
        if any(needle in normalized for needle in needles):
            return canonical
    return None


def _line_parts(geometry: BaseGeometry) -> list[LineString]:
    if geometry.is_empty:
        return []
    if isinstance(geometry, LineString):
        return [geometry]
    if isinstance(geometry, MultiLineString):
        return list(geometry.geoms)
    if hasattr(geometry, "geoms"):
        parts: list[LineString] = []
        for item in geometry.geoms:
            parts.extend(_line_parts(item))
        return parts
    return []


def _rounded_multiline(geometry: BaseGeometry) -> dict[str, Any]:
    lines = _line_parts(geometry)
    coordinates = [
        [[round(float(x), 7), round(float(y), 7)] for x, y, *_ in line.coords]
        for line in lines
        if len(line.coords) >= 2
    ]
    payload = {"type": "MultiLineString", "coordinates": coordinates}
    checked = shape(payload)
    if checked.is_empty or not checked.is_valid:
        raise ValueError("River normalization produced invalid linework")
    return payload


def _rivers(payload: dict[str, Any], region: BaseGeometry) -> dict[str, Any]:
    version = _source_version(payload)
    grouped: dict[str, list[tuple[int, str, LineString]]] = {}
    for element in payload.get("elements", []):
        tags = element.get("tags", {})
        raw_name = str(tags.get("name", ""))
        canonical_name = _canonical_river_name(raw_name)
        raw_geometry = element.get("geometry")
        if element.get("type") != "way" or not canonical_name or not raw_geometry:
            continue
        line = LineString([(float(item["lon"]), float(item["lat"])) for item in raw_geometry])
        for clipped in _line_parts(line.intersection(region)):
            if not clipped.is_empty and clipped.length > 0:
                grouped.setdefault(canonical_name, []).append(
                    (int(element["id"]), raw_name, clipped)
                )

    features: list[dict[str, Any]] = []
    for name, records in sorted(grouped.items()):
        way_ids = sorted({record[0] for record in records})
        source_names = sorted({record[1] for record in records})
        dissolved = unary_union([record[2] for record in records])
        merged = dissolved if isinstance(dissolved, LineString) else linemerge(dissolved)
        record_digest = hashlib.sha256(",".join(map(str, way_ids)).encode()).hexdigest()[:16]
        slug = re.sub(r"[^a-z0-9]+", "-", name.casefold()).strip("-")
        features.append(
            {
                "type": "Feature",
                "id": f"assam-river-{slug}",
                "geometry": _rounded_multiline(merged),
                "properties": {
                    "id": f"assam-river-{slug}",
                    "region_id": "assam",
                    "code": None,
                    "name": name,
                    "river_class": "major_context",
                    "source": "OpenStreetMap contributors",
                    "source_record_id": f"ways/{record_digest}",
                    "source_url": OSM_COPYRIGHT_URL,
                    "source_version": version,
                    "quality": "community_data",
                    "metadata": {
                        "source_way_ids": way_ids,
                        "source_names": source_names,
                        "selection": "reviewed major-river name allowlist",
                    },
                },
            }
        )
    if len(features) < 10:
        raise ValueError(f"Expected at least 10 named major rivers, received {len(features)}")
    return {"type": "FeatureCollection", "features": features}


def _update_manifest(
    path: Path,
    *,
    settlements: dict[str, Any],
    rivers: dict[str, Any],
    settlement_version: str,
    river_version: str,
    retrieved_at: datetime,
) -> None:
    manifest = _read_json(path)
    manifest["schema_version"] = "1.2"
    manifest["retrieved_at"] = retrieved_at.astimezone(UTC).isoformat()
    manifest["settlement_count"] = len(settlements["features"])
    manifest["river_count"] = len(rivers["features"])
    manifest.setdefault("normalization", {}).update(
        {
            "context_clip_boundary": "official normalized Assam region",
            "river_selection": "reviewed major-river name allowlist",
        }
    )
    limitations = manifest.setdefault("limitations", [])
    for limitation in (
        "Settlement and river context is community-maintained and may be incomplete or stale.",
        "River lines are a selected operational backdrop, not a hydrological network model.",
    ):
        if limitation not in limitations:
            limitations.append(limitation)

    for source in manifest.get("sources", []):
        if source.get("name") == "OpenStreetMap contributors":
            source["scope"] = sorted(set(source.get("scope", [])) | {"settlements", "rivers"})
            source["source_versions"] = sorted(
                set(source.get("source_versions", [])) | {settlement_version, river_version}
            )
        if source.get("name") == "Overpass API":
            source["scope"] = sorted(set(source.get("scope", [])) | {"settlements", "rivers"})
            source["url"] = OVERPASS_URL
    if not any(source.get("name") == "OpenStreetMap API" for source in manifest.get("sources", [])):
        manifest.setdefault("sources", []).append(
            {
                "name": "OpenStreetMap API",
                "scope": ["settlements"],
                "url": OSM_API_URL,
            }
        )
    _write_json(path, manifest)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--settlements", type=Path, nargs="+", required=True)
    parser.add_argument("--settlement-source-version", required=True)
    parser.add_argument("--rivers", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--retrieved-at", required=True)
    args = parser.parse_args()

    retrieved_at = datetime.fromisoformat(args.retrieved_at.replace("Z", "+00:00"))
    if retrieved_at.tzinfo is None:
        retrieved_at = retrieved_at.replace(tzinfo=UTC)
    region = _region_geometry(args.output / "regions.geojson")
    settlement_source = _merge_osm_payloads(
        args.settlements,
        source_version=args.settlement_source_version,
    )
    river_source = _read_json(args.rivers)
    settlements = _settlements(settlement_source, region)
    rivers = _rivers(river_source, region)
    _write_json(args.output / "settlements.geojson", settlements)
    _write_json(args.output / "rivers.geojson", rivers)
    _update_manifest(
        args.output / "manifest.json",
        settlements=settlements,
        rivers=rivers,
        settlement_version=_source_version(settlement_source),
        river_version=_source_version(river_source),
        retrieved_at=retrieved_at,
    )


if __name__ == "__main__":
    main()
