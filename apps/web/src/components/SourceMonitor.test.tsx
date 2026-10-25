import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { SourceMonitor } from "./SourceMonitor";

describe("SourceMonitor", () => {
  it("shows explicit source health and does not collapse degraded data into live", () => {
    render(
      <SourceMonitor
        isLoading={false}
        isUnavailable={false}
        sources={[
          {
            id: "nwdp",
            name: "National Water Data Portal",
            status: "degraded",
            last_updated_at: null,
          },
        ]}
      />,
    );

    expect(screen.getByText("National Water Data Portal")).toBeInTheDocument();
    expect(screen.getByText("Degraded")).toBeInTheDocument();
    expect(screen.getByText("No source timestamp supplied")).toBeInTheDocument();
  });

  it("explains an unavailable monitor", () => {
    render(<SourceMonitor isLoading={false} isUnavailable sources={[]} />);
    expect(screen.getByRole("status")).toHaveTextContent("freshness cannot be verified");
  });
});
