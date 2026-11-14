"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { loadWithFallback, type Source } from "@/lib/api";
import { type PreCall, preCallReplayHref } from "@/lib/preCall";

function dateLabel(value: string): string {
  return new Date(`${value}T12:00:00+05:30`).toLocaleDateString("en-IN", {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}

function SourceLink({ source }: { source: { label: string; url: string } }) {
  return (
    <a href={source.url} target="_blank" rel="noreferrer" className="underline decoration-line underline-offset-2">
      {source.label}
    </a>
  );
}

function SourceList({ sources }: { sources: { label: string; url: string }[] }) {
  return (
    <span className="flex flex-wrap gap-x-2 gap-y-0.5">
      {sources.map((source) => (
        <SourceLink key={source.url} source={source} />
      ))}
    </span>
  );
}

export function PreCallCard() {
  const [card, setCard] = useState<{ data: PreCall; source: Source } | null>(null);

  useEffect(() => {
    let live = true;
    loadWithFallback<PreCall>("/api/pre-call", "pre_call.json")
      .then((loaded) => live && setCard(loaded))
      .catch(() => {});
    return () => {
      live = false;
    };
  }, []);

  if (!card) return null;
  const data = card.data;
  if (data.mode === "empty" || !data.event || !data.as_of) return null;
  const promise = data.promises?.[0];

  return (
    <section className="mb-4 overflow-hidden rounded-xl border border-line bg-surface" aria-labelledby="pre-call-title">
      <div className="border-b border-line px-3 py-3">
        <div className="flex items-start justify-between gap-3">
          <div>
            <p className="text-[11px] font-semibold uppercase tracking-wider text-accent">
              Before the call {data.mode === "replay" ? "· replay" : ""}
            </p>
            <h2 id="pre-call-title" className="mt-0.5 text-[16px] font-semibold">
              {data.symbol} · {data.event.label}
            </h2>
          </div>
          <span className="shrink-0 text-right text-[12px] font-semibold tabular-nums">
            {dateLabel(data.event.date)}
          </span>
        </div>
        {data.mode === "replay" && data.replay_reason && (
          <p className="mt-2 text-[11px] leading-snug text-ink-3">{data.replay_reason}</p>
        )}
        <div className="mt-2 flex items-center gap-3 text-[11px] text-ink-3">
          <Link href={preCallReplayHref(data.as_of)} className="underline">
            Today as of {dateLabel(data.as_of)}
          </Link>
          <SourceLink source={data.event.source} />
          {card.source === "snapshot" && <span>Snapshot</span>}
        </div>
      </div>

      {promise && (
        <div className="border-b border-line px-3 py-3">
          <p className="text-[10px] font-semibold uppercase tracking-wider text-ink-3">Promise falling due</p>
          <p className="mt-1 text-[14px] font-semibold">{promise.label} · guided {promise.guided}</p>
          <p className="mt-1 text-[13px] leading-snug text-ink-2">{promise.run_rate}</p>
          <p className="mt-1 text-[11px] text-ink-3">{promise.due}</p>
          <div className="mt-1 text-[10px] text-ink-3">
            <SourceList sources={promise.sources} />
          </div>
        </div>
      )}

      <div className="px-3 py-3">
        <h3 className="text-[12px] font-semibold uppercase tracking-wider text-ink-3">Three cited questions</h3>
        <ol className="mt-1 divide-y divide-line">
          {data.questions?.map((question, index) => (
            <li key={question.text} className="py-2 text-[13px] leading-snug">
              <span className="mr-1 font-semibold text-accent">{index + 1}.</span> {question.text}
              <span className="mt-1 block pl-4 text-[10px] text-ink-3">
                <SourceList sources={question.sources} />
              </span>
            </li>
          ))}
        </ol>
        {data.help && (
          <Link href={data.help.href} className="mt-2 block rounded-md bg-bg px-3 py-2 text-[13px]">
            <span className="font-semibold text-accent">Who can help?</span>{" "}
            <span className="font-semibold">{data.help.name}</span>
            {data.help.synthetic && <span className="ml-1 text-[9px] uppercase tracking-wide text-ink-3">synthetic</span>}
            <span className="mt-0.5 block text-[11px] text-ink-2">{data.help.headline}</span>
          </Link>
        )}
      </div>
    </section>
  );
}
