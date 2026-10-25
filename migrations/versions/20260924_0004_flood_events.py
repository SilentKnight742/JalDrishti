"""Add flood events, evidence, affected districts, and timeline.

Revision ID: 20260924_0004
Revises: 20260924_0003
Create Date: 2026-09-24
"""

from collections.abc import Sequence

import geoalchemy2
import sqlalchemy as sa
from alembic import op

revision: str = "20260924_0004"
down_revision: str | None = "20260924_0003"
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
        "flood_events",
        sa.Column("id", sa.String(length=96), primary_key=True),
        sa.Column(
            "region_id",
            sa.String(length=64),
            sa.ForeignKey("regions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "primary_district_id",
            sa.String(length=64),
            sa.ForeignKey("districts.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("name", sa.String(length=240), nullable=False),
        sa.Column(
            "geometry",
            geoalchemy2.Geometry("MULTIPOLYGON", srid=4326, spatial_index=False),
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("state_changed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("trigger_summary", sa.Text(), nullable=False),
        sa.Column("rainfall_status", sa.String(length=64), nullable=False),
        sa.Column("river_status", sa.String(length=64), nullable=False),
        sa.Column("warning_status", sa.String(length=64), nullable=False),
        sa.Column("satellite_status", sa.String(length=64), nullable=False),
        sa.Column("created_by", sa.String(length=32), nullable=False),
        sa.Column("rule_version", sa.String(length=128), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
    )
    for column in (
        "region_id",
        "primary_district_id",
        "name",
        "started_at",
        "last_updated_at",
        "ended_at",
        "state",
    ):
        op.create_index(f"ix_flood_events_{column}", "flood_events", [column])
    op.create_index(
        "idx_flood_events_geometry",
        "flood_events",
        ["geometry"],
        postgresql_using="gist",
    )

    op.create_table(
        "flood_event_districts",
        sa.Column(
            "event_id",
            sa.String(length=96),
            sa.ForeignKey("flood_events.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "district_id",
            sa.String(length=64),
            sa.ForeignKey("districts.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("role", sa.String(length=32), nullable=False),
    )
    op.create_index(
        "ix_flood_event_districts_district_id",
        "flood_event_districts",
        ["district_id"],
    )

    op.create_table(
        "event_evidence",
        sa.Column("id", sa.String(length=96), primary_key=True),
        sa.Column(
            "event_id",
            sa.String(length=96),
            sa.ForeignKey("flood_events.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("evidence_type", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=240), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column(
            "geometry",
            geoalchemy2.Geometry("GEOMETRY", srid=4326, spatial_index=False),
            nullable=True,
        ),
        sa.Column("metadata", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        *_provenance_columns(),
        sa.UniqueConstraint(
            "event_id",
            "source",
            "source_record_id",
            name="uq_event_evidence_event_source_record",
        ),
    )
    for column in ("event_id", "evidence_type", "source"):
        op.create_index(f"ix_event_evidence_{column}", "event_evidence", [column])
    op.create_index(
        "idx_event_evidence_geometry",
        "event_evidence",
        ["geometry"],
        postgresql_using="gist",
    )

    op.create_table(
        "event_timeline_entries",
        sa.Column("id", sa.String(length=96), primary_key=True),
        sa.Column(
            "event_id",
            sa.String(length=96),
            sa.ForeignKey("flood_events.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "evidence_id",
            sa.String(length=96),
            sa.ForeignKey("event_evidence.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("category", sa.String(length=64), nullable=False),
        sa.Column("state_from", sa.String(length=32), nullable=True),
        sa.Column("state_to", sa.String(length=32), nullable=True),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
    )
    for column in ("event_id", "evidence_id", "occurred_at", "category"):
        op.create_index(
            f"ix_event_timeline_entries_{column}",
            "event_timeline_entries",
            [column],
        )


def downgrade() -> None:
    op.drop_table("event_timeline_entries")
    op.drop_table("event_evidence")
    op.drop_table("flood_event_districts")
    op.drop_table("flood_events")
