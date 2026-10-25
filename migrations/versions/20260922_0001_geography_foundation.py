"""Create the PostGIS geography and provenance foundation.

Revision ID: 20260922_0001
Revises: None
Create Date: 2026-09-22
"""

from collections.abc import Sequence

import geoalchemy2
import sqlalchemy as sa
from alembic import op

revision: str = "20260922_0001"
down_revision: str | None = None
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
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")

    op.create_table(
        "regions",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("code", sa.String(length=32), nullable=False, unique=True),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column(
            "geometry",
            geoalchemy2.Geometry("MULTIPOLYGON", srid=4326, spatial_index=False),
            nullable=False,
        ),
        sa.Column("metadata", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        *_provenance_columns(),
    )
    op.create_index("ix_regions_name", "regions", ["name"])
    op.create_index("ix_regions_source", "regions", ["source"])
    op.create_index("idx_regions_geometry", "regions", ["geometry"], postgresql_using="gist")

    op.create_table(
        "districts",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column(
            "region_id",
            sa.String(length=64),
            sa.ForeignKey("regions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column(
            "geometry",
            geoalchemy2.Geometry("MULTIPOLYGON", srid=4326, spatial_index=False),
            nullable=False,
        ),
        sa.Column("metadata", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        *_provenance_columns(),
        sa.UniqueConstraint("region_id", "code", name="uq_districts_region_code"),
    )
    op.create_index("ix_districts_region_id", "districts", ["region_id"])
    op.create_index("ix_districts_name", "districts", ["name"])
    op.create_index("ix_districts_source", "districts", ["source"])
    op.create_index("idx_districts_geometry", "districts", ["geometry"], postgresql_using="gist")

    op.create_table(
        "settlements",
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
        sa.Column("code", sa.String(length=64), nullable=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("settlement_type", sa.String(length=64), nullable=True),
        sa.Column("population", sa.BigInteger(), nullable=True),
        sa.Column(
            "geometry",
            geoalchemy2.Geometry("POINT", srid=4326, spatial_index=False),
            nullable=False,
        ),
        sa.Column("metadata", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        *_provenance_columns(),
        sa.UniqueConstraint("source", "source_record_id", name="uq_settlements_source_record"),
    )
    op.create_index("ix_settlements_region_id", "settlements", ["region_id"])
    op.create_index("ix_settlements_district_id", "settlements", ["district_id"])
    op.create_index("ix_settlements_name", "settlements", ["name"])
    op.create_index("ix_settlements_source", "settlements", ["source"])
    op.create_index(
        "idx_settlements_geometry", "settlements", ["geometry"], postgresql_using="gist"
    )

    op.create_table(
        "rivers",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column(
            "region_id",
            sa.String(length=64),
            sa.ForeignKey("regions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("code", sa.String(length=64), nullable=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("river_class", sa.String(length=64), nullable=True),
        sa.Column(
            "geometry",
            geoalchemy2.Geometry("MULTILINESTRING", srid=4326, spatial_index=False),
            nullable=False,
        ),
        sa.Column("metadata", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        *_provenance_columns(),
        sa.UniqueConstraint("source", "source_record_id", name="uq_rivers_source_record"),
    )
    op.create_index("ix_rivers_region_id", "rivers", ["region_id"])
    op.create_index("ix_rivers_name", "rivers", ["name"])
    op.create_index("ix_rivers_river_class", "rivers", ["river_class"])
    op.create_index("ix_rivers_source", "rivers", ["source"])
    op.create_index("idx_rivers_geometry", "rivers", ["geometry"], postgresql_using="gist")

    op.create_table(
        "facilities",
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
        sa.Column("code", sa.String(length=64), nullable=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("category", sa.String(length=80), nullable=False),
        sa.Column("subcategory", sa.String(length=120), nullable=True),
        sa.Column(
            "geometry",
            geoalchemy2.Geometry("GEOMETRY", srid=4326, spatial_index=False),
            nullable=False,
        ),
        sa.Column("metadata", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("importance", sa.Float(), nullable=True),
        *_provenance_columns(),
        sa.UniqueConstraint("source", "source_record_id", name="uq_facilities_source_record"),
    )
    op.create_index("ix_facilities_region_id", "facilities", ["region_id"])
    op.create_index("ix_facilities_district_id", "facilities", ["district_id"])
    op.create_index("ix_facilities_name", "facilities", ["name"])
    op.create_index("ix_facilities_category", "facilities", ["category"])
    op.create_index("ix_facilities_source", "facilities", ["source"])
    op.create_index("idx_facilities_geometry", "facilities", ["geometry"], postgresql_using="gist")


def downgrade() -> None:
    op.drop_table("facilities")
    op.drop_table("rivers")
    op.drop_table("settlements")
    op.drop_table("districts")
    op.drop_table("regions")
