"use client";

import { useEffect, useMemo, useState } from "react";
import { type Alert, type AlertInputs, type AlertRules, evaluate } from "@/lib/alerts";
import { loadWithFallback } from "@/lib/api";
import { formatWhen } from "@/lib/format";
import { PushSettings } from "@/components/PushSettings";

const KEY = "finn.alertRules.v2"; // v2: defaults re-chosen by measurement (13 Nov)
const CATS = ["results", "M&A", "management_change", "litigation", "fund_raise", "capex", "credit_rating",
  "insider_trading", "pledging", "dividend"];
const KIND_ICON: Record<Alert["kind"], string> = { volume: "▮▮", price: "↕", filing: "▤" };

function readRules(def: AlertRules): AlertRules {
  try {
    const raw = window.localStorage.getItem(KEY);
    return raw ? { ...def, ...(JSON.parse(raw) as Partial<AlertRules>) } : def;
  } catch {
    return def;
  }
}

/** The alert inbox on Today: a one-line strip that opens the inbox + the investor's own rules. */
export function AlertsStrip() {
  const [data, setData] = useState<AlertInputs | null>(null);
  const [rules, setRules] = useState<AlertRules | null>(null);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    loadWithFallback<AlertInputs>("/api/alerts/inputs", "alerts_inputs.json")
      .then((d) => {
        setData(d.data);
        setRules(readRules(d.data.defaults));
      })
      .catch(() => {});
  }, []);

  const recent = useMemo(
    () => (data && rules ? evaluate(data, { ...rules, days: 7 }) : []),
    [data, rules],
  );
  if (!data || !rules) return null;

  const save = (r: AlertRules) => {
    setRules(r);
    try {
      window.localStorage.setItem(KEY, JSON.stringify(r));
    } catch {}
  };

  return (
    <>
      <button
        onClick={() => setOpen(true)}
        className="mb-4 flex min-h-11 w-full items-center gap-2 rounded-lg border border-line bg-surface px-3 text-left"
      >
        <span className="text-[13px] font-semibold text-accent">Alerts</span>
        <span className="flex-1 truncate text-[13px] text-ink-2">
          {recent.length
            ? `${recent.length} in 7 days · latest ${recent[0].symbol}: ${recent[0].text}`
            : "Nothing crossed your thresholds in 7 days"}
        </span>
        <span className="text-[13px] text-ink-3">Rules</span>
      </button>
      {open && <AlertsSheet data={data} rules={rules} onChange={save} onClose={() => setOpen(false)} />}
    </>
  );
}

