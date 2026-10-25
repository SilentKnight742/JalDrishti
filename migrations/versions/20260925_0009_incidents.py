"""Add privacy-separated community incident reports.

Revision ID: 20260925_0009
Revises: 20260925_0008
Create Date: 2026-09-25
"""

from collections.abc import Sequence

import geoalchemy2
import sqlalchemy as sa
from alembic import op

revision: str = "20260925_0009"
down_revision: str | None = "20260925_0008"
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
            server_default="unverified_report",
        ),
    ]


def upgrade() -> None:
    op.create_table(
        "incident_reports",
        sa.Column("id", sa.String(length=96), primary_key=True),
        sa.Column("submission_id", sa.String(length=64), nullable=False),
        sa.Column("public_reference", sa.String(length=32), nullable=False),
        sa.Column("request_fingerprint", sa.String(length=64), nullable=False),
        sa.Column(
            "event_id",
            sa.String(length=96),
            sa.ForeignKey("flood_events.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("incident_type", sa.String(length=64), nullable=False),
        sa.Column("people_affected", sa.Integer(), nullable=True),
        sa.Column(
            "people_count_approximate", sa.Boolean(), nullable=False, server_default=sa.true()
        ),
        sa.Column("description_private", sa.Text(), nullable=False),
        sa.Column("public_summary", sa.String(length=320), nullable=False),
        sa.Column("reported_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "verification_state", sa.String(length=40), nullable=False, server_default="unverified"
        ),
        sa.Column("status", sa.String(length=40), nullable=False, server_default="received"),
        sa.Column("location_method", sa.String(length=32), nullable=False),
        sa.Column("location_accuracy_m", sa.Float(), nullable=True),
        sa.Column(
            "exact_geometry",
            geoalchemy2.Geometry("POINT", srid=4326, spatial_index=False),
            nullable=False,
        ),
        sa.Column(
            "public_geometry",
            geoalchemy2.Geometry("POINT", srid=4326, spatial_index=False),
            nullable=False,
        ),
        sa.Column("media_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("privacy_consent_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        *_provenance_columns(),
        sa.UniqueConstraint("submission_id", name="uq_incident_reports_submission_id"),
        sa.UniqueConstraint("public_reference", name="uq_incident_reports_public_reference"),
    )
    for column in (
        "event_id",
        "incident_type",
        "reported_at",
        "verification_state",
        "status",
        "source",
    ):
        op.create_index(f"ix_incident_reports_{column}", "incident_reports", [column])
    for column in ("exact_geometry", "public_geometry"):
        op.create_index(
            f"idx_incident_reports_{column}",
            "incident_reports",
            [column],
            postgresql_using="gist",
        )

    op.create_table(
        "incident_contacts",
        sa.Column(
            "report_id",
            sa.String(length=96),
            sa.ForeignKey("incident_reports.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("encrypted_contact", sa.LargeBinary(), nullable=False),
        sa.Column("encryption_key_id", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "incident_media",
        sa.Column("id", sa.String(length=96), primary_key=True),
        sa.Column(
            "report_id",
            sa.String(length=96),
            sa.ForeignKey("incident_reports.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("private_uri", sa.String(length=2048), nullable=False),
        sa.Column("mime_type", sa.String(length=128), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("normalization_status", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("report_id", "sha256", name="uq_incident_media_report_sha256"),
    )
    op.create_index("ix_incident_media_report_id", "incident_media", ["report_id"])
    op.create_index("ix_incident_media_sha256", "incident_media", ["sha256"])


def downgrade() -> None:
    op.drop_table("incident_media")
    op.drop_table("incident_contacts")
    op.drop_table("incident_reports")
