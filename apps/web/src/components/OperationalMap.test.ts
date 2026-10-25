import { describe, expect, it } from "vitest";
import { boundsFromGeometry, OPENSTREETMAP_TILE_URL } from "./OperationalMap";

describe("operational map basemap", () => {
  it("uses the no-key OpenStreetMap tile endpoint", () => {
    expect(OPENSTREETMAP_TILE_URL).toBe(
      "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
    );
    expect(OPENSTREETMAP_TILE_URL).not.toContain("cartocdn");
  });

  it("derives a camera extent from selectable geometry", () => {
    expect(
      boundsFromGeometry({
        type: "Polygon",
        coordinates: [[[91, 26], [94, 25], [93, 28], [91, 26]]],
      }),
    ).toEqual([[91, 25], [94, 28]]);
  });
});
