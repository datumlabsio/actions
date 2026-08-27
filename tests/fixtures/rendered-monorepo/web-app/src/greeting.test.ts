import { describe, expect, it } from "vitest";
import { greeting } from "./greeting";

// A starter test that actually asserts something. DES §11: coverage shows code
// ran, not that the test checks anything — so the example checks behaviour,
// including the edge case, rather than just calling the function.
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
