"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import { CandidateRow } from "@/components/Network";
import { type Loaded, loadWithFallback } from "@/lib/api";
import { formatCr } from "@/lib/format";
import type { GuidancePoint, GuidanceTrack, Quarter, Research, ResearchIndex } from "@/lib/types";

const H = "mb-2 text-[12px] font-semibold uppercase tracking-wider text-ink-3";

const VERDICT: Record<string, { icon: string; cls: string }> = {
  delivered: { icon: "✓", cls: "text-up" },
  "on track": { icon: "✓", cls: "text-up" },
  beat: { icon: "▲", cls: "text-up" },
  ahead: { icon: "▲", cls: "text-up" },
  missed: { icon: "✕", cls: "text-down" },
  behind: { icon: "▼", cls: "text-down" },
  "not comparable": { icon: "≠", cls: "text-ink-3" },
  unverifiable: { icon: "·", cls: "text-ink-3" },
};

export function ResearchView() {
  const params = useSearchParams();
  const router = useRouter();
  const [index, setIndex] = useState<ResearchIndex | null>(null);
  const sym = (params.get("s") ?? "INFY").toUpperCase();
  const [res, setRes] = useState<{ sym: string; r: Loaded<Research> | null } | null>(null);
  const [q, setQ] = useState("");

  useEffect(() => {
    loadWithFallback<ResearchIndex>("/api/research", "research_index.json")
      .then((d) => setIndex(d.data))
      .catch(() => setIndex({ companies: [] }));
  }, []);

  useEffect(() => {
    let live = true;
    loadWithFallback<Research>(`/api/research/${encodeURIComponent(sym)}`, `research_${sym}.json`)
      .then((r) => live && setRes({ sym, r }))
      .catch(() => live && setRes({ sym, r: null }));
    return () => {
      live = false;
    };
  }, [sym]);

  const go = (s: string) => router.replace(`/research?s=${encodeURIComponent(s.trim().toUpperCase())}`);
  const cur = res?.sym === sym ? res.r : undefined;

  return (
    <div>
      <header className="mb-3">
        <h1 className="text-[22px] font-semibold tracking-tight">Research</h1>
        <p className="text-[14px] text-ink-2">Promised vs delivered, from the company&apos;s own filings and calls.</p>
      </header>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          if (q.trim()) go(q);
        }}
        className="mb-2 flex gap-2"
      >
        <label htmlFor="sym" className="sr-only">
          NSE symbol
        </label>
        <input
          id="sym"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Any NSE symbol, e.g. KAYNES"
          autoCapitalize="characters"
          className="h-11 flex-1 rounded-lg border border-line bg-surface px-3 text-[15px] placeholder:text-ink-3"
        />
        <button className="h-11 rounded-lg bg-ink px-4 text-[14px] font-semibold text-bg">Open</button>
      </form>
      <div className="-mx-4 mb-4 flex gap-1.5 overflow-x-auto px-4 pb-1">
        {(index?.companies ?? []).map((c) => (
          <button
            key={c.symbol}
            onClick={() => go(c.symbol)}
            className={`h-9 shrink-0 rounded-full border px-3 text-[13px] ${
              c.symbol === sym ? "border-ink bg-ink text-bg" : "border-line text-ink-2"
            }`}
          >
            {c.symbol}
          </button>
        ))}
      </div>
      {cur === undefined && <p className="text-[14px] text-ink-3">Loading {sym}…</p>}
      {cur === null && (
        <div className="rounded-lg border border-line bg-surface px-3 py-3 text-[14px] text-ink-2">
          <p className="font-medium text-ink">No research view for {sym} yet.</p>
          <p className="mt-1 text-[13px]">
            The engine works on any NSE ticker with XBRL results and call transcripts: the worker runs{" "}
            <code className="rounded bg-bg px-1">finn research {sym}</code>, which fetches the last four
            transcripts once (politely, cached) and builds this page. The hosted API can&apos;t reach NSE, so
            that step runs on the worker, not on demand from your phone.
          </p>
        </div>
      )}
      {cur && <Body r={cur.data} />}
    </div>
  );
}

