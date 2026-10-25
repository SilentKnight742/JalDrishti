"""Public API response contracts."""

from datetime import date, datetime
from typing import Any, Generic, Literal, TypeVar

from jaldrishti.domain.provenance import ProvenanceQuality
from pydantic import UUID4, BaseModel, ConfigDict, Field, field_validator


class GeoJSONGeometry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal[
        "Point",
        "MultiPoint",
        "LineString",
        "MultiLineString",
        "Polygon",
        "MultiPolygon",
    ]
    coordinates: Any

    @field_validator("coordinates")
    @classmethod
    def coordinates_are_an_array(cls, value: Any) -> Any:
        if not isinstance(value, (list, tuple)):
            raise TypeError("GeoJSON coordinates must be an array")
        return value


class FeatureProperties(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    code: str | None
    name: str
    source: str
    source_url: str | None
    source_version: str | None
    quality: ProvenanceQuality | str
    ingested_at: datetime


class FacilityProperties(FeatureProperties):
    category: str
    subcategory: str | None


class SettlementProperties(FeatureProperties):
    settlement_type: str | None
    population: int | None


class RiverProperties(FeatureProperties):
    river_class: str | None


class StationProperties(FeatureProperties):
    region_id: str
    district_id: str | None
    external_id: str | None
    river_name: str | None
    basin_name: str | None
    warning_level_m: float | None
    danger_level_m: float | None
    datum: str | None
    time_zone: str | None
    operational_status: str
    coverage_status: str


class WeatherSummaryProperties(FeatureProperties):
    district_id: str
    precipitation_24h_mm: float
    maximum_probability_pct: float | None
    forecast_from: datetime
    forecast_through: datetime
    model: str


class WarningProperties(FeatureProperties):
    district_id: str
    external_id: str
    issue_at: datetime
    valid_date: date
    day_index: int
    severity: Literal["green", "yellow", "orange", "red"]
    color_code: int
    warning_codes: list[int]
    hazards: list[str]
    description: str | None


class EventProperties(FeatureProperties):
    region_id: str
    primary_district_id: str | None
    state: Literal["watch", "warning", "severe", "recovery"]
    started_at: datetime
    last_updated_at: datetime
    state_changed_at: datetime
    ended_at: datetime | None
    trigger_summary: str
    rainfall_status: str
    river_status: str
    warning_status: str
    satellite_status: str
    created_by: Literal["auto", "operator"]
    rule_version: str
    rationale: list[str]


class EventEvidenceProperties(FeatureProperties):
    event_id: str
    evidence_type: str
    summary: str
    source_record_id: str | None
    observed_at: datetime | None
    published_at: datetime | None
    metadata: dict[str, Any]


class EventTimelineItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    event_id: str
    evidence_id: str | None
    occurred_at: datetime
    category: str
    state_from: str | None
    state_to: str | None
    summary: str
    metadata: dict[str, Any]


class SatelliteJobRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    before_days: int = Field(default=24, ge=6, le=60)
    after_days: int = Field(default=12, ge=1, le=30)
    resolution_m: float = Field(default=30, ge=10, le=100)
    median_kernel: Literal[1, 3, 5] = 3
    minimum_valid_coverage: float = Field(default=0.8, gt=0, le=1)
    water_threshold_override_db: float | None = Field(default=None, ge=-35, le=0)
    vv_drop_db: float = Field(default=-3, ge=-20, le=0)
    vh_drop_db: float = Field(default=-2, ge=-20, le=0)
    min_component_pixels: int = Field(default=10, ge=1, le=10_000)


class SatelliteJobItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    event_id: str
    status: Literal[
        "queued",
        "searching",
        "no_scenes",
        "awaiting_credentials",
        "downloading",
        "processing",
        "completed",
        "completed_no_extent",
        "failed",
    ]
    requested_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    before_start: datetime
    before_end: datetime
    after_start: datetime
    after_end: datetime
    algorithm: str
    parameters: dict[str, Any]
    error_code: str | None
    error_message: str | None
    catalog_source: str
    catalog_url: str | None
    scene_count: int


class FloodExtentProperties(FeatureProperties):
    event_id: str
    job_id: str
    acquired_at: datetime
    algorithm: str
    algorithm_version: str
    parameters: dict[str, Any]
    area_km2: float
    high_evidence_area_km2: float
    valid_coverage_fraction: float
    resolution_m: float
    analysis_crs: str
    raster_uri: str
    metadata: dict[str, Any]


class SatelliteComparisonProperties(FeatureProperties):
    event_id: str
    flood_extent_id: str
    reference_name: str
    reference_acquired_at: datetime | None
    compared_at: datetime
    analysis_crs: str
    iou: float
    dice_f1: float
    precision: float
    recall: float
    detected_area_km2: float
    reference_area_km2: float
    overlap_area_km2: float
    union_area_km2: float
    area_difference_km2: float
    temporal_offset_hours: float | None
    caveat: str
    source_record_id: str | None
    observed_at: datetime | None
    published_at: datetime | None
    metadata: dict[str, Any]


class PotentialExposureProperties(FeatureProperties):
    snapshot_id: str
    event_id: str
    flood_extent_id: str
    asset_type: Literal["settlement", "facility", "road", "building", "other"]
    asset_id: str
    metric_type: str
    metric_value: float
    unit: str
    source_record_id: str | None
    observed_at: datetime | None
    published_at: datetime | None
    metadata: dict[str, Any]


class ImpactSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    event_id: str
    flood_extent_id: str
    calculated_at: datetime
    algorithm: str
    algorithm_version: str
    inundated_area_km2: float
    settlement_count: int
    facility_count: int
    population_potentially_exposed: int | None
    population_record_count: int
    road_overlap_km: float | None
    building_count: int | None
    coverage: dict[str, Any]
    metadata: dict[str, Any]


class RoadDisruptionProperties(FeatureProperties):
    snapshot_id: str
    event_id: str
    flood_extent_id: str
    road_segment_id: str | None
    road_class: str
    overlap_km: float
    source_record_id: str | None
    observed_at: datetime | None
    metadata: dict[str, Any]


class SettlementAccessibilityProperties(FeatureProperties):
    snapshot_id: str
    event_id: str
    flood_extent_id: str
    settlement_id: str | None
    snapped_distance_m: float | None
    major_road_reachable_before: bool
    major_road_reachable_after: bool
    hospital_reachable_before: bool
    hospital_reachable_after: bool
    nearest_major_road_km: float | None
    nearest_hospital_km: float | None
    potentially_isolated: bool
    assessment_status: str
    source_record_id: str | None
    observed_at: datetime | None
    metadata: dict[str, Any]


class AccessibilitySummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    event_id: str
    flood_extent_id: str
    calculated_at: datetime
    algorithm: str
    algorithm_version: str
    status: str
    road_count: int
    graph_node_count: int
    graph_edge_count: int
    potentially_affected_road_count: int
    potentially_affected_road_km: float
    assessed_settlement_count: int
    potentially_isolated_settlement_count: int
    coverage: dict[str, Any]
    metadata: dict[str, Any]


IncidentType = Literal[
    "stranded_people",
    "medical_emergency",
    "road_flooded",
    "bridge_damage",
    "building_flooding",
    "embankment_issue",
    "other",
]


class IncidentSubmissionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    submission_id: UUID4
    incident_type: IncidentType
    people_affected: int | None = Field(default=None, ge=0, le=1_000_000)
    people_count_approximate: bool = True
    description: str = Field(min_length=5, max_length=2_000)
    latitude: float = Field(ge=24.0, le=28.5)
    longitude: float = Field(ge=89.4, le=96.3)
    location_accuracy_m: float | None = Field(default=None, ge=0, le=100_000)
    location_method: Literal["gps", "map"]
    contact: str | None = Field(default=None, max_length=240)
    privacy_consent: Literal[True]


class IncidentProperties(FeatureProperties):
    event_id: str | None
    public_reference: str
    incident_type: IncidentType
    people_affected: int | None
    people_count_approximate: bool
    public_summary: str
    reported_at: datetime
    verification_state: Literal["unverified", "verified", "rejected"]
    status: str
    location_method: Literal["gps", "map"]
    location_accuracy_m: float | None
    media_count: int
    source_record_id: str | None
    metadata: dict[str, Any]


class IncidentReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid")

    public_reference: str
    event_id: str | None
    status: str
    verification_state: str
    reported_at: datetime
    public_location_precision: str
    duplicate: bool
    message: str


class StationObservation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    station_id: str
    source_observed_at: str
    observed_at: datetime | None
    water_level_m: float
    unit: str
    quality_flag: str
    source: str
    source_url: str | None
    source_version: str | None
    quality: ProvenanceQuality | str
    ingested_at: datetime


class StationObservationSeries(BaseModel):
    model_config = ConfigDict(extra="forbid")

    station_id: str
    operational_status: Literal["pilot"] = "pilot"
    coverage_status: Literal["incomplete_public_feed"] = "incomplete_public_feed"
    time_zone: None = None
    warning_level_m: None = None
    danger_level_m: None = None
    caveats: list[str]
    observations: list[StationObservation] = Field(default_factory=list)


PropertiesT = TypeVar("PropertiesT", bound=FeatureProperties)


class GeoJSONFeature(BaseModel, Generic[PropertiesT]):  # noqa: UP046 - Pydantic compatibility
    model_config = ConfigDict(extra="forbid")

    type: Literal["Feature"] = "Feature"
    geometry: GeoJSONGeometry | None
    properties: PropertiesT


class GeoJSONFeatureCollection(
    BaseModel,
    Generic[PropertiesT],  # noqa: UP046 - Pydantic compatibility
):
    model_config = ConfigDict(extra="forbid")

    type: Literal["FeatureCollection"] = "FeatureCollection"
    features: list[GeoJSONFeature[PropertiesT]] = Field(default_factory=list)


class ImpactResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["available", "not_available"]
    summary: ImpactSummary | None
    exposures: GeoJSONFeatureCollection[PotentialExposureProperties]
    caveats: list[str]


class AccessibilityResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["available", "not_available", "not_configured"]
    summary: AccessibilitySummary | None
    road_disruptions: GeoJSONFeatureCollection[RoadDisruptionProperties]
    settlements: GeoJSONFeatureCollection[SettlementAccessibilityProperties]
    caveats: list[str]


class DependencyStatus(BaseModel):
    status: Literal["ok", "unavailable"]


class DependencyStatuses(BaseModel):
    database: DependencyStatus
    redis: DependencyStatus


class SourceStatus(BaseModel):
    id: str
    name: str
    status: Literal["ok", "degraded", "stale", "unavailable", "not_configured"]
    last_updated_at: datetime | None
    detail: str | None = None


class ServiceStatus(BaseModel):
    status: Literal["ok", "degraded"]
    service: str
    version: str
    checked_at: datetime
    dependencies: DependencyStatuses
    sources: list[SourceStatus] = Field(default_factory=list)
