// Mirrors api/finn/models.py. To be generated from the OpenAPI schema once shapes settle.

export type Window = "24h" | "3d" | "7d" | "30d";
export type Tier = "now" | "worth" | "buried";

export interface BriefItem {
  id: string;
  tier: Tier;
  company: string;
  headline: string;
}

export interface Brief {
  window: Window;
  as_of: string;
  placeholder: boolean;
  counts: { filings: number; now: number; worth: number; buried: number };
  items: BriefItem[];
}