function Body({ r }: { r: Research }) {
  const tracks = r.guidance;
  const checkable = tracks.filter((t) => t.points.some((p) => p.unit === "%"));
  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-[19px] font-semibold leading-tight">{r.name}</h2>
        <p className="text-[12px] text-ink-3">
          {r.industry ?? r.format} · {r.calls.length} earnings calls · {r.quarters.length} quarters of filings
        </p>
      </div>

      <section>
        <h2 className={H}>Promised vs delivered</h2>
        {tracks.length === 0 ? (
          <p className="rounded-lg border border-line bg-surface px-3 py-3 text-[13px] text-ink-2">
            {r.calls.length === 0
              ? "No earnings-call transcripts filed recently, so there is no guidance to hold management to. The numbers below still come from the filings."
              : "Management gave no explicit numeric guidance in the last four calls (we only count verbatim targets)."}
          </p>
        ) : (
          <div className="space-y-3">
            {(checkable.length ? checkable : tracks).map((t) => (
              <TrackCard key={`${t.metric}-${t.period}`} t={t} />
            ))}
            {checkable.length > 0 && tracks.length > checkable.length && (
              <OtherTracks tracks={tracks.filter((t) => !checkable.includes(t))} />
            )}
          </div>
        )}
      </section>

      {(r.signals.bull.length > 0 || r.signals.bear.length > 0) && (
        <section>
          <h2 className={H}>Bull vs bear — from the numbers</h2>
          <div className="grid grid-cols-2 gap-2">
            <Case title="Bull" items={r.signals.bull} cls="text-up" />
            <Case title="Bear" items={r.signals.bear} cls="text-down" />
          </div>
        </section>
      )}

      <Trajectory qs={r.quarters} format={r.format} />

      {r.network.length > 0 && (
        <section>
          <h2 className={H}>Who to call about {r.symbol}</h2>
          <ul className="divide-y divide-line rounded-lg border border-line bg-surface px-3">
            {r.network.map((c) => (
              <CandidateRow key={c.id} c={c} />
            ))}
          </ul>
        </section>
      )}

      <section className="text-[11px] leading-snug text-ink-3">
        <p>{r.sources}</p>
        <ul className="mt-1 space-y-0.5">
          {r.calls.map((c) => (
            <li key={c.url}>
              <a href={c.url} target="_blank" rel="noreferrer" className="underline">
                {c.label} transcript
              </a>{" "}
              · {c.pages} pages · {c.n_items} guidance items
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}

function Case({ title, items, cls }: { title: string; items: string[]; cls: string }) {
  return (
    <div className="rounded-lg border border-line bg-surface px-3 py-2">
      <h3 className={`text-[13px] font-semibold ${cls}`}>{title}</h3>
      {items.length ? (
        <ul className="mt-1 space-y-1.5 text-[13px] leading-snug text-ink-2">
          {items.map((x) => (
            <li key={x}>{x}</li>
          ))}
        </ul>
      ) : (
        <p className="mt-1 text-[13px] text-ink-3">Nothing in the numbers.</p>
      )}
    </div>
  );
}

function band(p: GuidancePoint): string {
  const u = p.unit === "%" ? "%" : ` ${p.unit ?? ""}`;
  return p.low === p.high ? `${p.low}${u}` : `${p.low}–${p.high}${u}`;
}

function TrackCard({ t }: { t: GuidanceTrack }) {
  const [open, setOpen] = useState<number | null>(null);
  const v = VERDICT[t.verdict] ?? VERDICT.unverifiable;
  const pct = t.points.every((p) => p.unit === "%");
  const vals = t.points.flatMap((p) => [p.low, p.high]);
  if (t.actual && t.actual.unit === "%" && t.verdict !== "not comparable") vals.push(t.actual.value);
  const lo = Math.min(...vals);
  const hi = Math.max(...vals);
  const pad = Math.max(0.5, (hi - lo) * 0.15);
  const x = (n: number) => ((n - (lo - pad)) / (hi + pad - (lo - pad))) * 100;
  const showActual = pct && t.actual && t.actual.unit === "%" && t.verdict !== "not comparable";
  return (
    <article className="rounded-lg border border-line bg-surface px-3 py-3">
      <div className="flex items-baseline justify-between gap-2">
        <h3 className="text-[15px] font-semibold">
          {t.period} {t.label.toLowerCase()}
        </h3>
        <span className={`shrink-0 text-[13px] font-semibold ${v.cls}`}>
          {v.icon} {t.verdict}
        </span>
      </div>
      <p className="mt-0.5 text-[13px] leading-snug text-ink-2">{t.verdict_why}</p>

      <div className="mt-3 space-y-1">
        {t.points.map((p, i) => (
          <button
            key={i}
            onClick={() => setOpen(open === i ? null : i)}
            aria-expanded={open === i}
            className="grid w-full grid-cols-[5.5rem_1fr_4.5rem] items-center gap-2 text-left"
          >
            <span className="text-[12px] text-ink-3">{p.call.replace(" call", "")}</span>
            {pct ? (
              <span className="relative h-5">
                <span className="absolute inset-x-0 top-1/2 h-px bg-line" />
                <span
                  className="absolute top-1/2 h-2.5 -translate-y-1/2 rounded bg-accent/70"
                  style={{ left: `${x(p.low)}%`, width: `max(4px, ${x(p.high) - x(p.low)}%)` }}
                  title={band(p)}
                />
                {showActual && (
                  <span
                    className="absolute inset-y-0 w-0.5 bg-ink"
                    style={{ left: `${x(t.actual!.value)}%` }}
                    aria-hidden
                  />
                )}
              </span>
            ) : (
              <span className="text-[13px]">{band(p)}</span>
            )}
            <span className="text-right text-[12px] tabular-nums">
              {pct && <span className="block">{band(p)}</span>}
              <span
                className={
                  p.change === "cut" ? "text-down" : p.change === "raised" ? "text-up" : "text-ink-3"
                }
              >
                {p.change === "cut" ? "▼ cut" : p.change === "raised" ? "▲ raised" : p.change}
              </span>
            </span>
          </button>
        ))}
      </div>
      {showActual && (
        <p className="mt-1 flex items-center gap-1.5 text-[12px] text-ink-3">
          <span className="inline-block h-3 w-0.5 bg-ink" aria-hidden /> filings: {t.actual!.value}% (
          {t.actual!.span}, {t.actual!.basis})
        </p>
      )}
      {open !== null && <Quote p={t.points[open]} />}
      {open === null && <p className="mt-1 text-[11px] text-ink-3">Tap a call to see management&apos;s words.</p>}
    </article>
  );
}

function Quote({ p }: { p: GuidancePoint }) {
  return (
    <blockquote className="mt-2 border-l-2 border-line pl-3 text-[13px] leading-snug text-ink-2">
      “{p.quote}”
      <footer className="mt-1 text-[11px] text-ink-3">
        {p.call}, {p.call_date}
        {p.page ? `, p. ${p.page}` : ""} ·{" "}
        <a href={p.url} target="_blank" rel="noreferrer" className="underline">
          transcript on NSE
        </a>{" "}
        · {p.by === "rules" ? "matched by rule" : "extracted by model, verified verbatim"}
      </footer>
    </blockquote>
  );
}

function OtherTracks({ tracks }: { tracks: GuidanceTrack[] }) {
  return (
    <details className="rounded-lg border border-line bg-surface">
      <summary className="flex min-h-11 cursor-pointer items-center justify-between px-3 text-[14px]">
        <span>Other guidance (not checkable from filings)</span>
        <span className="text-ink-3">{tracks.length}</span>
      </summary>
      <ul className="divide-y divide-line border-t border-line px-3">
        {tracks.map((t) => (
          <li key={`${t.metric}-${t.period}`} className="py-2 text-[13px] text-ink-2">
            {t.story}
          </li>
        ))}
      </ul>
    </details>
  );
}

function Trajectory({ qs, format }: { qs: Quarter[]; format: string }) {
  const data = qs.filter((q) => q.revenue !== null).slice(-8);
  const [sel, setSel] = useState<number | null>(null);
  if (data.length < 2) return null;
  const mk: keyof Quarter = format === "indas" ? "ebitda_margin" : "pat_margin";
  const mLabel = format === "indas" ? "EBITDA margin" : "PAT margin";
  const maxR = Math.max(...data.map((q) => q.revenue ?? 0));
  const margins = data.map((q) => q[mk] as number | null);
  const mv = margins.filter((m): m is number => m !== null);
  const mMin = Math.min(...mv);
  const mMax = Math.max(...mv);
  const W = 340;
  const bw = W / data.length;
  const i = sel ?? data.length - 1;
  const q = data[i];
  return (
    <section>
      <h2 className={H}>Trajectory · last {data.length} quarters</h2>
      <div className="rounded-lg border border-line bg-surface px-3 py-3">
        <p className="text-[13px] text-ink-2">
          <span className="font-semibold text-ink">{q.label}</span> · revenue {formatCr(q.revenue)}
          {q.revenue_yoy !== null && ` (${q.revenue_yoy > 0 ? "+" : ""}${q.revenue_yoy}% YoY)`} · {mLabel}{" "}
          {(q[mk] as number | null) ?? "—"}% · PAT {formatCr(q.pat)}
        </p>
        <p className="mt-2 text-[11px] text-ink-3">Revenue, ₹ cr</p>
        <svg viewBox={`0 0 ${W} 96`} className="w-full" role="img" aria-label="Quarterly revenue">
          {data.map((d, k) => {
            const h = ((d.revenue ?? 0) / maxR) * 80;
            return (
              <g key={d.end} onMouseEnter={() => setSel(k)} onClick={() => setSel(k)} className="cursor-pointer">
                <rect x={k * bw} y={0} width={bw} height={96} fill="transparent" />
                <rect
                  x={k * bw + 3}
                  y={84 - h}
                  width={bw - 6}
                  height={h}
                  rx={4}
                  className={k === i ? "fill-accent" : "fill-accent/40"}
                />
                <text x={k * bw + bw / 2} y={95} textAnchor="middle" className="fill-ink-3 text-[9px]">
                  {d.label.replace(/^(Q\d) FY(\d\d)$/, "$1'$2")}
                </text>
              </g>
            );
          })}
        </svg>
        {mv.length > 1 && (
          <>
            <p className="mt-2 text-[11px] text-ink-3">
              {mLabel}, % ({mMin}–{mMax})
            </p>
            <svg viewBox={`0 0 ${W} 44`} className="w-full" role="img" aria-label={mLabel}>
              <polyline
                fill="none"
                strokeWidth={2}
                className="stroke-ink-2"
                points={margins
                  .map((m, k) =>
                    m === null ? null : `${k * bw + bw / 2},${36 - ((m - mMin) / (mMax - mMin || 1)) * 30}`,
                  )
                  .filter(Boolean)
                  .join(" ")}
              />
              {margins.map((m, k) =>
                m === null ? null : (
                  <circle
                    key={k}
                    cx={k * bw + bw / 2}
                    cy={36 - ((m - mMin) / (mMax - mMin || 1)) * 30}
                    r={k === i ? 4 : 2.5}
                    className={k === i ? "fill-ink stroke-surface" : "fill-ink-2"}
                    strokeWidth={2}
                    onMouseEnter={() => setSel(k)}
                  />
                ),
              )}
            </svg>
          </>
        )}
        <details className="mt-2">
          <summary className="min-h-9 cursor-pointer text-[12px] text-ink-3">Table</summary>
          <table className="w-full text-[12px] tabular-nums">
            <thead className="text-ink-3">
              <tr>
                <th className="text-left font-normal">Quarter</th>
                <th className="text-right font-normal">Revenue</th>
                <th className="text-right font-normal">YoY</th>
                <th className="text-right font-normal">{format === "indas" ? "EBITDA %" : "PAT %"}</th>
                <th className="text-right font-normal">PAT</th>
              </tr>
            </thead>
            <tbody>
              {data.map((d) => (
                <tr key={d.end} className="border-t border-line">
                  <td className="py-1">{d.label}</td>
                  <td className="text-right">{formatCr(d.revenue)}</td>
                  <td className="text-right">{d.revenue_yoy ?? "—"}</td>
                  <td className="text-right">{(d[mk] as number | null) ?? "—"}</td>
                  <td className="text-right">{formatCr(d.pat)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </details>
      </div>
    </section>
  );
}
