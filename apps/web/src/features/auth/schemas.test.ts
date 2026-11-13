import { describe, expect, it } from "vitest";

import { loginSchema, registerSchema, resetSchema, safeNext } from "./schemas";

describe("safeNext", () => {
  it.each([
    ["/admin/members", "/admin/members"],
    ["/invite?token=abc", "/invite?token=abc"],
    [null, "/overview"],
    ["https://evil.example", "/overview"],
    ["//evil.example", "/overview"],
    ["/\\evil.example", "/overview"],
  ])("%s → %s", (next, expected) => expect(safeNext(next)).toBe(expected));
});

describe("auth schemas", () => {
  it("normalises email and requires a password", () => {
    const r = loginSchema.safeParse({ email: "  Ana@Acme.EXAMPLE ", password: "" });
    expect(r.success).toBe(false);
    expect(loginSchema.parse({ email: " Ana@Acme.EXAMPLE", password: "x" }).email).toBe("ana@acme.example");
  });

  it("enforces the minimum password length on registration", () => {
    const r = registerSchema.safeParse({ full_name: "A", email: "a@b.example", password: "short", organisation_name: "X" });
    expect(r.success).toBe(false);
    expect(r.error?.issues[0].path).toEqual(["password"]);
  });

  it("requires matching passwords on reset", () => {
    const r = resetSchema.safeParse({ password: "long enough password", confirm: "different password" });
    expect(r.error?.issues[0].path).toEqual(["confirm"]);
  });
});
