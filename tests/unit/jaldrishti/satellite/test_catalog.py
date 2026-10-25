import json
from datetime import UTC, datetime

import pytest
from jaldrishti.satellite.catalog import (
    SatelliteCatalogError,
    build_search_url,
    parse_asf_feature,
    search_opera_s1,
    select_scene_pairs,
)
from shapely.geometry import Point


def feature(product: str, acquired_at: str, *, burst: str = "T103_1_IW3", orbit: int = 103):
    base = f"https://example.test/{product}"
    return {
        "type": "Feature",
        "geometry": {
            "type": "Polygon",
            "coordinates": [[[92, 26], [93, 26], [93, 27], [92, 27], [92, 26]]],
        },
        "properties": {
            "sceneName": product,
            "startTime": acquired_at,
            "stopTime": acquired_at,
            "pathNumber": orbit,
            "flightDirection": "ASCENDING",
            "operaBurstID": burst,
            "polarization": ["VV", "VH"],
            "productVersion": "1.0",
            "platform": "Sentinel-1A",
            "sensor": "C-SAR",
            "url": f"{base}_VV.tif",
            "additionalUrls": [f"{base}_VH.tif", f"{base}_mask.tif"],
            "bytes": {f"{product}_VV.tif": {"bytes": 12}},
        },
    }


def test_parse_asf_feature_retains_required_provenance_and_assets():
    scene = parse_asf_feature(feature("OPERA_TEST", "2026-09-01T10:00:00Z"))

    assert scene.product_id == "OPERA_TEST"
    assert scene.acquired_at == datetime(2026, 9, 1, 10, tzinfo=UTC)
    assert scene.polarizations == ("VH", "VV")
    assert set(scene.assets) == {"vv", "vh", "mask"}
    assert scene.assets["vv"].expected_bytes == 12


def test_parse_asf_feature_rejects_incomplete_download_contract():
    payload = feature("OPERA_TEST", "2026-09-01T10:00:00Z")
    payload["properties"]["additionalUrls"] = []

    with pytest.raises(SatelliteCatalogError, match="missing required assets"):
        parse_asf_feature(payload)


def test_search_uses_public_catalogue_and_returns_raw_payload():
    payload = {
        "type": "FeatureCollection",
        "features": [feature("OPERA_TEST", "2026-09-01T10:00:00Z")],
    }
    captured = {}

    def fetch(url: str, timeout: int) -> bytes:
        captured.update(url=url, timeout=timeout)
        return json.dumps(payload).encode()

    scenes, raw, url = search_opera_s1(
        geometry_wkt="POLYGON ((92 26, 93 26, 93 27, 92 27, 92 26))",
        starts_at=datetime(2026, 8, 1, tzinfo=UTC),
        ends_at=datetime(2026, 9, 2, tzinfo=UTC),
        fetch=fetch,
    )

    assert len(scenes) == 1
    assert raw == payload
    assert captured["timeout"] == 60
    assert "dataset=OPERA-S1" in url
    assert "output=geojson" in captured["url"]


def test_pairing_selects_nearest_compatible_scenes_per_burst():
    scenes = [
        parse_asf_feature(feature("before-old", "2026-08-20T10:00:00Z")),
        parse_asf_feature(feature("before-near", "2026-08-31T10:00:00Z")),
        parse_asf_feature(feature("after-near", "2026-09-02T10:00:00Z")),
        parse_asf_feature(feature("after-late", "2026-09-08T10:00:00Z")),
        parse_asf_feature(feature("wrong-orbit", "2026-09-01T12:00:00Z", orbit=12)),
    ]

    pairs = select_scene_pairs(
        scenes,
        before_start=datetime(2026, 8, 1, tzinfo=UTC),
        before_end=datetime(2026, 9, 1, tzinfo=UTC),
        after_start=datetime(2026, 9, 1, tzinfo=UTC),
        after_end=datetime(2026, 9, 10, tzinfo=UTC),
    )

    assert [(pair.before.product_id, pair.after.product_id) for pair in pairs] == [
        ("before-near", "after-near")
    ]


def test_search_url_uses_bounding_envelope_to_keep_complex_aoi_request_bounded():
    geometry_wkt = Point(92.5, 26.5).buffer(0.5, quad_segs=512).wkt

    url = build_search_url(
        geometry_wkt=geometry_wkt,
        starts_at=datetime(2026, 8, 1, tzinfo=UTC),
        ends_at=datetime(2026, 9, 2, tzinfo=UTC),
    )

    assert len(url) < 1000
    assert "intersectsWith=POLYGON" in url
