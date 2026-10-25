import type {
  AccessibilityResponse,
  EventEvidenceProperties,
  EventProperties,
  EventTimelineItem,
  FacilityProperties,
  FloodExtentProperties,
  GeographyCollection,
  GeographyFeature,
  ImpactResponse,
  IncidentProperties,
  IncidentReceipt,
  RiverProperties,
  SettlementProperties,
  StationObservationSeries,
  StationProperties,
  SatelliteJob,
  SatelliteComparisonProperties,
  SystemStatus,
  WarningProperties,
  WeatherSummaryProperties,
} from "../types";
import { toFeature, toFeatureCollection } from "./geojson";

const configuredBase = import.meta.env.VITE_API_BASE_URL?.trim() || "/api/v1";
export const API_BASE_URL = configuredBase.replace(/\/$/, "");

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly endpoint: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

const request = async <T>(path: string, signal?: AbortSignal): Promise<T> => {
  const endpoint = `${API_BASE_URL}${path}`;
  const response = await fetch(endpoint, {
    signal,
    headers: { Accept: "application/json" },
  });

  if (!response.ok) {
    throw new ApiError(`The API returned ${response.status} for ${path}.`, response.status, endpoint);
  }

  try {
    return (await response.json()) as T;
  } catch {
    throw new ApiError(`The API returned invalid JSON for ${path}.`, response.status, endpoint);
  }
};

