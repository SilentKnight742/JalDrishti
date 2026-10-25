import type { Feature, FeatureCollection, Geometry } from "geojson";

export type ServiceCondition = "ok" | "degraded" | "unavailable" | string;

export interface DependencyStatus {
  status: ServiceCondition;
  detail?: string;
}

export interface SourceStatus {
  id: string;
  name: string;
  status: ServiceCondition;
  last_updated_at: string | null;
  detail?: string | null;
}

export interface SystemStatus {
  status: ServiceCondition;
  service: string;
  version: string;
  checked_at: string;
  dependencies: {
    database: DependencyStatus;
    redis: DependencyStatus;
    [name: string]: DependencyStatus;
  };
  sources: SourceStatus[];
}

export interface GeographyProperties {
  id: string;
  code?: string | null;
  name: string;
  source?: string | null;
  source_url?: string | null;
  source_version?: string | null;
  quality?: string | null;
  ingested_at?: string | null;
  [key: string]: unknown;
}

export interface FacilityProperties extends GeographyProperties {
  category?: string | null;
  subcategory?: string | null;
}

export interface SettlementProperties extends GeographyProperties {
  settlement_type?: string | null;
  population?: number | null;
}

export interface RiverProperties extends GeographyProperties {
  river_class?: string | null;
}

export interface StationProperties extends GeographyProperties {
  region_id: string;
  district_id?: string | null;
  external_id?: string | null;
  river_name?: string | null;
  basin_name?: string | null;
  warning_level_m?: number | null;
  danger_level_m?: number | null;
  datum?: string | null;
  time_zone?: string | null;
  operational_status: string;
  coverage_status: string;
}

export interface WeatherSummaryProperties extends GeographyProperties {
  district_id: string;
  precipitation_24h_mm: number;
  maximum_probability_pct?: number | null;
  forecast_from: string;
  forecast_through: string;
  model: string;
}

export interface WarningProperties extends GeographyProperties {
  district_id: string;
  external_id: string;
  issue_at: string;
  valid_date: string;
  day_index: number;
  severity: "green" | "yellow" | "orange" | "red";
  color_code: number;
  warning_codes: number[];
  hazards: string[];
  description?: string | null;
}

export interface EventProperties extends GeographyProperties {
  region_id: string;
  primary_district_id?: string | null;
  state: "watch" | "warning" | "severe" | "recovery";
  started_at: string;
  last_updated_at: string;
  state_changed_at: string;
  ended_at?: string | null;
  trigger_summary: string;
  rainfall_status: string;
  river_status: string;
  warning_status: string;
  satellite_status: string;
  created_by: "auto" | "operator";
  rule_version: string;
  rationale: string[];
}

export interface EventEvidenceProperties extends GeographyProperties {
  event_id: string;
  evidence_type: string;
  summary: string;
  source_record_id?: string | null;
  observed_at?: string | null;
  published_at?: string | null;
  metadata: Record<string, unknown>;
}

export interface EventTimelineItem {
  id: string;
  event_id: string;
  evidence_id?: string | null;
  occurred_at: string;
  category: string;
  state_from?: string | null;
  state_to?: string | null;
  summary: string;
  metadata: Record<string, unknown>;
}

export type SatelliteJobStatus =
  | "queued"
  | "searching"
  | "no_scenes"
  | "awaiting_credentials"
  | "downloading"
  | "processing"
  | "completed"
  | "completed_no_extent"
  | "failed";

export interface SatelliteJob {
  id: string;
  event_id: string;
  status: SatelliteJobStatus;
  requested_at: string;
  started_at?: string | null;
  completed_at?: string | null;
  before_start: string;
  before_end: string;
  after_start: string;
  after_end: string;
  algorithm: string;
  parameters: Record<string, unknown>;
  error_code?: string | null;
  error_message?: string | null;
  catalog_source: string;
  catalog_url?: string | null;
  scene_count: number;
}

export interface FloodExtentProperties extends GeographyProperties {
  event_id: string;
  job_id: string;
  acquired_at: string;
  algorithm: string;
  algorithm_version: string;
  parameters: Record<string, unknown>;
  area_km2: number;
  high_evidence_area_km2: number;
  valid_coverage_fraction: number;
  resolution_m: number;
  analysis_crs: string;
  raster_uri: string;
  metadata: Record<string, unknown>;
}

export interface SatelliteComparisonProperties extends GeographyProperties {
  event_id: string;
  flood_extent_id: string;
  reference_name: string;
  reference_acquired_at?: string | null;
  compared_at: string;
  analysis_crs: string;
  iou: number;
  dice_f1: number;
  precision: number;
  recall: number;
  detected_area_km2: number;
  reference_area_km2: number;
  overlap_area_km2: number;
  union_area_km2: number;
  area_difference_km2: number;
  temporal_offset_hours?: number | null;
  caveat: string;
  source_record_id?: string | null;
  observed_at?: string | null;
  published_at?: string | null;
  metadata: Record<string, unknown>;
}

export interface PotentialExposureProperties extends GeographyProperties {
  snapshot_id: string;
  event_id: string;
  flood_extent_id: string;
  asset_type: "settlement" | "facility" | "road" | "building" | "other";
  asset_id: string;
  metric_type: string;
  metric_value: number;
  unit: string;
  source_record_id?: string | null;
  observed_at?: string | null;
  published_at?: string | null;
  metadata: Record<string, unknown>;
}

