import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { Delta } from "@/components/data-display/delta";
import { ProvenanceBadge } from "@/components/data-display/provenance-badge";
import { ErrorState, PermissionDenied } from "@/components/feedback/states";
import { InsightsPanel } from "@/components/domain/dashboard/insights-panel";
import { summariseFillRate } from "@/components/domain/dashboard/fill-rate-chart";
import { IndicatorStrip } from "@/components/domain/dashboard/indicator-strip";
import { Button } from "@/components/ui/button";
import { dashboardSummarySchema } from "@/features/dashboard/contract";
import demo from "@/test/fixtures/dashboard-demo.json";

describe("Delta", () => {
  it("describes direction in words, not only colour", () => {
    render(<Delta value={7} previous={4} increaseIs="bad" periodLabel="previous 7 days" />);
    expect(screen.getByText(/\+3/)).toBeInTheDocument();
    expect(screen.getByText(/vs previous 7 days/)).toBeInTheDocument();
  });

  it("renders nothing without a comparison value", () => {
    const { container } = render(<Delta value={1} previous={null} increaseIs="good" periodLabel="x" />);
    expect(container).toBeEmptyDOMElement();
  });
});

describe("ProvenanceBadge", () => {
  it("labels demo data with an accessible hint", () => {
    render(<ProvenanceBadge provenance="demo" />);
    expect(screen.getByText("Demo data")).toBeInTheDocument();
    expect(screen.getByText(/Fictional sample data/)).toBeInTheDocument();
  });
});

describe("feedback states", () => {
  it("permission denied names the missing permission", () => {
    render(<PermissionDenied permission="workflows.approve" />);
    expect(screen.getByText("Requires workflows.approve")).toBeInTheDocument();
  });

  it("error state offers retry and shows the request id", async () => {
    const onRetry = vi.fn();
    render(<ErrorState onRetry={onRetry} requestId="abc123" />);
    expect(screen.getByRole("alert")).toHaveTextContent("Request ID abc123");
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(onRetry).toHaveBeenCalledOnce();
  });
});

describe("Button", () => {
  it("is disabled and busy while loading", () => {
    render(<Button loading>Save</Button>);
    const button = screen.getByRole("button", { name: "Save" });
    expect(button).toBeDisabled();
    expect(button).toHaveAttribute("aria-busy", "true");
  });
});

describe("InsightsPanel", () => {
  const insights = dashboardSummarySchema.parse(demo).insights.data!;

  it("orders by severity and expands evidence on demand", async () => {
    render(<InsightsPanel insights={[...insights].reverse()} openCount={7} provenance="demo" />);
    const titles = screen.getAllByRole("heading", { level: 3 }).map((h) => h.textContent);
    expect(titles[0]).toMatch(/Stockout risk/);

    const toggles = screen.getAllByRole("button", { name: /evidence/ });
    expect(toggles[0]).toHaveAttribute("aria-expanded", "true");
    expect(toggles[1]).toHaveAttribute("aria-expanded", "false");
    await userEvent.click(toggles[1]);
    expect(toggles[1]).toHaveAttribute("aria-expanded", "true");
  });

  it("states how each explanation was produced", () => {
    render(<InsightsPanel insights={insights} openCount={7} provenance="demo" />);
    expect(screen.getAllByText(/Explanation by demo-model, checked against evidence/)).toHaveLength(2);
    expect(screen.getByText(/Explanation from template \(no model used\)/)).toBeInTheDocument();
  });

  it("does not offer an action that is not connected", () => {
    render(<InsightsPanel insights={insights} openCount={7} provenance="demo" />);
    expect(screen.getByRole("button", { name: "Create purchase request" })).toHaveAttribute("aria-disabled", "true");
  });
});

describe("IndicatorStrip", () => {
  it("shows a dash and the reason for unavailable indicators, never a zero", () => {
    render(
      <IndicatorStrip
        period="7d"
        indicators={[
          { key: "open_insights", label: "Open insights", value: null, total: null, previous_value: null, increase_is: "bad", state: "neutral", detail: "Detection starts once data flows", provenance: "unavailable" },
          { key: "members", label: "Members", value: 3, total: null, previous_value: null, increase_is: "neutral", state: "neutral", detail: "1 invitation pending", provenance: "live" },
        ]}
      />,
    );
    expect(screen.getByText("Detection starts once data flows")).toBeInTheDocument();
    expect(screen.getByText("(not available yet)", { exact: false })).toBeInTheDocument();
    expect(screen.queryByText("0")).not.toBeInTheDocument();
    expect(screen.getByText("3")).toBeInTheDocument();
  });
});

describe("summariseFillRate", () => {
  it("counts consecutive days below target", () => {
    const s = summariseFillRate({
      target: 97,
      points: [
        { date: "2026-11-10", value: 98 },
        { date: "2026-11-11", value: 96.5 },
        { date: "2026-11-12", value: 96 },
      ],
    });
    expect(s.daysBelow).toBe(2);
    expect(s.average).toBeCloseTo(96.83, 2);
  });
});
