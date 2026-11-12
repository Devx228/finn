import { describe, expect, it } from "vitest";
import { loadWithFallback } from "./api";
import { formatAsOf } from "./format";

function respond(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status });
}

describe("loadWithFallback", () => {
  it("returns live data when the API answers", async () => {
    const f = (async (url: string) =>
      url.startsWith("http://api") ? respond({ v: "live" }) : respond({ v: "snap" })) as typeof fetch;
    const r = await loadWithFallback<{ v: string }>("/x", "x.json", { base: "http://api", fetchFn: f });
    expect(r).toEqual({ data: { v: "live" }, source: "live" });
  });

  it("falls back to the snapshot on HTTP error", async () => {
    const f = (async (url: string) =>
      url.startsWith("http://api") ? respond({}, 500) : respond({ v: "snap" })) as typeof fetch;
    const r = await loadWithFallback<{ v: string }>("/x", "x.json", { base: "http://api", fetchFn: f });
    expect(r.source).toBe("snapshot");
    expect(r.data.v).toBe("snap");
  });

  it("falls back to the snapshot when the API is slower than the timeout", async () => {
    const f = ((url: string, init?: RequestInit) => {
      if (!url.startsWith("http://api")) return Promise.resolve(respond({ v: "snap" }));
      return new Promise<Response>((_, reject) =>
        init?.signal?.addEventListener("abort", () => reject(new Error("aborted"))),
      );
    }) as typeof fetch;
    const r = await loadWithFallback<{ v: string }>("/x", "x.json", {
      base: "http://api",
      timeoutMs: 20,
      fetchFn: f,
    });
    expect(r.source).toBe("snapshot");
  });

  it("throws when both API and snapshot fail", async () => {
    const f = (async () => respond({}, 503)) as typeof fetch;
    await expect(
      loadWithFallback("/x", "x.json", { base: "http://api", fetchFn: f }),
    ).rejects.toThrow();
  });
});

describe("formatAsOf", () => {
  it("renders in IST", () => {
    expect(formatAsOf("2026-11-12T09:30:00Z")).toBe("12 Nov, 15:00 IST");
  });
  it("formats crore and percent the Indian way", async () => {
    const { formatCr, formatPct } = await import("./format");
    expect(formatCr(21793.6)).toBe("₹21,794 cr");
    expect(formatCr(529.5)).toBe("₹529.5 cr");
    expect(formatCr(178_500)).toBe("₹1.79 lakh cr");
    expect(formatPct(12.34)).toEqual({ text: "▲ 12.3%", dir: "up" });
    expect(formatPct(-4)).toEqual({ text: "▼ 4.0%", dir: "down" });
    expect(formatPct(null).text).toBe("—");
  });
});
