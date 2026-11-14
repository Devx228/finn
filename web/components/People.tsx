"use client";

import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import { CopyButton } from "@/components/ActionBlock";
import { FreshnessBadge } from "@/components/FreshnessBadge";
import { CandidateRow, ContactLine, PersonBlock, Strength, SyntheticTag } from "@/components/Network";
import { type Loaded, loadWithFallback } from "@/lib/api";
import { formatWhen } from "@/lib/format";
import type { CompanyNetwork, Figure, NetworkHome, PersonView } from "@/lib/types";
import { search } from "@/lib/whoKnows";

const H = "mb-2 text-[12px] font-semibold uppercase tracking-wider text-ink-3";

function short(name: string): string {
  return name.replace(/^(Mr|Mrs|Ms|Dr)\.?\s+/i, "");
}

export function People() {
  const params = useSearchParams();
  const [home, setHome] = useState<Loaded<NetworkHome> | "error" | null>(null);
  const [person, setPerson] = useState<number | null>(null);

  useEffect(() => {
    let live = true;
    loadWithFallback<NetworkHome>("/api/network", "network_home.json")
      .then((d) => live && setHome(d))
      .catch(() => live && setHome("error"));
    return () => {
      live = false;
    };
  }, []);

  return (
    <div>
      <header className="mb-4">
        <h1 className="text-[22px] font-semibold tracking-tight">People</h1>
        <p className="text-[14px] text-ink-2">What your network notices that you wouldn&apos;t.</p>
      </header>
      {home === null && <p className="text-[14px] text-ink-3">Loading your network…</p>}
      {home === "error" && <p className="text-[14px] text-down">Couldn&apos;t load your network.</p>}
      {home && home !== "error" && (
        <div className="mb-3">
          <FreshnessBadge source={home.source} asOf={home.data.as_of} />
        </div>
      )}
      {home && home !== "error" && <Home h={home.data} onPerson={setPerson} initialQuery={params.get("q") ?? ""} />}
      {person !== null && <PersonSheet id={person} onClose={() => setPerson(null)} />}
    </div>
  );
}