function AlertsSheet({
  data,
  rules,
  onChange,
  onClose,
}: {
  data: AlertInputs;
  rules: AlertRules;
  onChange: (r: AlertRules) => void;
  onClose: () => void;
}) {
  const fired30 = useMemo(() => evaluate(data, { ...rules, days: 30 }), [data, rules]);
  const byKind = (k: Alert["kind"]) => fired30.filter((a) => a.kind === k).length;
  const groups = useMemo(() => {
    const g = new Map<string, Alert[]>();
    for (const a of fired30.slice(0, 60)) g.set(a.date, [...(g.get(a.date) ?? []), a]);
    return [...g.entries()];
  }, [fired30]);

  return (
    <div className="fixed inset-0 z-30 flex items-end justify-center" role="dialog" aria-modal="true">
      <button aria-label="Close" className="absolute inset-0 bg-black/40" onClick={onClose} />
      <div className="relative max-h-[90dvh] w-full max-w-[480px] overflow-y-auto rounded-t-2xl border-t border-line bg-surface px-4 pb-[max(env(safe-area-inset-bottom),16px)] pt-4">
        <div className="mb-2 flex items-baseline justify-between">
          <h2 className="text-[16px] font-semibold">Your alert rules</h2>
          <button onClick={onClose} className="min-h-11 px-2 text-[14px] text-ink-2">
            Close
          </button>
        </div>

        <Slider
          label="Unusual volume"
          value={rules.volume_x}
          min={1.5}
          max={5}
          step={0.5}
          fmt={(v) => `≥ ${v}× the 20-day average`}
          onChange={(v) => onChange({ ...rules, volume_x: v })}
        />
        <Slider
          label="Big daily move"
          value={rules.move_pct}
          min={1}
          max={10}
          step={0.5}
          fmt={(v) => `≥ ±${v}% in a day`}
          onChange={(v) => onChange({ ...rules, move_pct: v })}
        />
        <label className="flex min-h-11 items-center justify-between text-[14px]">
          <span>Measure moves against NIFTY</span>
          <input
            type="checkbox"
            checked={rules.vs_nifty}
            onChange={(e) => onChange({ ...rules, vs_nifty: e.target.checked })}
            className="h-5 w-5 accent-[var(--accent)]"
          />
        </label>
        <p className="mt-2 text-[13px] text-ink-2">Filings that should alert me</p>
        <div className="mt-1 flex flex-wrap gap-1.5">
          {CATS.map((c) => {
            const on = rules.categories.includes(c);
            return (
              <button
                key={c}
                aria-pressed={on}
                onClick={() =>
                  onChange({
                    ...rules,
                    categories: on ? rules.categories.filter((x) => x !== c) : [...rules.categories, c],
                  })
                }
                className={`h-9 rounded-full border px-3 text-[13px] ${
                  on ? "border-ink bg-ink text-bg" : "border-line text-ink-2"
                }`}
              >
                {data.category_labels[c] ?? c}
              </button>
            );
          })}
        </div>
        <button onClick={() => onChange(data.defaults)} className="mt-2 min-h-9 text-[12px] text-accent">
          Reset to defaults
        </button>

        <PushSettings />

        <div className="mt-3 rounded-md bg-bg px-3 py-2 text-[13px]">
          With these rules FINN would have alerted you{" "}
          <b className="tabular-nums">{fired30.length}</b> times in the last 30 days —{" "}
          <span className="tabular-nums">
            {byKind("volume")} volume · {byKind("price")} price · {byKind("filing")} filings
          </span>
          .
        </div>

        <h3 className="mt-4 text-[11px] font-semibold uppercase tracking-wider text-ink-3">Inbox · 30 days</h3>
        <div className="mt-1 space-y-3">
          {groups.map(([d, as]) => (
            <div key={d}>
              <p className="text-[12px] text-ink-3">{formatWhen(`${d}T12:00:00+05:30`)}</p>
              <ul className="divide-y divide-line">
                {as.map((a, i) => (
                  <li key={i} className="flex gap-2 py-1.5 text-[13px] leading-snug">
                    <span aria-hidden className="w-5 shrink-0 text-ink-3">
                      {KIND_ICON[a.kind]}
                    </span>
                    <span className="w-24 shrink-0 font-semibold">{a.symbol}</span>
                    {a.url ? (
                      <a href={a.url} target="_blank" rel="noreferrer" className="line-clamp-2 text-ink-2 underline">
                        {a.text}
                      </a>
                    ) : (
                      <span className="text-ink-2">
                        {a.text.replace(" — moved with no disclosure", "")}
                        {a.no_disclosure && (
                          <span className="ml-1 whitespace-nowrap rounded border border-caution px-1 text-[11px] text-caution">
                            no disclosure
                          </span>
                        )}
                      </span>
                    )}
                  </li>
                ))}
              </ul>
            </div>
          ))}
          {fired30.length > 60 && <p className="text-[12px] text-ink-3">Showing the latest 60.</p>}
        </div>
        <p className="mt-4 text-[11px] text-ink-3">
          {data.credit} Evaluated on end-of-day data; your rules stay on this device.
        </p>
      </div>
    </div>
  );
}

function Slider({
  label,
  value,
  min,
  max,
  step,
  fmt,
  onChange,
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  step: number;
  fmt: (v: number) => string;
  onChange: (v: number) => void;
}) {
  return (
    <label className="block py-2">
      <span className="flex justify-between text-[14px]">
        <span>{label}</span>
        <span className="tabular-nums text-ink-2">{fmt(value)}</span>
      </span>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="mt-1 w-full accent-[var(--accent)]"
      />
    </label>
  );
}
