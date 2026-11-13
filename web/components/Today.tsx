"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useEffect, useState, useSyncExternalStore } from "react";
import { AlertsStrip } from "@/components/Alerts";
import { NetworkSheet, NetworkStrip } from "@/components/Network";
import { ResultsCard } from "@/components/ResultsCard";
import { WhySheet } from "@/components/WhySheet";
import { type Loaded, loadWithFallback } from "@/lib/api";
import { formatAsOf, formatToday, formatWhen } from "@/lib/format";
import type { Brief, BriefRow, Window } from "@/lib/types";

const WINDOWS: Window[] = ["24h", "3d", "7d", "30d"];

// Result is tagged with what it was loaded for; "loading" is derived, not stored.
type Key = string;
type Result = { key: Key; brief: Loaded<Brief> } | { key: Key; error: true };

const noSubscribe = () => () => {};

function useToday(): string | null {
  return useSyncExternalStore(noSubscribe, () => formatToday(), () => null);
}

export function Today() {
  const params = useSearchParams();
  const [win, setWin] = useState<Window>(() => {
    const w = params.get("w");
    return WINDOWS.includes(w as Window) ? (w as Window) : "24h";
  });
  // "" = now; else YYYY-MM-DD replay (deep-linkable: ?w=7d&as_of=2026-10-31)
  const [asOf, setAsOf] = useState<string>(() => {
    const a = params.get("as_of") ?? "";
    return /^\d{4}-\d{2}-\d{2}$/.test(a) ? a : "";
  });
  const [result, setResult] = useState<Result | null>(null);
  const [why, setWhy] = useState<BriefRow | null>(null);
  const today = useToday();
  const key = `${win}|${asOf}`;

  useEffect(() => {
    let live = true;
    const q = `/api/brief?window=${win}${asOf ? `&as_of=${asOf}` : ""}`;
    // A replay has no snapshot; fall back to the current window's snapshot only for "now".
    loadWithFallback<Brief>(q, `brief_${win}.json`)
      .then((brief) => live && setResult({ key, brief }))
      .catch(() => live && setResult({ key, error: true }));
    return () => {
      live = false;
    };
  }, [win, asOf, key]);

  const current = result?.key === key ? result : null;

  return (
    <div>
      <header className="mb-4">
        <div className="flex items-baseline justify-between">
          <h1 className="text-[22px] font-semibold tracking-tight">Today</h1>
          <span className="text-[13px] text-ink-3">{asOf ? `Replay · ${asOf}` : today}</span>
        </div>
        <div className="mt-3 flex items-center justify-between gap-2">
          <div role="tablist" aria-label="Window" className="flex gap-1">
            {WINDOWS.map((w) => (
              <button
                key={w}
                role="tab"
                aria-selected={w === win}
                onClick={() => setWin(w)}
                className={`h-11 min-w-11 rounded-md px-3 text-[14px] ${
                  w === win ? "bg-ink font-semibold text-bg" : "text-ink-2"
                }`}
              >
                {w}
              </button>
            ))}
          </div>
          <label className="flex items-center gap-1 text-[12px] text-ink-3">
            <span className="sr-only">Replay the brief as of a past date</span>
            <input
              type="date"
              value={asOf}
              max={new Date().toISOString().slice(0, 10)}
              onChange={(e) => setAsOf(e.target.value)}
              className="h-11 w-[8.5rem] rounded-md border border-line bg-surface px-2 text-[13px] text-ink-2"
              aria-label="As of"
            />
          </label>
        </div>
        {asOf && (
          <button onClick={() => setAsOf("")} className="mt-1 min-h-8 text-[12px] text-accent">
            Back to now
          </button>
        )}
      </header>

      {!asOf && <AlertsStrip />}
      {current === null && <p className="text-[14px] text-ink-3">Loading brief…</p>}
      {current && "error" in current && (
        <p className="text-[14px] text-down">
          Couldn&apos;t reach FINN or its snapshot. Check your connection and reload.
        </p>
      )}
      {current && "brief" in current && current.brief.source === "snapshot" && asOf ? (
        <p className="text-[14px] text-caution">
          Replays are built live and the API isn&apos;t reachable right now. Clear the date to see the
          last snapshot.
        </p>
      ) : (
        current && "brief" in current && <BriefView loaded={current.brief} onWhy={setWhy} />
      )}
      {why && <WhySheet item={why} onClose={() => setWhy(null)} />}
    </div>
  );
}

