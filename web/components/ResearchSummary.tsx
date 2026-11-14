import { formatCr } from "@/lib/format";
import type { Research } from "@/lib/types";

function latestResult(r: Research) {
  const q = r.quarters.filter((row) => row.revenue !== null).slice(-1)[0];
  if (!q) return null;
  const margin = r.format === "indas" ? q.ebitda_margin : q.pat_margin;
  const marginLabel = r.format === "indas" ? "EBITDA margin" : "PAT margin";
  return {
    href: q.xbrl,
    text: `${q.label} · revenue ${formatCr(q.revenue)}${
      q.revenue_yoy === null ? "" : ` (${q.revenue_yoy > 0 ? "+" : ""}${q.revenue_yoy}% YoY)`
    } · ${marginLabel} ${margin === null ? "not stated" : `${margin}%`} · PAT ${formatCr(q.pat)}`,
  };
}

export function ResearchSummary({ r }: { r: Research }) {
  const result = latestResult(r);
  const resolved = (r.groups ?? []).find((group) => group.resolved && group.verdicts.length > 0);
  const verdict = resolved?.verdicts[0];
  const question = r.help?.questions[0];
  const contact = r.help?.call[0];
  const callsRead = r.ledger?.calls_read ?? r.calls.length;
  const callsListed = r.ledger?.calls_listed ?? r.calls.length;
  const reviewed = r.provenance?.reviewed === true;

  return (
    <section aria-labelledby="research-summary-title" className="overflow-hidden rounded-lg border border-line bg-surface">
      <div className="flex items-baseline justify-between gap-3 border-b border-line px-3 py-2.5">
        <h2 id="research-summary-title" className="text-[14px] font-semibold">
          20-second brief
        </h2>
        <span className="shrink-0 text-[11px] text-ink-3">Stored report only</span>
      </div>
      <dl className="divide-y divide-line">
        <div className="px-3 py-2.5">
          <dt className="text-[10px] font-semibold uppercase tracking-wider text-ink-3">What changed</dt>
          <dd className="mt-0.5 text-[13px] leading-snug">
            {result ? (
              <a href={result.href} target="_blank" rel="noreferrer" className="underline decoration-line underline-offset-2">
                {result.text}
              </a>
            ) : (
              <span className="text-ink-2">No quarterly result is stored in this report.</span>
            )}
          </dd>
        </div>
        <div className="px-3 py-2.5">
          <dt className="text-[10px] font-semibold uppercase tracking-wider text-ink-3">What management promised</dt>
          <dd className="mt-0.5 text-[13px] leading-snug">
            <span>{r.ledger?.pattern ?? `${r.ledger?.resolved ?? 0} resolved promises`}</span>
            {resolved && verdict && (
              <a href={`#${resolved.id}`} className="mt-1 block text-ink-2 underline decoration-line underline-offset-2">
                {resolved.title} · {verdict.short}: {verdict.line || verdict.label}
              </a>
            )}
          </dd>
        </div>
        <div className="px-3 py-2.5">
          <dt className="text-[10px] font-semibold uppercase tracking-wider text-ink-3">What to investigate</dt>
          <dd className="mt-0.5 text-[13px] leading-snug text-ink-2">
            {question ? <a href="#ledger">{question}</a> : "No ledger question is stored for this report yet."}
          </dd>
        </div>
        <div className="px-3 py-2.5">
          <dt className="text-[10px] font-semibold uppercase tracking-wider text-ink-3">Who to call</dt>
          <dd className="mt-0.5 text-[13px] leading-snug">
            {contact ? (
              <a href="#people">
                <span className="font-semibold">{contact.name}</span>
                {contact.synthetic && <span className="ml-1 text-[10px] uppercase tracking-wide text-ink-3">synthetic</span>}
                <span className="block text-ink-2">{contact.headline ?? contact.what_theyd_know}</span>
              </a>
            ) : (
              <span className="text-ink-2">No contact is stored for this company yet.</span>
            )}
          </dd>
        </div>
      </dl>
      <p className="border-t border-line px-3 py-2 text-[11px] text-ink-3">
        Coverage · read {callsRead} of the last {callsListed} calls · ledger {reviewed ? "reviewed" : "not reviewed"}
      </p>
    </section>
  );
}
