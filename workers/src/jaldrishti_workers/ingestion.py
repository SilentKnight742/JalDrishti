"""Scheduled ingestion for the degraded NWDP Assam telemetry pilot."""

from __future__ import annotations

import asyncio
import json
import os
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from geoalchemy2.shape import from_shape
from jaldrishti.domain.provenance import ProvenanceQuality
from jaldrishti.ingestion.nwdp import (
    NWDP_DATASET_URL,
    NWDP_DATASTORE_URL,
    NWDP_RESOURCE_ID,
    NWDP_SOURCE,
    normalize_nwdp_payload,
)
from jaldrishti.persistence.models import Station, StationObservation
from shapely.geometry import Point
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import create_async_engine

from jaldrishti_workers.celery_app import celery_app

PACKAGE_URL = (
    "https://nwdp.nwic.gov.in/api/3/action/package_show?id=6273c426-32f9-4fdf-b67f-e4e7a46d8554"
)
DEFAULT_DATABASE_URL = "postgresql+asyncpg://jaldrishti:jaldrishti@postgres:5432/jaldrishti"
DEFAULT_ARCHIVE_DIR = "/var/lib/jaldrishti/raw"


def _fetch_json(url: str, *, timeout_seconds: float = 30.0) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "JalDrishti/0.1 (+local research ingestion)",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
        payload = json.load(response)
    if not isinstance(payload, dict):
        raise ValueError(f"Expected an object response from {url}")
    return payload


