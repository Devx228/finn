export interface PreCallSource {
  label: string;
  url: string;
}

export interface PreCall {
  mode: "live" | "replay" | "empty";
  message?: string;
  replay_reason?: string;
  as_of?: string;
  company?: string;
  symbol?: string;
  event?: { date: string; label: string; source: PreCallSource };
  promises?: {
    label: string;
    due: string;
    guided: string;
    run_rate: string;
    sources: PreCallSource[];
  }[];
  questions?: { text: string; sources: PreCallSource[] }[];
  help?: {
    name: string;
    headline: string;
    why: string;
    synthetic: boolean;
    href: string;
  };
}

export function preCallReplayHref(asOf: string): string {
  return `/?w=7d&as_of=${encodeURIComponent(asOf)}`;
}
