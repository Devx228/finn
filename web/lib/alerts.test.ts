import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { type AlertInputs, evaluate } from "./alerts";

// Same fixture and expectations as api/tests/test_alerts.py: the two implementations must agree.
const data = JSON.parse(readFileSync("../api/tests/fixtures/alerts_case.json", "utf8")) as AlertInputs;

describe("alert rules", () => {
  it("fires volume, price and category alerts at default thresholds", () => {
    const a = evaluate(data, data.defaults);
    expect(a.map((x) => x.kind).sort()).toEqual(["filing", "price", "volume"]);
  });
  it("a stricter threshold fires fewer alerts", () => {
    expect(evaluate(data, { ...data.defaults, volume_x: 4, move_pct: 7 }).map((x) => x.kind)).toEqual(["filing"]);
  });
  it("relative to NIFTY the +6% day is only +3%", () => {
    const a = evaluate(data, { ...data.defaults, vs_nifty: true });
    expect(a.filter((x) => x.kind === "price")).toHaveLength(0);
  });
});
