"use client";

import { useEffect, useState } from "react";
import type { AlertInputs } from "@/lib/alerts";
import { loadWithFallback } from "@/lib/api";
import { auditFilters, type FilterAuditResult, type FilterAuditRow } from "@/lib/filterAudit";
import type { Brief } from "@/lib/types";

function signed(value: number): string {
  return `${value >= 0 ? "+" : "−"}${Math.abs(value).toFixed(1)}%`;
}

function AuditRow({ row }: { row: FilterAuditRow }) {
  const text = (
    <>
      <span className="font-semibold">{row.symbol}</span> · {row.headline}
    </>
  );
  return (
    <li className="py-2 text-[13px] leading-snug">
      {row.url ? (
        <a href={row.url} target="_blank" rel="noreferrer" className="underline decoration-line underline-offset-2">
          {text}
        </a>
      ) : (
        text
      )}
      <span className="mt-1 block text-[11px] text-ink-3">
        {row.filingDate} → {row.moveDate} · stock {signed(row.movePct)} · {signed(row.relativePct)} vs NIFTY
      </span>
    </li>
  );
}

export function FilterAudit() {
  const [audit, setAudit] = useState<FilterAuditResult | null>(null);
  const [credit, setCredit] = useState("");

  useEffect(() => {
    let live = true;
    Promise.all([
      loadWithFallback<Brief>("/api/brief?window=30d", "brief_30d.json"),
      loadWithFallback<AlertInputs>("/api/alerts/inputs", "alerts_inputs.json"),
    ])
      .then(([brief, alerts]) => {
        if (!live) return;
        setAudit(auditFilters(brief.data, alerts.data));
        setCredit(alerts.data.credit);
      })
      .catch(() => {});
    return () => {
      live = false;
    };
  }, []);

  if (!audit) return null;
  return (
    <section className="mb-4 rounded-xl border border-line bg-surface px-3 py-3" aria-labelledby="filter-audit-title">
      <div className="flex items-baseline justify-between gap-3">
        <h2 id="filter-audit-title" className="text-[14px] font-semibold">
          Filter audit · 30 days
        </h2>
        <span className="text-[11px] text-ink-3">±{audit.threshold}% vs NIFTY</span>
      </div>
      <p className="mt-1 rounded-md bg-caution-bg px-2 py-1.5 text-[11px] font-medium leading-snug text-caution">
        A price move does not prove the filing caused it. This only checks what the filter may have missed or over-ranked.
      </p>
      <div className="mt-3 grid gap-3">
        <div>
          <h3 className="text-[11px] font-semibold uppercase tracking-wider text-ink-3">
            Buried, then moved · {audit.buriedThenMoved.length}
          </h3>
          <ul className="divide-y divide-line">
            {audit.buriedThenMoved.slice(0, 4).map((row) => (
              <AuditRow key={row.id} row={row} />
            ))}
          </ul>
          {audit.buriedThenMoved.length === 0 && <p className="mt-1 text-[12px] text-ink-3">None in this window.</p>}
        </div>
        <div>
          <h3 className="text-[11px] font-semibold uppercase tracking-wider text-ink-3">
            Now, then no threshold move · {audit.nowThenQuiet.length}
          </h3>
          <ul className="divide-y divide-line">
            {audit.nowThenQuiet.slice(0, 4).map((row) => (
              <AuditRow key={row.id} row={row} />
            ))}
          </ul>
          {audit.nowThenQuiet.length === 0 && <p className="mt-1 text-[12px] text-ink-3">None in this window.</p>}
        </div>
      </div>
      <p className="mt-2 text-[10px] leading-snug text-ink-3">
        Next two stored trading sessions after each filing · {credit}
      </p>
    </section>
  );
}
