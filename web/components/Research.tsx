"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { ResearchJobPanel } from "./ResearchJob";
import { useCallback, useEffect, useState } from "react";
import { GroupCard, HelpButton, LedgerHead, Legend, Scoreboard } from "@/components/Ledger";
import { CandidateRow } from "@/components/Network";
import { type Loaded, loadWithFallback } from "@/lib/api";
import { formatCr } from "@/lib/format";
import type {
  Business,
  GuidancePoint,
  GuidanceTrack,
  Quarter,
  Research,
  ResearchIndex,
} from "@/lib/types";

const H = "mb-2 text-[12px] font-semibold uppercase tracking-wider text-ink-3";

const VERDICT: Record<string, { icon: string; cls: string }> = {
  delivered: { icon: "✓", cls: "text-up" },
  "on track": { icon: "✓", cls: "text-up" },
  beat: { icon: "▲", cls: "text-up" },
  ahead: { icon: "▲", cls: "text-up" },
  missed: { icon: "✕", cls: "text-down" },
  behind: { icon: "▼", cls: "text-down" },
  pending: { icon: "…", cls: "text-ink-3" },
  "open-ended": { icon: "·", cls: "text-ink-3" },
  "not scored": { icon: "·", cls: "text-ink-3" },
  "met after cut": { icon: "✓", cls: "text-ink-2" },
  "missed after cut": { icon: "✕", cls: "text-down" },
  "beat raised": { icon: "▲", cls: "text-up" },
  "met revised": { icon: "✓", cls: "text-ink-2" },
};

export function ResearchView() {
  const params = useSearchParams();
  const router = useRouter();
  const [index, setIndex] = useState<ResearchIndex | null>(null);
  // default: the company the research set marks as hero (data/research_set.json), not a constant
  const hero = index?.companies.find((c) => c.hero)?.symbol ?? index?.companies[0]?.symbol;
  const sym = (params.get("s") ?? hero ?? "").toUpperCase();
  const [res, setRes] = useState<{ sym: string; r: Loaded<Research> | null } | null>(null);
  const [q, setQ] = useState("");
  const [reload, setReload] = useState(0);
  const bump = useCallback(() => setReload((n) => n + 1), []);

  useEffect(() => {
    loadWithFallback<ResearchIndex>("/api/research", "research_index.json")
      .then((d) => setIndex(d.data))
      .catch(() => setIndex({ companies: [] }));
  }, [reload]);

  useEffect(() => {
    if (!sym) return;
    let live = true;
    loadWithFallback<Research>(`/api/research/${encodeURIComponent(sym)}`, `research_${sym}.json`)
      .then((r) => live && setRes({ sym, r }))
      .catch(() => live && setRes({ sym, r: null }));
    return () => {
      live = false;
    };
  }, [sym, reload]);

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
      <div className="-mx-4 mb-4 flex gap-1.5 overflow-x-auto px-4 pb-1 [scrollbar-width:none]">
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
      {cur === null && <ResearchJobPanel key={sym} sym={sym} onReady={bump} />}
      {cur && <Body r={cur.data} />}
    </div>
  );
}

const FORMAT: Record<string, string> = { nbfc: "NBFC", bank: "Bank", indas: "Company" };

