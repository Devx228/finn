"use client";

import Link from "next/link";
import { useState } from "react";
import type { ItemNetwork } from "@/lib/types";

const H = "text-[11px] font-semibold uppercase tracking-wider text-ink-3";

/** Copies text to the clipboard; says "Copied" for two seconds. */
export function CopyButton({ text, label }: { text: string; label: string }) {
  const [done, setDone] = useState(false);
  return (
    <button
      onClick={() => {
        navigator.clipboard
          ?.writeText(text)
          .then(() => {
            setDone(true);
            setTimeout(() => setDone(false), 2000);
          })
          .catch(() => {});
      }}
      className="min-h-9 rounded-full border border-line px-3 text-[13px] font-medium text-ink"
    >
      {done ? "Copied" : label}
    </button>
  );
}

/** Event to action: what you promised to watch (your last note), what management promised (the
 * ledger), and a drafted message to the person worth calling, each from stored data only. */
export function ActionBlock({ net }: { net: ItemNetwork }) {
  const { note, promise, opener, questions } = net;
  if (!note && !promise && !opener) return null;
  return (
    <section className="mb-4 space-y-3 border-b border-line pb-4">
      {promise && (
        <div>
          <h4 className={H}>Their record on promises</h4>
          <p className="mt-0.5 text-[13px] leading-snug">{promise.pattern}</p>
          {promise.line && (
            <p className="text-[13px] leading-snug text-ink-2">
              {promise.title}: {promise.line}
            </p>
          )}
          <Link href={promise.href} className="mt-1 inline-flex min-h-9 items-center text-[13px] text-accent">
            View promise chain
          </Link>
        </div>
      )}
      {note && (
        <div>
          <h4 className={H}>Your last note on them</h4>
          <p className="mt-0.5 text-[13px] leading-snug text-ink-2">“{note.text}”</p>
          <p className="text-[12px] text-ink-3">
            {new Date(note.date).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" })}
            {note.with.length > 0 && ` · with ${note.with.join(", ")}`} · synthetic
          </p>
        </div>
      )}
      {opener && (
        <div>
          <h4 className={H}>Drafted opener to {opener.to}</h4>
          <p className="mt-0.5 rounded-md bg-bg px-3 py-2 text-[13px] leading-snug">{opener.text}</p>
          <div className="mt-2 flex flex-wrap gap-2">
            <CopyButton text={opener.text} label="Copy opener" />
            {questions.length > 0 && (
              <CopyButton
                text={questions.map((q, i) => `${i + 1}. ${q}`).join("\n")}
                label={`Copy ${questions.length} questions`}
              />
            )}
          </div>
        </div>
      )}
    </section>
  );
}
