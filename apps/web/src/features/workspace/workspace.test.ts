import { describe, expect, it } from "vitest";

import { initials } from "./workspace";

describe("initials", () => {
  it.each([
    ["Harbour & Vale Distribution", "HV"],
    ["Ana Okafor", "AO"],
    ["Acme", "AC"],
    ["  émile   zola ", "ÉZ"],
    ["", "—"],
  ])("%s → %s", (name, expected) => expect(initials(name)).toBe(expected));
});
