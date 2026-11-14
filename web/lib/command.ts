export interface CommandCompany {
  symbol: string;
  name: string;
  aliases: string[];
}

export interface CommandCatalog {
  companies: CommandCompany[];
}

export interface CommandSource {
  label: string;
  url: string | null;
}

export interface CommandItem {
  label: string;
  text: string;
  href?: string | null;
}

export interface CommandBlock {
  type: "brief" | "filings" | "research" | "who_can_help" | "paths" | "price_stats";
  title: string;
  subtitle?: string;
  items: CommandItem[];
  sources: CommandSource[];
}

export interface CommandResponse {
  query: string;
  blocks: CommandBlock[];
  model_wrote_answer: false;
}

export type LocalCommand = { kind: "research" | "people"; href: string };

const companyKey = (value: string) =>
  value
    .toLowerCase()
    .replace(/&/g, " and ")
    .replace(/\b(limited|ltd)\b/g, " ")
    .replace(/[^a-z0-9]+/g, " ")
    .trim();

export function localCommand(input: string, companies: CommandCompany[]): LocalCommand | null {
  const q = input.trim();
  if (!q) return null;
  if (/^who\s+(?:do\s+i\s+know|knows|can\s+help)\b/i.test(q)) {
    return { kind: "people", href: `/people?q=${encodeURIComponent(q)}` };
  }
  const upper = q.toUpperCase();
  const bySymbol = companies.find((company) => company.symbol.toUpperCase() === upper);
  if (bySymbol) return { kind: "research", href: `/research?s=${encodeURIComponent(bySymbol.symbol)}` };
  if (/^[A-Z0-9][A-Z0-9&-]{0,19}$/.test(q)) {
    return { kind: "research", href: `/research?s=${encodeURIComponent(q)}` };
  }
  const key = companyKey(q);
  const byName = companies.find(
    (company) => companyKey(company.name) === key || company.aliases.some((alias) => companyKey(alias) === key),
  );
  return byName ? { kind: "research", href: `/research?s=${encodeURIComponent(byName.symbol)}` } : null;
}
