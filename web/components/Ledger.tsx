"use client";

import { useState } from "react";
import { NetworkSheet } from "@/components/Network";
import { formatCr } from "@/lib/format";
import type { ChainGroup, GroupStep, GroupValue, GuidanceTrack, ItemNetwork, Ledger } from "@/lib/types";

/** Verdict colours: green only for a clean delivery, amber for a qualified one, red for a miss. */
export const TAG: Record<string, { icon: string; cls: string }> = {
  delivered: { icon: "✓", cls: "text-up" },
  beat: { icon: "▲", cls: "text-up" },
  "beat raised": { icon: "▲", cls: "text-up" },
  "on track": { icon: "✓", cls: "text-up" },
  ahead: { icon: "▲", cls: "text-up" },
  "met after cut": { icon: "✓", cls: "text-caution" },
  "met revised": { icon: "✓", cls: "text-caution" },
  missed: { icon: "✕", cls: "text-down" },
  "missed after cut": { icon: "✕", cls: "text-down" },
  behind: { icon: "▼", cls: "text-down" },
  pending: { icon: "…", cls: "text-ink-3" },
  "open-ended": { icon: "·", cls: "text-ink-3" },
  "not scored": { icon: "·", cls: "text-ink-3" },
};
const tag = (label: string) => TAG[label] ?? TAG["not scored"];

const day = (d: string) =>
  new Date(d).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" });

const pageUrl = (url: string, page: number | null | undefined) => (page ? `${url}#page=${page}` : url);

function bandOf(v: { low: number; high: number; unit: string | null; floor?: boolean }): string {
  const f = (x: number) => (v.unit === "₹ cr" ? formatCr(x) : `${x}%`);
  if (v.floor) return `${f(v.low)}+`;
  return v.low === v.high ? f(v.low) : v.unit === "₹ cr" ? `${f(v.low)}–${f(v.high)}` : `${v.low}–${v.high}%`;
}

const actualOf = (value: number, unit: string) => (unit === "₹ cr" ? formatCr(value) : `${value.toFixed(1)}%`);

// -- quotes: the clause(s) carrying this step's numbers, numbers in bold -------------------------
const NUM = /(\d[\d,]*(?:\.\d+)?\s*%?(?:\s*(?:-|–|to)\s*\d[\d,]*(?:\.\d+)?\s*%?)?)/g;

function forms(n: number): string[] {
  return [n.toLocaleString("en-IN"), n.toLocaleString("en-US"), String(n), n.toFixed(1)];
}

/** Keep only the sentence clauses that hold one of `nums`, starting at a clause boundary. */
export function clauseOf(quote: string, nums: number[]): { text: string; pre: boolean; post: boolean } {
  const has = (t: string) => nums.some((n) => forms(n).some((f) => t.includes(f)));
  const sentences = quote.split(/(?<=[.!?])\s+/);
  const kept = sentences.filter(has);
  if (!kept.length) return { text: quote, pre: false, post: false };
  const first = sentences.indexOf(kept[0]);
  const last = sentences.indexOf(kept[kept.length - 1]);
  let text = sentences.slice(first, last + 1).join(" ");
  let pre = first > 0;
  let post = last < sentences.length - 1;
  if (text.length > 170) {
    // within the sentence: from the first clause with a number to the last
    const clauses = text.split(/(?<=[,;:])\s+/);
    const idx = clauses.map((c, i) => (has(c) ? i : -1)).filter((i) => i >= 0);
    if (idx.length) {
      const a = idx[0];
      const b = idx[idx.length - 1];
      pre = pre || a > 0;
      post = post || b < clauses.length - 1;
      text = clauses.slice(a, b + 1).join(" ");
    }
  }
  return { text: text.replace(/[,;:]$/, ""), pre, post };
}

function QuoteText({ quote, nums }: { quote: string; nums: number[] }) {
  const { text, pre, post } = clauseOf(quote, nums);
  const parts = text.split(NUM);
  return (
    <>
      “{pre && "… "}
      {parts.map((p, i) =>
        i % 2 === 1 && nums.some((n) => forms(n).some((f) => p.includes(f))) ? (
          <b key={i} className="font-semibold text-ink">
            {p}
          </b>
        ) : (
          <span key={i}>{p}</span>
        ),
      )}
      {post && " …"}”
    </>
  );
}

