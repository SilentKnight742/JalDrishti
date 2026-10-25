import { describe, expect, it } from "vitest";
import { toFeature, toFeatureCollection } from "./geojson";

const districtFeature = {
  type: "Feature" as const,
  geometry: {
    type: "Polygon" as const,
    coordinates: [[[92, 26], [93, 26], [93, 27], [92, 26]]],
  },
  properties: {
    id: "dhemaji",
    code: "DHE",
    name: "Dhemaji",
    source: "Authoritative test fixture",
  },
};

describe("GeoJSON API normalisation", () => {
  it("preserves a canonical FeatureCollection", () => {
    const collection = { type: "FeatureCollection" as const, features: [districtFeature] };
    expect(toFeatureCollection(collection)).toEqual(collection);
  });

  it("accepts data envelopes without introducing local geography", () => {
    expect(toFeatureCollection({ data: districtFeature }).features).toEqual([districtFeature]);
  });

  it("converts spatial records returned in an items envelope", () => {
    const collection = toFeatureCollection({
      items: [
        {
          id: "facility-1",
          name: "District Hospital",
          category: "healthcare",
          geometry: { type: "Point", coordinates: [94.1, 27.4] },
        },
      ],
    });
    expect(collection.features[0].properties.name).toBe("District Hospital");
    expect(collection.features[0].geometry.type).toBe("Point");
  });

  it("rejects non-spatial payloads", () => {
    expect(() => toFeatureCollection({ message: "not geojson" })).toThrow(/FeatureCollection/);
    expect(() => toFeature({ type: "FeatureCollection", features: [] })).toThrow(/one GeoJSON/);
  });
});
