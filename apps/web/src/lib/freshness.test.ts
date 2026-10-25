import { describe, expect, it } from "vitest";
import {
  assessFreshness,
  assessSourceFreshness,
  formatTimestamp,
  relativeTime,
} from "./freshness";

const NOW = new Date("2026-09-22T06:30:00.000Z");

describe("source freshness", () => {
  it("marks observations from the last 30 minutes as current", () => {
    expect(assessFreshness("2026-09-22T06:20:00.000Z", NOW)).toEqual({
      level: "current",
      label: "Current",
      detail: "Updated 10 minutes ago",
    });
  });

  it("makes delayed and stale evidence explicit", () => {
    expect(assessFreshness("2026-09-22T05:20:00.000Z", NOW).level).toBe("delayed");
    expect(assessFreshness("2026-09-21T23:00:00.000Z", NOW).level).toBe("stale");
  });

  it("does not invent freshness when a timestamp is absent", () => {
    expect(assessFreshness(null, NOW)).toEqual({
      level: "unknown",
      label: "Not reported",
      detail: "No source timestamp supplied",
    });
    expect(relativeTime(undefined, NOW)).toBe("No update recorded");
  });

  it("uses the backend's source-specific status instead of a universal age threshold", () => {
    const oldBoundaryUpdate = "2026-05-12T08:51:34.000Z";
    expect(assessSourceFreshness("ok", oldBoundaryUpdate, NOW).level).toBe("current");
    expect(assessSourceFreshness("stale", oldBoundaryUpdate, NOW).level).toBe("stale");
    expect(assessSourceFreshness("not_configured", null, NOW).level).toBe("unknown");
  });

  it("formats operator timestamps in India Standard Time", () => {
    expect(formatTimestamp("2026-09-22T06:30:00.000Z")).toContain("12:00");
  });
});
