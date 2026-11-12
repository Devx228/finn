// Display formatting (spec §11.4): IST times, ₹ crore with Indian grouping, signed % with arrows.

const IST = "Asia/Kolkata";

export function formatAsOf(iso: string): string {
  const d = new Date(iso);
  const date = d.toLocaleDateString("en-IN", { day: "numeric", month: "short", timeZone: IST });
  const time = d.toLocaleTimeString("en-IN", {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
    timeZone: IST,
  });
  return `${date}, ${time} IST`;
}

export function formatToday(now: Date = new Date()): string {
  return now.toLocaleDateString("en-IN", {
    weekday: "short",
    day: "numeric",
    month: "short",
    timeZone: IST,
  });
}

/** "12 Nov" or "14:05" if today (IST). */
export function formatWhen(iso: string, now: Date = new Date()): string {
  const d = new Date(iso);
  const day = (x: Date) => x.toLocaleDateString("en-CA", { timeZone: IST });
  if (day(d) === day(now)) {
    return d.toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit", hour12: false, timeZone: IST });
  }
  return d.toLocaleDateString("en-IN", { day: "numeric", month: "short", timeZone: IST });
}

/** ₹ crore, Indian grouping, one decimal below 1,000 cr; "₹1.2 lakh cr" from 1,00,000 cr. */
export function formatCr(v: number | null): string {
  if (v === null) return "—";
  if (Math.abs(v) >= 100_000) {
    return `₹${(v / 100_000).toLocaleString("en-IN", { maximumFractionDigits: 2 })} lakh cr`;
  }
  const digits = Math.abs(v) >= 1000 ? 0 : 1;
  return `₹${v.toLocaleString("en-IN", { minimumFractionDigits: digits, maximumFractionDigits: digits })} cr`;
}

/** "▲ 12.3%" / "▼ 4.0%" / "—". Direction is carried by the arrow, not only by colour. */
export function formatPct(v: number | null): { text: string; dir: "up" | "down" | "flat" | "none" } {
  if (v === null) return { text: "—", dir: "none" };
  if (Math.abs(v) < 0.05) return { text: "0.0%", dir: "flat" };
  return { text: `${v > 0 ? "▲" : "▼"} ${Math.abs(v).toFixed(1)}%`, dir: v > 0 ? "up" : "down" };
}

export function formatBps(v: number | null | undefined): string {
  if (v === null || v === undefined) return "";
  return `${v > 0 ? "▲" : "▼"} ${Math.abs(v)} bps`;
}
