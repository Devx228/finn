// Three layers of resilience (spec §5.3): live API → (Vercel cache, later) → bundled snapshot.
// If the API errors or takes longer than the timeout, render the committed snapshot instead.

export const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";
export const API_TIMEOUT_MS = Number(process.env.NEXT_PUBLIC_API_TIMEOUT_MS ?? 4000);

export type Source = "live" | "snapshot";

export interface Loaded<T> {
  data: T;
  source: Source;
}

type FetchFn = typeof fetch;

async function fetchJson<T>(url: string, timeoutMs: number, f: FetchFn): Promise<T> {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), timeoutMs);
  try {
    const r = await f(url, { signal: ctrl.signal, cache: "no-store" });
    if (!r.ok) throw new Error(`${url} → HTTP ${r.status}`);
    return (await r.json()) as T;
  } finally {
    clearTimeout(timer);
  }
}

/**
 * Load `apiPath` from the API; on any failure or timeout load `/snapshot/<snapshotFile>`.
 * Throws only when both fail.
 */
export async function loadWithFallback<T>(
  apiPath: string,
  snapshotFile: string,
  opts: { base?: string; timeoutMs?: number; fetchFn?: FetchFn } = {},
): Promise<Loaded<T>> {
  const f = opts.fetchFn ?? fetch;
  const base = opts.base ?? API_BASE;
  try {
    const data = await fetchJson<T>(`${base}${apiPath}`, opts.timeoutMs ?? API_TIMEOUT_MS, f);
    return { data, source: "live" };
  } catch {
    const data = await fetchJson<T>(`/snapshot/${snapshotFile}`, 10_000, f);
    return { data, source: "snapshot" };
  }
}

/** Fire-and-forget warm-up so a sleeping backend starts waking while the UI renders. */
export function warmUp(): void {
  fetch(`${API_BASE}/health`, { cache: "no-store" }).catch(() => {});
}
