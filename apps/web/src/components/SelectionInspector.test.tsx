import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type {
  EventEvidenceProperties,
  EventTimelineItem,
  GeographyCollection,
  SelectedMapFeature,
  StationObservationSeries,
} from "../types";
import { SelectionInspector } from "./SelectionInspector";

const stationSelection: SelectedMapFeature = {
  kind: "station",
  properties: {
    id: "nwdp-test-station",
    name: "NH15 Crossing Fakirpara Tangni",
    region_id: "assam",
    district_id: "assam-district-283",
    river_name: null,
    time_zone: null,
    warning_level_m: null,
    danger_level_m: null,
    operational_status: "pilot",
    coverage_status: "incomplete_public_feed",
    source: "Assam WRD / National Water Data Portal",
    source_version: "nwdp-test",
    quality: "official",
    ingested_at: "2026-09-24T05:00:00Z",
  },
};

const series: StationObservationSeries = {
  station_id: "nwdp-test-station",
  operational_status: "pilot",
  coverage_status: "incomplete_public_feed",
  time_zone: null,
  warning_level_m: null,
  danger_level_m: null,
  caveats: ["Observation timestamps do not include a timezone."],
  observations: [
    {
      id: "reading-2",
      station_id: "nwdp-test-station",
      source_observed_at: "22-09-2026 23:00",
      observed_at: null,
      water_level_m: 61.083,
      unit: "m",
      quality_flag: "source_time_zone_unverified",
      source: "Assam WRD / National Water Data Portal",
      source_url: null,
      source_version: "nwdp-test",
      quality: "official",
      ingested_at: "2026-09-24T05:00:00Z",
    },
    {
      id: "reading-1",
      station_id: "nwdp-test-station",
      source_observed_at: "22-09-2026 22:00",
      observed_at: null,
      water_level_m: 61.084,
      unit: "m",
      quality_flag: "source_time_zone_unverified",
      source: "Assam WRD / National Water Data Portal",
      source_url: null,
      source_version: "nwdp-test",
      quality: "official",
      ingested_at: "2026-09-24T05:00:00Z",
    },
  ],
};

describe("SelectionInspector station evidence", () => {
  it("shows the pilot reading without inventing a timezone or alert threshold", () => {
    render(
      <SelectionInspector
        selection={stationSelection}
        isDetailLoading={false}
        stationObservations={series}
        isStationDetailLoading={false}
        hasStationDetailError={false}
        onClear={vi.fn()}
      />,
    );

    expect(screen.getByText("Pilot")).toBeInTheDocument();
    expect(screen.getAllByText(/61\.083/)).toHaveLength(2);
    expect(screen.getByText(/timezone not published/i)).toBeInTheDocument();
    expect(screen.getByText("Incomplete public feed")).toBeInTheDocument();
    expect(screen.getAllByText("Not published")).toHaveLength(2);
    expect(screen.getByRole("img", { name: "Recent pilot water-level readings" })).toBeInTheDocument();
  });
});

describe("SelectionInspector event evidence", () => {
  const eventSelection: SelectedMapFeature = {
    kind: "event",
    properties: {
      id: "event-baksa",
      name: "Baksa flood event",
      region_id: "assam",
      primary_district_id: "baksa",
      state: "watch",
      started_at: "2026-09-24T06:00:00Z",
      last_updated_at: "2026-09-24T06:05:00Z",
      state_changed_at: "2026-09-24T06:00:00Z",
      trigger_summary: "Official IMD yellow warning establishes a watch.",
      rainfall_status: "supporting",
      river_status: "not_configured",
      warning_status: "yellow",
      satellite_status: "not_available",
      created_by: "auto",
      rule_version: "assam-official-warning-v1",
      rationale: ["Official warning is authoritative trigger evidence."],
      source: "JalDrishti event engine",
      source_version: "assam-official-warning-v1",
      quality: "model_derived",
      ingested_at: "2026-09-24T06:05:00Z",
    },
  };
  const evidence: GeographyCollection<EventEvidenceProperties> = {
    type: "FeatureCollection",
    features: [
      {
        type: "Feature",
        geometry: { type: "Point", coordinates: [91.4, 26.6] },
        properties: {
          id: "evidence-warning",
          event_id: "event-baksa",
          evidence_type: "official_warning",
          name: "IMD district warning",
          summary: "Yellow warning for Baksa.",
          metadata: {},
          source: "India Meteorological Department",
          quality: "official",
          ingested_at: "2026-09-24T06:00:00Z",
        },
      },
    ],
  };
  const timeline: EventTimelineItem[] = [
    {
      id: "timeline-created",
      event_id: "event-baksa",
      occurred_at: "2026-09-24T06:00:00Z",
      category: "state_transition",
      state_to: "watch",
      summary: "Event entered watch state.",
      metadata: {},
    },
  ];

  it("shows the rule rationale, evidence record and state timeline", () => {
    render(
      <SelectionInspector
        selection={eventSelection}
        isDetailLoading={false}
        isStationDetailLoading={false}
        hasStationDetailError={false}
        eventEvidence={evidence}
        eventTimeline={timeline}
        onClear={vi.fn()}
      />,
    );

    expect(screen.getAllByText("Watch").length).toBeGreaterThan(0);
    expect(screen.getByText(/authoritative trigger evidence/i)).toBeInTheDocument();
    expect(screen.getByText("IMD district warning")).toBeInTheDocument();
    expect(screen.getByText("Event entered watch state.")).toBeInTheDocument();
    expect(screen.getAllByText("assam-official-warning-v1")).toHaveLength(2);
  });
});
