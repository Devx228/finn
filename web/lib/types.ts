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
  network?: ItemNetwork | null;
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

// ---- Network (api/finn/network/service.py) ----

export interface Contact {
  id: number;
  name: string;
  synthetic: boolean;
  headline: string | null;
  how_known: string | null;
  last_contact: string | null;
  warmth: number;
  warmth_label: "strong" | "medium" | "weak";
  warmth_why: string;
}

export interface Candidate extends Contact {
  relevance: number;
  rank: number;
  why: string;
  what_theyd_know: string;
  compliance: string | null;
}

export interface PathView {
  via: Contact;
  overlap: number;
  overlap_label: string;
  strength: number;
  strength_label: string;
  evidence: string[];
  sentence: string;
}

export interface Mention {
  filing_id: number;
  person_id: number;
  role: string | null;
  event: string | null;
  url: string | null;
  symbol: string;
  ts: string;
}

export interface PersonView {
  id: number;
  name: string;
  kind: string;
  synthetic: boolean;
  career: { org: string; title: string | null; span: string; current: boolean }[];
  education: { institution: string; degree: string | null; year: number | null }[];
  you: string[];
  paths: PathView[];
  mentions: Mention[];
  source: string;
  role?: string | null;
  event?: string | null;
}

export interface ItemNetwork {
  people: PersonView[];
  call: Candidate[];
  questions: string[];
  points: number;
}

export interface Figure {
  id: number;
  name: string;
  symbol: string;
  role: string | null;
  event: string | null;
  ts: string;
  paths: number;
  best: PathView | null;
  you: string[];
}

export interface KeepWarm extends Contact {
  symbol: string;
  org: string;
  relation: string;
  event: string;
  event_label: string;
  event_ts: string;
  event_text: string;
  url: string | null;
  months_cold: number;
}

export interface ExpertiseRow {
  theme: string;
  count: number;
  people: (Contact & { years: number; orgs: string[] })[];
}

export interface CoverageRow {
  symbol: string;
  name: string;
  weight_pct: number;
  direct: number;
  adjacent: number;
  best: Candidate | null;
}

export interface NetworkHome {
  as_of: string;
  contacts: number;
  synthetic_note: string;
  keep_warm: KeepWarm[];
  figures: Figure[];
  expertise: ExpertiseRow[];
  coverage: CoverageRow[];
  directory?: import("./whoKnows").DirectoryEntry[];
}

export interface CompanyNetwork {
  symbol: string;
  company: string;
  who: Candidate[];
  people: Figure[];
}

// ---- Research / pull (api/finn/pull/research.py) ----

export interface Quarter {
  end: string;
  label: string;
  fy: number;
  basis: string;
  revenue: number | null;
  ebitda: number | null;
  ebit: number | null;
  pat: number | null;
  nii: number | null;
  ebitda_margin: number | null;
  ebit_margin: number | null;
  pat_margin: number | null;
  revenue_yoy: number | null;
  pat_yoy: number | null;
  xbrl: string;
}

export interface GuidancePoint {
  metric: string;
  period: string;
  low: number;
  high: number;
  unit: string | null;
  quote: string;
  page: number | null;
  by: "rules" | "model";
  scope?: "company" | "segment";
  source?: string;
  call: string;
  call_date: string;
  url: string;
  change: "first given" | "raised" | "cut" | "held" | "narrowed";
}

export interface GuidanceTrack {
  metric: string;
  label: string;
  period: string;
  points: GuidancePoint[];
  actual: {
    value: number;
    unit: string;
    span: string;
    quarters: number;
    basis: string;
    source?: { quote?: string; page?: number; url?: string; call?: string; from?: string; xbrl?: string | null };
  } | null;
  cross_check?: { value: number; unit: string; span: string; basis: string } | null;
  run_rate?: string | null;
  context?: string | null;
  verdict: string;
  verdict_why: string;
  resolved?: boolean;
  story: string;
}

export interface Segment {
  name: string;
  revenue: number;
  ebit: number | null;
  share: number | null;
  margin: number | null;
  yoy: number | null;
}

export interface Business {
  industry: string | null;
  year: string | null;
  basis?: string;
  segments: Segment[];
  single_segment: boolean;
  segment_total?: number;
  source: { xbrl: string } | null;
  note: string | null;
}

export interface CostSummary {
  as_of: string;
  totals: {
    model_calls: number;
    cache_hits: number;
    cache_hit_rate: number | null;
    input_tokens: number;
    output_tokens: number;
    actual_cost_inr: number;
    list_price_usd: number;
    unpriced_calls: number;
  };
  filings: { total: number; by_rules: number; by_model: number };
  documents_read: Record<string, number>;
  by_model: {
    provider: string;
    model: string;
    calls: number;
    cache_hits: number;
    failed: number;
    input_tokens: number;
    output_tokens: number;
    avg_latency_ms: number | null;
  }[];
  by_purpose: { purpose: string; calls: number; cache_hits: number }[];
  note: string;
}

export interface Ledger {
  calls_listed: number;
  calls_read: number;
  resolved: number;
  delivered: number;
  missed: number;
  open: number;
  unverifiable: number;
}

export interface Research {
  symbol: string;
  name: string;
  industry: string | null;
  format: "indas" | "bank" | "nbfc";
  as_of: string;
  quarters: Quarter[];
  guidance: GuidanceTrack[];
  calls: { label: string; filed_at: string; url: string; source?: string; pages: number; n_items: number }[];
  signals: { bull: string[]; bear: string[] };
  ledger?: Ledger;
  business?: Business;
  sources: string;
  network: Candidate[];
}

export interface ResearchIndex {
  companies: {
    symbol: string;
    name: string;
    tracks: number;
    calls: number;
    resolved?: number;
    role?: string | null;
    hero?: boolean;
  }[];
}

export interface JobStep {
  name: string;
  label: string;
  state: "pending" | "running" | "done" | "skipped" | "refused" | "empty";
  detail?: string;
  at?: string;
}

export interface ResearchJob {
  id: number;
  symbol: string;
  status: "queued" | "dispatched" | "running" | "done" | "failed" | "refused";
  runner: "laptop" | "github" | null;
  requested_at: string;
  dispatched_at: string | null;
  claimed_at: string | null;
  heartbeat_at: string | null;
  finished_at: string | null;
  steps: JobStep[];
  message: string | null;
  run_url: string | null;
  note: string;
  laptop_online: boolean;
}

export type JobResponse =
  | { state: "cached"; symbol: string; name: string }
  | { state: "job"; joined: boolean; job: ResearchJob };
