import { formatBps, formatCr, formatPct } from "@/lib/format";
import type { ResultsCard as Card } from "@/lib/types";

function Delta({ v }: { v: number | null }) {
  const p = formatPct(v);
  const cls = p.dir === "up" ? "text-up" : p.dir === "down" ? "text-down" : "text-ink-3";
  return <span className={`${cls} tabular-nums`}>{p.text}</span>;
}

/** Spec §11.2: 4×3 grid — rows Revenue/EBITDA/PBT/PAT (bank: NII/PPOP/PBT/PAT), columns value, QoQ, YoY. */
export function ResultsCard({ card }: { card: Card }) {
  const margin = card.margins["ebitda_margin_pct"] ?? card.margins["pat_margin_pct"];
  const marginLabel = card.margins["ebitda_margin_pct"] != null ? "EBITDA margin" : "PAT margin";
  const bps = card.margins["ebitda_margin_bps_yoy"] ?? card.margins["pat_margin_bps_yoy"];
  return (
    <div>
      <div className="mb-2 flex flex-wrap items-center gap-x-2 gap-y-1 text-[12px] text-ink-3">
        <span>{card.period_label}</span>
        <span>·</span>
        <span>{card.basis}</span>
        {card.audited === false && <span>· unaudited</span>}
        <span
          className={`rounded px-1.5 py-px ${card.verified ? "border border-line text-ink-2" : "bg-caution-bg text-caution"}`}
          title={card.verified ? "The filing's own arithmetic checks out" : card.issues.join("; ")}
        >
          {card.verified ? "verified" : "unverified — check filing"}
        </span>
      </div>
      <table className="w-full text-[14px]">
        <thead>
          <tr className="text-[11px] uppercase tracking-wider text-ink-3">
            <th className="py-1 text-left font-normal"></th>
            <th className="py-1 text-right font-normal">{card.unit}</th>
            <th className="py-1 text-right font-normal">QoQ</th>
            <th className="py-1 text-right font-normal">YoY</th>
          </tr>
        </thead>
        <tbody className="tabular-nums">
          {card.rows.map((r) => (
            <tr key={r.metric} className="border-t border-line">
              <td className="py-1.5 pr-2 text-ink-2">{r.label}</td>
              <td className="py-1.5 text-right">{formatCr(r.value_cr).replace(" cr", "")}</td>
              <td className="py-1.5 text-right">
                <Delta v={r.qoq_pct} />
              </td>
              <td className="py-1.5 text-right">
                <Delta v={r.yoy_pct} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {margin != null && (
        <p className="mt-2 text-[13px] text-ink-2 tabular-nums">
          {marginLabel} {margin.toFixed(1)}% <span className="text-ink-3">{formatBps(bps)} YoY</span>
        </p>
      )}
      {card.basis_note && <p className="mt-1 text-[12px] text-caution">{card.basis_note}</p>}
      <p className="mt-2 text-[12px] text-ink-3">
        EBITDA = profit before exceptional items and tax + finance costs + depreciation − other income.
        Numbers from the company&apos;s XBRL filing on NSE.{" "}
        <a className="underline" href={card.sources.xbrl} target="_blank" rel="noreferrer">
          Data
        </a>
        {card.sources.filing && (
          <>
            {" · "}
            <a className="underline" href={card.sources.filing} target="_blank" rel="noreferrer">
              Filing
            </a>
          </>
        )}
      </p>
    </div>
  );
}
