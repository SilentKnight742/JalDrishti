"""Add pilot hydrology stations and observations.

Revision ID: 20260924_0002
Revises: 20260922_0001
Create Date: 2026-09-24
"""

from collections.abc import Sequence

import geoalchemy2
import sqlalchemy as sa
from alembic import op

revision: str = "20260924_0002"
down_revision: str | None = "20260922_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

QUALITY_VALUES = (
    "official",
    "community_data",
    "satellite_observed",
    "model_derived",
    "public_report",
    "operator_entered",
    "simulated",
    "unverified_report",
)


def _provenance_columns() -> list[sa.Column]:
    return [
        sa.Column("source", sa.String(length=128), nullable=False),
        sa.Column("source_record_id", sa.String(length=256), nullable=True),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "ingested_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source_url", sa.String(length=2048), nullable=True),
        sa.Column("source_version", sa.String(length=128), nullable=True),
        sa.Column(
            "quality",
            sa.Enum(
                *QUALITY_VALUES,
                name="provenance_quality",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
            server_default="official",
        ),
    ]


def upgrade() -> None:
    op.create_table(
        "stations",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column(
            "region_id",
            sa.String(length=64),
            sa.ForeignKey("regions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "district_id",
            sa.String(length=64),
            sa.ForeignKey("districts.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("external_id", sa.String(length=128), nullable=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("river_name", sa.String(length=200), nullable=True),
        sa.Column("basin_name", sa.String(length=200), nullable=True),
        sa.Column("warning_level_m", sa.Float(), nullable=True),
        sa.Column("danger_level_m", sa.Float(), nullable=True),
        sa.Column("datum", sa.String(length=160), nullable=True),
        sa.Column("time_zone", sa.String(length=64), nullable=True),
        sa.Column("operational_status", sa.String(length=32), nullable=False),
        sa.Column("coverage_status", sa.String(length=64), nullable=False),
        sa.Column(
            "geometry",
            geoalchemy2.Geometry("POINT", srid=4326, spatial_index=False),
            nullable=False,
        ),
        sa.Column("metadata", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        *_provenance_columns(),
        sa.UniqueConstraint("source", "source_record_id", name="uq_stations_source_record"),
    )
    op.create_index("ix_stations_region_id", "stations", ["region_id"])
    op.create_index("ix_stations_district_id", "stations", ["district_id"])
    op.create_index("ix_stations_name", "stations", ["name"])
    op.create_index("ix_stations_source", "stations", ["source"])
    op.create_index("idx_stations_geometry", "stations", ["geometry"], postgresql_using="gist")

    op.create_table(
        "station_observations",
        sa.Column("id", sa.String(length=96), primary_key=True),
        sa.Column(
            "station_id",
            sa.String(length=64),
            sa.ForeignKey("stations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("source_observed_at", sa.String(length=64), nullable=False),
        sa.Column("source_observed_at_local", sa.DateTime(timezone=False), nullable=False),
        sa.Column("water_level_m", sa.Float(), nullable=False),
        sa.Column("unit", sa.String(length=16), nullable=False),
        sa.Column("quality_flag", sa.String(length=64), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        *_provenance_columns(),
        sa.UniqueConstraint(
            "station_id",
            "source",
            "source_observed_at",
            name="uq_station_observations_station_source_time",
        ),
    )
    op.create_index("ix_station_observations_station_id", "station_observations", ["station_id"])
    op.create_index("ix_station_observations_source", "station_observations", ["source"])
    op.create_index(
        "ix_station_observations_source_observed_at_local",
        "station_observations",
        ["source_observed_at_local"],
    )


def downgrade() -> None:
    op.drop_table("station_observations")
    op.drop_table("stations")
