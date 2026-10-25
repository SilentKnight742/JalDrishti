"""Scheduled Phase 3 weather guidance and official-warning ingestion."""

from __future__ import annotations

import asyncio
import json
import os
import urllib.parse
import urllib.request
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from geoalchemy2.shape import from_shape
from jaldrishti.domain.provenance import ProvenanceQuality
from jaldrishti.ingestion.imd import (
    IMD_WARNING_PAGE_URL,
    IMD_WARNING_SOURCE,
    IMD_WARNING_WFS_URL,
    normalize_imd_warning_payload,
)
from jaldrishti.ingestion.open_meteo import (
    OPEN_METEO_FORECAST_URL,
    OPEN_METEO_MODEL,
    OPEN_METEO_SOURCE,
    DistrictForecastLocation,
    normalize_open_meteo_payload,
)
from jaldrishti.persistence.models import District, OfficialWarning, WeatherForecast
from shapely.geometry import Point
from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import create_async_engine

from jaldrishti_workers.celery_app import celery_app

DEFAULT_DATABASE_URL = "postgresql+asyncpg://jaldrishti:jaldrishti@postgres:5432/jaldrishti"
DEFAULT_ARCHIVE_DIR = "/var/lib/jaldrishti/raw"
FORECAST_UPSERT_BATCH_SIZE = 1_000


def _fetch_json(
    base_url: str,
    *,
    parameters: dict[str, str],
    timeout_seconds: float = 45.0,
) -> dict[str, Any] | list[dict[str, Any]]:
    url = f"{base_url}?{urllib.parse.urlencode(parameters)}"
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "JalDrishti/0.1 (+research weather ingestion)",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
        payload = json.load(response)
    if not isinstance(payload, (dict, list)):
        raise ValueError(f"Expected a JSON object or array from {base_url}")
    return payload


