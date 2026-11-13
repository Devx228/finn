"use client";

import { useEffect, useState } from "react";
import { API_BASE, postJson } from "@/lib/api";
import type { JobResponse, JobStep, ResearchJob } from "@/lib/types";

const TERMINAL = new Set(["done", "failed", "refused"]);
const KEY = (s: string) => `finn.job.${s}`;
const store = {
  get: (s: string) => {
    try {
      return Number(localStorage.getItem(KEY(s))) || null;
    } catch {
      return null;
    }
  },
  set: (s: string, id: number | null) => {
    try {
      if (id) localStorage.setItem(KEY(s), String(id));
      else localStorage.removeItem(KEY(s));
    } catch {}
  },
};

const ICON: Record<JobStep["state"], string> = {
  pending: "○",
  running: "◐",
  done: "●",
  skipped: "–",
  refused: "×",
  empty: "×",
};

const secs = (from: string | null, to?: string | null) =>
  from ? Math.max(0, Math.round(((to ? Date.parse(to) : Date.now()) - Date.parse(from)) / 1000)) : null;

/** No report for this ticker yet: start a research job and show where it is until it's ready. */
export function ResearchJobPanel({ sym, onReady }: { sym: string; onReady: () => void }) {
  const [job, setJob] = useState<ResearchJob | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [, tick] = useState(0);
  const [jobId, setJobId] = useState<number | null>(() => store.get(sym));

  useEffect(() => {
    const t = setInterval(() => tick((x) => x + 1), 1000); // elapsed-time counters
    return () => clearInterval(t);
  }, []);

  // poll the job until it finishes; a reload of the page resumes the same job
  useEffect(() => {
    if (!jobId) return;
    let alive = true;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const once = async () => {
      try {
        const r = await fetch(`${API_BASE}/api/research/jobs/${jobId}`, { cache: "no-store" });
        if (!alive) return;
        if (!r.ok) {
          store.set(sym, null);
          setJobId(null);
          return;
        }
        const j = (await r.json()) as ResearchJob;
        if (!alive) return;
        setJob(j);
        setErr(null);
        if (TERMINAL.has(j.status)) {
          store.set(sym, null);
          if (j.status === "done") onReady();
          return;
        }
      } catch {
        if (alive) setErr("Lost contact with the live API; retrying.");
      }
      if (alive) timer = setTimeout(once, 4000);
    };
    once();
    return () => {
      alive = false;
      if (timer) clearTimeout(timer);
    };
  }, [jobId, sym, onReady]);

  const start = async () => {
    setBusy(true);
    setErr(null);
    try {
      const r = await postJson<JobResponse | { detail: { message: string } }>("/api/research/jobs", { symbol: sym });
      if (!r.ok) {
        setErr("detail" in r.data ? r.data.detail.message : `The API answered HTTP ${r.status}.`);
        return;
      }
      const d = r.data as JobResponse;
      if (d.state === "cached") return onReady();
      store.set(sym, d.job.id);
      setJob(d.job);
      setJobId(d.job.id);
    } catch {
      setErr(
        "The live API isn't reachable right now (it may be waking up, about a minute on the free tier), so a new ticker can't be started from here. Try again shortly.",
      );
    } finally {
      setBusy(false);
    }
  };

  if (!job) {
    return (
      <div className="rounded-lg border border-line bg-surface px-3 py-3 text-[14px] text-ink-2">
        <p className="font-medium text-ink">No research view for {sym} yet.</p>
        <p className="mt-1 text-[13px]">
          FINN can build one now: it fetches two years of quarterly results and up to eight call transcripts from
          NSE (once, slowly, cached), reads them, and checks what management promised against what was
          reported. It runs on the owner&apos;s laptop if it&apos;s online, otherwise on a GitHub Actions runner.
          It takes a few minutes.
        </p>
        <button
          onClick={start}
          disabled={busy}
          className="mt-3 h-11 w-full rounded-lg bg-ink text-[14px] font-semibold text-bg disabled:opacity-50"
        >
          {busy ? "Asking…" : `Research ${sym} now`}
        </button>
        {err && <p className="mt-2 text-[13px] text-ink">{err}</p>}
      </div>
    );
  }

  const waited = secs(job.requested_at, job.finished_at);
  const ran = secs(job.claimed_at, job.finished_at);
  return (
    <div className="rounded-lg border border-line bg-surface px-3 py-3 text-[14px]" aria-live="polite">
      <p className="font-medium">
        Researching {sym}
        <span className="ml-2 text-[12px] font-normal text-ink-3">job {job.id}</span>
      </p>
      <p className="mt-1 text-[13px] text-ink-2">{job.note}</p>
      <ol className="mt-3 space-y-2">
        <li className="flex gap-2 text-[13px]">
          <span className="w-4 text-center">{job.claimed_at ? "●" : "◐"}</span>
          <span>
            {job.claimed_at
              ? `Runner started (${job.runner === "laptop" ? "owner's laptop" : "GitHub Actions"}) after ${secs(job.dispatched_at ?? job.requested_at, job.claimed_at)} s`
              : job.dispatched_at
                ? `Waiting for a GitHub runner to start: ${secs(job.dispatched_at)} s so far`
                : "Waiting for a worker"}
          </span>
        </li>
        {job.steps.map((s) => (
          <li key={s.name} className="flex gap-2 text-[13px]">
            <span className="w-4 text-center">{ICON[s.state]}</span>
            <span>
              {s.label}
              {s.detail && <span className="block text-[12px] text-ink-3">{s.detail}</span>}
            </span>
          </li>
        ))}
      </ol>
      <p className="mt-3 text-[11px] text-ink-3">
        {waited !== null && `${waited} s since you asked`}
        {ran !== null && ` · ${ran} s running`}
        {job.run_url && (
          <>
            {" · "}
            <a className="underline" href={job.run_url} target="_blank" rel="noreferrer">
              run log
            </a>
          </>
        )}
      </p>
      {(job.status === "failed" || job.status === "refused") && (
        <button
          onClick={() => {
            setJob(null);
            setJobId(null);
            store.set(sym, null);
          }}
          className="mt-2 h-10 w-full rounded-lg border border-line text-[13px]"
        >
          Back
        </button>
      )}
      {err && <p className="mt-2 text-[12px] text-ink-3">{err}</p>}
    </div>
  );
}