def _fetch_datastore_pages(
    *, page_size: int = 1_000
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    pages: list[dict[str, Any]] = []
    records: list[dict[str, Any]] = []
    offset = 0
    total: int | None = None
    while total is None or offset < total:
        separator = "&" if "?" in NWDP_DATASTORE_URL else "?"
        url = f"{NWDP_DATASTORE_URL}{separator}" + urllib.parse.urlencode(
            {"limit": page_size, "offset": offset}
        )
        page = _fetch_json(url)
        pages.append(page)
        result = page.get("result")
        if not isinstance(result, dict) or not isinstance(result.get("records"), list):
            raise ValueError("NWDP datastore page has no result.records list")
        page_records = result["records"]
        records.extend(item for item in page_records if isinstance(item, dict))
        page_total = result.get("total")
        if not isinstance(page_total, int) or page_total < 0:
            raise ValueError("NWDP datastore page has no valid total")
        total = page_total
        if not page_records:
            break
        offset += len(page_records)

    combined = {
        "success": all(page.get("success") is True for page in pages),
        "result": {
            "resource_id": NWDP_RESOURCE_ID,
            "total": total or len(records),
            "records": records,
        },
    }
    return combined, pages


def _resource_metadata(package_payload: dict[str, Any]) -> tuple[datetime | None, dict[str, Any]]:
    result = package_payload.get("result")
    resources = result.get("resources") if isinstance(result, dict) else None
    if not isinstance(resources, list):
        raise ValueError("NWDP package metadata has no resources list")
    resource = next(
        (
            item
            for item in resources
            if isinstance(item, dict) and item.get("id") == NWDP_RESOURCE_ID
        ),
        None,
    )
    if resource is None:
        raise ValueError("NWDP package no longer exposes the configured resource")
    raw_modified = resource.get("last_modified")
    if not isinstance(raw_modified, str) or not raw_modified.strip():
        return None, resource
    parsed = datetime.fromisoformat(raw_modified.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC), resource


def _archive_raw(
    *,
    fetched_at: datetime,
    datastore_pages: list[dict[str, Any]],
    package_payload: dict[str, Any],
) -> Path:
    archive_root = Path(os.getenv("JALDRISHTI_RAW_ARCHIVE_DIR", DEFAULT_ARCHIVE_DIR)) / "nwdp"
    archive_root.mkdir(parents=True, exist_ok=True)
    target = archive_root / f"{fetched_at.strftime('%Y%m%dT%H%M%S.%fZ')}.json"
    temporary = target.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(
            {
                "fetched_at": fetched_at.isoformat(),
                "dataset_url": NWDP_DATASET_URL,
                "resource_id": NWDP_RESOURCE_ID,
                "package": package_payload,
                "datastore_pages": datastore_pages,
            },
            ensure_ascii=False,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    temporary.replace(target)
    return target


async def _persist_batch(batch, *, published_at: datetime | None) -> dict[str, int]:
    database_url = os.getenv("JALDRISHTI_DATABASE_URL", DEFAULT_DATABASE_URL)
    engine = create_async_engine(database_url, pool_pre_ping=True)
    try:
        station_rows = []
        for station in batch.stations:
            station_rows.append(
                {
                    "id": station.id,
                    "region_id": "assam",
                    "district_id": None,
                    "external_id": None,
                    "name": station.name,
                    "river_name": station.river_name,
                    "basin_name": station.basin_name,
                    "warning_level_m": None,
                    "danger_level_m": None,
                    "datum": None,
                    "time_zone": None,
                    "operational_status": "pilot",
                    "coverage_status": "incomplete_public_feed",
                    "geometry": from_shape(Point(station.longitude, station.latitude), srid=4326),
                    "metadata": {
                        **station.metadata,
                        "district_name": station.district_name,
                        "district_lgd_code": station.district_lgd_code,
                        "resource_id": batch.resource_id,
                        "source_total": batch.source_total,
                        "raw_sha256": batch.raw_sha256,
                        "caveats": list(batch.caveats),
                    },
                    "source": NWDP_SOURCE,
                    "source_record_id": station.source_record_id,
                    "observed_at": None,
                    "published_at": published_at,
                    "ingested_at": batch.fetched_at,
                    "last_checked_at": batch.fetched_at,
                    "source_url": NWDP_DATASET_URL,
                    "source_version": batch.source_version,
                    "quality": ProvenanceQuality.OFFICIAL,
                }
            )
        observation_rows = [
            {
                "id": item.id,
                "station_id": item.station_id,
                "source_observed_at": item.source_observed_at,
                "source_observed_at_local": item.source_observed_at_local,
                "water_level_m": item.water_level_m,
                "unit": "m",
                "quality_flag": "source_time_zone_unverified",
                "metadata": {
                    **item.metadata,
                    "resource_id": batch.resource_id,
                    "raw_sha256": batch.raw_sha256,
                },
                "source": NWDP_SOURCE,
                "source_record_id": item.source_record_id,
                "observed_at": None,
                "published_at": published_at,
                "ingested_at": batch.fetched_at,
                "last_checked_at": batch.fetched_at,
                "source_url": NWDP_DATASET_URL,
                "source_version": batch.source_version,
                "quality": ProvenanceQuality.OFFICIAL,
            }
            for item in batch.observations
        ]

        async with engine.begin() as connection:
            if station_rows:
                statement = insert(Station.__table__).values(station_rows)
                await connection.execute(
                    statement.on_conflict_do_update(
                        index_elements=["id"],
                        set_={
                            column.name: statement.excluded[column.name]
                            for column in Station.__table__.columns
                            if column.name != "id"
                        },
                    )
                )
            if observation_rows:
                statement = insert(StationObservation.__table__).values(observation_rows)
                await connection.execute(
                    statement.on_conflict_do_update(
                        index_elements=["id"],
                        set_={
                            column.name: statement.excluded[column.name]
                            for column in StationObservation.__table__.columns
                            if column.name != "id"
                        },
                    )
                )
            await connection.execute(
                text(
                    """
                    UPDATE stations AS station
                       SET district_id = district.id
                      FROM districts AS district
                     WHERE station.region_id = 'assam'
                       AND district.region_id = station.region_id
                       AND ST_Covers(district.geometry, station.geometry)
                    """
                )
            )
        return {"stations": len(station_rows), "observations": len(observation_rows)}
    finally:
        await engine.dispose()


@celery_app.task(name="jaldrishti.ingestion.nwdp_assam")
def ingest_nwdp_assam() -> dict[str, Any]:
    """Archive, validate, and idempotently persist the public Assam pilot feed."""

    fetched_at = datetime.now(UTC)
    package_payload = _fetch_json(PACKAGE_URL)
    combined_payload, pages = _fetch_datastore_pages()
    archive_path = _archive_raw(
        fetched_at=fetched_at,
        datastore_pages=pages,
        package_payload=package_payload,
    )
    resource_last_modified, _ = _resource_metadata(package_payload)
    batch = normalize_nwdp_payload(
        combined_payload,
        fetched_at=fetched_at,
        resource_last_modified=resource_last_modified,
    )
    counts = asyncio.run(_persist_batch(batch, published_at=resource_last_modified))
    return {
        **counts,
        "source_total": batch.source_total,
        "source_version": batch.source_version,
        "archive": str(archive_path),
        "operational_status": "pilot",
        "coverage_status": "incomplete_public_feed",
    }
