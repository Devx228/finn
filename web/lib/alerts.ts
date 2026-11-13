// Mirrors api/finn/push/alerts.py `evaluate` exactly (tested on both sides) so a threshold change
// is applied instantly, with no round trip.

export interface AlertRules {
  volume_x: number;
  move_pct: number;
  vs_nifty: boolean;
  categories: string[];
  days: number;
}

export type Bar = [string, number | null, number];

export interface AlertInputs {
  as_of: string;
  defaults: AlertRules;
  category_labels: Record<string, string>;
  nifty: Bar[];
  companies: { symbol: string; name: string; bars: Bar[] }[];
  filings: { id: number; symbol: string; ts: string; category: string; headline: string; url: string | null }[];
  /** every filing date per holding, any category (a move with none nearby is unexplained) */
  disclosures?: Record<string, string[]>;
  credit: string;
}

export interface Alert {
  kind: "volume" | "price" | "filing";
  symbol: string;
  date: string;
  value: number | null;
  text: string;
  url?: string | null;
  no_disclosure?: boolean;
}

const DISCLOSURE_LOOKBACK_DAYS = 2;

const round1 = (x: number) => Math.round(x * 10) / 10;
const signed = (x: number) => `${x >= 0 ? "+" : "-"}${Math.abs(x).toFixed(1)}`;

function minusDays(iso: string, n: number): string {
  const d = new Date(`${iso}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() - n);
  return d.toISOString().slice(0, 10);
}

export function evaluate(data: AlertInputs, rules: AlertRules): Alert[] {
  const out: Alert[] = [];
  const nifty = new Map(data.nifty.map(([d, c]) => [d, c]));
  const nd = [...nifty.keys()].sort();
  const nret = new Map<string, number>();
  for (let i = 1; i < nd.length; i++) {
    const a = nifty.get(nd[i]);
    const b = nifty.get(nd[i - 1]);
    if (a != null && b) nret.set(nd[i], a / b - 1);
  }
  const days = data.companies.flatMap((c) => c.bars.map((b) => b[0]));
  if (!days.length) return out;
  const last = days.reduce((a, b) => (a > b ? a : b));
  const cutoff = minusDays(last, rules.days);
  const disc = data.disclosures;
  for (const c of data.companies) {
    const bars = c.bars;
    for (let i = 20; i < bars.length; i++) {
      const [d, close, vol] = bars[i];
      const prev = bars[i - 1][1];
      if (d < cutoff || close == null || !prev) continue;
      const avg = bars.slice(i - 20, i).reduce((s, b) => s + b[2], 0) / 20;
      const vx = avg ? vol / avg : 0;
      const r = (close / prev - 1) * 100;
      const rel = rules.vs_nifty ? r - (nret.get(d) ?? 0) * 100 : r;
      const hitV = vx >= rules.volume_x;
      const hitP = Math.abs(rel) >= rules.move_pct;
      if (!hitV && !hitP) continue;
      const parts: string[] = [];
      if (hitP) {
        parts.push(`${r > 0 ? "Up" : "Down"} ${Math.abs(r).toFixed(1)}% in a day` +
          (rules.vs_nifty ? ` (${signed(rel)}% vs NIFTY)` : ""));
      }
      if (hitV) {
        parts.push(parts.length ? `volume ${vx.toFixed(1)}× its 20-day average`
          : `Volume ${vx.toFixed(1)}× its 20-day average (${signed(r)}%)`);
      }
      const text = parts.length === 2 ? parts.join(" on ") : parts[0];
      let quiet: boolean | null = null;
      if (disc) {
        // two sessions before (a Monday move answers Friday's filing) and the day itself
        const lo = bars[Math.max(0, i - DISCLOSURE_LOOKBACK_DAYS)][0];
        quiet = !(disc[c.symbol] ?? []).some((x) => lo <= x && x <= d);
      }
      out.push({ kind: hitP ? "price" : "volume", symbol: c.symbol, date: d,
        value: hitP ? round1(r) : round1(vx),
        text: text + (quiet ? " — moved with no disclosure" : ""), no_disclosure: !!quiet });
    }
  }
  const cats = new Set(rules.categories);
  const seen = new Set<string>();
  for (const f of data.filings) {
    const key = `${f.symbol}|${f.ts.slice(0, 10)}|${f.headline}`;
    if (cats.has(f.category) && f.ts.slice(0, 10) >= cutoff && !seen.has(key)) {
      seen.add(key);
      out.push({ kind: "filing", symbol: f.symbol, date: f.ts.slice(0, 10), value: null,
        text: `${data.category_labels[f.category] ?? f.category}: ${f.headline}`, url: f.url });
    }
  }
  return out.sort((a, b) => (a.date === b.date ? (a.kind < b.kind ? 1 : -1) : a.date < b.date ? 1 : -1));
}
