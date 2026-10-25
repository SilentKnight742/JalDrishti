"""Public ASF catalogue discovery and deterministic OPERA-S1 pairing.

Catalogue metadata is public, but downloading the referenced OPERA assets
requires NASA Earthdata authentication and acceptance of ASF's terms.  Search
results describe candidate observations; they are not flood evidence until the
imagery has been processed and its coverage validated.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from shapely.geometry import shape
from shapely.geometry.base import BaseGeometry
from shapely.wkt import loads as load_wkt

ASF_SEARCH_URL = "https://api.daac.asf.alaska.edu/services/search/param"
CATALOG_SOURCE = "NASA ASF DAAC OPERA-S1 catalogue"


class SatelliteCatalogError(ValueError):
    """Raised when an ASF response cannot satisfy the catalogue contract."""


@dataclass(frozen=True, slots=True)
class SarAsset:
    name: str
    url: str
    expected_bytes: int | None


@dataclass(frozen=True, slots=True)
class SarScene:
    product_id: str
    acquired_at: datetime
    stopped_at: datetime | None
    platform: str
    sensor: str
    relative_orbit: int
    flight_direction: str
    burst_id: str
    polarizations: tuple[str, ...]
    product_version: str
    footprint: BaseGeometry
    assets: Mapping[str, SarAsset]
    raw_properties: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class SarScenePair:
    burst_id: str
    before: SarScene
    after: SarScene


def _parse_datetime(value: Any, *, field: str, required: bool = True) -> datetime | None:
    if value in {None, ""} and not required:
        return None
    if not isinstance(value, str):
        raise SatelliteCatalogError(f"{field} must be an RFC 3339 string")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise SatelliteCatalogError(f"{field} is not a valid RFC 3339 timestamp") from exc
    if parsed.tzinfo is None:
        raise SatelliteCatalogError(f"{field} must include a timezone")
    return parsed.astimezone(UTC)


def _asset_table(properties: Mapping[str, Any]) -> dict[str, SarAsset]:
    urls = [properties.get("url"), *(properties.get("additionalUrls") or [])]
    byte_table = properties.get("bytes") or {}
    assets: dict[str, SarAsset] = {}
    for key, suffix in (("vv", "_VV.tif"), ("vh", "_VH.tif"), ("mask", "_mask.tif")):
        url = next(
            (item for item in urls if isinstance(item, str) and item.endswith(suffix)),
            None,
        )
        if url is None:
            continue
        filename = url.rsplit("/", 1)[-1]
        details = byte_table.get(filename, {}) if isinstance(byte_table, Mapping) else {}
        expected = details.get("bytes") if isinstance(details, Mapping) else None
        assets[key] = SarAsset(
            name=filename,
            url=url,
            expected_bytes=int(expected) if expected is not None else None,
        )
    return assets


def parse_asf_feature(feature: Mapping[str, Any]) -> SarScene:
    """Validate the subset of an ASF GeoJSON feature required by the pipeline."""

    properties = feature.get("properties")
    geometry = feature.get("geometry")
    if not isinstance(properties, Mapping) or not isinstance(geometry, Mapping):
        raise SatelliteCatalogError("ASF feature must contain properties and geometry objects")
    product_id = properties.get("sceneName")
    burst_id = properties.get("operaBurstID")
    if not isinstance(product_id, str) or not product_id:
        raise SatelliteCatalogError("ASF sceneName is missing")
    if not isinstance(burst_id, str) or not burst_id:
        raise SatelliteCatalogError(f"ASF operaBurstID is missing for {product_id}")
    assets = _asset_table(properties)
    missing_assets = sorted({"vv", "vh", "mask"} - assets.keys())
    if missing_assets:
        raise SatelliteCatalogError(
            f"ASF scene {product_id} is missing required assets: {', '.join(missing_assets)}"
        )
    footprint = shape(geometry)
    if footprint.is_empty or not footprint.is_valid:
        raise SatelliteCatalogError(f"ASF scene {product_id} has an invalid footprint")
    try:
        relative_orbit = int(properties["pathNumber"])
    except (KeyError, TypeError, ValueError) as exc:
        raise SatelliteCatalogError(f"ASF pathNumber is invalid for {product_id}") from exc
    raw_polarizations = properties.get("polarization") or []
    if not isinstance(raw_polarizations, Sequence) or isinstance(raw_polarizations, str):
        raise SatelliteCatalogError(f"ASF polarization is invalid for {product_id}")
    acquired_at = _parse_datetime(properties.get("startTime"), field="startTime")
    assert acquired_at is not None
    return SarScene(
        product_id=product_id,
        acquired_at=acquired_at,
        stopped_at=_parse_datetime(properties.get("stopTime"), field="stopTime", required=False),
        platform=str(properties.get("platform") or "Sentinel-1"),
        sensor=str(properties.get("sensor") or "C-SAR"),
        relative_orbit=relative_orbit,
        flight_direction=str(properties.get("flightDirection") or "UNKNOWN").upper(),
        burst_id=burst_id,
        polarizations=tuple(sorted(str(item).upper() for item in raw_polarizations)),
        product_version=str(properties.get("productVersion") or "unknown"),
        footprint=footprint,
        assets=assets,
        raw_properties=dict(properties),
    )


def parse_asf_feature_collection(payload: Mapping[str, Any]) -> list[SarScene]:
    features = payload.get("features")
    if not isinstance(features, list):
        raise SatelliteCatalogError("ASF response does not contain a features array")
    return [parse_asf_feature(item) for item in features if isinstance(item, Mapping)]


def build_search_url(
    *,
    geometry_wkt: str,
    starts_at: datetime,
    ends_at: datetime,
    max_results: int = 500,
) -> str:
    if starts_at.tzinfo is None or ends_at.tzinfo is None:
        raise SatelliteCatalogError("catalogue search timestamps must be timezone-aware")
    if starts_at >= ends_at:
        raise SatelliteCatalogError("catalogue search start must precede end")
    if not geometry_wkt.strip():
        raise SatelliteCatalogError("catalogue search geometry must not be empty")
    try:
        geometry = load_wkt(geometry_wkt)
    except Exception as exc:
        raise SatelliteCatalogError("catalogue search geometry is not valid WKT") from exc
    if geometry.is_empty or not geometry.is_valid:
        raise SatelliteCatalogError("catalogue search geometry must be non-empty and valid")
    # District boundaries can contain tens of thousands of vertices.  Sending that
    # complete WKT in a GET query exceeds common request-line limits (and ASF returns
    # HTTP 414).  The catalogue query is deliberately a coarse discovery filter;
    # exact AOI clipping and coverage validation happen during raster processing.
    search_geometry = geometry.envelope
    query = urlencode(
        {
            "dataset": "OPERA-S1",
            "intersectsWith": search_geometry.wkt,
            "start": starts_at.astimezone(UTC).isoformat().replace("+00:00", "Z"),
            "end": ends_at.astimezone(UTC).isoformat().replace("+00:00", "Z"),
            "maxResults": max_results,
            "output": "geojson",
        }
    )
    return f"{ASF_SEARCH_URL}?{query}"


def search_opera_s1(
    *,
    geometry_wkt: str,
    starts_at: datetime,
    ends_at: datetime,
    timeout_seconds: int = 60,
    fetch: Callable[[str, int], bytes] | None = None,
) -> tuple[list[SarScene], dict[str, Any], str]:
    """Search public ASF metadata without requiring Earthdata credentials."""

    url = build_search_url(
        geometry_wkt=geometry_wkt,
        starts_at=starts_at,
        ends_at=ends_at,
    )

    def default_fetch(target: str, timeout: int) -> bytes:
        request = Request(target, headers={"Accept": "application/geo+json"})
        with urlopen(request, timeout=timeout) as response:
            return response.read()

    try:
        payload = json.loads((fetch or default_fetch)(url, timeout_seconds))
    except (OSError, json.JSONDecodeError) as exc:
        raise SatelliteCatalogError(f"Unable to read the ASF catalogue: {exc}") from exc
    if not isinstance(payload, dict):
        raise SatelliteCatalogError("ASF catalogue response must be a JSON object")
    return parse_asf_feature_collection(payload), payload, url


def select_scene_pairs(
    scenes: Sequence[SarScene],
    *,
    before_start: datetime,
    before_end: datetime,
    after_start: datetime,
    after_end: datetime,
) -> list[SarScenePair]:
    """Choose the nearest compatible before/after scene for each OPERA burst."""

    if not (before_start < before_end <= after_start < after_end):
        raise SatelliteCatalogError("before/after windows must be ordered and non-overlapping")
    before_by_burst: dict[str, list[SarScene]] = {}
    after_by_burst: dict[str, list[SarScene]] = {}
    for scene in scenes:
        if not {"VV", "VH"}.issubset(scene.polarizations):
            continue
        if before_start <= scene.acquired_at <= before_end:
            before_by_burst.setdefault(scene.burst_id, []).append(scene)
        if after_start <= scene.acquired_at <= after_end:
            after_by_burst.setdefault(scene.burst_id, []).append(scene)

    pairs: list[SarScenePair] = []
    for burst_id in sorted(before_by_burst.keys() & after_by_burst.keys()):
        before = max(before_by_burst[burst_id], key=lambda item: item.acquired_at)
        compatible_after = [
            item
            for item in after_by_burst[burst_id]
            if item.relative_orbit == before.relative_orbit
            and item.flight_direction == before.flight_direction
        ]
        if not compatible_after:
            continue
        after = min(compatible_after, key=lambda item: item.acquired_at)
        pairs.append(SarScenePair(burst_id=burst_id, before=before, after=after))
    return pairs
