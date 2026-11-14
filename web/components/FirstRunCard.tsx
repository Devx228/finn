"use client";

import Link from "next/link";
import { useSyncExternalStore } from "react";
import { FIRST_RUN_EVENT, FIRST_RUN_KEY, FIRST_RUN_TRIES, isFirstRunVisible } from "@/lib/onboarding";

function subscribe(onChange: () => void): () => void {
  window.addEventListener(FIRST_RUN_EVENT, onChange);
  window.addEventListener("storage", onChange);
  return () => {
    window.removeEventListener(FIRST_RUN_EVENT, onChange);
    window.removeEventListener("storage", onChange);
  };
}

function snapshot(): boolean {
  try {
    return isFirstRunVisible(window.localStorage.getItem(FIRST_RUN_KEY));
  } catch {
    return true;
  }
}

function update(dismissed: boolean): void {
  try {
    if (dismissed) window.localStorage.setItem(FIRST_RUN_KEY, "1");
    else window.localStorage.removeItem(FIRST_RUN_KEY);
  } catch {}
  window.dispatchEvent(new Event(FIRST_RUN_EVENT));
}

export function restoreFirstRun(): void {
  update(false);
}

export function FirstRunCard() {
  const visible = useSyncExternalStore(subscribe, snapshot, () => false);
  if (!visible) return null;

  return (
    <section className="mb-4 rounded-xl border border-line bg-surface px-3 py-3" aria-labelledby="first-run-title">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-wider text-accent">Start here</p>
          <h2 id="first-run-title" className="mt-0.5 text-[16px] font-semibold">
            Three things to try
          </h2>
        </div>
        <button onClick={() => update(true)} className="min-h-9 px-2 text-[12px] text-ink-3">
          Dismiss
        </button>
      </div>
      <ol className="mt-2 divide-y divide-line">
        {FIRST_RUN_TRIES.map((item, index) => (
          <li key={item.href}>
            <Link href={item.href} className="flex min-h-14 items-center gap-3 py-2">
              <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-bg text-[12px] font-semibold text-accent">
                {index + 1}
              </span>
              <span className="min-w-0 flex-1">
                <span className="block text-[14px] font-semibold leading-tight">{item.label}</span>
                <span className="mt-0.5 block text-[12px] leading-snug text-ink-2">{item.detail}</span>
              </span>
              <span aria-hidden className="text-ink-3">
                →
              </span>
            </Link>
          </li>
        ))}
      </ol>
    </section>
  );
}
