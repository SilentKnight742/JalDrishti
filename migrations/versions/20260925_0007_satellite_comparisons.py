"""Add traceable external flood-product comparisons.

Revision ID: 20260925_0007
Revises: 20260925_0006
Create Date: 2026-09-25
"""

from collections.abc import Sequence

import geoalchemy2
import sqlalchemy as sa
from alembic import op

revision: str = "20260925_0007"
down_revision: str | None = "20260925_0006"
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
        "satellite_comparisons",
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
        sa.Column("reference_name", sa.String(length=240), nullable=False),
        sa.Column("reference_acquired_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("compared_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("analysis_crs", sa.String(length=64), nullable=False),
        sa.Column("iou", sa.Float(), nullable=False),
        sa.Column("dice_f1", sa.Float(), nullable=False),
        sa.Column("precision", sa.Float(), nullable=False),
        sa.Column("recall", sa.Float(), nullable=False),
        sa.Column("detected_area_km2", sa.Float(), nullable=False),
        sa.Column("reference_area_km2", sa.Float(), nullable=False),
        sa.Column("overlap_area_km2", sa.Float(), nullable=False),
        sa.Column("union_area_km2", sa.Float(), nullable=False),
        sa.Column("area_difference_km2", sa.Float(), nullable=False),
        sa.Column("temporal_offset_hours", sa.Float(), nullable=True),
        sa.Column("caveat", sa.Text(), nullable=False),
        sa.Column(
            "geometry",
            geoalchemy2.Geometry("MULTIPOLYGON", srid=4326, spatial_index=False),
            nullable=False,
        ),
        sa.Column("metadata", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        *_provenance_columns(),
        sa.UniqueConstraint(
            "flood_extent_id",
            "source",
            "source_record_id",
            name="uq_satellite_comparisons_extent_reference",
        ),
    )
    for column in ("event_id", "flood_extent_id", "compared_at", "source"):
        op.create_index(f"ix_satellite_comparisons_{column}", "satellite_comparisons", [column])
    op.create_index(
        "idx_satellite_comparisons_geometry",
        "satellite_comparisons",
        ["geometry"],
        postgresql_using="gist",
    )


def downgrade() -> None:
    op.drop_table("satellite_comparisons")
