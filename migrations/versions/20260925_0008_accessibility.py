"""Add road network and accessibility screening tables.

Revision ID: 20260925_0008
Revises: 20260925_0007
Create Date: 2026-09-25
"""

from collections.abc import Sequence

import geoalchemy2
import sqlalchemy as sa
from alembic import op

revision: str = "20260925_0008"
down_revision: str | None = "20260925_0007"
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


def _provenance_columns(*, default_quality: str) -> list[sa.Column]:
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
            server_default=default_quality,
        ),
    ]


def upgrade() -> None:
    op.create_table(
        "road_segments",
        sa.Column("id", sa.String(length=96), primary_key=True),
        sa.Column(
            "region_id",
            sa.String(length=64),
            sa.ForeignKey("regions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("code", sa.String(length=64), nullable=True),
        sa.Column("name", sa.String(length=240), nullable=False),
        sa.Column("road_class", sa.String(length=64), nullable=False),
        sa.Column("surface", sa.String(length=64), nullable=True),
        sa.Column("bridge", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("oneway", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("access", sa.String(length=64), nullable=True),
        sa.Column("length_m", sa.Float(), nullable=False),
        sa.Column(
            "geometry",
            geoalchemy2.Geometry("MULTILINESTRING", srid=4326, spatial_index=False),
            nullable=False,
        ),
        sa.Column("metadata", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        *_provenance_columns(default_quality="community_data"),
    )
    for column in ("region_id", "name", "road_class", "source"):
        op.create_index(f"ix_road_segments_{column}", "road_segments", [column])
    op.create_index(
        "idx_road_segments_geometry",
        "road_segments",
        ["geometry"],
        postgresql_using="gist",
    )

    op.create_table(
        "accessibility_snapshots",
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
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("road_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("graph_node_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("graph_edge_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "potentially_affected_road_count", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column("potentially_affected_road_km", sa.Float(), nullable=False, server_default="0"),
        sa.Column("assessed_settlement_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "potentially_isolated_settlement_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column("coverage", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("metadata", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.UniqueConstraint("flood_extent_id", name="uq_accessibility_snapshots_flood_extent_id"),
    )
    for column in ("event_id", "flood_extent_id", "calculated_at", "status"):
        op.create_index(f"ix_accessibility_snapshots_{column}", "accessibility_snapshots", [column])

    op.create_table(
        "road_disruptions",
        sa.Column("id", sa.String(length=96), primary_key=True),
        sa.Column(
            "snapshot_id",
            sa.String(length=96),
            sa.ForeignKey("accessibility_snapshots.id", ondelete="CASCADE"),
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
        sa.Column(
            "road_segment_id",
            sa.String(length=96),
            sa.ForeignKey("road_segments.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("name", sa.String(length=240), nullable=False),
        sa.Column("road_class", sa.String(length=64), nullable=False),
        sa.Column("overlap_km", sa.Float(), nullable=False),
        sa.Column(
            "geometry",
            geoalchemy2.Geometry("MULTILINESTRING", srid=4326, spatial_index=False),
            nullable=False,
        ),
        sa.Column("metadata", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        *_provenance_columns(default_quality="model_derived"),
        sa.UniqueConstraint("snapshot_id", "road_segment_id", name="uq_disruptions_snapshot_road"),
    )
    for column in (
        "snapshot_id",
        "event_id",
        "flood_extent_id",
        "road_segment_id",
        "source",
    ):
        op.create_index(f"ix_road_disruptions_{column}", "road_disruptions", [column])
    op.create_index(
        "idx_road_disruptions_geometry",
        "road_disruptions",
        ["geometry"],
        postgresql_using="gist",
    )

    op.create_table(
        "settlement_accessibility",
        sa.Column("id", sa.String(length=96), primary_key=True),
        sa.Column(
            "snapshot_id",
            sa.String(length=96),
            sa.ForeignKey("accessibility_snapshots.id", ondelete="CASCADE"),
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
        sa.Column(
            "settlement_id",
            sa.String(length=64),
            sa.ForeignKey("settlements.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("name", sa.String(length=240), nullable=False),
        sa.Column("snapped_distance_m", sa.Float(), nullable=True),
        sa.Column("major_road_reachable_before", sa.Boolean(), nullable=False),
        sa.Column("major_road_reachable_after", sa.Boolean(), nullable=False),
        sa.Column("hospital_reachable_before", sa.Boolean(), nullable=False),
        sa.Column("hospital_reachable_after", sa.Boolean(), nullable=False),
        sa.Column("nearest_major_road_km", sa.Float(), nullable=True),
        sa.Column("nearest_hospital_km", sa.Float(), nullable=True),
        sa.Column("potentially_isolated", sa.Boolean(), nullable=False),
        sa.Column("assessment_status", sa.String(length=64), nullable=False),
        sa.Column(
            "geometry",
            geoalchemy2.Geometry("POINT", srid=4326, spatial_index=False),
            nullable=False,
        ),
        sa.Column("metadata", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        *_provenance_columns(default_quality="model_derived"),
        sa.UniqueConstraint(
            "snapshot_id", "settlement_id", name="uq_settlement_accessibility_snapshot"
        ),
    )
    for column in (
        "snapshot_id",
        "event_id",
        "flood_extent_id",
        "settlement_id",
        "potentially_isolated",
        "source",
    ):
        op.create_index(
            f"ix_settlement_accessibility_{column}", "settlement_accessibility", [column]
        )
    op.create_index(
        "idx_settlement_accessibility_geometry",
        "settlement_accessibility",
        ["geometry"],
        postgresql_using="gist",
    )


def downgrade() -> None:
    op.drop_table("settlement_accessibility")
    op.drop_table("road_disruptions")
    op.drop_table("accessibility_snapshots")
    op.drop_table("road_segments")
