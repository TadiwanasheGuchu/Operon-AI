import { describe, expect, it } from "vitest";

import { groupModules, NAV_MODULES, sidebarModules, visibleModules } from "./registry";

const all = () => true;
const none = () => false;

describe("navigation registry", () => {
  it("never exposes unimplemented modules", () => {
    const visible = visibleModules({ showInternal: true, can: all });
    expect(visible.every((m) => m.implemented)).toBe(true);
    expect(visible.map((m) => m.id)).not.toContain("agents");
    expect(visible.map((m) => m.id)).toContain("integrations");
  });

  it("hides internal pages in production builds", () => {
    const ids = visibleModules({ showInternal: false, can: all }).map((m) => m.id);
    expect(ids).not.toContain("components");
    expect(ids).toContain("members");
  });

  it("hides administration from people without permission", () => {
    const ids = sidebarModules({ showInternal: false, can: none }).map((m) => m.id);
    expect(ids).toEqual(["overview"]);
  });

  it("shows only what a permission grants", () => {
    const ids = sidebarModules({ showInternal: false, can: (p) => p === "audit.read" }).map((m) => m.id);
    expect(ids).toEqual(["overview", "audit"]);
  });

  it("keeps account pages out of the sidebar", () => {
    const ids = sidebarModules({ showInternal: false, can: all }).map((m) => m.id);
    expect(ids).not.toContain("security");
    expect(visibleModules({ showInternal: false, can: all }).map((m) => m.id)).toContain("security");
  });

  it("omits empty groups", () => {
    expect(groupModules(sidebarModules({ showInternal: false, can: none })).map((g) => g.group)).toEqual(["operate"]);
  });

  it("has unique ids and hrefs", () => {
    expect(new Set(NAV_MODULES.map((m) => m.id)).size).toBe(NAV_MODULES.length);
    expect(new Set(NAV_MODULES.map((m) => m.href)).size).toBe(NAV_MODULES.length);
  });
});