def _archive_raw(*, source: str, fetched_at: datetime, payload: Any) -> Path:
    archive_root = Path(os.getenv("JALDRISHTI_RAW_ARCHIVE_DIR", DEFAULT_ARCHIVE_DIR)) / source
    archive_root.mkdir(parents=True, exist_ok=True)
    target = archive_root / f"{fetched_at.strftime('%Y%m%dT%H%M%S.%fZ')}.json"
    temporary = target.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(
            {"fetched_at": fetched_at.isoformat(), "payload": payload},
            ensure_ascii=False,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    temporary.replace(target)
    return target


async def _persist_warnings(batch) -> int:
    engine = create_async_engine(
        os.getenv("JALDRISHTI_DATABASE_URL", DEFAULT_DATABASE_URL),
        pool_pre_ping=True,
    )
    rows = [
        {
            "id": item.id,
            "region_id": "assam",
            "district_id": item.district_id,
            "external_id": item.external_id,
            "issue_at": item.issue_at,
            "valid_date": item.valid_date,
            "day_index": item.day_index,
            "severity": item.severity,
            "color_code": item.color_code,
            "warning_codes": list(item.warning_codes),
            "hazards": list(item.hazards),
            "description": item.description,
            "metadata": {
                **item.metadata,
                "source_district_name": item.source_district_name,
                "mapped_district_name": item.district_name,
                "mapped_districts": batch.mapped_districts,
                "expected_districts": batch.expected_districts,
            },
            "source": IMD_WARNING_SOURCE,
            "source_record_id": item.source_record_id,
            "observed_at": item.issue_at,
            "published_at": item.updated_at,
            "ingested_at": batch.fetched_at,
            "last_checked_at": batch.fetched_at,
            "source_url": IMD_WARNING_PAGE_URL,
            "source_version": batch.source_version,
            "quality": ProvenanceQuality.OFFICIAL,
        }
        for item in batch.warnings
    ]
    try:
        async with engine.begin() as connection:
            statement = insert(OfficialWarning.__table__).values(rows)
            await connection.execute(
                statement.on_conflict_do_update(
                    index_elements=["id"],
                    set_={
                        column.name: statement.excluded[column.name]
                        for column in OfficialWarning.__table__.columns
                        if column.name != "id"
                    },
                )
            )
        return len(rows)
    finally:
        await engine.dispose()


async def _district_locations() -> list[DistrictForecastLocation]:
    engine = create_async_engine(
        os.getenv("JALDRISHTI_DATABASE_URL", DEFAULT_DATABASE_URL),
        pool_pre_ping=True,
    )
    try:
        representative_point = func.ST_PointOnSurface(District.geometry)
        statement = (
            select(
                District.id,
                District.name,
                func.ST_X(representative_point),
                func.ST_Y(representative_point),
            )
            .where(District.region_id == "assam")
            .order_by(District.name)
        )
        async with engine.connect() as connection:
            rows = (await connection.execute(statement)).all()
        if not rows:
            raise ValueError("No Assam districts are available for weather forecast ingestion")
        return [
            DistrictForecastLocation(
                district_id=row[0],
                district_name=row[1],
                longitude=float(row[2]),
                latitude=float(row[3]),
            )
            for row in rows
        ]
    finally:
        await engine.dispose()


async def _persist_forecasts(batch) -> int:
    engine = create_async_engine(
        os.getenv("JALDRISHTI_DATABASE_URL", DEFAULT_DATABASE_URL),
        pool_pre_ping=True,
    )
    rows = [
        {
            "id": item.id,
            "region_id": "assam",
            "district_id": item.district_id,
            "model": item.model,
            "valid_at": item.valid_at,
            "lead_hours": item.lead_hours,
            "precipitation_mm": item.precipitation_mm,
            "precipitation_probability_pct": item.precipitation_probability_pct,
            "geometry": from_shape(Point(item.longitude, item.latitude), srid=4326),
            "metadata": {**item.metadata, "district_name": item.district_name},
            "source": OPEN_METEO_SOURCE,
            "source_record_id": item.source_record_id,
            "observed_at": None,
            "published_at": None,
            "ingested_at": batch.fetched_at,
            "last_checked_at": batch.fetched_at,
            "source_url": "https://open-meteo.com/en/docs",
            "source_version": batch.source_version,
            "quality": ProvenanceQuality.MODEL_DERIVED,
        }
        for item in batch.forecasts
    ]
    try:
        async with engine.begin() as connection:
            # asyncpg caps a single statement at 32,767 bind parameters. A
            # statewide 72-hour run has 2,520 rows and 19 columns, so persist
            # bounded batches within one transaction.
            for start in range(0, len(rows), FORECAST_UPSERT_BATCH_SIZE):
                statement = insert(WeatherForecast.__table__).values(
                    rows[start : start + FORECAST_UPSERT_BATCH_SIZE]
                )
                await connection.execute(
                    statement.on_conflict_do_update(
                        index_elements=["id"],
                        set_={
                            column.name: statement.excluded[column.name]
                            for column in WeatherForecast.__table__.columns
                            if column.name != "id"
                        },
                    )
                )
            await connection.execute(
                delete(WeatherForecast).where(
                    WeatherForecast.valid_at < batch.fetched_at - timedelta(hours=48)
                )
            )
        return len(rows)
    finally:
        await engine.dispose()


@celery_app.task(name="jaldrishti.ingestion.imd_warnings_assam")
def ingest_imd_warnings_assam() -> dict[str, Any]:
    fetched_at = datetime.now(UTC)
    payload = _fetch_json(
        IMD_WARNING_WFS_URL,
        parameters={
            "service": "WFS",
            "version": "1.1.0",
            "request": "GetFeature",
            "typename": "imd:district_warnings_india",
            "outputFormat": "application/json",
            "CQL_FILTER": "BBOX(geom,89.5,24.0,96.5,28.5,'EPSG:4326')",
            "propertyName": (
                "Obj_id,Date,UTC,District,Day_1,Day_2,Day_3,Day_4,Day_5,"
                "Day1_Color,Day2_Color,Day3_Color,Day4_Color,Day5_Color,"
                "Day1_text,Day2_text,Day3_text,Day4_text,Day5_text,updated_at"
            ),
        },
    )
    if not isinstance(payload, dict):
        raise ValueError("IMD WFS response must be an object")
    archive_path = _archive_raw(source="imd-warnings", fetched_at=fetched_at, payload=payload)
    batch = normalize_imd_warning_payload(payload, fetched_at=fetched_at)
    count = asyncio.run(_persist_warnings(batch))
    celery_app.send_task("jaldrishti.events.evaluate_assam")
    return {
        "warnings": count,
        "mapped_districts": batch.mapped_districts,
        "expected_districts": batch.expected_districts,
        "source_version": batch.source_version,
        "archive": str(archive_path),
    }


@celery_app.task(name="jaldrishti.ingestion.rainfall_forecast_assam")
def ingest_rainfall_forecast_assam() -> dict[str, Any]:
    fetched_at = datetime.now(UTC)
    locations = asyncio.run(_district_locations())
    payload = _fetch_json(
        OPEN_METEO_FORECAST_URL,
        parameters={
            "latitude": ",".join(str(item.latitude) for item in locations),
            "longitude": ",".join(str(item.longitude) for item in locations),
            "hourly": "precipitation,precipitation_probability",
            "models": OPEN_METEO_MODEL,
            "forecast_hours": "72",
            "timezone": "UTC",
        },
    )
    archive_path = _archive_raw(
        source="open-meteo-rainfall",
        fetched_at=fetched_at,
        payload=payload,
    )
    batch = normalize_open_meteo_payload(
        payload,
        locations=locations,
        fetched_at=fetched_at,
    )
    count = asyncio.run(_persist_forecasts(batch))
    celery_app.send_task("jaldrishti.events.evaluate_assam")
    return {
        "districts": len(locations),
        "forecasts": count,
        "forecast_hours": 72,
        "model": OPEN_METEO_MODEL,
        "source_version": batch.source_version,
        "archive": str(archive_path),
        "quality": ProvenanceQuality.MODEL_DERIVED.value,
    }
