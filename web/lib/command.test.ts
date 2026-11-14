import { describe, expect, it } from "vitest";
import { type CommandCompany, localCommand } from "./command";

const companies: CommandCompany[] = [
  { symbol: "HDFCBANK", name: "HDFC Bank Limited", aliases: ["HDFC Bank"] },
  { symbol: "M&M", name: "Mahindra & Mahindra Limited", aliases: [] },
];

describe("command bar rules", () => {
  it("routes a known symbol without a model", () => {
    expect(localCommand("hdfcbank", companies)?.href).toBe("/research?s=HDFCBANK");
  });
  it("routes an exact company name while ignoring Limited", () => {
    expect(localCommand("HDFC Bank", companies)?.href).toBe("/research?s=HDFCBANK");
  });
  it("routes who-knows language to People with the query", () => {
    expect(localCommand("Who do I know at HDFC Bank?", companies)).toEqual({
      kind: "people",
      href: "/people?q=Who%20do%20I%20know%20at%20HDFC%20Bank%3F",
    });
  });
  it("leaves a natural-language request for the typed tool fallback", () => {
    expect(localCommand("Show HDFC Bank's latest filings", companies)).toBeNull();
  });
});
