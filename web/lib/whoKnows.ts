// Free-text "who do I know at X / who knows about Y" over the contact directory. Deterministic:
// every query word must match something on the person (name, employer, title, theme, NSE symbol);
// matches are ranked by where they hit, then by how warm the relationship is. No model.

export interface DirectoryEntry {
  id: number;
  name: string;
  synthetic: boolean;
  headline: string | null;
  how_known: string | null;
  last_contact: string | null;
  warmth: number;
  warmth_label: string;
  warmth_why: string;
  career: { org: string; title: string; span: string; current: boolean }[];
  themes: string[];
  symbols: string[];
}

export interface Hit {
  person: DirectoryEntry;
  score: number;
  why: string[];
}

const STOP = new Set(
  "who whom do does i we know knows knew someone anyone person people about at in on of the a an for with to me my our is are has have worked works working there that this".split(" "),
);

const norm = (s: string) => s.toLowerCase().replace(/&/g, " and ").replace(/[^a-z0-9]+/g, " ").trim();

export function terms(q: string): string[] {
  return norm(q)
    .split(" ")
    .filter((w) => w.length > 1 && !STOP.has(w));
}

export function search(dir: DirectoryEntry[], q: string, limit = 8): Hit[] {
  const ts = terms(q);
  if (!ts.length) return [];
  const hits: Hit[] = [];
  for (const p of dir) {
    let score = 0;
    const why = new Set<string>();
    let all = true;
    for (const t of ts) {
      const pre = (s: string) => norm(s).split(" ").some((w) => w.startsWith(t));
      let best = 0;
      let reason = "";
      for (const e of p.career) {
        if (pre(e.org)) {
          const s = e.current ? 4 : 3;
          if (s > best) [best, reason] = [s, `${e.current ? "Works" : "Worked"} at ${e.org} (${e.span})`];
        } else if (pre(e.title) && best < 2) {
          [best, reason] = [2, `${e.title}, ${e.org}`];
        }
      }
      if (p.symbols.some((s) => s.toLowerCase() === t) && best < 4) [best, reason] = [4, `Linked to ${t.toUpperCase()}`];
      const th = p.themes.find((x) => pre(x));
      if (th && best < 2.5) [best, reason] = [2.5, `Knows ${th}`];
      if (pre(p.name) && best < 1) [best, reason] = [1, ""];
      if (!best) {
        all = false;
        break;
      }
      score += best;
      if (reason) why.add(reason);
    }
    if (all) hits.push({ person: p, score: score + p.warmth, why: [...why] });
  }
  return hits.sort((a, b) => b.score - a.score || b.person.warmth - a.person.warmth).slice(0, limit);
}