function Body({ r }: { r: Research }) {
  const tracks = r.guidance;
  const groups = r.groups ?? [];
  const firstResolved = groups.find((g) => g.resolved)?.id ?? null;
  const [openIds, setOpenIds] = useState<Set<string>>(() => new Set(firstResolved ? [firstResolved] : []));
  const toggle = (id: string) =>
    setOpenIds((s) => {
      const n = new Set(s);
      if (n.has(id)) n.delete(id);
      else n.add(id);
      return n;
    });
  const jump = (id: string) => {
    setOpenIds((s) => new Set(s).add(id));
    requestAnimationFrame(() => document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" }));
  };
  const grouped = new Set(groups.flatMap((g) => g.metrics.map((m) => `${m}|${g.period}`)));
  const rest = tracks.filter((t) => !grouped.has(`${t.metric}|${t.period}`));
  const sections: [string, string][] = [
    ["ledger", "Promise ledger"],
    ...(r.business ? ([["business", "Business"]] as [string, string][]) : []),
    ...(r.signals.bull.length || r.signals.bear.length ? ([["signals", "Bull vs bear"]] as [string, string][]) : []),
    ["financials", "Financials"],
    ...(r.network.length ? ([["people", "Who to call"]] as [string, string][]) : []),
  ];
  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-[19px] font-semibold leading-tight">{r.name}</h2>
        <p className="text-[12px] text-ink-3">
          {r.industry ?? FORMAT[r.format] ?? r.format} · {r.calls.length} earnings calls · {r.quarters.length}{" "}
          quarters of filings
        </p>
        {r.provenance && !r.provenance.reviewed && <Unreviewed asOf={r.as_of} />}
        <nav aria-label="On this page" className="-mx-4 mt-2 flex gap-1.5 overflow-x-auto px-4 pb-1 [scrollbar-width:none]">
          {sections.map(([id, label]) => (
            <a key={id} href={`#${id}`} className="h-8 shrink-0 rounded-full border border-line px-3 text-[12px] leading-8 text-ink-2">
              {label}
            </a>
          ))}
        </nav>
      </div>

      <section id="ledger" className="scroll-mt-4">
        <div className="mb-1 flex items-center justify-between gap-2">
          <h2 className={H + " mb-0"}>Promised vs delivered</h2>
          <HelpButton help={r.help} company={r.name} />
        </div>
        {r.ledger && <LedgerHead l={r.ledger} />}
        {tracks.length === 0 ? (
          <p className="rounded-lg border border-line bg-surface px-3 py-3 text-[13px] text-ink-2">
            {r.calls.length === 0
              ? "No earnings-call transcripts filed recently, so there is no guidance to hold management to. The numbers below still come from the filings."
              : `No numeric guidance found in the ${r.ledger?.calls_read ?? r.calls.length} calls read (only verbatim management targets count).`}
          </p>
        ) : (
          <div className="space-y-3">
            <Scoreboard tracks={tracks} groups={groups} onJump={jump} />
            {groups.length > 0 && <Legend />}
            {groups.map((g) => (
              <GroupCard key={g.id} g={g} open={openIds.has(g.id)} onToggle={() => toggle(g.id)} />
            ))}
            {groups.length === 0 &&
              tracks
                .filter((t) => t.verdict !== "not scored")
                .map((t) => <TrackCard key={`${t.metric}-${t.period}`} t={t} />)}
            {rest.filter((t) => t.verdict === "not scored").length > 0 && (
              <OtherTracks tracks={rest.filter((t) => t.verdict === "not scored")} />
            )}
          </div>
        )}
      </section>

      {r.business && (
        <div id="business" className="scroll-mt-4">
          <BusinessSnapshot b={r.business} />
        </div>
      )}

      {(r.signals.bull.length > 0 || r.signals.bear.length > 0) && (
        <section id="signals" className="scroll-mt-4">
          <h2 className={H}>Bull vs bear — from the numbers</h2>
          <div className="grid grid-cols-2 gap-2">
            <Case title="Bull" items={r.signals.bull} cls="text-up" />
            <Case title="Bear" items={r.signals.bear} cls="text-down" />
          </div>
        </section>
      )}

      <div id="financials" className="scroll-mt-4">
        <Trajectory qs={r.quarters} format={r.format} />
      </div>

      {r.network.length > 0 && (
        <section id="people" className="scroll-mt-4">
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
        <p className="mt-1">
          <a href="/cost" className="underline">
            Under the hood: what this cost to compute
          </a>
        </p>
        <ul className="mt-1 space-y-0.5">
          {r.calls.map((c) => (
            <li key={c.url}>
              <a href={c.url} target="_blank" rel="noreferrer" className="underline">
                {c.label} transcript
              </a>
              {c.source && c.source !== "NSE" ? ` (${c.source})` : ""}{" "}
              · {c.pages} pages · {c.n_items} guidance items
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}

/** What the company does, from its own segment note: mix, segment result ÷ revenue, YoY. */
/** What it does, in the company's own words from its latest annual report, with the page. */
function About({ a }: { a?: Business["about"] }) {
  if (!a) return null;
  if (!a.text) return <p className="mb-2 text-[13px] text-ink-3">{a.note}</p>;
  return (
    <blockquote className="mb-3 text-[14px] leading-snug">
      “{a.text}”
      <footer className="mt-1 text-[12px] text-ink-3">
        <a href={a.page ? `${a.url}#page=${a.page}` : a.url} target="_blank" rel="noreferrer" className="underline">
          {a.period} annual report, p. {a.page}
        </a>{" "}
        · the company&apos;s own words
      </footer>
    </blockquote>
  );
}

function BusinessSnapshot({ b }: { b: Business }) {
  if (!b.segments.length) {
    return (
      <section>
        <h2 className={H}>Business snapshot</h2>
        <About a={b.about} />
        <p className="rounded-lg border border-line bg-surface px-3 py-3 text-[13px] text-ink-2">
          {b.industry ? `${b.industry}. ` : ""}
          {b.note}
        </p>
      </section>
    );
  }
  const max = Math.max(...b.segments.map((s) => s.share ?? 0));
  return (
    <section>
      <h2 className={H}>
        Business snapshot · {b.year} segments
      </h2>
      <About a={b.about} />
      <div className="rounded-lg border border-line bg-surface px-3 py-3">
        {b.industry && <p className="mb-2 text-[13px] text-ink-2">{b.industry}</p>}
        <ul className="space-y-2">
          {b.segments.map((s) => (
            <li key={s.name} className="text-[13px]">
              <div className="flex items-baseline justify-between gap-2">
                <span className="truncate font-medium">{s.name}</span>
                <span className="shrink-0 tabular-nums text-ink-2">{s.share}%</span>
              </div>
              <div className="mt-1 h-1.5 rounded bg-line">
                <div
                  className="h-1.5 rounded bg-accent/70"
                  style={{ width: `${max ? ((s.share ?? 0) / max) * 100 : 0}%` }}
                  aria-hidden
                />
              </div>
              <p className="mt-0.5 text-[11px] tabular-nums text-ink-3">
                {formatCr(s.revenue)}
                {s.margin !== null && ` · result ${s.margin}% of revenue`}
                {s.yoy !== null && ` · ${s.yoy > 0 ? "+" : ""}${s.yoy}% YoY`}
              </p>
            </li>
          ))}
        </ul>
        <p className="mt-2 text-[11px] text-ink-3">
          Segment revenue and segment result as the company reports them ({b.basis}), from its{" "}
          {b.source?.xbrl ? (
            <a href={b.source.xbrl} target="_blank" rel="noreferrer" className="underline">
              full-year results filing
            </a>
          ) : (
            "results filing"
          )}
          . YoY only where the same segment appears a year earlier.
        </p>
      </div>
    </section>
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
  const v = VERDICT[t.verdict] ?? VERDICT["not scored"];
  const shown =
    t.verdict === "pending"
      ? `open · due ${t.period}`
      : t.verdict === "open-ended"
        ? "open · no due year"
        : t.verdict;
  const pct = t.points.every((p) => p.unit === "%");
  const vals = t.points.flatMap((p) => [p.low, p.high]);
  if (t.actual && t.actual.unit === "%") vals.push(t.actual.value);
  const lo = Math.min(...vals);
  const hi = Math.max(...vals);
  const pad = Math.max(0.5, (hi - lo) * 0.15);
  const x = (n: number) => ((n - (lo - pad)) / (hi + pad - (lo - pad))) * 100;
  const showActual = pct && t.actual && t.actual.unit === "%";
  const lowerBetter = t.metric === "credit_cost"; // lower guidance here is good news
  return (
    <article className="rounded-lg border border-line bg-surface px-3 py-3">
      <div className="flex items-baseline justify-between gap-2">
        <h3 className="text-[15px] font-semibold">
          {t.period} {t.label.toLowerCase()}
        </h3>
        <span className={`shrink-0 text-[13px] font-semibold ${v.cls}`}>
          {v.icon} {shown}
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
                  p.change === (lowerBetter ? "raised" : "cut")
                    ? "text-down"
                    : p.change === (lowerBetter ? "cut" : "raised")
                      ? "text-up"
                      : "text-ink-3"
                }
              >
                {p.change === "cut" ? "▼ cut" : p.change === "raised" ? "▲ raised" : p.change}
              </span>
            </span>
          </button>
        ))}
      </div>
      {t.actual && <Outcome t={t} marker={!!showActual} />}
      {t.cross_check && (
        <p className="mt-1 text-[11px] text-ink-3">
          Our cross-check from the filings:{" "}
          {t.cross_check.unit === "₹ cr" ? formatCr(t.cross_check.value) : `${t.cross_check.value}%`} (
          {t.cross_check.span}, {t.cross_check.basis}) — shown for comparison, never used for the verdict
        </p>
      )}
      {t.run_rate && <p className="mt-1 text-[12px] text-ink-2">{t.run_rate}</p>}
      {t.context && <p className="mt-1 text-[11px] text-ink-3">{t.context}</p>}
      {open !== null && <Quote p={t.points[open]} />}
      {open === null && <p className="mt-1 text-[11px] text-ink-3">Tap a call to see management&apos;s words.</p>}
    </article>
  );
}

const srcLabel = (s?: string) =>
  !s || s === "NSE"
    ? "transcript on NSE"
    : s.includes("by hand")
      ? "transcript on the company's IR site (downloaded by hand)"
      : "transcript on the company's IR site";

/** The end of the chain: what was actually reported, and where it is written down. */
function Outcome({ t, marker }: { t: GuidanceTrack; marker: boolean }) {
  const a = t.actual!;
  const val = a.unit === "₹ cr" ? formatCr(a.value) : `${a.value}%`;
  const src = a.source;
  return (
    <div className="mt-2 border-t border-line pt-2 text-[12px] leading-snug text-ink-2">
      <p className="flex items-center gap-1.5">
        {marker && <span className="inline-block h-3 w-0.5 shrink-0 bg-ink" aria-hidden />}
        <span>
          <span className="font-semibold text-ink">Outcome {val}</span> ({a.span}) · {a.basis}
        </span>
      </p>
      {src?.quote ? (
        <blockquote className="mt-1 border-l-2 border-line pl-3 text-ink-2">
          “{src.quote}”
          <footer className="mt-0.5 text-[11px] text-ink-3">
            {src.call}
            {src.page ? `, p. ${src.page}` : ""} ·{" "}
            <a href={src.url} target="_blank" rel="noreferrer" className="underline">
              {srcLabel(src.from)}
            </a>
          </footer>
        </blockquote>
      ) : src?.xbrl ? (
        <p className="mt-0.5 text-[11px] text-ink-3">
          Computed from the{" "}
          <a href={src.xbrl} target="_blank" rel="noreferrer" className="underline">
            XBRL results filing on NSE
          </a>
        </p>
      ) : null}
    </div>
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
          {srcLabel(p.source)}
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
        <span>Not scored (no company-reported or unambiguous figure)</span>
        <span className="text-ink-3">{tracks.length}</span>
      </summary>
      <ul className="divide-y divide-line border-t border-line px-3">
        {tracks.map((t) => (
          <li key={`${t.metric}-${t.period}`} className="py-2 text-[13px] text-ink-2">
            {t.story}
            <span className="block text-[11px] text-ink-3">{t.verdict_why}</span>
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

function Unreviewed({ asOf }: { asOf: string }) {
  // the exact time, which stays true however long after the run the page is opened
  const when = new Date(asOf).toLocaleString("en-IN", {
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
  return (
    <p className="mt-2 rounded-md border border-line bg-surface px-2 py-1.5 text-[12px] text-ink-2">
      Generated automatically ({when}); not reviewed. Every verdict links to its quote: check before relying on it.
    </p>
  );
}

