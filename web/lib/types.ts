// Mirrors api/finn/models.py (Brief, BriefRow, BuriedGroup) and push/results.py (card).

export type Window = "24h" | "3d" | "7d" | "30d";
export type Tier = "now" | "worth" | "buried";

export interface ScoreComponent {
  points: number;
  why: string | Record<string, unknown> | null;
}

export interface ResultsRow {
  metric: string;
  label: string;
  value_cr: number | null;
  qoq_pct: number | null;
  yoy_pct: number | null;
}

export interface ResultsCard {
  symbol: string;
  name: string;
  period_end: string;
  period_label: string;
  basis: "consolidated" | "standalone";
  format: "indas" | "bank" | "nbfc";
  audited: boolean | null;
  unit: string;
  rows: ResultsRow[];
  margins: Record<string, number | null>;
  take: string;
  verified: boolean;
  issues: string[];
  basis_note: string | null;
  sources: { xbrl: string; filing: string | null; filed_at: string | null; credit: string };
}

export interface BriefRow {
  id: string;
  tier: Tier;
  symbol: string;
  company: string;
  ts: string;
  category: string;
  category_label: string;
  sub_type: string | null;
  kind: string;
  headline: string;
  score: number;
  components: Record<string, ScoreComponent>;
  pdf_url: string | null;
  filing_ids: number[];
  bundled: number;
  card: ResultsCard | null;
}

export interface BuriedGroup {
  label: string;
  count: number;
  items: BriefRow[];
}

export interface Brief {
  window: Window;
  as_of: string;
  placeholder: boolean;
  counts: { filings: number; now: number; worth: number; buried: number };
  now: BriefRow[];
  worth: BriefRow[];
  buried: BuriedGroup[];
  source_credit: string | null;
}
