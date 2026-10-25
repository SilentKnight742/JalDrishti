import { fireEvent, render, screen } from "@testing-library/react";
import type { Geometry } from "geojson";
import { describe, expect, it, vi } from "vitest";
import type {
  GeographyCollection,
  EventProperties,
  StationProperties,
  WarningProperties,
  WeatherSummaryProperties,
} from "../types";
import {
  boundsFromGeometries,
  focusBoundsFromGeometry,
  geometryToSvgPath,
  projectPosition,
  StaticGeographyMap,
} from "./StaticGeographyMap";

const districtGeometry: Geometry = {
  type: "Polygon",
  coordinates: [[[92, 26], [94, 26], [94, 28], [92, 28], [92, 26]]],
};

const districts: GeographyCollection = {
  type: "FeatureCollection",
  features: [
    {
      type: "Feature",
      geometry: districtGeometry,
      properties: { id: "district-1", name: "Test district" },
    },
  ],
};

const emptyCollection: GeographyCollection = { type: "FeatureCollection", features: [] };
const emptyStations: GeographyCollection<StationProperties> = {
  type: "FeatureCollection",
  features: [],
};
const emptyWeather: GeographyCollection<WeatherSummaryProperties> = {
  type: "FeatureCollection",
  features: [],
};
const emptyWarnings: GeographyCollection<WarningProperties> = {
  type: "FeatureCollection",
  features: [],
};
const emptyEvents: GeographyCollection<EventProperties> = {
  type: "FeatureCollection",
  features: [],
};

describe("static geography compatibility map", () => {
  it("projects the source bounds into the padded SVG extent", () => {
    const bounds = boundsFromGeometries([districtGeometry]);
    expect(projectPosition([92, 28], bounds)).toEqual([26, 26]);
    expect(projectPosition([94, 26], bounds)).toEqual([974, 534]);
  });

  it("creates a closed SVG path for polygon geography", () => {
    const path = geometryToSvgPath(districtGeometry, boundsFromGeometries([districtGeometry]));
    expect(path).toMatch(/^M26\.00 534\.00/);
    expect(path).toMatch(/Z$/);
  });

  it("creates a non-degenerate focused extent for a point", () => {
    const fullBounds = boundsFromGeometries([districtGeometry]);
    const focused = focusBoundsFromGeometry(
      { type: "Point", coordinates: [93, 27] },
      fullBounds,
    );
    expect(focused.maxLongitude - focused.minLongitude).toBeCloseTo(0.5);
    expect(focused.maxLatitude - focused.minLatitude).toBeCloseTo(0.32);
    expect(focused.minLongitude).toBeLessThan(93);
    expect(focused.maxLongitude).toBeGreaterThan(93);
  });

  it("keeps mapped records inspectable without WebGL", () => {
    const onSelect = vi.fn();
    const { container } = render(
      <StaticGeographyMap
        regions={emptyCollection}
        districts={districts}
        settlements={emptyCollection}
        rivers={emptyCollection}
        stations={emptyStations}
        facilities={emptyCollection}
        weather={emptyWeather}
        warnings={emptyWarnings}
        events={emptyEvents}
        visibleLayers={{
          districts: true,
          rivers: true,
          settlements: true,
          stations: true,
          facilities: true,
          weather: true,
          warnings: true,
          events: true,
        }}
        onSelect={onSelect}
        focusGeometry={districtGeometry}
        selectedRecord={{
          kind: "district",
          properties: { id: "district-1", name: "Test district" },
        }}
      />,
    );

    const districtPath = container.querySelector(".static-map__districts path");
    expect(districtPath).not.toBeNull();
    expect(districtPath).toHaveClass("is-selected");
    expect(container.querySelector("svg")).toHaveAttribute("data-focused", "true");
    fireEvent.click(districtPath as SVGPathElement);
    expect(onSelect).toHaveBeenCalledWith({
      kind: "district",
      properties: { id: "district-1", name: "Test district" },
    });
    expect(screen.getByRole("link", { name: "© OpenStreetMap contributors" })).toHaveAttribute(
      "href",
      "https://www.openstreetmap.org/copyright",
    );
  });
});
