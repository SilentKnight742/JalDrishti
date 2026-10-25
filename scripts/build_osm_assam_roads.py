"""Build a deterministic Assam routable-road bootstrap from a Geofabrik PBF.

The output is a connectivity screening network, not an authoritative statement
of road existence, condition, legal access, or passability.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

import pyogrio
from pyproj import Transformer
from shapely import make_valid
from shapely.geometry import LineString, MultiLineString, shape
from shapely.geometry.base import BaseGeometry
from shapely.ops import transform

OSM_COPYRIGHT_URL = "https://www.openstreetmap.org/copyright"
ROAD_CLASSES = (
    "motorway",
    "motorway_link",
    "trunk",
    "trunk_link",
    "primary",
    "primary_link",
    "secondary",
    "secondary_link",
    "tertiary",
    "tertiary_link",
    "unclassified",
)
TAG_PATTERN = re.compile(r'"([^"]+)"=>"([^"]*)"')


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


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _region(path: Path) -> BaseGeometry:
    payload = _read_json(path)
    features = payload.get("features", [])
    if len(features) != 1 or features[0].get("properties", {}).get("id") != "assam":
        raise ValueError("Region file must contain the normalized Assam feature")
    geometry = make_valid(shape(features[0]["geometry"]))
    if geometry.is_empty:
        raise ValueError("Assam boundary is empty")
    return geometry


def _tags(value: object) -> dict[str, str]:
    return dict(TAG_PATTERN.findall(str(value or "")))


def _line_parts(geometry: BaseGeometry) -> tuple[LineString, ...]:
    if geometry.is_empty:
        return ()
    if isinstance(geometry, LineString):
        return (geometry,)
    if isinstance(geometry, MultiLineString):
        return tuple(geometry.geoms)
    if hasattr(geometry, "geoms"):
        return tuple(line for part in geometry.geoms for line in _line_parts(part))
    return ()


def _rounded_multiline(line: LineString) -> dict[str, Any]:
    coordinates = [
        [round(float(coordinate[0]), 7), round(float(coordinate[1]), 7)]
        for coordinate in line.coords
    ]
    return {"type": "MultiLineString", "coordinates": [coordinates]}


def build_roads(
    pbf_path: Path,
    region_path: Path,
    *,
    source_version: str,
) -> dict[str, Any]:
    region = _region(region_path)
    where_values = ",".join(f"'{item}'" for item in ROAD_CLASSES)
    roads = pyogrio.read_dataframe(
        pbf_path,
        layer="lines",
        bbox=region.bounds,
        where=f"highway IN ({where_values})",
        columns=["osm_id", "name", "highway", "other_tags"],
    )
    roads = roads[roads.geometry.notna()].copy()
    roads["geometry"] = roads.geometry.intersection(region)
    roads = roads[~roads.geometry.is_empty].copy()
    to_metric = Transformer.from_crs("EPSG:4326", "EPSG:32646", always_xy=True).transform
    to_wgs84 = Transformer.from_crs("EPSG:32646", "EPSG:4326", always_xy=True).transform
    features: list[dict[str, Any]] = []
    for row in roads.itertuples(index=False):
        tags = _tags(row.other_tags)
        for part_index, raw_part in enumerate(_line_parts(make_valid(row.geometry))):
            metric = transform(to_metric, raw_part)
            if metric.length < 20:
                continue
            simplified = metric.simplify(2, preserve_topology=True)
            part = transform(to_wgs84, simplified)
            if part.is_empty or len(part.coords) < 2:
                continue
            osm_id = str(row.osm_id)
            record_id = f"osm-way-{osm_id}-{part_index}"
            road_class = str(row.highway)
            features.append(
                {
                    "type": "Feature",
                    "id": record_id,
                    "geometry": _rounded_multiline(part),
                    "properties": {
                        "id": record_id,
                        "region_id": "assam",
                        "code": None,
                        "name": str(row.name or tags.get("ref") or f"Unnamed {road_class} road"),
                        "road_class": road_class,
                        "surface": tags.get("surface"),
                        "bridge": tags.get("bridge") not in {None, "no"},
                        "oneway": tags.get("oneway") in {"yes", "1", "true", "-1"},
                        "access": tags.get("access"),
                        "length_m": round(float(metric.length), 2),
                        "source": "OpenStreetMap contributors",
                        "source_record_id": f"way/{osm_id}",
                        "source_url": f"https://www.openstreetmap.org/way/{osm_id}",
                        "source_version": source_version,
                        "quality": "community_data",
                        "metadata": {
                            "extract_provider": "Geofabrik GmbH",
                            "selection": "routable road backbone classes",
                            "simplification_metres": 2,
                        },
                    },
                }
            )
    features.sort(key=lambda item: item["id"])
    if len(features) < 10_000:
        raise ValueError(f"Expected at least 10,000 Assam road records, received {len(features)}")
    return {"type": "FeatureCollection", "features": features}


def update_manifest(
    path: Path,
    *,
    road_count: int,
    pbf_path: Path,
    download_url: str,
    source_version: str,
) -> None:
    manifest = _read_json(path)
    manifest["schema_version"] = "1.3"
    manifest["road_count"] = road_count
    manifest.setdefault("normalization", {})["road_selection"] = list(ROAD_CLASSES)
    limitation = (
        "Road accessibility uses community-maintained OSM linework as a screening network; "
        "it does not confirm legal access, surface condition, or closure."
    )
    if limitation not in manifest.setdefault("limitations", []):
        manifest["limitations"].append(limitation)
    for source in manifest.get("sources", []):
        if source.get("name") == "OpenStreetMap contributors":
            source["scope"] = sorted(set(source.get("scope", [])) | {"roads"})
            source["source_versions"] = sorted(
                set(source.get("source_versions", [])) | {source_version}
            )
    manifest.setdefault("sources", []).append(
        {
            "name": "Geofabrik GmbH",
            "scope": ["roads"],
            "url": download_url,
            "license": "ODbL-1.0",
            "source_version": source_version,
            "archive_sha256": _sha256(pbf_path),
        }
    )
    _write_json(path, manifest)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pbf", type=Path, required=True)
    parser.add_argument("--region", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--source-version", required=True)
    parser.add_argument("--download-url", required=True)
    args = parser.parse_args()
    roads = build_roads(
        args.pbf,
        args.region,
        source_version=args.source_version,
    )
    _write_json(args.output, roads)
    update_manifest(
        args.manifest,
        road_count=len(roads["features"]),
        pbf_path=args.pbf,
        download_url=args.download_url,
        source_version=args.source_version,
    )


if __name__ == "__main__":
    main()
