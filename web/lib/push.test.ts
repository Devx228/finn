import { describe, expect, it } from "vitest";
import { briefPushUrl } from "./push";

describe("web push deep links", () => {
  it("opens the related seven-day brief card", () => {
    expect(briefPushUrl("42")).toBe("/?w=7d&item=42#brief-42");
  });

  it("escapes an opaque item id", () => {
    expect(briefPushUrl("x/y")).toBe("/?w=7d&item=x%2Fy#brief-x%2Fy");
  });
});