// -- scoreboard -------------------------------------------------------------------------------
export function Scoreboard({ tracks, groups, onJump }: { tracks: GuidanceTrack[]; groups: ChainGroup[]; onJump: (id: string) => void }) {
  const rows = tracks.filter((t) => t.resolved);
  if (!rows.length) return null;
  const groupOf = (t: GuidanceTrack) =>
    groups.find((g) => g.period === t.period && g.metrics.includes(t.metric))?.id ?? "";
  const cell = "px-1.5 py-2 text-right tabular-nums";
  return (
    <table className="w-full table-fixed border-collapse text-[12px]">
      <colgroup>
        <col className="w-[26%]" />
        <col className="w-[17%]" />
        <col className="w-[21%]" />
        <col className="w-[13%]" />
        <col className="w-[23%]" />
      </colgroup>
      <thead className="text-[11px] text-ink-3">
        <tr className="border-b border-line">
          <th className="py-1 pr-1 text-left font-normal">Promise</th>
          <th className="px-1.5 py-1 text-right font-normal">First</th>
          <th className="px-1.5 py-1 text-right font-normal">Final</th>
          <th className="px-1.5 py-1 text-right font-normal">Result</th>
          <th className="py-1 pl-1.5 text-left font-normal">Verdict</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((t) => {
          const f = t.points[0];
          const l = t.points[t.points.length - 1];
          const lbl = t.verdict_label ?? t.verdict;
          const v = tag(lbl);
          const id = groupOf(t);
          return (
            <tr
              key={`${t.metric}-${t.period}`}
              onClick={() => id && onJump(id)}
              className="cursor-pointer border-b border-line last:border-0"
            >
              <td className="py-2 pr-1 font-medium leading-tight">
                {t.period} {t.short ?? t.label}
              </td>
              <td className={`${cell} ${t.first_is_revision ? "text-ink-3" : ""}`}>
                {t.first_is_revision ? "not read" : bandOf({ ...f, floor: false })}
              </td>
              <td className={`${cell} whitespace-nowrap`}>{f === l ? "same" : bandOf({ ...l, floor: false })}</td>
              <td className={`${cell} font-semibold`}>{t.actual ? actualOf(t.actual.value, t.actual.unit) : "—"}</td>
              <td className={`py-2 pl-1.5 font-semibold leading-tight ${v.cls}`}>
                {v.icon} {lbl}
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

export function LedgerHead({ l }: { l: Ledger }) {
  return (
    <div className="mb-2">
      <p className="text-[12px] text-ink-3">
        Read {l.calls_read} of the last {l.calls_listed} calls
      </p>
      {l.pattern && <p className="text-[14px] font-medium leading-snug">{l.pattern}</p>}
    </div>
  );
}

export function Legend() {
  return (
    <p className="mb-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-[12px] text-ink-3">
      <span className="flex items-center gap-1">
        <Dot kind="statement" /> statement
      </span>
      <span className="flex items-center gap-1">
        <Dot kind="steer" /> analyst steer
      </span>
      <span className="flex items-center gap-1">
        <Dot kind="result" /> result
      </span>
      <span>· tap a step to open the source</span>
    </p>
  );
}

function Dot({ kind, abs }: { kind: "statement" | "steer" | "result"; abs?: boolean }) {
  const pos = abs ? "absolute -left-[17px] top-1.5" : "inline-block";
  if (kind === "steer") return <span className={`${pos} h-2 w-2 rounded-full border border-ink-2 bg-surface`} aria-hidden />;
  if (kind === "result") return <span className={`${pos} h-2 w-2 bg-ink`} aria-hidden />;
  return <span className={`${pos} h-2 w-2 rounded-full bg-accent`} aria-hidden />;
}

// -- one chain (possibly several metrics stated together) ----------------------------------------
function changeText(c: GroupValue["change"]) {
  return c === "cut" ? "▼ lowered" : c === "raised" ? "▲ raised" : c;
}

function Values({ s }: { s: GroupStep }) {
  const vals = s.values ?? [];
  const multi = vals.length > 1;
  const changes = new Set(vals.map((v) => v.change));
  const one = changes.size === 1 ? vals[0]?.change : null;
  return (
    <p className="text-[14px] font-semibold leading-snug">
      {s.qualifier ? `${s.qualifier} ` : ""}
      {vals.map((v, i) => (
        <span key={v.metric}>
          {i > 0 && " · "}
          {bandOf(v)}
          {multi && ` ${v.short}`}
          {!one && <ChangeTag c={v.change} />}
        </span>
      ))}
      {one && <ChangeTag c={one} />}
    </p>
  );
}

function ChangeTag({ c }: { c: GroupValue["change"] }) {
  const cls = c === "cut" ? "text-down" : c === "raised" ? "text-up" : "text-ink-3";
  return <span className={`ml-1 text-[12px] font-normal ${cls}`}>{changeText(c)}</span>;
}

export function GroupCard({ g, open, onToggle }: { g: ChainGroup; open: boolean; onToggle: () => void }) {
  const head = g.verdicts.length === 1 ? tag(g.verdicts[0].label) : null;
  return (
    <article id={g.id} className="scroll-mt-4 rounded-lg border border-line bg-surface">
      <button onClick={onToggle} aria-expanded={open} className="w-full px-3 py-2.5 text-left">
        <div className="flex items-baseline justify-between gap-2">
          <h3 className="text-[15px] font-semibold">{g.title}</h3>
          <span className="shrink-0 text-[12px] text-ink-3">{open ? "Hide" : "Show"} chain</span>
        </div>
        <ul className="mt-1 space-y-0.5">
          {g.verdicts.map((v) => {
            const t = tag(v.label);
            return (
              <li key={v.metric} className="text-[13px] leading-snug">
                <span className={`font-semibold ${t.cls}`}>
                  {t.icon} {g.verdicts.length > 1 ? `${v.short}: ` : ""}
                  {v.label}
                </span>
                {(v.line && v.line !== v.label) && <span className="text-ink-2"> · {v.line}</span>}
                {v.caveat && <span className="block text-[12px] text-caution">{v.caveat}</span>}
              </li>
            );
          })}
        </ul>
        {head === null && null}
      </button>
      {open && (
        <div className="px-3 pb-3">
          <ol className="ml-1 border-l border-line pl-3">
            {g.steps.map((s, i) =>
              s.kind === "statement" ? (
                <li key={i} className="relative pb-3">
                  <Dot kind="statement" abs />
                  <a href={pageUrl(s.url, s.page)} target="_blank" rel="noreferrer" className="block">
                    <p className="text-[12px] text-ink-3">
                      {day(s.date)} · {s.speaker || "Management"} · {s.call}
                      {s.page ? `, p. ${s.page}` : ""}
                    </p>
                    <Values s={s} />
                    <p className="text-[13px] leading-snug text-ink-2">
                      <QuoteText quote={s.quote} nums={(s.values ?? []).flatMap((v) => [v.low, v.high])} />
                    </p>
                  </a>
                </li>
              ) : (
                <li key={i} className="relative pb-3">
                  <Dot kind="steer" abs />
                  <a href={pageUrl(s.url, s.reply_page)} target="_blank" rel="noreferrer" className="block">
                    <p className="text-[12px] text-ink-3">
                      {day(s.date)} · {s.call}, p. {s.page} · analyst steer, no new number
                    </p>
                    <p className="text-[13px] leading-snug text-ink-2">
                      Analyst ({s.analyst}): <QuoteText quote={s.analyst_quote ?? ""} nums={[s.low ?? 0, s.high ?? 0]} />
                    </p>
                    <p className="text-[13px] font-medium leading-snug">
                      {s.speaker}: “{s.reply_quote}”
                    </p>
                  </a>
                </li>
              ),
            )}
            {g.results.map((r, i) => (
              <li key={`r${i}`} className="relative pb-3 last:pb-0">
                <Dot kind="result" abs />
                <a
                  href={r.source.url ? pageUrl(r.source.url, r.source.page) : (r.source.xbrl ?? undefined)}
                  target="_blank"
                  rel="noreferrer"
                  className="block"
                >
                  <p className="text-[12px] text-ink-3">
                    Result · {r.source.call ?? "results filing"}
                    {r.source.page ? `, p. ${r.source.page}` : ""} · {r.basis}
                  </p>
                  <p className="text-[14px] font-semibold">
                    {r.values.map((v, k) => (
                      <span key={v.metric}>
                        {k > 0 && " · "}
                        {actualOf(v.value, v.unit)}
                        {r.values.length > 1 || g.verdicts.length > 1 ? ` ${v.short}` : ""}
                        {v.span !== "FY" ? ` (${v.span})` : ""}
                      </span>
                    ))}
                  </p>
                  {r.source.quote && (
                    <p className="text-[13px] leading-snug text-ink-2">
                      <QuoteText quote={r.source.quote} nums={r.values.map((v) => v.value)} />
                    </p>
                  )}
                </a>
              </li>
            ))}
          </ol>
          {g.cross_checks.length > 0 && (
            <p className="mt-2 text-[12px] leading-snug text-ink-3">
              Our own figures from the filings, for comparison only (never used for a verdict):{" "}
              {g.cross_checks
                .map((c) => `${c.short} ${c.unit === "₹ cr" ? formatCr(c.value) : `${c.value}%`} (${c.basis})`)
                .join(" · ")}
            </p>
          )}
        </div>
      )}
    </article>
  );
}

export function HelpButton({ help, company }: { help?: ItemNetwork; company: string }) {
  const [open, setOpen] = useState(false);
  if (!help || (!help.call.length && !help.questions.length)) return null;
  return (
    <>
      <button
        onClick={() => setOpen(true)}
        className="h-9 rounded-full border border-line px-3 text-[13px] font-medium text-ink"
      >
        Who can help? · {help.call.length}
      </button>
      {open && <NetworkSheet net={help} company={company} onClose={() => setOpen(false)} />}
    </>
  );
}
