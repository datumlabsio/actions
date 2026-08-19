import { describe, expect, it } from "vitest";
import { greeting } from "./greeting";

describe("greeting", () => {
  it("greets a name", () => {
    expect(greeting("Datum")).toBe("Hello, Datum");
  });

  it("trims surrounding space", () => {
    expect(greeting("  Datum  ")).toBe("Hello, Datum");
  });

  it("falls back when the name is blank", () => {
    expect(greeting("   ")).toBe("Hello, there");
  });
});
