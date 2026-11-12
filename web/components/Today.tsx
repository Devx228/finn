"use client";

import { useEffect, useState, useSyncExternalStore } from "react";
import { type Loaded, loadWithFallback } from "@/lib/api";
import { formatAsOf, formatToday } from "@/lib/format";
import type { Brief, BriefItem, Tier, Window } from "@/lib/types";

const WINDOWS: Window[] = ["24h", "3d", "7d", "30d"];

// Result is tagged with the window it was loaded for; "loading" is derived, not stored.
type Result = { win: Window; brief: Loaded<Brief> } | { win: Window; error: true };

const noSubscribe = () => () => {};

/** Today's date, read only on the client (prerender must not read the clock). */
function useToday(): string | null {
  return useSyncExternalStore(noSubscribe, () => formatToday(), () => null);
}

export function Today() {
  const [win, setWin] = useState<Window>("24h");
  const [result, setResult] = useState<Result | null>(null);
  const today = useToday();

  useEffect(() => {
    let live = true;
    loadWithFallback<Brief>(`/api/brief?window=${win}`, `brief_${win}.json`)
      .then((brief) => live && setResult({ win, brief }))
      .catch(() => live && setResult({ win, error: true }));
    return () => {
      live = false;
    };
  }, [win]);

  const current = result?.win === win ? result : null;

  return (
    <div>
      <header className="mb-4">
        <div className="flex items-baseline justify-between">
          <h1 className="text-[22px] font-semibold tracking-tight">Today</h1>
          <span className="text-[13px] text-ink-3">{today}</span>
        </div>
        <div role="tablist" aria-label="Window" className="mt-3 flex gap-1">
          {WINDOWS.map((w) => (
            <button
              key={w}
              role="tab"
              aria-selected={w === win}
              onClick={() => setWin(w)}
              className={`h-11 min-w-11 rounded-md px-3 text-[14px] ${
                w === win ? "bg-ink text-bg font-semibold" : "text-ink-2"
              }`}
            >
              {w}
            </button>
          ))}
        </div>
      </header>

      {current === null && <p className="text-[14px] text-ink-3">Loading brief…</p>}
      {current && "error" in current && (
        <p className="text-[14px] text-down">
          Couldn&apos;t reach FINN or its snapshot. Check your connection and reload.
        </p>
      )}
      {current && "brief" in current && <BriefView loaded={current.brief} />}
    </div>
  );
}

function BriefView({ loaded }: { loaded: Loaded<Brief> }) {
  const { data: b, source } = loaded;
  const by = (t: Tier) => b.items.filter((i) => i.tier === t);
  return (
    <div>
      <div className="mb-3 flex flex-wrap items-center gap-2 text-[13px]">
        <span className="text-ink-2">
          {b.counts.filings} filings · {b.counts.now} need you · {b.counts.worth} worth knowing ·{" "}
          {b.counts.buried} buried
        </span>
      </div>
      <div className="mb-4 flex flex-wrap gap-2">
        {source === "snapshot" ? (
          <Badge tone="caution">Snapshot · as of {formatAsOf(b.as_of)}</Badge>
        ) : (
          <Badge tone="neutral">Live · as of {formatAsOf(b.as_of)}</Badge>
        )}
        {b.placeholder && <Badge tone="caution">Placeholder data — wiring test</Badge>}
      </div>

      <Section title="Now" items={by("now")} accent />
      <Section title="Worth knowing" items={by("worth")} />
      <Section title="Buried" items={by("buried")} muted />

      <p className="mt-8 text-center text-[14px] text-ink-3">You&apos;re caught up.</p>
    </div>
  );
}

function Section(props: { title: string; items: BriefItem[]; accent?: boolean; muted?: boolean }) {
  if (props.items.length === 0) return null;
  return (
    <section className="mb-5">
      <h2
        className={`mb-2 text-[12px] font-semibold uppercase tracking-wider ${
          props.accent ? "text-accent" : "text-ink-3"
        }`}
      >
        {props.title} <span className="font-normal">{props.items.length}</span>
      </h2>
      <ul className="divide-y divide-line rounded-lg border border-line bg-surface">
        {props.items.map((i) => (
          <li key={i.id} className={`px-3 py-3 ${props.muted ? "text-ink-2" : ""}`}>
            <div className="text-[13px] text-ink-3">{i.company}</div>
            <div className="text-[15px] leading-snug">{i.headline}</div>
          </li>
        ))}
      </ul>
    </section>
  );
}

function Badge({ tone, children }: { tone: "neutral" | "caution"; children: React.ReactNode }) {
  const cls =
    tone === "caution" ? "bg-caution-bg text-caution" : "border border-line text-ink-2";
  return <span className={`rounded px-2 py-0.5 text-[12px] ${cls}`}>{children}</span>;
}
