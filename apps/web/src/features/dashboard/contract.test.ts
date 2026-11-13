import { describe, expect, it } from "vitest";

import demo from "@/test/fixtures/dashboard-demo.json";
import layout from "@/test/fixtures/dashboard-layout.json";
import live from "@/test/fixtures/dashboard-live.json";
import operations from "@/test/fixtures/dashboard-operations.json";
import viewer from "@/test/fixtures/dashboard-viewer.json";

import { arrange } from "./arrange";
import { dashboardSummarySchema, layoutSettingsSchema, sectionKeys } from "./contract";

// Fixtures are real API responses captured from the backend (see docs/development.md), so these
// tests prove the frontend contract matches what the API actually sends.
describe("dashboard contract", () => {
  it.each([
    ["live", live],
    ["operations", operations],
    ["viewer", viewer],
    ["demo", demo],
  ])("parses a real %s response", (_, payload) => {
    const r = dashboardSummarySchema.safeParse(payload);
    expect(r.success, JSON.stringify(r.error?.issues.slice(0, 3))).toBe(true);
  });

  it("parses layout settings", () => {
    expect(layoutSettingsSchema.safeParse(layout).success).toBe(true);
  });

  it("never pairs data with unavailable provenance", () => {
    for (const payload of [live, operations, viewer, demo]) {
      const s = dashboardSummarySchema.parse(payload);
      for (const key of sectionKeys) {
        const section = s[key];
        if (section.state !== "ready") expect(section.data, key).toBeNull();
        else expect(["live", "demo"]).toContain(section.provenance);
      }
    }
  });
});

describe("arrange", () => {
  it("collapses unavailable sections for a real organisation", () => {
    const a = arrange(dashboardSummarySchema.parse(live));
    // Incidents are live from the start (zero is a real count); insights need data first.
    expect(a.panels.map((p) => p.key)).toEqual(["getting_started", "incidents", "team", "approvals", "activity"]);
    expect(a.unavailable.map((u) => u.key)).toEqual(["insights", "fill_rate", "workflows", "integrations"]);
  });

  it("shows live insights, incidents and stock risk once data arrives", () => {
    const s = dashboardSummarySchema.parse(operations);
    expect(s.insights.provenance).toBe("live");
    expect(s.insights.data?.map((i) => i.severity)).toEqual(["critical", "high"]);
    const a = arrange(s);
    expect(a.panels.map((p) => p.key)).toEqual(expect.arrayContaining(["insights", "incidents", "integrations"]));
    expect(s.approvals.data?.map((x) => x.ref)).toEqual(["PR-0001"]);
    expect(s.workflows.data?.[0].awaiting_approval).toBe(1);
    expect(s.inventory_risk.data).toEqual([{ location: "Leeds DC", skus_at_risk: 1, skus_tracked: 2 }]);
    expect(a.unavailable.map((u) => u.key)).not.toContain("insights");
  });

  it("omits restricted sections entirely", () => {
    const a = arrange(dashboardSummarySchema.parse(viewer));
    const keys = [...a.panels.map((p) => p.key), ...a.unavailable.map((u) => u.key)];
    expect(keys).not.toContain("team");
    expect(keys).not.toContain("activity");
  });

  it("renders every operational section for a demo organisation", () => {
    const a = arrange(dashboardSummarySchema.parse(demo));
    expect(a.unavailable).toEqual([]);
    expect(a.panels.map((p) => p.key)).toEqual(
      expect.arrayContaining(["insights", "fill_rate", "approvals", "incidents", "workflows", "integrations", "activity"]),
    );
    expect(a.panels.map((p) => p.key)).not.toContain("getting_started");
  });

  it("hides a completed setup checklist", () => {
    const s = dashboardSummarySchema.parse(live);
    const done = { ...s, getting_started: { ...s.getting_started, data: s.getting_started.data!.map((st) => ({ ...st, done: true })) } };
    expect(arrange(done).panels.map((p) => p.key)).not.toContain("getting_started");
  });
});
