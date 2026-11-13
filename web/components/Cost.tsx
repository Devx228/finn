"use client";

import { useEffect, useState } from "react";
import { type Loaded, loadWithFallback } from "@/lib/api";
import type { CostSummary } from "@/lib/types";

const H = "mb-2 text-[12px] font-semibold uppercase tracking-wider text-ink-3";
const n = (x: number) => x.toLocaleString("en-IN");

/** Under the hood: every model call, hit or miss, and how much work rules did instead. */
export function CostView() {
  const [d, setD] = useState<Loaded<CostSummary> | null | undefined>(undefined);
  useEffect(() => {
    loadWithFallback<CostSummary>("/api/cost", "cost_summary.json")
      .then(setD)
      .catch(() => setD(null));
  }, []);
  if (d === undefined) return <p className="text-[14px] text-ink-3">Loading…</p>;
  if (d === null) return <p className="text-[14px] text-ink-2">The cost ledger hasn&apos;t been computed yet.</p>;
  const c = d.data;
  const t = c.totals;
  const ruleShare = c.filings.total ? Math.round((c.filings.by_rules / c.filings.total) * 100) : 0;
  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-[22px] font-semibold tracking-tight">Under the hood</h1>
        <p className="text-[14px] text-ink-2">What it took to compute what you see. Every model call is logged.</p>
      </header>

      <section className="grid grid-cols-2 gap-2">
        <Stat label="Model calls" value={n(t.model_calls)} sub={`${t.cache_hit_rate ?? 0}% answered from cache`} />
        <Stat label="Actual cost" value={`₹${n(t.actual_cost_inr)}`} sub="free tiers + a local model" />
        <Stat label="Filings classified" value={n(c.filings.total)} sub={`${ruleShare}% by rules, no model`} />
        <Stat
          label="Tokens read"
          value={n(t.input_tokens)}
          sub={`${n(t.output_tokens)} written`}
        />
      </section>

      <section>
        <h2 className={H}>By model</h2>
        <div className="overflow-x-auto rounded-lg border border-line bg-surface">
          <table className="w-full text-[12px] tabular-nums">
            <thead className="text-ink-3">
              <tr>
                <th className="px-2 py-1.5 text-left font-normal">Model</th>
                <th className="px-2 py-1.5 text-right font-normal">Calls</th>
                <th className="px-2 py-1.5 text-right font-normal">Cached</th>
                <th className="px-2 py-1.5 text-right font-normal">Failed</th>
                <th className="px-2 py-1.5 text-right font-normal">Avg s</th>
              </tr>
            </thead>
            <tbody>
              {c.by_model.map((m) => (
                <tr key={`${m.provider}:${m.model}`} className="border-t border-line">
                  <td className="px-2 py-1.5">
                    <span className="block">{m.model}</span>
                    <span className="text-[11px] text-ink-3">{m.provider}</span>
                  </td>
                  <td className="px-2 py-1.5 text-right">{n(m.calls)}</td>
                  <td className="px-2 py-1.5 text-right">{n(m.cache_hits)}</td>
                  <td className="px-2 py-1.5 text-right">{n(m.failed)}</td>
                  <td className="px-2 py-1.5 text-right">
                    {m.avg_latency_ms !== null ? (m.avg_latency_ms / 1000).toFixed(1) : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section>
        <h2 className={H}>By task</h2>
        <ul className="divide-y divide-line rounded-lg border border-line bg-surface px-3 text-[13px]">
          {c.by_purpose.map((p) => (
            <li key={p.purpose} className="flex justify-between py-1.5">
              <span>{p.purpose.replaceAll("_", " ")}</span>
              <span className="tabular-nums text-ink-2">
                {n(p.calls)} · {n(p.cache_hits)} cached
              </span>
            </li>
          ))}
        </ul>
      </section>

      <section className="text-[11px] leading-snug text-ink-3">
        <p>{c.note}</p>
        <p className="mt-1">
          Transcripts read: {Object.entries(c.documents_read).map(([k, v]) => `${v} from ${k}`).join(" · ")}.
          {t.unpriced_calls > 0 && ` ${n(t.unpriced_calls)} hosted calls have no verified list price, so none is shown.`}
        </p>
        <p className="mt-1">As of {new Date(c.as_of).toLocaleString("en-IN", { dateStyle: "medium", timeStyle: "short" })}.</p>
      </section>
    </div>
  );
}

function Stat({ label, value, sub }: { label: string; value: string; sub: string }) {
  return (
    <div className="rounded-lg border border-line bg-surface px-3 py-2">
      <p className="text-[11px] text-ink-3">{label}</p>
      <p className="text-[20px] font-semibold tabular-nums">{value}</p>
      <p className="text-[11px] text-ink-3">{sub}</p>
    </div>
  );
}
