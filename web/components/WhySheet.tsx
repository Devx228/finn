"use client";

import type { BriefRow } from "@/lib/types";

const ORDER: [string, string][] = [
  ["base", "Type of filing"],
  ["magnitude", "Size of the change"],
  ["portfolio", "Your holding"],
  ["network", "Your network"],
  ["price_reaction", "Price reaction"],
  ["user_pref", "Your preferences"],
  ["staleness", "Age"],
];

function describe(why: unknown): string | null {
  if (why === null || why === undefined) return null;
  if (typeof why === "string") return why;
  const w = why as Record<string, unknown>;
  if ("abnormal_return_pct" in w) {
    const vm = w.volume_multiple != null ? `, volume ${w.volume_multiple}× its 20-day average` : "";
    return `${Number(w.abnormal_return_pct) > 0 ? "+" : ""}${w.abnormal_return_pct}% vs NIFTY on ${w.session}${vm}`;
  }
  return JSON.stringify(why);
}

/** "Why is this here?" — the deterministic score, component by component (spec §8.6). */
export function WhySheet({ item, onClose }: { item: BriefRow; onClose: () => void }) {
  return (
    <div className="fixed inset-0 z-30 flex items-end justify-center" role="dialog" aria-modal="true">
      <button aria-label="Close" className="finn-scrim absolute inset-0 bg-black/40" onClick={onClose} />
      <div className="finn-sheet relative w-full max-w-[480px] rounded-t-2xl border-t border-line bg-surface px-4 pb-[max(env(safe-area-inset-bottom),16px)] pt-4">
        <div className="mb-3 flex items-baseline justify-between">
          <h2 className="text-[16px] font-semibold">Why is this here?</h2>
          <button onClick={onClose} className="min-h-11 px-2 text-[14px] text-ink-2">
            Close
          </button>
        </div>
        <p className="mb-3 text-[13px] text-ink-2">
          {item.company} · {item.category_label}. Score {item.score}: Now from 70, Worth knowing from 40.
        </p>
        <table className="w-full text-[14px]">
          <tbody>
            {ORDER.map(([key, label]) => {
              const c = item.components[key];
              if (!c) return null;
              return (
                <tr key={key} className="border-t border-line align-top">
                  <td className="py-2 pr-2 text-ink-2">{label}</td>
                  <td className="py-2 pr-2 text-[13px] text-ink-3">{describe(c.why)}</td>
                  <td className="py-2 text-right tabular-nums">{c.points > 0 ? `+${c.points}` : c.points}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
