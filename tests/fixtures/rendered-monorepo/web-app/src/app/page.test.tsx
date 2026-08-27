import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import Page from "./page";

// A component test as well as a unit test, because the archetype ships
// @testing-library/react and a starter that never uses it teaches the wrong
// habit. DES §11: the test has to check something.
describe("Page", () => {
  it("renders the greeting as a heading", () => {
    render(<Page />);
    expect(screen.getByRole("heading", { name: "Hello, Rendered Monorepo" })).toBeDefined();
  });
});