export interface ImpactSummary {
  id: string;
  event_id: string;
  flood_extent_id: string;
  calculated_at: string;
  algorithm: string;
  algorithm_version: string;
  inundated_area_km2: number;
  settlement_count: number;
  facility_count: number;
  population_potentially_exposed: number | null;
  population_record_count: number;
  road_overlap_km: number | null;
  building_count: number | null;
  coverage: Record<string, { status?: string; basis?: string; [key: string]: unknown }>;
  metadata: Record<string, unknown>;
}

export interface ImpactResponse {
  status: "available" | "not_available";
  summary: ImpactSummary | null;
  exposures: GeographyCollection<PotentialExposureProperties>;
  caveats: string[];
}

export interface RoadDisruptionProperties extends GeographyProperties {
  snapshot_id: string;
  event_id: string;
  flood_extent_id: string;
  road_segment_id?: string | null;
  road_class: string;
  overlap_km: number;
  source_record_id?: string | null;
  observed_at?: string | null;
  metadata: Record<string, unknown>;
}

export interface SettlementAccessibilityProperties extends GeographyProperties {
  snapshot_id: string;
  event_id: string;
  flood_extent_id: string;
  settlement_id?: string | null;
  snapped_distance_m?: number | null;
  major_road_reachable_before: boolean;
  major_road_reachable_after: boolean;
  hospital_reachable_before: boolean;
  hospital_reachable_after: boolean;
  nearest_major_road_km?: number | null;
  nearest_hospital_km?: number | null;
  potentially_isolated: boolean;
  assessment_status: string;
  source_record_id?: string | null;
  observed_at?: string | null;
  metadata: Record<string, unknown>;
}

export interface AccessibilitySummary {
  id: string;
  event_id: string;
  flood_extent_id: string;
  calculated_at: string;
  algorithm: string;
  algorithm_version: string;
  status: string;
  road_count: number;
  graph_node_count: number;
  graph_edge_count: number;
  potentially_affected_road_count: number;
  potentially_affected_road_km: number;
  assessed_settlement_count: number;
  potentially_isolated_settlement_count: number;
  coverage: Record<string, { status?: string; basis?: string; [key: string]: unknown }>;
  metadata: Record<string, unknown>;
}

export interface AccessibilityResponse {
  status: "available" | "not_available" | "not_configured";
  summary: AccessibilitySummary | null;
  road_disruptions: GeographyCollection<RoadDisruptionProperties>;
  settlements: GeographyCollection<SettlementAccessibilityProperties>;
  caveats: string[];
}

export type IncidentType =
  | "stranded_people"
  | "medical_emergency"
  | "road_flooded"
  | "bridge_damage"
  | "building_flooding"
  | "embankment_issue"
  | "other";

export interface IncidentProperties extends GeographyProperties {
  event_id?: string | null;
  public_reference: string;
  incident_type: IncidentType;
  people_affected?: number | null;
  people_count_approximate: boolean;
  public_summary: string;
  reported_at: string;
  verification_state: "unverified" | "verified" | "rejected";
  status: string;
  location_method: "gps" | "map";
  location_accuracy_m?: number | null;
  media_count: number;
  source_record_id?: string | null;
  metadata: Record<string, unknown>;
}

export interface IncidentReceipt {
  public_reference: string;
  event_id?: string | null;
  status: string;
  verification_state: string;
  reported_at: string;
  public_location_precision: string;
  duplicate: boolean;
  message: string;
}

export interface StationObservation {
  id: string;
  station_id: string;
  source_observed_at: string;
  observed_at: string | null;
  water_level_m: number;
  unit: string;
  quality_flag: string;
  source: string;
  source_url: string | null;
  source_version: string | null;
  quality: string;
  ingested_at: string;
}

export interface StationObservationSeries {
  station_id: string;
  operational_status: "pilot";
  coverage_status: "incomplete_public_feed";
  time_zone: null;
  warning_level_m: null;
  danger_level_m: null;
  caveats: string[];
  observations: StationObservation[];
}

export type GeographyFeature<P extends GeographyProperties = GeographyProperties> = Feature<
  Geometry,
  P
>;

export type GeographyCollection<P extends GeographyProperties = GeographyProperties> =
  FeatureCollection<Geometry, P>;

export type SelectedMapFeature =
  | { kind: "district"; properties: GeographyProperties }
  | { kind: "facility"; properties: FacilityProperties }
  | { kind: "settlement"; properties: SettlementProperties }
  | { kind: "river"; properties: RiverProperties }
  | { kind: "station"; properties: StationProperties }
  | { kind: "weather"; properties: WeatherSummaryProperties }
  | { kind: "warning"; properties: WarningProperties }
  | { kind: "event"; properties: EventProperties }
  | { kind: "extent"; properties: FloodExtentProperties }
  | { kind: "road_disruption"; properties: RoadDisruptionProperties }
  | { kind: "accessibility"; properties: SettlementAccessibilityProperties }
  | { kind: "incident"; properties: IncidentProperties };
