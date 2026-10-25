"""Canonical Phase 1 geography models.

Geometry is stored in WGS84 (EPSG:4326), the coordinate reference system used
by GeoJSON and the MapLibre client.  Keeping provenance on the records
themselves makes it impossible for a query to silently detach a feature from
its source.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

from geoalchemy2 import Geometry
from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from jaldrishti.domain.provenance import ProvenanceQuality
from jaldrishti.persistence.base import Base


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _quality_enum() -> Enum:
    return Enum(
        ProvenanceQuality,
        name="provenance_quality",
        native_enum=False,
        create_constraint=True,
        validate_strings=True,
        values_callable=lambda enum: [item.value for item in enum],
    )


class ProvenanceMixin:
    """Columns required to trace a record to its original evidence."""

    source: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    source_record_id: Mapped[str | None] = mapped_column(String(256))
    observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utc_now,
        server_default=func.now(),
    )
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source_url: Mapped[str | None] = mapped_column(String(2048))
    source_version: Mapped[str | None] = mapped_column(String(128))
    quality: Mapped[ProvenanceQuality] = mapped_column(
        _quality_enum(),
        nullable=False,
        default=ProvenanceQuality.OFFICIAL,
        server_default=ProvenanceQuality.OFFICIAL.value,
    )


class Region(ProvenanceMixin, Base):
    __tablename__ = "regions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    code: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    geometry: Mapped[Any] = mapped_column(
        Geometry(geometry_type="MULTIPOLYGON", srid=4326, spatial_index=True),
        nullable=False,
    )
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, default=dict)

    districts: Mapped[list[District]] = relationship(
        back_populates="region",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    flood_events: Mapped[list[FloodEvent]] = relationship(
        back_populates="region",
        passive_deletes=True,
    )


class District(ProvenanceMixin, Base):
    __tablename__ = "districts"
    __table_args__ = (UniqueConstraint("region_id", "code", name="uq_districts_region_code"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    region_id: Mapped[str] = mapped_column(
        ForeignKey("regions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    code: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    geometry: Mapped[Any] = mapped_column(
        Geometry(geometry_type="MULTIPOLYGON", srid=4326, spatial_index=True),
        nullable=False,
    )
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, default=dict)

    region: Mapped[Region] = relationship(back_populates="districts")
    settlements: Mapped[list[Settlement]] = relationship(
        back_populates="district",
        passive_deletes=True,
    )
    facilities: Mapped[list[Facility]] = relationship(
        back_populates="district",
        passive_deletes=True,
    )
    stations: Mapped[list[Station]] = relationship(
        back_populates="district",
        passive_deletes=True,
    )
    weather_observations: Mapped[list[WeatherObservation]] = relationship(
        back_populates="district",
        passive_deletes=True,
    )
    weather_forecasts: Mapped[list[WeatherForecast]] = relationship(
        back_populates="district",
        passive_deletes=True,
    )
    official_warnings: Mapped[list[OfficialWarning]] = relationship(
        back_populates="district",
        passive_deletes=True,
    )
    primary_flood_events: Mapped[list[FloodEvent]] = relationship(
        back_populates="primary_district",
        passive_deletes=True,
    )
    flood_event_links: Mapped[list[FloodEventDistrict]] = relationship(
        back_populates="district",
        passive_deletes=True,
    )


class Settlement(ProvenanceMixin, Base):
    __tablename__ = "settlements"
    __table_args__ = (
        UniqueConstraint("source", "source_record_id", name="uq_settlements_source_record"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    region_id: Mapped[str] = mapped_column(
        ForeignKey("regions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    district_id: Mapped[str | None] = mapped_column(
        ForeignKey("districts.id", ondelete="SET NULL"),
        index=True,
    )
    code: Mapped[str | None] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    settlement_type: Mapped[str | None] = mapped_column(String(64))
    population: Mapped[int | None] = mapped_column(BigInteger)
    geometry: Mapped[Any] = mapped_column(
        Geometry(geometry_type="POINT", srid=4326, spatial_index=True),
        nullable=False,
    )
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, default=dict)

    district: Mapped[District | None] = relationship(back_populates="settlements")


class River(ProvenanceMixin, Base):
    __tablename__ = "rivers"
    __table_args__ = (
        UniqueConstraint("source", "source_record_id", name="uq_rivers_source_record"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    region_id: Mapped[str] = mapped_column(
        ForeignKey("regions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    code: Mapped[str | None] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    river_class: Mapped[str | None] = mapped_column(String(64), index=True)
    geometry: Mapped[Any] = mapped_column(
        Geometry(geometry_type="MULTILINESTRING", srid=4326, spatial_index=True),
        nullable=False,
    )
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, default=dict)


class RoadSegment(ProvenanceMixin, Base):
    """Community-maintained road line used for accessibility screening."""

    __tablename__ = "road_segments"

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    region_id: Mapped[str] = mapped_column(
        ForeignKey("regions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    code: Mapped[str | None] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(240), nullable=False, index=True)
    road_class: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    surface: Mapped[str | None] = mapped_column(String(64))
    bridge: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    oneway: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    access: Mapped[str | None] = mapped_column(String(64))
    length_m: Mapped[float] = mapped_column(Float, nullable=False)
    geometry: Mapped[Any] = mapped_column(
        Geometry(geometry_type="MULTILINESTRING", srid=4326, spatial_index=True),
        nullable=False,
    )
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, default=dict)


class Facility(ProvenanceMixin, Base):
    __tablename__ = "facilities"
    __table_args__ = (
        UniqueConstraint("source", "source_record_id", name="uq_facilities_source_record"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    region_id: Mapped[str] = mapped_column(
        ForeignKey("regions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    district_id: Mapped[str | None] = mapped_column(
        ForeignKey("districts.id", ondelete="SET NULL"),
        index=True,
    )
    code: Mapped[str | None] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    category: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    subcategory: Mapped[str | None] = mapped_column(String(120))
    geometry: Mapped[Any] = mapped_column(
        Geometry(geometry_type="GEOMETRY", srid=4326, spatial_index=True),
        nullable=False,
    )
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, default=dict)
    importance: Mapped[float | None] = mapped_column(Float)

    district: Mapped[District | None] = relationship(back_populates="facilities")


class Station(ProvenanceMixin, Base):
    """Hydrological station; thresholds remain null until a source publishes them."""

    __tablename__ = "stations"
    __table_args__ = (
        UniqueConstraint("source", "source_record_id", name="uq_stations_source_record"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    region_id: Mapped[str] = mapped_column(
        ForeignKey("regions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    district_id: Mapped[str | None] = mapped_column(
        ForeignKey("districts.id", ondelete="SET NULL"),
        index=True,
    )
    external_id: Mapped[str | None] = mapped_column(String(128))
    name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    river_name: Mapped[str | None] = mapped_column(String(200))
    basin_name: Mapped[str | None] = mapped_column(String(200))
    warning_level_m: Mapped[float | None] = mapped_column(Float)
    danger_level_m: Mapped[float | None] = mapped_column(Float)
    datum: Mapped[str | None] = mapped_column(String(160))
    time_zone: Mapped[str | None] = mapped_column(String(64))
    operational_status: Mapped[str] = mapped_column(String(32), nullable=False, default="pilot")
    coverage_status: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default="incomplete_public_feed",
    )
    geometry: Mapped[Any] = mapped_column(
        Geometry(geometry_type="POINT", srid=4326, spatial_index=True),
        nullable=False,
    )
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, default=dict)

    district: Mapped[District | None] = relationship(back_populates="stations")
    observations: Mapped[list[StationObservation]] = relationship(
        back_populates="station",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class StationObservation(ProvenanceMixin, Base):
    """Water level with both canonical and unverified source-local time fields."""

    __tablename__ = "station_observations"
    __table_args__ = (
        UniqueConstraint(
            "station_id",
            "source",
            "source_observed_at",
            name="uq_station_observations_station_source_time",
        ),
    )

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    station_id: Mapped[str] = mapped_column(
        ForeignKey("stations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    source_observed_at: Mapped[str] = mapped_column(String(64), nullable=False)
    source_observed_at_local: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        nullable=False,
        index=True,
    )
    water_level_m: Mapped[float] = mapped_column(Float, nullable=False)
    unit: Mapped[str] = mapped_column(String(16), nullable=False, default="m")
    quality_flag: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default="source_unverified",
    )
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, default=dict)

    station: Mapped[Station] = relationship(back_populates="observations")


class WeatherObservation(ProvenanceMixin, Base):
    """Rainfall observation or estimate, with its evidence quality made explicit."""

    __tablename__ = "weather_observations"
    __table_args__ = (
        UniqueConstraint(
            "source", "source_record_id", name="uq_weather_observations_source_record"
        ),
    )

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    region_id: Mapped[str] = mapped_column(
        ForeignKey("regions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    district_id: Mapped[str | None] = mapped_column(
        ForeignKey("districts.id", ondelete="SET NULL"), index=True
    )
    observation_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    period_hours: Mapped[int] = mapped_column(nullable=False, default=1)
    precipitation_mm: Mapped[float | None] = mapped_column(Float)
    geometry: Mapped[Any] = mapped_column(
        Geometry(geometry_type="POINT", srid=4326, spatial_index=True), nullable=False
    )
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, default=dict)

    district: Mapped[District | None] = relationship(back_populates="weather_observations")


class WeatherForecast(ProvenanceMixin, Base):
    """One model-derived precipitation forecast at a district representative point."""

    __tablename__ = "weather_forecasts"
    __table_args__ = (
        UniqueConstraint(
            "district_id", "model", "valid_at", name="uq_weather_forecasts_district_model_valid"
        ),
    )

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    region_id: Mapped[str] = mapped_column(
        ForeignKey("regions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    district_id: Mapped[str] = mapped_column(
        ForeignKey("districts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    model: Mapped[str] = mapped_column(String(96), nullable=False, index=True)
    valid_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    lead_hours: Mapped[int] = mapped_column(nullable=False)
    precipitation_mm: Mapped[float] = mapped_column(Float, nullable=False)
    precipitation_probability_pct: Mapped[float | None] = mapped_column(Float)
    geometry: Mapped[Any] = mapped_column(
        Geometry(geometry_type="POINT", srid=4326, spatial_index=True), nullable=False
    )
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, default=dict)

    district: Mapped[District] = relationship(back_populates="weather_forecasts")


class OfficialWarning(ProvenanceMixin, Base):
    """Official district warning; the district table owns the canonical geometry."""

    __tablename__ = "official_warnings"
    __table_args__ = (
        UniqueConstraint(
            "source", "external_id", "valid_date", name="uq_official_warnings_source_valid"
        ),
    )

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    region_id: Mapped[str] = mapped_column(
        ForeignKey("regions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    district_id: Mapped[str] = mapped_column(
        ForeignKey("districts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    external_id: Mapped[str] = mapped_column(String(96), nullable=False)
    issue_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    valid_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    day_index: Mapped[int] = mapped_column(nullable=False, index=True)
    severity: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    color_code: Mapped[int] = mapped_column(nullable=False)
    warning_codes: Mapped[list[int]] = mapped_column(JSON, nullable=False, default=list)
    hazards: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    description: Mapped[str | None] = mapped_column(String(2000))
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, default=dict)

    district: Mapped[District] = relationship(back_populates="official_warnings")


class FloodEvent(Base):
    """Rule-derived flood event with an explicit evidence-backed lifecycle."""

    __tablename__ = "flood_events"

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    region_id: Mapped[str] = mapped_column(
        ForeignKey("regions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    primary_district_id: Mapped[str | None] = mapped_column(
        ForeignKey("districts.id", ondelete="SET NULL"), index=True
    )
    name: Mapped[str] = mapped_column(String(240), nullable=False, index=True)
    geometry: Mapped[Any] = mapped_column(
        Geometry(geometry_type="MULTIPOLYGON", srid=4326, spatial_index=True),
        nullable=False,
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    last_updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utc_now, index=True
    )
    state_changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utc_now
    )
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    state: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    trigger_summary: Mapped[str] = mapped_column(Text, nullable=False)
    rainfall_status: Mapped[str] = mapped_column(String(64), nullable=False)
    river_status: Mapped[str] = mapped_column(String(64), nullable=False)
    warning_status: Mapped[str] = mapped_column(String(64), nullable=False)
    satellite_status: Mapped[str] = mapped_column(String(64), nullable=False)
    created_by: Mapped[str] = mapped_column(String(32), nullable=False, default="auto")
    rule_version: Mapped[str] = mapped_column(String(128), nullable=False)
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, default=dict)

    region: Mapped[Region] = relationship(back_populates="flood_events")
    primary_district: Mapped[District | None] = relationship(back_populates="primary_flood_events")
    district_links: Mapped[list[FloodEventDistrict]] = relationship(
        back_populates="event",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    evidence: Mapped[list[EventEvidence]] = relationship(
        back_populates="event",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    timeline: Mapped[list[EventTimelineEntry]] = relationship(
        back_populates="event",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    satellite_jobs: Mapped[list[SatelliteJob]] = relationship(
        back_populates="event",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    flood_extents: Mapped[list[FloodExtent]] = relationship(
        back_populates="event",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    impact_snapshots: Mapped[list[ImpactSnapshot]] = relationship(
        back_populates="event",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    accessibility_snapshots: Mapped[list[AccessibilitySnapshot]] = relationship(
        back_populates="event",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    incident_reports: Mapped[list[IncidentReport]] = relationship(
        back_populates="event",
        passive_deletes=True,
    )


class FloodEventDistrict(Base):
    """Affected-district link, allowing future multi-district events."""

    __tablename__ = "flood_event_districts"

    event_id: Mapped[str] = mapped_column(
        ForeignKey("flood_events.id", ondelete="CASCADE"), primary_key=True
    )
    district_id: Mapped[str] = mapped_column(
        ForeignKey("districts.id", ondelete="CASCADE"), primary_key=True, index=True
    )
    role: Mapped[str] = mapped_column(String(32), nullable=False, default="affected")

    event: Mapped[FloodEvent] = relationship(back_populates="district_links")
    district: Mapped[District] = relationship(back_populates="flood_event_links")


class EventEvidence(ProvenanceMixin, Base):
    """One traceable source item supporting or contextualising an event."""

    __tablename__ = "event_evidence"
    __table_args__ = (
        UniqueConstraint(
            "event_id",
            "source",
            "source_record_id",
            name="uq_event_evidence_event_source_record",
        ),
    )

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    event_id: Mapped[str] = mapped_column(
        ForeignKey("flood_events.id", ondelete="CASCADE"), nullable=False, index=True
    )
    evidence_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    geometry: Mapped[Any | None] = mapped_column(
        Geometry(geometry_type="GEOMETRY", srid=4326, spatial_index=True)
    )
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, default=dict)

    event: Mapped[FloodEvent] = relationship(back_populates="evidence")


class EventTimelineEntry(Base):
    """Immutable, idempotently keyed event-lifecycle entry."""

    __tablename__ = "event_timeline_entries"

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    event_id: Mapped[str] = mapped_column(
        ForeignKey("flood_events.id", ondelete="CASCADE"), nullable=False, index=True
    )
    evidence_id: Mapped[str | None] = mapped_column(
        ForeignKey("event_evidence.id", ondelete="SET NULL"), index=True
    )
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    category: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    state_from: Mapped[str | None] = mapped_column(String(32))
    state_to: Mapped[str | None] = mapped_column(String(32))
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, default=dict)

    event: Mapped[FloodEvent] = relationship(back_populates="timeline")


class SatelliteJob(Base):
    """Event-scoped request to discover and process a matched SAR acquisition."""

    __tablename__ = "satellite_jobs"
    __table_args__ = (
        UniqueConstraint(
            "event_id",
            "request_fingerprint",
            name="uq_satellite_jobs_event_request",
        ),
    )

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    event_id: Mapped[str] = mapped_column(
        ForeignKey("flood_events.id", ondelete="CASCADE"), nullable=False, index=True
    )
    request_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utc_now, index=True
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    before_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    before_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    after_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    after_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    algorithm: Mapped[str] = mapped_column(String(128), nullable=False)
    parameters: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    error_code: Mapped[str | None] = mapped_column(String(64))
    error_message: Mapped[str | None] = mapped_column(Text)
    catalog_source: Mapped[str] = mapped_column(String(160), nullable=False)
    catalog_url: Mapped[str | None] = mapped_column(String(2048))
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, default=dict)

    event: Mapped[FloodEvent] = relationship(back_populates="satellite_jobs")
    scenes: Mapped[list[SatelliteScene]] = relationship(
        back_populates="job",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    flood_extents: Mapped[list[FloodExtent]] = relationship(
        back_populates="job",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class SatelliteScene(Base):
    """One catalogue-validated OPERA RTC scene selected for a SAR job."""

    __tablename__ = "satellite_scenes"
    __table_args__ = (
        UniqueConstraint(
            "job_id", "role", "product_id", name="uq_satellite_scenes_job_role_product"
        ),
    )

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    job_id: Mapped[str] = mapped_column(
        ForeignKey("satellite_jobs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    event_id: Mapped[str] = mapped_column(
        ForeignKey("flood_events.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    product_id: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    acquired_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    stopped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    platform: Mapped[str] = mapped_column(String(64), nullable=False)
    sensor: Mapped[str] = mapped_column(String(64), nullable=False)
    relative_orbit: Mapped[int] = mapped_column(nullable=False)
    flight_direction: Mapped[str] = mapped_column(String(16), nullable=False)
    burst_id: Mapped[str] = mapped_column(String(96), nullable=False, index=True)
    polarizations: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    product_version: Mapped[str] = mapped_column(String(64), nullable=False)
    geometry: Mapped[Any] = mapped_column(
        Geometry(geometry_type="GEOMETRY", srid=4326, spatial_index=True), nullable=False
    )
    assets: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    source: Mapped[str] = mapped_column(String(128), nullable=False)
    source_url: Mapped[str | None] = mapped_column(String(2048))
    catalog_record: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)

    job: Mapped[SatelliteJob] = relationship(back_populates="scenes")


class FloodExtent(ProvenanceMixin, Base):
    """Vectorised satellite-observed change evidence attached to an event."""

    __tablename__ = "flood_extents"
    __table_args__ = (UniqueConstraint("job_id", name="uq_flood_extents_job"),)

    quality: Mapped[ProvenanceQuality] = mapped_column(
        _quality_enum(),
        nullable=False,
        default=ProvenanceQuality.SATELLITE_OBSERVED,
        server_default=ProvenanceQuality.SATELLITE_OBSERVED.value,
    )

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    event_id: Mapped[str] = mapped_column(
        ForeignKey("flood_events.id", ondelete="CASCADE"), nullable=False, index=True
    )
    job_id: Mapped[str] = mapped_column(
        ForeignKey("satellite_jobs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    acquired_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    algorithm: Mapped[str] = mapped_column(String(160), nullable=False)
    algorithm_version: Mapped[str] = mapped_column(String(64), nullable=False)
    parameters: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    area_km2: Mapped[float] = mapped_column(Float, nullable=False)
    high_evidence_area_km2: Mapped[float] = mapped_column(Float, nullable=False)
    valid_coverage_fraction: Mapped[float] = mapped_column(Float, nullable=False)
    resolution_m: Mapped[float] = mapped_column(Float, nullable=False)
    analysis_crs: Mapped[str] = mapped_column(String(64), nullable=False)
    raster_uri: Mapped[str] = mapped_column(String(2048), nullable=False)
    geometry: Mapped[Any] = mapped_column(
        Geometry(geometry_type="MULTIPOLYGON", srid=4326, spatial_index=True),
        nullable=False,
    )
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, default=dict)

    event: Mapped[FloodEvent] = relationship(back_populates="flood_extents")
    job: Mapped[SatelliteJob] = relationship(back_populates="flood_extents")
    impact_snapshot: Mapped[ImpactSnapshot | None] = relationship(
        back_populates="flood_extent",
        cascade="all, delete-orphan",
        passive_deletes=True,
        uselist=False,
    )
    comparisons: Mapped[list[SatelliteComparison]] = relationship(
        back_populates="flood_extent",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    accessibility_snapshot: Mapped[AccessibilitySnapshot | None] = relationship(
        back_populates="flood_extent",
        cascade="all, delete-orphan",
        passive_deletes=True,
        uselist=False,
    )


class SatelliteComparison(ProvenanceMixin, Base):
    """One traceable geometric comparison with an external flood product."""

    __tablename__ = "satellite_comparisons"
    __table_args__ = (
        UniqueConstraint(
            "flood_extent_id",
            "source",
            "source_record_id",
            name="uq_satellite_comparisons_extent_reference",
        ),
    )

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    event_id: Mapped[str] = mapped_column(
        ForeignKey("flood_events.id", ondelete="CASCADE"), nullable=False, index=True
    )
    flood_extent_id: Mapped[str] = mapped_column(
        ForeignKey("flood_extents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    reference_name: Mapped[str] = mapped_column(String(240), nullable=False)
    reference_acquired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    compared_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utc_now, index=True
    )
    analysis_crs: Mapped[str] = mapped_column(String(64), nullable=False)
    iou: Mapped[float] = mapped_column(Float, nullable=False)
    dice_f1: Mapped[float] = mapped_column(Float, nullable=False)
    precision: Mapped[float] = mapped_column(Float, nullable=False)
    recall: Mapped[float] = mapped_column(Float, nullable=False)
    detected_area_km2: Mapped[float] = mapped_column(Float, nullable=False)
    reference_area_km2: Mapped[float] = mapped_column(Float, nullable=False)
    overlap_area_km2: Mapped[float] = mapped_column(Float, nullable=False)
    union_area_km2: Mapped[float] = mapped_column(Float, nullable=False)
    area_difference_km2: Mapped[float] = mapped_column(Float, nullable=False)
    temporal_offset_hours: Mapped[float | None] = mapped_column(Float)
    caveat: Mapped[str] = mapped_column(Text, nullable=False)
    geometry: Mapped[Any] = mapped_column(
        Geometry(geometry_type="MULTIPOLYGON", srid=4326, spatial_index=True),
        nullable=False,
    )
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, default=dict)

    flood_extent: Mapped[FloodExtent] = relationship(back_populates="comparisons")


class ImpactSnapshot(Base):
    """One reproducible potential-exposure summary for a flood extent."""

    __tablename__ = "impact_snapshots"
    __table_args__ = (
        UniqueConstraint("flood_extent_id", name="uq_impact_snapshots_flood_extent_id"),
    )

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    event_id: Mapped[str] = mapped_column(
        ForeignKey("flood_events.id", ondelete="CASCADE"), nullable=False, index=True
    )
    flood_extent_id: Mapped[str] = mapped_column(
        ForeignKey("flood_extents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    calculated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utc_now, index=True
    )
    algorithm: Mapped[str] = mapped_column(String(160), nullable=False)
    algorithm_version: Mapped[str] = mapped_column(String(64), nullable=False)
    inundated_area_km2: Mapped[float] = mapped_column(Float, nullable=False)
    settlement_count: Mapped[int] = mapped_column(nullable=False, default=0)
    facility_count: Mapped[int] = mapped_column(nullable=False, default=0)
    population_potentially_exposed: Mapped[int | None] = mapped_column(BigInteger)
    population_record_count: Mapped[int] = mapped_column(nullable=False, default=0)
    road_overlap_km: Mapped[float | None] = mapped_column(Float)
    building_count: Mapped[int | None] = mapped_column()
    coverage: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, default=dict)

    event: Mapped[FloodEvent] = relationship(back_populates="impact_snapshots")
    flood_extent: Mapped[FloodExtent] = relationship(back_populates="impact_snapshot")
    exposures: Mapped[list[PotentialExposure]] = relationship(
        back_populates="snapshot",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class PotentialExposure(ProvenanceMixin, Base):
    """A source asset geometrically intersecting satellite change evidence."""

    __tablename__ = "potential_exposures"
    __table_args__ = (
        UniqueConstraint(
            "snapshot_id", "asset_type", "asset_id", name="uq_exposures_snapshot_asset"
        ),
    )

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    snapshot_id: Mapped[str] = mapped_column(
        ForeignKey("impact_snapshots.id", ondelete="CASCADE"), nullable=False, index=True
    )
    event_id: Mapped[str] = mapped_column(
        ForeignKey("flood_events.id", ondelete="CASCADE"), nullable=False, index=True
    )
    flood_extent_id: Mapped[str] = mapped_column(
        ForeignKey("flood_extents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    asset_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    asset_id: Mapped[str] = mapped_column(String(96), nullable=False)
    name: Mapped[str] = mapped_column(String(240), nullable=False)
    metric_type: Mapped[str] = mapped_column(String(64), nullable=False)
    metric_value: Mapped[float] = mapped_column(Float, nullable=False)
    unit: Mapped[str] = mapped_column(String(32), nullable=False)
    geometry: Mapped[Any] = mapped_column(
        Geometry(geometry_type="GEOMETRY", srid=4326, spatial_index=True), nullable=False
    )
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, default=dict)

    snapshot: Mapped[ImpactSnapshot] = relationship(back_populates="exposures")


class AccessibilitySnapshot(Base):
    """Road-network reachability screening for one observed extent."""

    __tablename__ = "accessibility_snapshots"
    __table_args__ = (
        UniqueConstraint("flood_extent_id", name="uq_accessibility_snapshots_flood_extent_id"),
    )

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    event_id: Mapped[str] = mapped_column(
        ForeignKey("flood_events.id", ondelete="CASCADE"), nullable=False, index=True
    )
    flood_extent_id: Mapped[str] = mapped_column(
        ForeignKey("flood_extents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    calculated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utc_now, index=True
    )
    algorithm: Mapped[str] = mapped_column(String(160), nullable=False)
    algorithm_version: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    road_count: Mapped[int] = mapped_column(nullable=False, default=0)
    graph_node_count: Mapped[int] = mapped_column(nullable=False, default=0)
    graph_edge_count: Mapped[int] = mapped_column(nullable=False, default=0)
    potentially_affected_road_count: Mapped[int] = mapped_column(nullable=False, default=0)
    potentially_affected_road_km: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    assessed_settlement_count: Mapped[int] = mapped_column(nullable=False, default=0)
    potentially_isolated_settlement_count: Mapped[int] = mapped_column(nullable=False, default=0)
    coverage: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, default=dict)

    event: Mapped[FloodEvent] = relationship(back_populates="accessibility_snapshots")
    flood_extent: Mapped[FloodExtent] = relationship(back_populates="accessibility_snapshot")
    road_disruptions: Mapped[list[RoadDisruption]] = relationship(
        back_populates="snapshot",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    settlement_results: Mapped[list[SettlementAccessibility]] = relationship(
        back_populates="snapshot",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class RoadDisruption(ProvenanceMixin, Base):
    """Road geometry intersecting flood evidence; not a confirmed closure."""

    __tablename__ = "road_disruptions"
    __table_args__ = (
        UniqueConstraint("snapshot_id", "road_segment_id", name="uq_disruptions_snapshot_road"),
    )

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    snapshot_id: Mapped[str] = mapped_column(
        ForeignKey("accessibility_snapshots.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    event_id: Mapped[str] = mapped_column(
        ForeignKey("flood_events.id", ondelete="CASCADE"), nullable=False, index=True
    )
    flood_extent_id: Mapped[str] = mapped_column(
        ForeignKey("flood_extents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    road_segment_id: Mapped[str | None] = mapped_column(
        ForeignKey("road_segments.id", ondelete="SET NULL"), index=True
    )
    name: Mapped[str] = mapped_column(String(240), nullable=False)
    road_class: Mapped[str] = mapped_column(String(64), nullable=False)
    overlap_km: Mapped[float] = mapped_column(Float, nullable=False)
    geometry: Mapped[Any] = mapped_column(
        Geometry(geometry_type="MULTILINESTRING", srid=4326, spatial_index=True),
        nullable=False,
    )
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, default=dict)

    snapshot: Mapped[AccessibilitySnapshot] = relationship(back_populates="road_disruptions")


class SettlementAccessibility(ProvenanceMixin, Base):
    """Before/after reachability result for one settlement point."""

    __tablename__ = "settlement_accessibility"
    __table_args__ = (
        UniqueConstraint(
            "snapshot_id", "settlement_id", name="uq_settlement_accessibility_snapshot"
        ),
    )

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    snapshot_id: Mapped[str] = mapped_column(
        ForeignKey("accessibility_snapshots.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    event_id: Mapped[str] = mapped_column(
        ForeignKey("flood_events.id", ondelete="CASCADE"), nullable=False, index=True
    )
    flood_extent_id: Mapped[str] = mapped_column(
        ForeignKey("flood_extents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    settlement_id: Mapped[str | None] = mapped_column(
        ForeignKey("settlements.id", ondelete="SET NULL"), index=True
    )
    name: Mapped[str] = mapped_column(String(240), nullable=False)
    snapped_distance_m: Mapped[float | None] = mapped_column(Float)
    major_road_reachable_before: Mapped[bool] = mapped_column(Boolean, nullable=False)
    major_road_reachable_after: Mapped[bool] = mapped_column(Boolean, nullable=False)
    hospital_reachable_before: Mapped[bool] = mapped_column(Boolean, nullable=False)
    hospital_reachable_after: Mapped[bool] = mapped_column(Boolean, nullable=False)
    nearest_major_road_km: Mapped[float | None] = mapped_column(Float)
    nearest_hospital_km: Mapped[float | None] = mapped_column(Float)
    potentially_isolated: Mapped[bool] = mapped_column(Boolean, nullable=False, index=True)
    assessment_status: Mapped[str] = mapped_column(String(64), nullable=False)
    geometry: Mapped[Any] = mapped_column(
        Geometry(geometry_type="POINT", srid=4326, spatial_index=True), nullable=False
    )
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, default=dict)

    snapshot: Mapped[AccessibilitySnapshot] = relationship(back_populates="settlement_results")


class IncidentReport(ProvenanceMixin, Base):
    """Privacy-separated public incident record and its exact internal location."""

    __tablename__ = "incident_reports"
    __table_args__ = (
        UniqueConstraint("submission_id", name="uq_incident_reports_submission_id"),
        UniqueConstraint("public_reference", name="uq_incident_reports_public_reference"),
    )

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    submission_id: Mapped[str] = mapped_column(String(64), nullable=False)
    public_reference: Mapped[str] = mapped_column(String(32), nullable=False)
    request_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    event_id: Mapped[str | None] = mapped_column(
        ForeignKey("flood_events.id", ondelete="SET NULL"), index=True
    )
    incident_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    people_affected: Mapped[int | None] = mapped_column()
    people_count_approximate: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    description_private: Mapped[str] = mapped_column(Text, nullable=False)
    public_summary: Mapped[str] = mapped_column(String(320), nullable=False)
    reported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utc_now, index=True
    )
    verification_state: Mapped[str] = mapped_column(
        String(40), nullable=False, default="unverified", index=True
    )
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="received", index=True)
    location_method: Mapped[str] = mapped_column(String(32), nullable=False)
    location_accuracy_m: Mapped[float | None] = mapped_column(Float)
    exact_geometry: Mapped[Any] = mapped_column(
        Geometry(geometry_type="POINT", srid=4326, spatial_index=True), nullable=False
    )
    public_geometry: Mapped[Any] = mapped_column(
        Geometry(geometry_type="POINT", srid=4326, spatial_index=True), nullable=False
    )
    media_count: Mapped[int] = mapped_column(nullable=False, default=0)
    privacy_consent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, default=dict)

    event: Mapped[FloodEvent | None] = relationship(back_populates="incident_reports")
    contact: Mapped[IncidentContact | None] = relationship(
        back_populates="report",
        cascade="all, delete-orphan",
        passive_deletes=True,
        uselist=False,
    )
    media: Mapped[list[IncidentMedia]] = relationship(
        back_populates="report",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class IncidentContact(Base):
    """Encrypted optional contact details, never exposed by the public API."""

    __tablename__ = "incident_contacts"

    report_id: Mapped[str] = mapped_column(
        ForeignKey("incident_reports.id", ondelete="CASCADE"), primary_key=True
    )
    encrypted_contact: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    encryption_key_id: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utc_now
    )

    report: Mapped[IncidentReport] = relationship(back_populates="contact")


class IncidentMedia(Base):
    """Reference to a normalised private upload; media is not publicly served."""

    __tablename__ = "incident_media"
    __table_args__ = (
        UniqueConstraint("report_id", "sha256", name="uq_incident_media_report_sha256"),
    )

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    report_id: Mapped[str] = mapped_column(
        ForeignKey("incident_reports.id", ondelete="CASCADE"), nullable=False, index=True
    )
    private_uri: Mapped[str] = mapped_column(String(2048), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(128), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    normalization_status: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utc_now
    )

    report: Mapped[IncidentReport] = relationship(back_populates="media")
