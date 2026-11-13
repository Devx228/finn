import { describe, expect, it } from "vitest";
import { type DirectoryEntry, search, terms } from "./whoKnows";

const p = (id: number, name: string, career: DirectoryEntry["career"], themes: string[], symbols: string[], warmth: number) =>
  ({ id, name, synthetic: true, headline: null, how_known: null, last_contact: null, warmth, warmth_label: "", warmth_why: "", career, themes, symbols }) as DirectoryEntry;

const dir = [
  p(1, "Varun Bhatia", [{ org: "HDFC Bank Limited", title: "Head of FP&A", span: "2011–now", current: true }], ["banking"], ["HDFCBANK"], 0.38),
  p(2, "Asha Rao", [{ org: "ICICI Bank Limited", title: "Credit Risk", span: "2014–2019", current: false }], ["banking"], [], 0.8),
  p(3, "Neel Shah", [{ org: "Tata Steel Limited", title: "VP Sales", span: "2018–now", current: true }], ["metals"], ["TATASTEEL"], 0.5),
];

describe("who knows X", () => {
  it("drops filler words", () => {
    expect(terms("Who do I know at HDFC Bank?")).toEqual(["hdfc", "bank"]);
  });
  it("finds people at a company, current employees first", () => {
    const h = search(dir, "who do I know at HDFC Bank");
    expect(h.map((x) => x.person.id)).toEqual([1]);
    expect(h[0].why[0]).toContain("Works at HDFC Bank");
  });
  it("finds people by theme, warmer first among equals", () => {
    expect(search(dir, "who knows about banking").map((x) => x.person.id)).toEqual([2, 1]);
  });
  it("matches an NSE symbol and requires every word", () => {
    expect(search(dir, "TATASTEEL").map((x) => x.person.id)).toEqual([3]);
    expect(search(dir, "banking steel")).toEqual([]);
  });
});
