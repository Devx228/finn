import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { type AlertInputs, evaluate } from "./alerts";

// Same fixture and expectations as api/tests/test_alerts.py: the two implementations must agree.
const data = JSON.parse(readFileSync("../api/tests/fixtures/alerts_case.json", "utf8")) as AlertInputs;

describe("alert rules", () => {
  it("one alert for volume and price on the same day, flagged when nothing was disclosed", () => {
    const a = evaluate(data, data.defaults);
    expect(a.map((x) => x.kind).sort()).toEqual(["filing", "price"]);
    const m = a.find((x) => x.kind === "price")!;
    expect(m.text).toContain("on volume");
    expect(m.no_disclosure).toBe(true);
    expect(m.text.endsWith("moved with no disclosure")).toBe(true);
  });
  it("a stricter threshold fires fewer alerts", () => {
    expect(evaluate(data, { ...data.defaults, volume_x: 4, move_pct: 7 }).map((x) => x.kind)).toEqual(["filing"]);
  });
  it("relative to NIFTY the +6% day is only +3%", () => {
    expect(evaluate(data, { ...data.defaults, vs_nifty: true }).map((x) => x.kind)).toEqual(["filing", "volume"]);
  });
  it("duplicate filing lines collapse", () => {
    const d = { ...data, filings: [...data.filings, { ...data.filings[0], id: 9 }] };
    expect(evaluate(d, data.defaults).filter((x) => x.kind === "filing")).toHaveLength(1);
  });
});
