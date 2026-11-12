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
});
