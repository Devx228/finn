export const FIRST_RUN_KEY = "finn.firstRunDismissed.v1";
export const FIRST_RUN_EVENT = "finn:first-run";

export const FIRST_RUN_TRIES = [
  { label: "Scan the last 7 days", detail: "See what needs you and what FINN buried.", href: "/?w=7d" },
  {
    label: "Open a 20-second Research brief",
    detail: "CREDITACC has a reviewed promise ledger.",
    href: "/research?s=CREDITACC",
  },
  {
    label: "Find who can help",
    detail: "Search your network for HDFC Bank.",
    href: "/people?q=HDFC%20Bank",
  },
] as const;

export function isFirstRunVisible(value: string | null): boolean {
  return value !== "1";
}
