import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { Geometry } from "geojson";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type {
  AccessibilityResponse,
  EventProperties,
  FloodExtentProperties,
  GeographyCollection,
  IncidentProperties,
  StationProperties,
  WarningProperties,
  WeatherSummaryProperties,
} from "../types";
import { OperationalMap } from "./OperationalMap";

interface MockSource {
  data: GeographyCollection;
  setData: ReturnType<typeof vi.fn>;
}

interface MockMapInstance {
  addedSourceData: Map<string, GeographyCollection>;
  sources: Map<string, MockSource>;
  triggerRepaint: ReturnType<typeof vi.fn>;
  setLayoutProperty: ReturnType<typeof vi.fn>;
  emit: (event: string, payload: unknown) => void;
}

const mapMockState = vi.hoisted(() => ({
  instances: [] as MockMapInstance[],
}));

vi.mock("maplibre-gl", () => {
  class MockMap {
    addedSourceData = new Map<string, GeographyCollection>();
    sources = new Map<string, MockSource>();
    listeners = new Map<string, Array<(payload: unknown) => void>>();
    triggerRepaint = vi.fn();
    addControl = vi.fn();
    addLayer = vi.fn();
    fitBounds = vi.fn();
    flyTo = vi.fn();
    remove = vi.fn();
    setFilter = vi.fn();
    setLayoutProperty = vi.fn();

    constructor() {
      mapMockState.instances.push(this as unknown as MockMapInstance);
    }

    addSource(id: string, specification: { data: GeographyCollection }) {
      this.addedSourceData.set(id, specification.data);
      const source: MockSource = {
        data: specification.data,
        setData: vi.fn(async (data: GeographyCollection) => {
          source.data = data;
        }),
      };
      this.sources.set(id, source);
    }

    getSource(id: string) {
      return this.sources.get(id);
    }

    getCanvas() {
      return { style: { cursor: "" } };
    }

    on(event: string, layerOrHandler: string | ((payload: unknown) => void), handler?: (payload: unknown) => void) {
      const listener = typeof layerOrHandler === "function" ? layerOrHandler : handler;
      if (!listener) return;
      this.listeners.set(event, [...(this.listeners.get(event) ?? []), listener]);
    }

    once(event: string, handler: () => void) {
      if (event === "load") queueMicrotask(handler);
    }

    emit(event: string, payload: unknown) {
      this.listeners.get(event)?.forEach((listener) => listener(payload));
    }
  }

  class MockLngLatBounds {
    extend = vi.fn();
    isEmpty() {
      return false;
    }
  }

  return {
    Map: MockMap,
    setWorkerUrl: vi.fn(),
    LngLatBounds: MockLngLatBounds,
    NavigationControl: class {},
    ScaleControl: class {},
    AttributionControl: class {},
  };
});

const collection = (
  id: string,
  name: string,
  geometry: Geometry,
): GeographyCollection => ({
  type: "FeatureCollection",
  features: [{ type: "Feature", geometry, properties: { id, name } }],
});

