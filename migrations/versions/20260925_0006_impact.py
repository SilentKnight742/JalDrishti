"""Add reproducible potential-exposure snapshots.

Revision ID: 20260925_0006
Revises: 20260925_0005
Create Date: 2026-09-25
"""

from collections.abc import Sequence

import geoalchemy2
import sqlalchemy as sa
from alembic import op

revision: str = "20260925_0006"
down_revision: str | None = "20260925_0005"
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
            server_default="model_derived",
        ),
    ]


def upgrade() -> None:
    op.create_table(
        "impact_snapshots",
        sa.Column("id", sa.String(length=96), primary_key=True),
        sa.Column(
            "event_id",
            sa.String(length=96),
            sa.ForeignKey("flood_events.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "flood_extent_id",
            sa.String(length=96),
            sa.ForeignKey("flood_extents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("calculated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("algorithm", sa.String(length=160), nullable=False),
        sa.Column("algorithm_version", sa.String(length=64), nullable=False),
        sa.Column("inundated_area_km2", sa.Float(), nullable=False),
        sa.Column("settlement_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("facility_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("population_potentially_exposed", sa.BigInteger(), nullable=True),
        sa.Column("population_record_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("road_overlap_km", sa.Float(), nullable=True),
        sa.Column("building_count", sa.Integer(), nullable=True),
        sa.Column("coverage", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("metadata", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.UniqueConstraint("flood_extent_id", name="uq_impact_snapshots_flood_extent_id"),
    )
    for column in ("event_id", "flood_extent_id", "calculated_at"):
        op.create_index(f"ix_impact_snapshots_{column}", "impact_snapshots", [column])

    op.create_table(
        "potential_exposures",
        sa.Column("id", sa.String(length=96), primary_key=True),
        sa.Column(
            "snapshot_id",
            sa.String(length=96),
            sa.ForeignKey("impact_snapshots.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "event_id",
            sa.String(length=96),
            sa.ForeignKey("flood_events.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "flood_extent_id",
            sa.String(length=96),
            sa.ForeignKey("flood_extents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("asset_type", sa.String(length=64), nullable=False),
        sa.Column("asset_id", sa.String(length=96), nullable=False),
        sa.Column("name", sa.String(length=240), nullable=False),
        sa.Column("metric_type", sa.String(length=64), nullable=False),
        sa.Column("metric_value", sa.Float(), nullable=False),
        sa.Column("unit", sa.String(length=32), nullable=False),
        sa.Column(
            "geometry",
            geoalchemy2.Geometry("GEOMETRY", srid=4326, spatial_index=False),
            nullable=False,
        ),
        sa.Column("metadata", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        *_provenance_columns(),
        sa.UniqueConstraint(
            "snapshot_id",
            "asset_type",
            "asset_id",
            name="uq_exposures_snapshot_asset",
        ),
    )
    for column in (
        "snapshot_id",
        "event_id",
        "flood_extent_id",
        "asset_type",
        "source",
    ):
        op.create_index(f"ix_potential_exposures_{column}", "potential_exposures", [column])
    op.create_index(
        "idx_potential_exposures_geometry",
        "potential_exposures",
        ["geometry"],
        postgresql_using="gist",
    )


def downgrade() -> None:
    op.drop_table("potential_exposures")
    op.drop_table("impact_snapshots")