const post = async <T>(path: string, body: unknown): Promise<T> => {
  const endpoint = `${API_BASE_URL}${path}`;
  const response = await fetch(endpoint, {
    method: "POST",
    headers: { Accept: "application/json", "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    throw new ApiError(`The API returned ${response.status} for ${path}.`, response.status, endpoint);
  }
  try {
    return (await response.json()) as T;
  } catch {
    throw new ApiError(`The API returned invalid JSON for ${path}.`, response.status, endpoint);
  }
};

export const getStatus = (signal?: AbortSignal): Promise<SystemStatus> =>
  request<SystemStatus>("/status", signal);

export const getRegions = async (signal?: AbortSignal): Promise<GeographyCollection> =>
  toFeatureCollection(await request<unknown>("/regions", signal));

export const getDistricts = async (signal?: AbortSignal): Promise<GeographyCollection> =>
  toFeatureCollection(await request<unknown>("/districts?region_id=assam", signal));

export const getDistrict = async (
  districtId: string,
  signal?: AbortSignal,
): Promise<GeographyFeature> =>
  toFeature(await request<unknown>(`/districts/${encodeURIComponent(districtId)}`, signal));

export const getFacilities = async (
  signal?: AbortSignal,
): Promise<GeographyCollection<FacilityProperties>> =>
  toFeatureCollection(await request<unknown>("/facilities?region_id=assam", signal)) as GeographyCollection<FacilityProperties>;

export const getSettlements = async (
  signal?: AbortSignal,
): Promise<GeographyCollection<SettlementProperties>> =>
  toFeatureCollection(
    await request<unknown>("/settlements?region_id=assam", signal),
  ) as GeographyCollection<SettlementProperties>;

export const getRivers = async (
  signal?: AbortSignal,
): Promise<GeographyCollection<RiverProperties>> =>
  toFeatureCollection(
    await request<unknown>("/rivers?region_id=assam", signal),
  ) as GeographyCollection<RiverProperties>;

export const getStations = async (
  signal?: AbortSignal,
): Promise<GeographyCollection<StationProperties>> =>
  toFeatureCollection(
    await request<unknown>("/stations?region_id=assam", signal),
  ) as GeographyCollection<StationProperties>;

export const getStationObservations = (
  stationId: string,
  signal?: AbortSignal,
): Promise<StationObservationSeries> =>
  request<StationObservationSeries>(
    `/stations/${encodeURIComponent(stationId)}/observations?limit=168`,
    signal,
  );

export const getWeatherForecasts = async (
  signal?: AbortSignal,
): Promise<GeographyCollection<WeatherSummaryProperties>> =>
  toFeatureCollection(
    await request<unknown>("/weather/forecasts?region_id=assam&hours=24", signal),
  ) as GeographyCollection<WeatherSummaryProperties>;

export const getWarnings = async (
  signal?: AbortSignal,
): Promise<GeographyCollection<WarningProperties>> =>
  toFeatureCollection(
    await request<unknown>("/warnings?region_id=assam&day=1", signal),
  ) as GeographyCollection<WarningProperties>;

export const getEvents = async (
  signal?: AbortSignal,
): Promise<GeographyCollection<EventProperties>> =>
  toFeatureCollection(
    await request<unknown>("/events?region_id=assam", signal),
  ) as GeographyCollection<EventProperties>;

export const getEventEvidence = async (
  eventId: string,
  signal?: AbortSignal,
): Promise<GeographyCollection<EventEvidenceProperties>> =>
  toFeatureCollection(
    await request<unknown>(`/events/${encodeURIComponent(eventId)}/evidence`, signal),
  ) as GeographyCollection<EventEvidenceProperties>;

export const getEventTimeline = (
  eventId: string,
  signal?: AbortSignal,
): Promise<EventTimelineItem[]> =>
  request<EventTimelineItem[]>(
    `/events/${encodeURIComponent(eventId)}/timeline`,
    signal,
  );

export const getSatelliteJobs = (
  eventId: string,
  signal?: AbortSignal,
): Promise<SatelliteJob[]> =>
  request<SatelliteJob[]>(
    `/events/${encodeURIComponent(eventId)}/satellite-jobs`,
    signal,
  );

export const requestSatelliteObservation = (eventId: string): Promise<SatelliteJob> =>
  post<SatelliteJob>(`/events/${encodeURIComponent(eventId)}/satellite-jobs`, {});

export const getFloodExtents = async (
  eventId: string,
  signal?: AbortSignal,
): Promise<GeographyCollection<FloodExtentProperties>> =>
  toFeatureCollection(
    await request<unknown>(`/events/${encodeURIComponent(eventId)}/flood-extents`, signal),
  ) as GeographyCollection<FloodExtentProperties>;

export const getSatelliteComparisons = async (
  eventId: string,
  signal?: AbortSignal,
): Promise<GeographyCollection<SatelliteComparisonProperties>> =>
  toFeatureCollection(
    await request<unknown>(
      `/events/${encodeURIComponent(eventId)}/satellite-comparisons`,
      signal,
    ),
  ) as GeographyCollection<SatelliteComparisonProperties>;

export const getEventImpact = (
  eventId: string,
  signal?: AbortSignal,
): Promise<ImpactResponse> =>
  request<ImpactResponse>(`/events/${encodeURIComponent(eventId)}/impact`, signal);

export const getEventAccessibility = (
  eventId: string,
  signal?: AbortSignal,
): Promise<AccessibilityResponse> =>
  request<AccessibilityResponse>(
    `/events/${encodeURIComponent(eventId)}/accessibility`,
    signal,
  );

export const getEventIncidents = async (
  eventId: string,
  signal?: AbortSignal,
): Promise<GeographyCollection<IncidentProperties>> =>
  toFeatureCollection(
    await request<unknown>(`/events/${encodeURIComponent(eventId)}/incidents`, signal),
  ) as GeographyCollection<IncidentProperties>;

export const submitIncidentReport = async (body: FormData): Promise<IncidentReceipt> => {
  const endpoint = `${API_BASE_URL}/incidents/report`;
  const response = await fetch(endpoint, {
    method: "POST",
    headers: { Accept: "application/json" },
    body,
  });
  if (!response.ok) {
    let detail = `The API returned ${response.status}.`;
    try {
      const payload = (await response.json()) as { detail?: string };
      if (typeof payload.detail === "string") detail = payload.detail;
    } catch {
      // Retain the safe status message when the response has no JSON body.
    }
    throw new ApiError(detail, response.status, endpoint);
  }
  return (await response.json()) as IncidentReceipt;
};
