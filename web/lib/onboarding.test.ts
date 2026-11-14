import { describe, expect, it } from "vitest";
import { FIRST_RUN_TRIES, isFirstRunVisible } from "./onboarding";

describe("first-run guide", () => {
  it("has three deterministic in-app routes", () => {
    expect(FIRST_RUN_TRIES.map((item) => item.href)).toEqual([
      "/?w=7d",
      "/research?s=CREDITACC",
      "/people?q=HDFC%20Bank",
    ]);
  });

  it("is hidden only after an explicit dismissal", () => {
    expect(isFirstRunVisible(null)).toBe(true);
    expect(isFirstRunVisible("1")).toBe(false);
  });
});
