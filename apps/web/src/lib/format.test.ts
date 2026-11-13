import { describe, expect, it } from "vitest";

import { formatCurrency, formatRelative } from "./format";

describe("format", () => {
  const now = new Date("2026-11-13T12:00:00Z");
  it.each([
    ["2026-11-13T11:59:30Z", "just now"],
    ["2026-11-13T11:56:00Z", "4 min ago"],
    ["2026-11-13T09:00:00Z", "3 h ago"],
    ["2026-11-11T12:00:00Z", "2 d ago"],
  ])("formatRelative(%s)", (iso, expected) => {
    expect(formatRelative(iso, now)).toBe(expected);
  });

  it("formats currency without minor units", () => {
    expect(formatCurrency(9700, "GBP")).toBe("£9,700");
  });
});
