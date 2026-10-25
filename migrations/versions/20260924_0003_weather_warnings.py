"""Add weather guidance and official district warnings.

Revision ID: 20260924_0003
Revises: 20260924_0002
Create Date: 2026-09-24
"""

from collections.abc import Sequence

import geoalchemy2
import sqlalchemy as sa
from alembic import op

revision: str = "20260924_0003"
down_revision: str | None = "20260924_0002"
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
        "weather_observations",
        sa.Column("id", sa.String(length=96), primary_key=True),
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
        sa.Column("observation_type", sa.String(length=64), nullable=False),
        sa.Column("period_hours", sa.Integer(), nullable=False),
        sa.Column("precipitation_mm", sa.Float(), nullable=True),
        sa.Column(
            "geometry",
            geoalchemy2.Geometry("POINT", srid=4326, spatial_index=False),
            nullable=False,
        ),
        sa.Column("metadata", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        *_provenance_columns(default_quality="official"),
        sa.UniqueConstraint(
            "source", "source_record_id", name="uq_weather_observations_source_record"
        ),
    )
    for column in ("region_id", "district_id", "observation_type", "source"):
        op.create_index(f"ix_weather_observations_{column}", "weather_observations", [column])
    op.create_index(
        "idx_weather_observations_geometry",
        "weather_observations",
        ["geometry"],
        postgresql_using="gist",
    )

    op.create_table(
        "weather_forecasts",
        sa.Column("id", sa.String(length=96), primary_key=True),
        sa.Column(
            "region_id",
            sa.String(length=64),
            sa.ForeignKey("regions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "district_id",
            sa.String(length=64),
            sa.ForeignKey("districts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("model", sa.String(length=96), nullable=False),
        sa.Column("valid_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lead_hours", sa.Integer(), nullable=False),
        sa.Column("precipitation_mm", sa.Float(), nullable=False),
        sa.Column("precipitation_probability_pct", sa.Float(), nullable=True),
        sa.Column(
            "geometry",
            geoalchemy2.Geometry("POINT", srid=4326, spatial_index=False),
            nullable=False,
        ),
        sa.Column("metadata", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        *_provenance_columns(default_quality="model_derived"),
        sa.UniqueConstraint(
            "district_id", "model", "valid_at", name="uq_weather_forecasts_district_model_valid"
        ),
    )
    for column in ("region_id", "district_id", "model", "valid_at", "source"):
        op.create_index(f"ix_weather_forecasts_{column}", "weather_forecasts", [column])
    op.create_index(
        "idx_weather_forecasts_geometry", "weather_forecasts", ["geometry"], postgresql_using="gist"
    )

    op.create_table(
        "official_warnings",
        sa.Column("id", sa.String(length=96), primary_key=True),
        sa.Column(
            "region_id",
            sa.String(length=64),
            sa.ForeignKey("regions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "district_id",
            sa.String(length=64),
            sa.ForeignKey("districts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("external_id", sa.String(length=96), nullable=False),
        sa.Column("issue_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_date", sa.Date(), nullable=False),
        sa.Column("day_index", sa.Integer(), nullable=False),
        sa.Column("severity", sa.String(length=32), nullable=False),
        sa.Column("color_code", sa.Integer(), nullable=False),
        sa.Column("warning_codes", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
        sa.Column("hazards", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
        sa.Column("description", sa.String(length=2000), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        *_provenance_columns(default_quality="official"),
        sa.UniqueConstraint(
            "source", "external_id", "valid_date", name="uq_official_warnings_source_valid"
        ),
    )
    for column in (
        "region_id",
        "district_id",
        "issue_at",
        "valid_date",
        "day_index",
        "severity",
        "source",
    ):
        op.create_index(f"ix_official_warnings_{column}", "official_warnings", [column])


def downgrade() -> None:
    op.drop_table("official_warnings")
    op.drop_table("weather_forecasts")
    op.drop_table("weather_observations")
