"use client";

import type { Candidate, Contact, ItemNetwork, PathView, PersonView } from "@/lib/types";
import { ActionBlock } from "@/components/ActionBlock";

const DOTS: Record<string, number> = { strong: 3, medium: 2, weak: 1 };

/** Three-dot strength meter; the label is always written out too (never colour alone). */
export function Strength({ label, title }: { label: string; title?: string }) {
  const n = DOTS[label] ?? 0;
  return (
    <span className="inline-flex items-center gap-1 text-[12px] text-ink-3" title={title}>
      <span aria-hidden className="inline-flex gap-[3px]">
        {[1, 2, 3].map((i) => (
          <span key={i} className={`h-1.5 w-1.5 rounded-full ${i <= n ? "bg-accent" : "bg-line"}`} />
        ))}
      </span>
      {label}
    </span>
  );
}

export function SyntheticTag() {
  return (
    <span className="rounded border border-line px-1 text-[10px] uppercase tracking-wide text-ink-3">
      synthetic
    </span>
  );
}

function short(name: string): string {
  return name.replace(/^(Mr|Mrs|Ms|Dr)\.?\s+/i, "");
}

function formerFirst(call: Candidate[]): Candidate[] {
  return [...call].sort((a, b) => Number(Boolean(a.compliance)) - Number(Boolean(b.compliance)));
}

/** The one line on a brief card: the single most useful thing the network knows. */
export function NetworkStrip({ net, onOpen }: { net: ItemNetwork; onOpen: () => void }) {
  const lead = net.people[0];
  const path = lead?.paths[0];
  const call = formerFirst(net.call)[0];
  let line: React.ReactNode;
  if (lead && lead.you.length) {
    line = (
      <>
        <b className="font-semibold">{lead.you[0].replace("they were", `${short(lead.name)} was`)}.</b>
        {path && <> {path.via.name} can introduce you.</>}
      </>
    );
  } else if (lead && path) {
    line = (
      <>
        You don&apos;t know {short(lead.name)}, but <b className="font-semibold">{path.via.name}</b> does —{" "}
        {path.evidence[0]}.
      </>
    );
  } else if (call) {
    line = (
      <>
        Call <b className="font-semibold">{call.name}</b> — {call.why.split(";")[0]}.
      </>
    );
  } else return null;
  return (
    <button
      onClick={onOpen}
      className="mt-3 flex w-full items-start gap-2 rounded-md border-l-2 border-accent bg-bg px-3 py-2 text-left"
    >
      <span className="flex-1 text-[13px] leading-snug text-ink-2">
        <span className="mb-0.5 block text-[11px] font-semibold uppercase tracking-wider text-accent">
          Your network
        </span>
        {line}
      </span>
      <span className="self-center text-[13px] text-accent">Open</span>
    </button>
  );
}

export function PathLine({ p, target }: { p: PathView; target: string }) {
  return (
    <div className="py-2">
      <div className="flex flex-wrap items-center gap-1 text-[14px]">
        <span className="text-ink-3">You</span>
        <span className="text-ink-3">→</span>
        <span className="font-medium">{p.via.name}</span>
        <span className="text-ink-3">→</span>
        <span>{short(target)}</span>
        <span className="ml-auto">
          <Strength label={p.strength_label} title={`warmth ${p.via.warmth} × overlap ${p.overlap}`} />
        </span>
      </div>
      <p className="mt-0.5 text-[12px] leading-snug text-ink-3">
        {p.via.headline}. {cap(p.evidence[0] ?? "")}. You: {p.via.warmth_why}.
      </p>
    </div>
  );
}

function cap(s: string): string {
  return s ? s[0].toUpperCase() + s.slice(1) : s;
}

export function PersonBlock({ p }: { p: PersonView }) {
  const career = [...p.career].reverse();
  return (
    <section>
      <div className="flex items-baseline gap-2">
        <h3 className="text-[17px] font-semibold">{short(p.name)}</h3>
        {p.event && <span className="text-[12px] text-ink-3">{p.event}</span>}
      </div>
      {p.role && <p className="text-[13px] text-ink-2">{p.role}</p>}
      {p.you.length > 0 && (
        <p className="mt-2 rounded-md bg-caution-bg px-2 py-1.5 text-[13px] text-caution">{p.you.join(" · ")}</p>
      )}
      {career.length > 0 && (
        <ol className="mt-3 border-l border-line pl-3">
          {career.map((c, i) => (
            <li key={i} className="relative pb-2 text-[13px] leading-snug">
              <span
                className={`absolute -left-[17px] top-1.5 h-2 w-2 rounded-full ${c.current ? "bg-accent" : "bg-ink-3"}`}
              />
              <span className="font-medium">{c.org}</span>
              {c.span && <span className="ml-1 text-ink-3 tabular-nums">{c.span}</span>}
              {c.title && <span className="block text-ink-2 line-clamp-2">{c.title}</span>}
            </li>
          ))}
        </ol>
      )}
      {p.education.length > 0 && (
        <p className="mt-1 text-[13px] text-ink-2">
          {p.education.map((e) => [e.degree, e.institution, e.year].filter(Boolean).join(", ")).join(" · ")}
        </p>
      )}
      {career.length === 0 && p.education.length === 0 && (
        <p className="mt-2 text-[13px] text-ink-3">The filing doesn&apos;t disclose a career profile.</p>
      )}
      <h4 className="mt-4 text-[11px] font-semibold uppercase tracking-wider text-ink-3">
        Second-degree reach
      </h4>
      {p.paths.length ? (
        <div className="divide-y divide-line">
          {p.paths.map((x) => (
            <PathLine key={x.via.id} p={x} target={p.name} />
          ))}
        </div>
      ) : (
        <p className="py-2 text-[13px] text-ink-3">No one in your network overlaps with their disclosed career.</p>
      )}
      {p.mentions[0]?.url && (
        <a
          href={p.mentions[0].url}
          target="_blank"
          rel="noreferrer"
          className="mt-1 inline-flex min-h-11 items-center text-[12px] text-ink-2 underline"
        >
          Profile as disclosed in the filing (NSE)
        </a>
      )}
    </section>
  );
}

