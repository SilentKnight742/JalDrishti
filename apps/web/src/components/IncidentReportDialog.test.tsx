import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { submitIncidentReport } from "../lib/api";
import { IncidentReportDialog } from "./IncidentReportDialog";

vi.mock("../lib/api", () => ({ submitIncidentReport: vi.fn() }));

describe("IncidentReportDialog", () => {
  beforeEach(() => {
    vi.mocked(submitIncidentReport).mockReset();
    Object.defineProperty(navigator, "geolocation", {
      configurable: true,
      value: {
        getCurrentPosition: (success: PositionCallback) =>
          success({
            coords: {
              latitude: 26.50831,
              longitude: 92.11638,
              accuracy: 18,
            },
          } as GeolocationPosition),
      },
    });
  });

  it("captures location, submits privacy fields and presents the unverified receipt", async () => {
    vi.mocked(submitIncidentReport).mockResolvedValue({
      public_reference: "JD-TEST123456",
      event_id: "event-darrang",
      status: "received",
      verification_state: "unverified",
      reported_at: "2026-09-25T12:00:00Z",
      public_location_precision: "approximately 1 km; exact location withheld",
      duplicate: false,
      message: "Report received for review.",
    });
    const onSubmitted = vi.fn();
    render(
      <IncidentReportDialog open onClose={vi.fn()} onSubmitted={onSubmitted} />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Use my device location" }));
    expect(await screen.findByText(/Location captured/)).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText(/What can be seen/), {
      target: { value: "Road under water near the bridge" },
    });
    fireEvent.click(
      screen.getByLabelText(/I consent to JalDrishti storing the exact location/),
    );
    fireEvent.click(screen.getByRole("button", { name: "Submit unverified report" }));

    await waitFor(() => expect(submitIncidentReport).toHaveBeenCalledOnce());
    const body = vi.mocked(submitIncidentReport).mock.calls[0][0];
    expect(body.get("latitude")).toBe("26.50831");
    expect(body.get("longitude")).toBe("92.11638");
    expect(body.get("privacy_consent")).toBe("true");
    expect(body.has("photo")).toBe(false);
    expect(await screen.findByText("JD-TEST123456")).toBeInTheDocument();
    expect(screen.getByText("unverified")).toBeInTheDocument();
    expect(onSubmitted).toHaveBeenCalledOnce();
  });
});
