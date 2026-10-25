"""Add event-scoped satellite jobs, selected scenes, and flood extents.

Revision ID: 20260925_0005
Revises: 20260924_0004
Create Date: 2026-09-25
"""

from collections.abc import Sequence

import geoalchemy2
import sqlalchemy as sa
from alembic import op

revision: str = "20260925_0005"
down_revision: str | None = "20260924_0004"
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
            server_default="satellite_observed",
        ),
    ]


def upgrade() -> None:
    op.create_table(
        "satellite_jobs",
        sa.Column("id", sa.String(length=96), primary_key=True),
        sa.Column(
            "event_id",
            sa.String(length=96),
            sa.ForeignKey("flood_events.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("request_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("before_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("before_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("after_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("after_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("algorithm", sa.String(length=128), nullable=False),
        sa.Column("parameters", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("catalog_source", sa.String(length=160), nullable=False),
        sa.Column("catalog_url", sa.String(length=2048), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.UniqueConstraint(
            "event_id",
            "request_fingerprint",
            name="uq_satellite_jobs_event_request",
        ),
    )
    for column in ("event_id", "status", "requested_at"):
        op.create_index(f"ix_satellite_jobs_{column}", "satellite_jobs", [column])

    op.create_table(
        "satellite_scenes",
        sa.Column("id", sa.String(length=96), primary_key=True),
        sa.Column(
            "job_id",
            sa.String(length=96),
            sa.ForeignKey("satellite_jobs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "event_id",
            sa.String(length=96),
            sa.ForeignKey("flood_events.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("product_id", sa.String(length=256), nullable=False),
        sa.Column("acquired_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("stopped_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("platform", sa.String(length=64), nullable=False),
        sa.Column("sensor", sa.String(length=64), nullable=False),
        sa.Column("relative_orbit", sa.Integer(), nullable=False),
        sa.Column("flight_direction", sa.String(length=16), nullable=False),
        sa.Column("burst_id", sa.String(length=96), nullable=False),
        sa.Column("polarizations", sa.JSON(), nullable=False),
        sa.Column("product_version", sa.String(length=64), nullable=False),
        sa.Column(
            "geometry",
            geoalchemy2.Geometry("GEOMETRY", srid=4326, spatial_index=False),
            nullable=False,
        ),
        sa.Column("assets", sa.JSON(), nullable=False),
        sa.Column("source", sa.String(length=128), nullable=False),
        sa.Column("source_url", sa.String(length=2048), nullable=True),
        sa.Column(
            "catalog_record", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")
        ),
        sa.UniqueConstraint(
            "job_id",
            "role",
            "product_id",
            name="uq_satellite_scenes_job_role_product",
        ),
    )
    for column in ("job_id", "event_id", "role", "product_id", "acquired_at", "burst_id"):
        op.create_index(f"ix_satellite_scenes_{column}", "satellite_scenes", [column])
    op.create_index(
        "idx_satellite_scenes_geometry",
        "satellite_scenes",
        ["geometry"],
        postgresql_using="gist",
    )

    op.create_table(
        "flood_extents",
        sa.Column("id", sa.String(length=96), primary_key=True),
        sa.Column(
            "event_id",
            sa.String(length=96),
            sa.ForeignKey("flood_events.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "job_id",
            sa.String(length=96),
            sa.ForeignKey("satellite_jobs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("acquired_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("algorithm", sa.String(length=160), nullable=False),
        sa.Column("algorithm_version", sa.String(length=64), nullable=False),
        sa.Column("parameters", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("area_km2", sa.Float(), nullable=False),
        sa.Column("high_evidence_area_km2", sa.Float(), nullable=False),
        sa.Column("valid_coverage_fraction", sa.Float(), nullable=False),
        sa.Column("resolution_m", sa.Float(), nullable=False),
        sa.Column("analysis_crs", sa.String(length=64), nullable=False),
        sa.Column("raster_uri", sa.String(length=2048), nullable=False),
        sa.Column(
            "geometry",
            geoalchemy2.Geometry("MULTIPOLYGON", srid=4326, spatial_index=False),
            nullable=False,
        ),
        sa.Column("metadata", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        *_provenance_columns(),
        sa.UniqueConstraint("job_id", name="uq_flood_extents_job"),
    )
    for column in ("event_id", "job_id", "acquired_at", "source"):
        op.create_index(f"ix_flood_extents_{column}", "flood_extents", [column])
    op.create_index(
        "idx_flood_extents_geometry",
        "flood_extents",
        ["geometry"],
        postgresql_using="gist",
    )


def downgrade() -> None:
    op.drop_table("flood_extents")
    op.drop_table("satellite_scenes")
    op.drop_table("satellite_jobs")