export function CandidateRow({ c }: { c: Candidate }) {
  return (
    <li className="py-2.5">
      <div className="flex items-center gap-2">
        <span className="text-[15px] font-medium">{c.name}</span>
        {c.synthetic && <SyntheticTag />}
        <span className="ml-auto">
          <Strength label={c.warmth_label} title={c.warmth_why} />
        </span>
      </div>
      <p className="text-[13px] leading-snug text-ink-2">{cap(c.why.split(";")[0])}.</p>
      <p className="text-[12px] leading-snug text-ink-3">
        Would know: {c.what_theyd_know}. {cap(c.warmth_why)}.
      </p>
      {c.compliance && (
        <p className="mt-1 rounded bg-caution-bg px-2 py-1 text-[12px] leading-snug text-caution">{c.compliance}</p>
      )}
    </li>
  );
}

export function ContactLine({ c, right }: { c: Contact; right?: React.ReactNode }) {
  return (
    <div className="flex items-center gap-2">
      <span className="text-[14px] font-medium">{c.name}</span>
      {c.synthetic && <SyntheticTag />}
      <span className="ml-auto">{right ?? <Strength label={c.warmth_label} title={c.warmth_why} />}</span>
    </div>
  );
}

/** Bottom sheet: who is this person, how do I reach them, who else can help, what to ask. */
export function NetworkSheet({
  net,
  company,
  onClose,
}: {
  net: ItemNetwork;
  company: string;
  onClose: () => void;
}) {
  const call = formerFirst(net.call);
  const shownNet = {
    ...net,
    call,
    opener: net.opener && call[0]?.name !== net.opener.to ? undefined : net.opener,
  };
  return (
    <div className="fixed inset-0 z-30 flex items-end justify-center" role="dialog" aria-modal="true">
      <button aria-label="Close" className="finn-scrim absolute inset-0 bg-black/40" onClick={onClose} />
      <div className="finn-sheet relative max-h-[88dvh] w-full max-w-[480px] overflow-y-auto rounded-t-2xl border-t border-line bg-surface px-4 pb-[max(env(safe-area-inset-bottom),16px)] pt-4">
        <div className="mb-2 flex items-baseline justify-between">
          <h2 className="text-[16px] font-semibold">Who can help · {company.replace(/ Limited$/, "")}</h2>
          <button onClick={onClose} className="min-h-11 px-2 text-[14px] text-ink-2">
            Close
          </button>
        </div>
        <ActionBlock net={shownNet} />
        {net.people.length > 0 && (
          <div className="space-y-5 border-b border-line pb-4">
            {net.people.slice(0, 2).map((p) => (
              <PersonBlock key={p.id} p={p} />
            ))}
          </div>
        )}
        {call.length > 0 && (
          <section className="mt-4">
            <h4 className="text-[11px] font-semibold uppercase tracking-wider text-ink-3">Call for context</h4>
            <ul className="divide-y divide-line">
              {call.map((c) => (
                <CandidateRow key={c.id} c={c} />
              ))}
            </ul>
          </section>
        )}
        {net.questions.length > 0 && (
          <section className="mt-3">
            <h4 className="text-[11px] font-semibold uppercase tracking-wider text-ink-3">Worth asking</h4>
            <ol className="mt-1 list-decimal space-y-1 pl-5 text-[13px] leading-snug text-ink-2">
              {net.questions.map((q) => (
                <li key={q}>{q}</li>
              ))}
            </ol>
          </section>
        )}
        <p className="mt-4 text-[11px] leading-snug text-ink-3">
          Your contacts are synthetic (fictional people at real organisations). Executives&apos; careers come
          only from what the company disclosed to NSE. Ranking is warmth × relevance, computed — not guessed.
        </p>
      </div>
    </div>
  );
}