const regions = collection("region-1", "Assam", {
  type: "Polygon",
  coordinates: [[[90, 25], [96, 25], [96, 28], [90, 28], [90, 25]]],
});
const districts = collection("district-1", "Test district", {
  type: "Polygon",
  coordinates: [[[92, 26], [94, 26], [94, 28], [92, 28], [92, 26]]],
});
const rivers = collection("river-1", "Test river", {
  type: "LineString",
  coordinates: [[92, 26], [94, 27]],
});
const settlements = collection("settlement-1", "Test settlement", {
  type: "Point",
  coordinates: [93, 27],
});
const facilities = collection("facility-1", "Test facility", {
  type: "Point",
  coordinates: [93.1, 27.1],
});
const incidents: GeographyCollection<IncidentProperties> = {
  type: "FeatureCollection",
  features: [
    {
      type: "Feature",
      geometry: { type: "Point", coordinates: [92.12, 26.51] },
      properties: {
        id: "incident-1",
        name: "Road flooding reported",
        event_id: "event-1",
        public_reference: "JD-TEST123456",
        incident_type: "road_flooded",
        people_affected: null,
        people_count_approximate: true,
        public_summary: "Road flooding reported",
        reported_at: "2026-09-25T12:00:00Z",
        verification_state: "unverified",
        status: "received",
        location_method: "gps",
        location_accuracy_m: 18,
        media_count: 0,
        metadata: {},
      },
    },
  ],
};
const stations: GeographyCollection<StationProperties> = {
  type: "FeatureCollection",
  features: [
    {
      type: "Feature",
      geometry: { type: "Point", coordinates: [92.1, 26.5] },
      properties: {
        id: "station-1",
        name: "Test station",
        region_id: "assam",
        operational_status: "pilot",
        coverage_status: "incomplete_public_feed",
      },
    },
  ],
};
const weather: GeographyCollection<WeatherSummaryProperties> = {
  type: "FeatureCollection",
  features: [
    {
      type: "Feature",
      geometry: { type: "Point", coordinates: [93.2, 26.8] },
      properties: {
        id: "weather-1",
        name: "Test district rainfall",
        district_id: "district-1",
        precipitation_24h_mm: 18.4,
        maximum_probability_pct: 70,
        forecast_from: "2026-09-24T00:00:00Z",
        forecast_through: "2026-09-25T00:00:00Z",
        model: "ecmwf_ifs025",
      },
    },
  ],
};
const warnings: GeographyCollection<WarningProperties> = {
  type: "FeatureCollection",
  features: [
    {
      type: "Feature",
      geometry: districts.features[0].geometry,
      properties: {
        id: "warning-1",
        name: "Test district warning",
        district_id: "district-1",
        external_id: "1",
        issue_at: "2026-09-24T00:00:00Z",
        valid_date: "2026-09-24",
        day_index: 1,
        severity: "yellow",
        color_code: 3,
        warning_codes: [2],
        hazards: ["Heavy rain"],
      },
    },
  ],
};
const events: GeographyCollection<EventProperties> = {
  type: "FeatureCollection",
  features: [
    {
      type: "Feature",
      geometry: districts.features[0].geometry,
      properties: {
        id: "event-1",
        name: "Test district flood event",
        region_id: "assam",
        primary_district_id: "district-1",
        state: "watch",
        started_at: "2026-09-24T00:00:00Z",
        last_updated_at: "2026-09-24T00:10:00Z",
        state_changed_at: "2026-09-24T00:00:00Z",
        trigger_summary: "Official yellow warning",
        rainfall_status: "supporting",
        river_status: "not_configured",
        warning_status: "yellow",
        satellite_status: "not_available",
        created_by: "auto",
        rule_version: "test-v1",
        rationale: ["Official warning establishes a watch."],
      },
    },
  ],
};
const floodExtents: GeographyCollection<FloodExtentProperties> = {
  type: "FeatureCollection",
  features: [
    {
      type: "Feature",
      geometry: districts.features[0].geometry,
      properties: {
        id: "extent-1",
        name: "Test satellite change extent",
        event_id: "event-1",
        job_id: "job-1",
        acquired_at: "2026-09-24T06:00:00Z",
        algorithm: "test-change",
        algorithm_version: "1",
        parameters: {},
        area_km2: 2.4,
        high_evidence_area_km2: 1.2,
        valid_coverage_fraction: 0.95,
        resolution_m: 30,
        analysis_crs: "EPSG:32646",
        raster_uri: "products/test.tif",
        metadata: {},
      },
    },
  ],
};
const accessibility: AccessibilityResponse = {
  status: "available",
  summary: {
    id: "access-1",
    event_id: "event-1",
    flood_extent_id: "extent-1",
    calculated_at: "2026-09-24T07:00:00Z",
    algorithm: "test-routing",
    algorithm_version: "1",
    status: "available",
    road_count: 1,
    graph_node_count: 2,
    graph_edge_count: 1,
    potentially_affected_road_count: 1,
    potentially_affected_road_km: 0.4,
    assessed_settlement_count: 1,
    potentially_isolated_settlement_count: 1,
    coverage: {},
    metadata: {},
  },
  road_disruptions: {
    type: "FeatureCollection",
    features: [{
      type: "Feature",
      geometry: rivers.features[0].geometry,
      properties: {
        id: "disruption-1",
        name: "Test road",
        snapshot_id: "access-1",
        event_id: "event-1",
        flood_extent_id: "extent-1",
        road_segment_id: "road-1",
        road_class: "primary",
        overlap_km: 0.4,
        metadata: {},
      },
    }],
  },
  settlements: {
    type: "FeatureCollection",
    features: [{
      type: "Feature",
      geometry: settlements.features[0].geometry,
      properties: {
        id: "access-settlement-1",
        name: "Test settlement",
        snapshot_id: "access-1",
        event_id: "event-1",
        flood_extent_id: "extent-1",
        settlement_id: "settlement-1",
        major_road_reachable_before: true,
        major_road_reachable_after: false,
        hospital_reachable_before: true,
        hospital_reachable_after: false,
        potentially_isolated: true,
        assessment_status: "assessed",
        metadata: {},
      },
    }],
  },
  caveats: ["Potential disruption only"],
};