function BriefView({ loaded, onWhy }: { loaded: Loaded<Brief>; onWhy: (r: BriefRow) => void }) {
  const { data: b, source } = loaded;
  const [openBuried, setOpenBuried] = useState(false);
  return (
    <div>
      <p className="mb-2 text-[13px] text-ink-2 tabular-nums">
        {b.counts.filings} filings · {b.counts.now} need you · {b.counts.worth} worth knowing ·{" "}
        {b.counts.buried} buried
      </p>
      <div className="mb-4 flex flex-wrap gap-2">
        <span
          className={`rounded px-2 py-0.5 text-[12px] ${
            source === "snapshot" ? "bg-caution-bg text-caution" : "border border-line text-ink-2"
          }`}
        >
          {source === "snapshot" ? "Snapshot" : "Live"} · as of {formatAsOf(b.as_of)}
        </span>
      </div>

      {b.now.length > 0 && (
        <section className="mb-5">
          <h2 className="mb-2 text-[12px] font-semibold uppercase tracking-wider text-accent">
            Now <span className="font-normal">{b.now.length}</span>
          </h2>
          <div className="space-y-3">
            {b.now.map((it) => (
              <NowCard key={it.id} it={it} onWhy={onWhy} />
            ))}
          </div>
        </section>
      )}

      {b.worth.length > 0 && (
        <section className="mb-5">
          <h2 className="mb-2 text-[12px] font-semibold uppercase tracking-wider text-ink-3">
            Worth knowing <span className="font-normal">{b.worth.length}</span>
          </h2>
          <ul className="divide-y divide-line rounded-lg border border-line bg-surface">
            {b.worth.map((it) => (
              <WorthRow key={it.id} it={it} onWhy={onWhy} />
            ))}
          </ul>
        </section>
      )}

      {b.buried.length > 0 && (
        <section className="mb-5">
          <button
            onClick={() => setOpenBuried((o) => !o)}
            aria-expanded={openBuried}
            className="flex min-h-11 w-full items-center justify-between rounded-lg border border-line bg-surface px-3 text-left text-[14px] text-ink-2"
          >
            <span>
              Buried · {b.counts.buried} routine filing{b.counts.buried === 1 ? "" : "s"}
            </span>
            <span className="text-ink-3">{openBuried ? "Hide" : "Show"}</span>
          </button>
          {openBuried && (
            <div className="mt-2 space-y-2">
              {b.buried.map((g) => (
                <details key={g.label} className="rounded-lg border border-line bg-surface">
                  <summary className="flex min-h-11 cursor-pointer items-center justify-between px-3 text-[14px]">
                    <span>{g.label}</span>
                    <span className="text-ink-3 tabular-nums">{g.count}</span>
                  </summary>
                  <ul className="divide-y divide-line border-t border-line">
                    {g.items.map((it) => (
                      <WorthRow key={it.id} it={it} onWhy={onWhy} muted />
                    ))}
                  </ul>
                </details>
              ))}
            </div>
          )}
        </section>
      )}

      {b.counts.filings === 0 ? (
        <p className="mt-8 text-center text-[14px] text-ink-3">Nothing filed in this window.</p>
      ) : (
        <p className="mt-8 text-center text-[14px] text-ink-3">
          You&apos;re caught up.
          {b.now.length === 0 && ` Nothing crossed your bar; ${b.counts.buried} routine filings buried.`}
        </p>
      )}
      {b.source_credit && <p className="mt-4 text-center text-[11px] text-ink-3">{b.source_credit}</p>}
      <p className="mt-2 text-center text-[11px]">
        <a href="/cost" className="text-ink-3 underline">
          Under the hood: what this cost to compute
        </a>
      </p>
    </div>
  );
}

function Meta({ it }: { it: BriefRow }) {
  return (
    <div className="flex items-baseline gap-2 text-[12px] text-ink-3">
      <span className="font-semibold text-ink-2">{it.symbol}</span>
      <span>{it.category_label}</span>
      <span className="ml-auto tabular-nums">{formatWhen(it.ts)}</span>
    </div>
  );
}

function Actions({ it, onWhy }: { it: BriefRow; onWhy: (r: BriefRow) => void }) {
  return (
    <div className="mt-2 flex gap-4 text-[13px]">
      <button onClick={() => onWhy(it)} className="min-h-11 text-accent">
        Why is this here?
      </button>
      {it.pdf_url && (
        <a href={it.pdf_url} target="_blank" rel="noreferrer" className="flex min-h-11 items-center text-ink-2 underline">
          Filing on NSE
        </a>
      )}
      {(() => {
        // a results card links to the promises that fall due in its fiscal year
        const fy = it.card?.period_label.match(/FY\d{2}/)?.[0];
        return (
          <Link
            href={`/research?s=${encodeURIComponent(it.symbol)}${fy ? `&fy=${fy}` : ""}`}
            className="flex min-h-11 items-center text-ink-2"
          >
            {fy ? `${fy} promises` : "Research"}
          </Link>
        );
      })()}
      {it.bundled > 0 && (
        <span className="flex min-h-11 items-center text-ink-3">+{it.bundled} related</span>
      )}
    </div>
  );
}

function NetworkFor({ it }: { it: BriefRow }) {
  const [open, setOpen] = useState(false);
  if (!it.network) return null;
  return (
    <>
      <NetworkStrip net={it.network} onOpen={() => setOpen(true)} />
      {open && <NetworkSheet net={it.network} company={it.company} onClose={() => setOpen(false)} />}
    </>
  );
}

function NowCard({ it, onWhy }: { it: BriefRow; onWhy: (r: BriefRow) => void }) {
  return (
    <article className="rounded-lg border border-line bg-surface px-3 py-3">
      <Meta it={it} />
      <p className="mt-1 text-[15px] font-medium leading-snug">{it.card ? it.card.take : it.headline}</p>
      {it.card && (
        <div className="mt-3">
          <ResultsCard card={it.card} />
        </div>
      )}
      <NetworkFor it={it} />
      <Actions it={it} onWhy={onWhy} />
    </article>
  );
}

function WorthRow({ it, onWhy, muted }: { it: BriefRow; onWhy: (r: BriefRow) => void; muted?: boolean }) {
  const [open, setOpen] = useState(false);
  return (
    <li className="px-3 py-2">
      <button onClick={() => setOpen((o) => !o)} aria-expanded={open} className="block w-full text-left">
        <Meta it={it} />
        <p className={`mt-0.5 text-[14px] leading-snug ${muted ? "text-ink-2" : ""} ${open ? "" : "line-clamp-2"}`}>
          {it.headline}
        </p>
      </button>
      {open && (
        <>
          {it.card && (
            <div className="mt-2">
              <ResultsCard card={it.card} />
            </div>
          )}
          <NetworkFor it={it} />
          <Actions it={it} onWhy={onWhy} />
        </>
      )}
    </li>
  );
}