function Home({ h, onPerson, initialQuery }: { h: NetworkHome; onPerson: (id: number) => void; initialQuery: string }) {
  const gaps = h.coverage.filter((c) => c.direct === 0);
  const figures = h.figures.filter((f) => f.best || f.you.length).slice(0, 6);
  return (
    <div className="space-y-6">
      {h.directory && <WhoKnows key={initialQuery} h={h} initialQuery={initialQuery} />}

      <p className="rounded-md border border-line px-3 py-2 text-[12px] leading-snug text-ink-3">
        {h.contacts} contacts · {h.synthetic_note}
      </p>

      {figures.length > 0 && (
        <section>
          <h2 className={H}>New faces at your companies</h2>
          <ul className="divide-y divide-line rounded-lg border border-line bg-surface">
            {figures.map((f) => (
              <FigureRow key={f.id} f={f} onOpen={() => onPerson(f.id)} />
            ))}
          </ul>
        </section>
      )}

      {h.keep_warm.length > 0 && (
        <section>
          <h2 className={H}>Reasons to reconnect</h2>
          <ul className="space-y-2">
            {h.keep_warm.slice(0, 5).map((k) => (
              <li key={k.id} className="rounded-lg border border-line bg-surface px-3 py-2.5">
                <ContactLine
                  c={k}
                  right={<span className="text-[12px] text-ink-3">quiet {k.months_cold} mo</span>}
                />
                <p className="mt-0.5 text-[13px] leading-snug text-ink-2">
                  {k.org.replace(/ Limited$/, "")} ({k.relation}) filed{" "}
                  <span className="font-medium text-ink">{k.event_label}</span> on {formatWhen(k.event_ts)}
                  {k.event_text && <>: {k.event_text}</>}
                </p>
                <p className="mt-0.5 text-[12px] text-ink-3">
                  {k.headline} · {k.how_known}
                </p>
                {k.opener && (
                  <details className="mt-1">
                    <summary className="min-h-9 cursor-pointer text-[13px] text-accent">Drafted opener</summary>
                    <p className="mt-1 rounded-md bg-bg px-3 py-2 text-[13px] leading-snug">{k.opener}</p>
                    <div className="mt-2">
                      <CopyButton text={k.opener} label="Copy opener" />
                    </div>
                  </details>
                )}
              </li>
            ))}
          </ul>
        </section>
      )}

      <WhoToCall symbols={h.coverage.map((c) => c.symbol)} />

      <section>
        <h2 className={H}>Expertise map</h2>
        <div className="space-y-2">
          {h.expertise.map((e) => (
            <details key={e.theme} className="rounded-lg border border-line bg-surface">
              <summary className="flex min-h-11 cursor-pointer items-center justify-between px-3 text-[14px]">
                <span className="capitalize">{e.theme}</span>
                <span className="text-[13px] text-ink-3">
                  {e.people[0]?.name} {e.count > 1 && `+${e.count - 1}`}
                </span>
              </summary>
              <ul className="divide-y divide-line border-t border-line px-3">
                {e.people.map((p) => (
                  <li key={p.id} className="py-2">
                    <ContactLine c={p} />
                    <p className="text-[12px] text-ink-3">
                      {p.years} yrs · {p.orgs.join(", ")}
                    </p>
                  </li>
                ))}
              </ul>
            </details>
          ))}
        </div>
      </section>

      <section>
        <h2 className={H}>Coverage of your holdings</h2>
        {gaps.length > 0 && (
          <p className="mb-2 text-[13px] leading-snug text-caution">
            No one who has worked at {gaps.map((g) => g.symbol).join(", ")} — you&apos;d rely on peers.
          </p>
        )}
        <ul className="grid grid-cols-3 gap-1.5">
          {h.coverage.map((c) => (
            <li
              key={c.symbol}
              className={`rounded-md border px-2 py-1.5 text-[12px] ${
                c.direct ? "border-line bg-surface" : "border-caution/40 bg-caution-bg"
              }`}
            >
              <span className="block font-semibold">{c.symbol}</span>
              <span className="text-ink-3 tabular-nums">
                {c.direct} inside · {c.adjacent} peer
              </span>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}

/** Free-text "who do I know at X / who knows about Y" over the directory (no model). */
function WhoKnows({ h, initialQuery }: { h: NetworkHome; initialQuery: string }) {
  const [q, setQ] = useState(initialQuery);
  const hits = useMemo(() => (q.trim().length > 1 ? search(h.directory ?? [], q) : []), [h.directory, q]);
  const examples = ["HDFC Bank", "banking", "steel", "credit risk"];
  return (
    <section>
      <label htmlFor="who" className="sr-only">
        Who do I know at, or who knows about
      </label>
      <input
        id="who"
        value={q}
        onChange={(e) => setQ(e.target.value)}
        placeholder="Who do I know at… / who knows about…"
        className="h-11 w-full rounded-lg border border-line bg-surface px-3 text-[15px] placeholder:text-ink-3"
      />
      {!q && (
        <div className="mt-2 flex flex-wrap gap-1.5">
          {examples.map((x) => (
            <button
              key={x}
              onClick={() => setQ(x)}
              className="h-8 rounded-full border border-line px-3 text-[12px] text-ink-2"
            >
              {x}
            </button>
          ))}
        </div>
      )}
      {q.trim().length > 1 && (
        <ul className="mt-2 divide-y divide-line rounded-lg border border-line bg-surface px-3">
          {hits.length === 0 && <li className="py-2 text-[13px] text-ink-3">No one in your network matches every word.</li>}
          {hits.map(({ person: p, why }) => (
            <li key={p.id} className="py-2">
              <div className="flex items-center justify-between gap-2">
                <span className="text-[14px] font-semibold">
                  {p.name} {p.synthetic && <SyntheticTag />}
                </span>
                <Strength label={p.warmth_label} />
              </div>
              {p.headline && <p className="text-[13px] text-ink-2">{p.headline}</p>}
              {why.length > 0 && <p className="text-[12px] text-ink-2">{why.join(" · ")}</p>}
              <p className="text-[11px] text-ink-3">{p.warmth_why}</p>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function FigureRow({ f, onOpen }: { f: Figure; onOpen: () => void }) {
  return (
    <li>
      <button onClick={onOpen} className="block w-full px-3 py-2.5 text-left">
        <div className="flex items-baseline gap-2 text-[12px] text-ink-3">
          <span className="font-semibold text-ink-2">{f.symbol}</span>
          <span>{f.event}</span>
          <span className="ml-auto tabular-nums">{formatWhen(f.ts)}</span>
        </div>
        <p className="text-[15px] font-medium">{short(f.name)}</p>
        <p className="line-clamp-1 text-[12px] text-ink-3">{f.role}</p>
        {f.you.length > 0 ? (
          <p className="mt-1 text-[13px] text-caution">{f.you[0]}</p>
        ) : (
          f.best && (
            <p className="mt-1 flex items-center gap-2 text-[13px] text-ink-2">
              <span>
                via <span className="font-medium text-ink">{f.best.via.name}</span>
              </span>
              <Strength label={f.best.strength_label} />
            </p>
          )
        )}
      </button>
    </li>
  );
}

function WhoToCall({ symbols }: { symbols: string[] }) {
  const [sym, setSym] = useState<string>(symbols[0] ?? "");
  const [data, setData] = useState<{ sym: string; v: CompanyNetwork | null } | null>(null);
  useEffect(() => {
    if (!sym) return;
    let live = true;
    loadWithFallback<CompanyNetwork>(
      `/api/network/company/${encodeURIComponent(sym)}`,
      `network_company_${sym}.json`,
    )
      .then((d) => live && setData({ sym, v: d.data }))
      .catch(() => live && setData({ sym, v: null }));
    return () => {
      live = false;
    };
  }, [sym]);
  const cur = data?.sym === sym ? data.v : undefined;
  return (
    <section>
      <h2 className={H}>Who should I call about…</h2>
      <div className="-mx-4 mb-2 flex gap-1.5 overflow-x-auto px-4 pb-1">
        {symbols.map((s) => (
          <button
            key={s}
            onClick={() => setSym(s)}
            className={`h-9 shrink-0 rounded-full border px-3 text-[13px] ${
              s === sym ? "border-ink bg-ink text-bg" : "border-line text-ink-2"
            }`}
          >
            {s}
          </button>
        ))}
      </div>
      <div className="rounded-lg border border-line bg-surface px-3">
        {cur === undefined && <p className="py-3 text-[13px] text-ink-3">Loading…</p>}
        {cur === null && <p className="py-3 text-[13px] text-ink-3">No network view for {sym}.</p>}
        {cur && cur.who.length === 0 && (
          <p className="py-3 text-[13px] text-ink-3">No one in your network has worked at {sym} or a peer.</p>
        )}
        {cur && cur.who.length > 0 && (
          <ul className="divide-y divide-line">
            {cur.who.slice(0, 3).map((c) => (
              <CandidateRow key={c.id} c={c} />
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}

function PersonSheet({ id, onClose }: { id: number; onClose: () => void }) {
  const [p, setP] = useState<PersonView | "error" | null>(null);
  useEffect(() => {
    let live = true;
    loadWithFallback<PersonView>(`/api/network/person/${id}`, `network_person_${id}.json`)
      .then((d) => live && setP(d.data))
      .catch(() => live && setP("error"));
    return () => {
      live = false;
    };
  }, [id]);
  return (
    <div className="fixed inset-0 z-30 flex items-end justify-center" role="dialog" aria-modal="true">
      <button aria-label="Close" className="absolute inset-0 bg-black/40" onClick={onClose} />
      <div className="relative max-h-[88dvh] w-full max-w-[480px] overflow-y-auto rounded-t-2xl border-t border-line bg-surface px-4 pb-[max(env(safe-area-inset-bottom),16px)] pt-4">
        <div className="mb-2 flex items-baseline justify-between">
          <h2 className="text-[16px] font-semibold">Diligence on a person</h2>
          <button onClick={onClose} className="min-h-11 px-2 text-[14px] text-ink-2">
            Close
          </button>
        </div>
        {p === null && <p className="text-[13px] text-ink-3">Loading…</p>}
        {p === "error" && <p className="text-[13px] text-down">Couldn&apos;t load this person.</p>}
        {p && p !== "error" && (
          <>
            <PersonBlock p={{ ...p, role: p.mentions[0]?.role, event: p.mentions[0]?.event }} />
            <p className="mt-3 flex items-center gap-1 text-[11px] text-ink-3">
              <SyntheticTag /> contacts on the path are fictional; the executive&apos;s profile is from NSE.
            </p>
          </>
        )}
      </div>
    </div>
  );
}