const defaultProps = {
  regions,
  districts,
  rivers,
  settlements,
  stations,
  weather,
  warnings,
  events,
  floodExtents,
  accessibility,
  incidents,
  facilities,
  isLoading: false,
  hasError: false,
  onRetry: vi.fn(),
  selection: null,
  onSelect: vi.fn(),
};

describe("operational MapLibre source lifecycle", () => {
  beforeEach(() => {
    cleanup();
    mapMockState.instances.length = 0;
  });

  it("creates every runtime source with the API collection instead of an empty placeholder", async () => {
    render(<OperationalMap {...defaultProps} />);

    await waitFor(() => expect(mapMockState.instances[0]?.sources.size).toBe(13));
    const map = mapMockState.instances[0];

    expect(map.addedSourceData.get("regions")).toBe(regions);
    expect(map.addedSourceData.get("districts")).toBe(districts);
    expect(map.addedSourceData.get("rivers")).toBe(rivers);
    expect(map.addedSourceData.get("settlements")).toBe(settlements);
    expect(map.addedSourceData.get("stations")).toBe(stations);
    expect(map.addedSourceData.get("weather")).toBe(weather);
    expect(map.addedSourceData.get("warnings")).toBe(warnings);
    expect(map.addedSourceData.get("events")).toBe(events);
    expect(map.addedSourceData.get("extents")).toBe(floodExtents);
    expect(map.addedSourceData.get("disruptions")).toBe(accessibility.road_disruptions);
    expect(map.addedSourceData.get("accessibility")).toBe(accessibility.settlements);
    expect(map.addedSourceData.get("facilities")).toBe(facilities);
    expect(
      [...map.addedSourceData.values()].every((source) => source.features.length > 0),
    ).toBe(true);
    expect([...map.sources.values()].every((source) => source.setData.mock.calls.length === 0)).toBe(true);
  });

  it("awaits later collection updates and requests a repaint", async () => {
    const { rerender } = render(<OperationalMap {...defaultProps} />);
    await waitFor(() => expect(mapMockState.instances[0]?.sources.size).toBe(13));
    const map = mapMockState.instances[0];
    const updatedFacilities: GeographyCollection = {
      ...facilities,
      features: [
        ...facilities.features,
        {
          type: "Feature",
          geometry: { type: "Point", coordinates: [93.2, 27.2] },
          properties: { id: "facility-2", name: "Second facility" },
        },
      ],
    };

    rerender(<OperationalMap {...defaultProps} facilities={updatedFacilities} />);

    await waitFor(() => {
      expect(map.sources.get("facilities")?.setData).toHaveBeenCalledWith(updatedFacilities);
      expect(map.triggerRepaint).toHaveBeenCalledTimes(1);
    });
  });

  it("hides facilities by default and reveals them when a facility is selected", async () => {
    render(<OperationalMap {...defaultProps} />);
    await waitFor(() => expect(mapMockState.instances[0]?.sources.size).toBe(13));
    const map = mapMockState.instances[0];

    await waitFor(() => {
      expect(map.setLayoutProperty).toHaveBeenCalledWith(
        "facility-dot",
        "visibility",
        "none",
      );
      expect(screen.getByRole("button", { name: "Facilities" })).toHaveAttribute(
        "aria-pressed",
        "false",
      );
    });

    fireEvent.change(screen.getByLabelText("Inspect mapped record"), {
      target: { value: "facility:facility-1" },
    });

    await waitFor(() => {
      expect(map.setLayoutProperty).toHaveBeenCalledWith(
        "facility-dot",
        "visibility",
        "visible",
      );
      expect(screen.getByRole("button", { name: "Facilities" })).toHaveAttribute(
        "aria-pressed",
        "true",
      );
    });
  });

  it("switches to the compatibility map when an operational source reports an error", async () => {
    render(<OperationalMap {...defaultProps} />);
    await waitFor(() => expect(mapMockState.instances[0]?.sources.size).toBe(13));

    act(() => {
      mapMockState.instances[0].emit("error", {
        sourceId: "districts",
        error: new Error("worker update failed"),
      });
    });

    expect(
      screen.getByText("Compatibility view · The districts layer could not be rendered."),
    ).toBeInTheDocument();
  });
});
