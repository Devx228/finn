import type { AlertInputs } from "@/lib/alerts";
import type { Brief, BriefRow } from "@/lib/types";

export interface FilterAuditRow {
  id: string;
  symbol: string;
  filingDate: string;
  headline: string;
  url: string | null;
  score: number;
  moveDate: string;
  movePct: number;
  relativePct: number;
}

export interface FilterAuditResult {
  threshold: number;
  buriedThenMoved: FilterAuditRow[];
  nowThenQuiet: FilterAuditRow[];
}

function istDay(value: string): string {
  const instant = new Date(value);
  return new Date(instant.getTime() + 5.5 * 60 * 60 * 1000).toISOString().slice(0, 10);
}

function oneDecimal(value: number): number {
  return Math.round(value * 10) / 10;
}

function nextMoves(
  item: BriefRow,
  data: AlertInputs,
  niftyReturns: Map<string, number>,
): { date: string; move: number; relative: number }[] {
  const bars = data.companies.find((company) => company.symbol === item.symbol)?.bars ?? [];
  const after = istDay(item.ts);
  const moves = [];
  for (let index = 1; index < bars.length && moves.length < 2; index += 1) {
    const [day, close] = bars[index];
    const previous = bars[index - 1][1];
    if (day <= after || close === null || !previous) continue;
    const move = (close / previous - 1) * 100;
    moves.push({ date: day, move, relative: move - (niftyReturns.get(day) ?? 0) });
  }
  return moves;
}

function row(item: BriefRow, move: { date: string; move: number; relative: number }): FilterAuditRow {
  return {
    id: item.id,
    symbol: item.symbol,
    filingDate: istDay(item.ts),
    headline: item.headline,
    url: item.pdf_url,
    score: item.score,
    moveDate: move.date,
    movePct: oneDecimal(move.move),
    relativePct: oneDecimal(move.relative),
  };
}

export function auditFilters(brief: Brief, data: AlertInputs): FilterAuditResult {
  const nifty = new Map(data.nifty.map(([day, close]) => [day, close]));
  const days = [...nifty.keys()].sort();
  const niftyReturns = new Map<string, number>();
  for (let index = 1; index < days.length; index += 1) {
    const close = nifty.get(days[index]);
    const previous = nifty.get(days[index - 1]);
    if (close !== null && close !== undefined && previous) {
      niftyReturns.set(days[index], (close / previous - 1) * 100);
    }
  }
  const threshold = data.defaults.move_pct;
  const buried = brief.buried.flatMap((group) => group.items);
  const buriedThenMoved = buried.flatMap((item) => {
    const moves = nextMoves(item, data, niftyReturns);
    const hit = moves
      .filter((move) => Math.abs(move.relative) >= threshold)
      .sort((left, right) => Math.abs(right.relative) - Math.abs(left.relative))[0];
    return hit ? [row(item, hit)] : [];
  });
  const nowThenQuiet = brief.now.flatMap((item) => {
    const moves = nextMoves(item, data, niftyReturns);
    if (moves.length < 2 || moves.some((move) => Math.abs(move.relative) >= threshold)) return [];
    const largest = [...moves].sort((left, right) => Math.abs(right.relative) - Math.abs(left.relative))[0];
    return [row(item, largest)];
  });
  return {
    threshold,
    buriedThenMoved: buriedThenMoved.sort(
      (left, right) => Math.abs(right.relativePct) - Math.abs(left.relativePct),
    ),
    nowThenQuiet: nowThenQuiet.sort((left, right) => right.score - left.score),
  };
}
