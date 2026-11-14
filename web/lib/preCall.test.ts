import { describe, expect, it } from "vitest";
import { preCallReplayHref } from "./preCall";

describe("pre-call replay", () => {
  it("opens Today at the evidence cutoff date", () => {
    expect(preCallReplayHref("2026-04-30")).toBe("/?w=7d&as_of=2026-04-30");
  });
});
