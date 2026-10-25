"""Idempotently synchronize the attributed Assam development bootstrap."""

from __future__ import annotations

import argparse
import asyncio
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from geoalchemy2.shape import from_shape
from jaldrishti.ingestion import load_assam_bootstrap
from jaldrishti.persistence.models import (
    District,
    Facility,
    Region,
    River,
    RoadSegment,
    Settlement,
)
from shapely.geometry import shape
from sqlalchemy import delete, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine

from jaldrishti_api.config import get_settings
from jaldrishti_api.logging import configure_logging

logger = logging.getLogger(__name__)


def _base_values(feature: dict[str, Any], *, checked_at: datetime) -> dict[str, Any]:
    properties = feature["properties"]
    return {
        "id": properties["id"],
        "code": properties.get("code"),
        "name": properties["name"],
        "geometry": from_shape(shape(feature["geometry"]), srid=4326),
        "metadata": properties.get("metadata", {}),
        "source": properties["source"],
        "source_record_id": properties["source_record_id"],
        "observed_at": None,
        "published_at": None,
        "ingested_at": checked_at,
        "last_checked_at": checked_at,
        "source_url": properties["source_url"],
        "source_version": properties["source_version"],
        "quality": properties["quality"],
    }


async def _upsert(
    connection: AsyncConnection,
    table,
    rows: list[dict[str, Any]],
    *,
    batch_size: int = 250,
) -> None:
    for offset in range(0, len(rows), batch_size):
        statement = insert(table).values(rows[offset : offset + batch_size])
        updates = {
            column.name: statement.excluded[column.name]
            for column in table.columns
            if column.name != "id"
        }
        await connection.execute(
            statement.on_conflict_do_update(index_elements=["id"], set_=updates)
        )


async def _prune_snapshot(
    connection: AsyncConnection,
    table,
    rows: list[dict[str, Any]],
    *,
    region_id: str,
) -> int:
    """Remove stale records from the same regional source snapshot."""

    record_ids = sorted({str(row["id"]) for row in rows})
    sources = sorted({str(row["source"]) for row in rows})
    if not record_ids or not sources:
        return 0
    result = await connection.execute(
        delete(table).where(
            table.c.region_id == region_id,
            table.c.source.in_(sources),
            table.c.id.not_in(record_ids),
        )
    )
    return result.rowcount or 0


async def seed_assam(directory: Path) -> dict[str, int]:
    dataset = load_assam_bootstrap(directory)
    settings = get_settings()
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    checked_at = datetime.now(UTC)

    region_rows = [_base_values(feature, checked_at=checked_at) for feature in dataset.regions]
    district_rows = []
    for feature in dataset.districts:
        values = _base_values(feature, checked_at=checked_at)
        values["region_id"] = feature["properties"]["region_id"]
        district_rows.append(values)
    settlement_rows = []
    for feature in dataset.settlements:
        properties = feature["properties"]
        values = _base_values(feature, checked_at=checked_at)
        values.update(
            {
                "region_id": properties["region_id"],
                "district_id": properties.get("district_id"),
                "settlement_type": properties.get("settlement_type"),
                "population": properties.get("population"),
            }
        )
        settlement_rows.append(values)
    river_rows = []
    for feature in dataset.rivers:
        properties = feature["properties"]
        values = _base_values(feature, checked_at=checked_at)
        values.update(
            {
                "region_id": properties["region_id"],
                "river_class": properties.get("river_class"),
            }
        )
        river_rows.append(values)
    facility_rows = []
    for feature in dataset.facilities:
        properties = feature["properties"]
        values = _base_values(feature, checked_at=checked_at)
        values.update(
            {
                "region_id": properties["region_id"],
                "district_id": properties.get("district_id"),
                "category": properties["category"],
                "subcategory": properties.get("subcategory"),
                "importance": None,
            }
        )
        facility_rows.append(values)
    road_rows = []
    for feature in dataset.roads:
        properties = feature["properties"]
        values = _base_values(feature, checked_at=checked_at)
        values.update(
            {
                "region_id": properties["region_id"],
                "road_class": properties["road_class"],
                "surface": properties.get("surface"),
                "bridge": bool(properties.get("bridge", False)),
                "oneway": bool(properties.get("oneway", False)),
                "access": properties.get("access"),
                "length_m": float(properties["length_m"]),
            }
        )
        road_rows.append(values)

    async with engine.begin() as connection:
        await _upsert(connection, Region.__table__, region_rows)
        await _upsert(connection, District.__table__, district_rows)
        await _upsert(connection, Settlement.__table__, settlement_rows)
        await _upsert(connection, River.__table__, river_rows)
        await _upsert(connection, Facility.__table__, facility_rows)
        await _upsert(connection, RoadSegment.__table__, road_rows)
        removed_records = {
            "facilities": await _prune_snapshot(
                connection,
                Facility.__table__,
                facility_rows,
                region_id="assam",
            ),
            "settlements": await _prune_snapshot(
                connection,
                Settlement.__table__,
                settlement_rows,
                region_id="assam",
            ),
            "rivers": await _prune_snapshot(
                connection,
                River.__table__,
                river_rows,
                region_id="assam",
            ),
            "districts": await _prune_snapshot(
                connection,
                District.__table__,
                district_rows,
                region_id="assam",
            ),
            "roads": await _prune_snapshot(
                connection,
                RoadSegment.__table__,
                road_rows,
                region_id="assam",
            ),
        }
        await connection.execute(
            text(
                """
                UPDATE facilities AS facility
                   SET district_id = district.id
                  FROM districts AS district
                 WHERE facility.region_id = 'assam'
                   AND district.region_id = facility.region_id
                   AND ST_Covers(district.geometry, facility.geometry)
                """
            )
        )
        await connection.execute(
            text(
                """
                UPDATE settlements AS settlement
                   SET district_id = district.id
                  FROM districts AS district
                 WHERE settlement.region_id = 'assam'
                   AND district.region_id = settlement.region_id
                   AND ST_Covers(district.geometry, settlement.geometry)
                """
            )
        )
    await engine.dispose()
    counts = {
        "regions": len(region_rows),
        "districts": len(district_rows),
        "settlements": len(settlement_rows),
        "rivers": len(river_rows),
        "facilities": len(facility_rows),
        "roads": len(road_rows),
    }
    logger.info(
        "Assam bootstrap loaded",
        extra={"record_counts": counts, "removed_records": removed_records},
    )
    return counts


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--directory",
        type=Path,
        default=Path("data/bootstrap/assam"),
        help="Directory containing normalized Phase 1 GeoJSON files",
    )
    args = parser.parse_args()
    settings = get_settings()
    configure_logging(level=settings.log_level, service=settings.service_id)
    asyncio.run(seed_assam(args.directory))


if __name__ == "__main__":
    main()
