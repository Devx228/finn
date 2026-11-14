import { describe, expect, it } from "vitest";
import type { AlertInputs } from "./alerts";
import { auditFilters } from "./filterAudit";
import type { Brief, BriefRow } from "./types";

function item(id: string, tier: "now" | "buried"): BriefRow {
  return {
    id,
    tier,
    symbol: "TEST",
    company: "Test Limited",
    ts: "2026-11-02T18:00:00+00:00",
    category: "results",
    category_label: "Results",
    sub_type: null,
    kind: "filing",
    headline: `${tier} item`,
    score: tier === "now" ? 80 : 10,
    components: {},
    pdf_url: "https://example.test/filing.pdf",
    filing_ids: [1],
    bundled: 0,
    card: null,
  };
}

function brief(now: BriefRow[], buried: BriefRow[]): Brief {
  return {
    window: "30d",
    as_of: "2026-11-10T12:00:00+05:30",
    placeholder: false,
    counts: { filings: now.length + buried.length, now: now.length, worth: 0, buried: buried.length },
    now,
    worth: [],
    buried: [{ label: "Routine", count: buried.length, items: buried }],
    source_credit: null,
  };
}

const inputs: AlertInputs = {
  as_of: "2026-11-10T12:00:00+05:30",
  defaults: { days: 30, move_pct: 6, volume_x: 4, vs_nifty: true, categories: [] },
  category_labels: {},
  nifty: [
    ["2026-11-02", 100, 1],
    ["2026-11-03", 100, 1],
    ["2026-11-04", 100, 1],
  ],
  companies: [
    {
      symbol: "TEST",
      name: "Test Limited",
      bars: [
        ["2026-11-02", 100, 1],
        ["2026-11-03", 93, 1],
        ["2026-11-04", 94, 1],
      ],
    },
  ],
  filings: [],
  credit: "Test prices",
};

describe("filter audit", () => {
  it("finds a buried item followed by a move beyond the relative threshold", () => {
    const result = auditFilters(brief([], [item("b", "buried")]), inputs);
    expect(result.buriedThenMoved[0]).toMatchObject({ id: "b", movePct: -7, relativePct: -7 });
  });

  it("does not call a Now item quiet until two sessions are observed", () => {
    const quietInputs = structuredClone(inputs);
    quietInputs.companies[0].bars[1][1] = 98;
    quietInputs.companies[0].bars[2][1] = 99;
    expect(auditFilters(brief([item("n", "now")], []), quietInputs).nowThenQuiet).toHaveLength(1);
    quietInputs.companies[0].bars.pop();
    expect(auditFilters(brief([item("n", "now")], []), quietInputs).nowThenQuiet).toHaveLength(0);
  });
});
