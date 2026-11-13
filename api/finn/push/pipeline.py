"""Push pipeline: classify → bundle → results cards → score → materialise the brief."""

from __future__ import annotations

import re
from collections import Counter

from psycopg import Connection
from psycopg.types.json import Jsonb

from finn.ingest import fetch_filing_text
from finn.llm.router import Router
from finn.push import classify_llm as cl
from finn.push.classify_rules import Classified, classify
from finn.sources.nse import NSE


def _text(pages, n: int = 2) -> str | None:
    return " ".join(pages[:n]) if pages else None


def _store(
    conn: Connection,
    fid: int,
    c: Classified,
    *,
    materiality=None,
    one_line=None,
    entities=None,
    needs_deep_read=False,
    model=None,
    prompt_version=None,
) -> None:
    conn.execute(
        "INSERT INTO filing_class (filing_id, category, sub_type, base, materiality, one_line, "
        "entities, needs_deep_read, decided_by, model, prompt_version, reason) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (filing_id) DO UPDATE SET "
        "category=EXCLUDED.category, sub_type=EXCLUDED.sub_type, base=EXCLUDED.base, "
        "materiality=EXCLUDED.materiality, entities=EXCLUDED.entities, "
        # a rules re-run keeps the fact line written from the text (fact_lines_stage)
        "one_line=CASE WHEN EXCLUDED.decided_by = 'rules' "
        "THEN coalesce(EXCLUDED.one_line, filing_class.one_line) "
        "ELSE EXCLUDED.one_line END, "
        "needs_deep_read=EXCLUDED.needs_deep_read, decided_by=EXCLUDED.decided_by, "
        "model=EXCLUDED.model, prompt_version=EXCLUDED.prompt_version, reason=EXCLUDED.reason, "
        "classified_at=now()",
        (
            fid,
            c.category,
            c.sub_type,
            c.base,
            materiality,
            one_line,
            Jsonb(entities or {}),
            needs_deep_read,
            c.decided_by,
            model,
            prompt_version,
            c.reason,
        ),
    )


def classify_rules_stage(conn: Connection, company_ids: list[int]) -> dict[str, int]:
    rows = conn.execute(
        "SELECT f.id, f.exch_category, f.subject, f.text_pages FROM filings f "
        "LEFT JOIN filing_class k ON k.filing_id = f.id "
        "WHERE f.company_id = ANY(%s) AND (k.filing_id IS NULL OR k.decided_by = 'rules')",
        (company_ids,),
    ).fetchall()
    n = 0
    for fid, cat, subj, pages in rows:
        c = classify(cat, subj, _text(pages))
        if c is not None:
            _store(conn, fid, c)
            n += 1
    conn.commit()
    return {"rules_decided": n, "considered": len(rows)}


def undecided(conn: Connection, company_ids: list[int]) -> list[tuple]:
    return conn.execute(
        "SELECT f.id, f.exch_category, f.subject, f.text_pages FROM filings f "
        "LEFT JOIN filing_class k ON k.filing_id = f.id "
        "WHERE f.company_id = ANY(%s) AND k.filing_id IS NULL ORDER BY f.company_id, f.ts_ist DESC",
        (company_ids,),
    ).fetchall()


def fetch_thin_texts(conn: Connection, nse: NSE, company_ids: list[int]) -> dict[str, int]:
    """Download PDF text only for undecided filings whose subject says nothing."""
    n = 0
    for fid, _cat, subj, pages in undecided(conn, company_ids):
        if pages is None and cl.thin_subject(subj):
            n += fetch_filing_text(conn, nse, fid)
    return {"thin_texts_fetched": n}


def _quarter_facts(conn: Connection, company_id: int) -> tuple[dict, int]:
    """{(period_end, basis): Period} for quarter-length plain facts; plus FY start month."""
    from finn.push.results import Period

    rows = conn.execute(
        """
        SELECT ff.period_end, ff.basis, ff.xbrl_url, ff.audited, x.concept, x.value
        FROM fin_filings ff JOIN fin_facts x ON x.fin_filing_id = ff.id
        WHERE ff.company_id = %s AND ff.parse_error IS NULL AND x.dims = '' AND x.unit = 'INR'
          AND x.period_end = ff.period_end AND x.period_start IS NOT NULL
          AND x.period_end - x.period_start < 100
        """,
        (company_id,),
    ).fetchall()
    out: dict = {}
    for end, basis, url, audited, concept, value in rows:
        p = out.setdefault((end, basis), Period(end, basis, {}, url, audited))
        p.facts[concept] = value
    fy = conn.execute(
        """
        SELECT date_part('month', x.period_start)::int, count(*) FROM fin_filings ff
        JOIN fin_facts x ON x.fin_filing_id = ff.id
        WHERE ff.company_id = %s AND x.period_end - x.period_start >= 360 GROUP BY 1 ORDER BY 2 DESC LIMIT 1
        """,
        (company_id,),
    ).fetchone()
    return out, (fy[0] if fy else 4)


def _shift(d, months: int):
    import calendar
    from datetime import date

    y, m = divmod(d.month - 1 + months, 12)
    y, m = d.year + y, m + 1
    return date(y, m, calendar.monthrange(y, m)[1])


def compute_results_cards(conn: Connection, company_ids: list[int]) -> dict[str, int]:
    from finn.push.results import build, fiscal_label

    n = verified = 0
    for cid in company_ids:
        sym, name, fmt = conn.execute(  # type: ignore[misc]
            "SELECT nse_symbol, name, coalesce(fin_format, 'indas') FROM companies WHERE id=%s", (cid,)
        ).fetchone()
        periods, fy_start = _quarter_facts(conn, cid)
        for (end, basis), cur in periods.items():
            if end < _shift(max(e for e, _ in periods), -12):  # cards for the last ~5 quarters
                continue
            # Prefer consolidated for the card; standalone only where consolidated is absent.
            if basis == "standalone" and (end, "consolidated") in periods:
                continue

            def find(e, b=basis, ps=periods):
                other = "standalone" if b == "consolidated" else "consolidated"
                return ps.get((e, b)) or ps.get((e, other))

            card = build(fmt, cur, find(_shift(end, -3)), find(_shift(end, -12)))
            ann = conn.execute(
                "SELECT f.pdf_url, f.ts_ist FROM filings f JOIN filing_class k ON k.filing_id = f.id "
                "WHERE f.company_id = %s AND k.category = 'results' AND k.sub_type = 'results_filing' "
                "AND f.ts_ist::date BETWEEN %s AND %s + 75 ORDER BY f.ts_ist LIMIT 1",
                (cid, end, end),
            ).fetchone()
            body = {
                "symbol": sym,
                "name": name,
                "period_end": str(end),
                "period_label": fiscal_label(end, fy_start),
                "basis": basis,
                "format": fmt,
                "audited": cur.audited,
                "unit": "₹ cr",
                "rows": card.rows,
                "margins": card.margins,
                "take": card.take,
                "verified": card.verified,
                "issues": card.issues,
                "basis_note": card.basis_note,
                "sources": {
                    "xbrl": cur.xbrl_url,
                    "filing": ann[0] if ann else None,
                    "filed_at": ann[1].isoformat() if ann else None,
                    "credit": "Source: NSE filings (XBRL)",
                },
            }
            conn.execute(
                "INSERT INTO results_cards (company_id, period_end, basis, card, verified, issues) "
                "VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT (company_id, period_end, basis) DO UPDATE "
                "SET card=EXCLUDED.card, verified=EXCLUDED.verified, issues=EXCLUDED.issues, "
                "computed_at=now()",
                (cid, end, basis, Jsonb(body), card.verified, card.issues),
            )
            n += 1
            verified += card.verified
    conn.commit()
    return {"results_cards": n, "verified": verified}


def names_other_company(one_line: str, own_id: int, source_text: str, names: dict[int, str]) -> str | None:
    """A company (from `names`) that the one-liner mentions but the filing itself does not —
    i.e. a detail the model pulled from elsewhere. Returns that company's name, else None."""
    import re

    low, src = one_line.lower(), source_text.lower()
    for cid, name in names.items():
        key = re.split(r"\s+", name.replace("&", "and"))[0].lower()
        if cid == own_id or len(key) <= 3:
            continue
        if re.search(rf"\b{re.escape(key)}\b", low) and not re.search(rf"\b{re.escape(key)}\b", src):
            return name
    return None


def drop_foreign_one_liners(conn: Connection) -> dict[str, int]:
    """Post-check every model one-liner; drop those naming a company absent from the filing."""
    names: dict[int, str] = dict(
        conn.execute(
            "SELECT id, name FROM companies WHERE kind = 'equity' AND id IN "
            "(SELECT DISTINCT company_id FROM filings)"
        ).fetchall()
    )
    rows = conn.execute(
        "SELECT k.filing_id, f.company_id, k.one_line, coalesce(f.subject, ''), f.text_pages "
        "FROM filing_class k JOIN filings f ON f.id = k.filing_id "
        "WHERE k.decided_by = 'llm' AND k.one_line IS NOT NULL"
    ).fetchall()
    dropped = 0
    for fid, cid, ol, subj, pages in rows:
        src = subj + " " + (" ".join(pages[:2]) if pages else "")
        other = names_other_company(ol, cid, src, names)
        if other:
            conn.execute(
                "UPDATE filing_class SET one_line = NULL, reason = reason || %s WHERE filing_id = %s",
                (f" [one-liner dropped: named {other}, not in the filing]", fid),
            )
            dropped += 1
    conn.commit()
    return {"one_liners_dropped": dropped}


def classify_llm_stage(
    conn: Connection, router: Router, company_ids: list[int], limit: int | None = None
) -> dict[str, int]:
    rows = undecided(conn, company_ids)[:limit]
    counts: Counter = Counter()
    for i in range(0, len(rows), cl.BATCH):
        batch = rows[i : i + cl.BATCH]
        payload = [
            {
                "ref": cl.ref_for(fid),
                "exch_category": cat,
                "subject": subj,
                "text": (_text(pages) if cl.thin_subject(subj) else None),
            }
            for fid, cat, subj, pages, _fallback in batch
        ]
        res = router.call(
            "BULK",
            "classify_batch",
            cl.PROMPT_VERSION,
            cl.SYSTEM,
            cl.render_batch(payload),
            cl.Batch,
            cache_payload=payload,
        )
        by_idx = {it.idx: it for it in res.data.items}  # type: ignore[attr-defined]
        for j, (fid, *_rest) in enumerate(batch):
            it = by_idx.get(j)
            if it is None or it.ref != cl.ref_for(fid):
                counts["missing_or_misaligned"] += 1  # left undecided; retried in another batch
                continue
            _store(
                conn,
                fid,
                cl.to_classified(it, res.model),
                materiality=it.materiality,
                one_line=cl.clip_words(it.one_line),
                entities={"people": it.people, "orgs": it.orgs, "amounts": it.amounts},
                needs_deep_read=it.needs_deep_read,
                model=f"{res.provider}:{res.model}",
                prompt_version=cl.PROMPT_VERSION,
            )
            counts["llm_decided"] += 1
        counts["calls"] += 0 if res.cache_hit else 1
        counts["cache_hits"] += 1 if res.cache_hit else 0
        conn.commit()
    return dict(counts)


# -- stage 1b: read event filings before scoring them (finn/push/severity.py) --------------------
def _revenue_ttm(conn: Connection, cid: int) -> float | None:
    from finn.pull.research import quarters

    fmt = conn.execute("SELECT coalesce(fin_format, 'indas') FROM companies WHERE id = %s", (cid,)).fetchone()
    qs, _ = quarters(conn, cid, fmt[0] if fmt else "indas")
    full = [q["revenue"] for q in qs if q.get("revenue") is not None]
    return sum(full[-4:]) if len(full) >= 4 else None


def severity_stage(conn: Connection, company_ids: list[int], days: int = 400) -> dict[str, int]:
    """Re-score every event filing from its text (any decider). Category and one-liner are kept;
    base and reason change. Filings no rule can judge are marked for the hosted model."""
    from finn.push import severity as sv

    rows = conn.execute(
        "SELECT f.id, f.company_id, f.subject, f.text_pages, k.category, k.sub_type, k.base, k.reason, "
        "k.decided_by, k.materiality "
        "FROM filings f JOIN filing_class k ON k.filing_id = f.id WHERE f.company_id = ANY(%s) "
        "AND f.ts_ist >= now() - make_interval(days => %s) AND k.category = ANY(%s)",
        (company_ids, days, list(sv.EVENT)),
    ).fetchall()
    rev: dict[int, float | None] = {}
    counts: Counter = Counter()
    for fid, cid, subj, pages, cat, st, base, reason, by, materiality in rows:
        if cid not in rev:
            rev[cid] = _revenue_ttm(conn, cid)
        why = (reason or "").split(" · read: ")[0].removeprefix("needs model: ")
        s = sv.assess(cat, st, base, why, subj or "", _text(pages, 6), rev[cid])
        if s is None:
            counts["routine"] += 1
            continue
        if s.needs_model:
            if by == "llm":  # the model rated it from the text: its own rating stands
                if materiality is not None:
                    conn.execute(
                        "UPDATE filing_class SET base = %s, reason = %s WHERE filing_id = %s",
                        (round(materiality * 0.6), why, fid),
                    )
                counts["model_rated"] += 1
                continue
            conn.execute(
                "UPDATE filing_class SET reason = %s WHERE filing_id = %s", (f"needs model: {why}", fid)
            )
            counts["to_model"] += 1
            continue
        conn.execute(
            "UPDATE filing_class SET base = %s, reason = %s WHERE filing_id = %s",
            (s.base, f"{why} · read: {s.reason}", fid),
        )
        counts["rescored"] += 1
    conn.commit()
    return dict(counts)


def _focus(reason: str | None) -> str:
    r = (reason or "").removeprefix("needs model: ").split(" · ")[0]
    return r.split(": ", 1)[1] if r.startswith("model (") and ": " in r else r


STOP = {
    "of",
    "the",
    "and",
    "or",
    "a",
    "an",
    "to",
    "in",
    "on",
    "for",
    "by",
    "with",
    "order",
    "update",
    "model",
}
RESULTS_LINE = re.compile(r"\b(?:approved|announced|declared)\b.{0,60}\b(?:financial )?results\b", re.I)


def _window(text: str, focus: str, n: int = 1400) -> str:
    """The part of the filing about this item: from the first place its words appear (a letter
    listing results first and the disposal third would otherwise only show the results)."""
    t = re.sub(r"\s+", " ", text)
    words = [w for w in re.findall(r"[a-z]{4,}", focus.lower()) if w not in STOP]
    hits = [i for w in words for i in [t.lower().find(w, 200)] if i > 0]
    start = max(0, min(hits) - 150) if hits else 0
    return t[start : start + n]


def fact_lines_stage(
    conn: Connection, router: Router, company_ids: list[int], days: int = 30
) -> dict[str, int]:
    """Every event filing gets a one-line fact from its text (hosted model), so a card never shows
    the exchange's generic label. Filings no rule could judge also take the model's rating. If the
    model returns nothing usable, an operational stop falls back to the filing's own sentence;
    anything else is left without a line and is buried by the brief."""
    from finn.push import severity as sv

    rows = conn.execute(
        "SELECT f.id, f.exch_category, f.subject, f.text_pages, k.one_line, k.reason, "
        "coalesce(k.model, '') FROM filings f "
        "JOIN filing_class k ON k.filing_id = f.id WHERE f.company_id = ANY(%s) AND f.dup_of IS NULL "
        "AND f.ts_ist >= now() - make_interval(days => %s) AND k.category = ANY(%s) "
        "AND coalesce(k.sub_type, '') <> ALL(%s) AND f.text_pages IS NOT NULL ORDER BY f.ts_ist",
        (company_ids, days, list(sv.EVENT), list(sv.ROUTINE_SUBTYPES)),
    ).fetchall()
    # empty line, no rule could judge it, or only the small local model has rated it
    todo = [
        r[:6]
        for r in rows
        if sv.says_nothing(r[4], r[1])
        or (r[5] or "").startswith("needs model: ")
        or (r[6].startswith("ollama") and " · read: " not in (r[5] or ""))
    ]
    counts: Counter = Counter()
    for i in range(0, len(todo), cl.BATCH):
        batch = todo[i : i + cl.BATCH]
        payload = [
            {
                "ref": cl.ref_for(fid),
                "exch_category": cat,
                # a board-outcome letter lists several items: name the one this filing is about
                "subject": f"{subj} [summarise the item about: {_focus(why)}]",
                "text": _window(" ".join(pages), _focus(why)),
            }
            for fid, cat, subj, pages, _one, why in batch
        ]
        try:
            res = router.call(
                "EXTRACT",
                "fact_line",
                cl.PROMPT_VERSION,
                cl.SYSTEM,
                cl.render_batch(payload),
                cl.Batch,
                cache_payload=payload,
            )
            by_idx = {it.idx: it for it in res.data.items}  # type: ignore[attr-defined]
            model = f"{res.provider}:{res.model}"
        except Exception as e:  # model down: fall back below
            by_idx, model = {}, f"unavailable: {type(e).__name__}"
            counts["model_errors"] += 1
        for j, (fid, cat, _subj, pages, _one, why) in enumerate(batch):
            it = by_idx.get(j)
            line = cl.clip_words(it.one_line) if it is not None and it.ref == cl.ref_for(fid) else None
            if line and (sv.says_nothing(line, cat) or not sv.grounded(line, " ".join(pages or []))):
                line = None
            if line is None and pages:
                line = sv.verbatim_fact(" ".join(pages), sv.OPSTOP)
            sets, args = ["one_line = %s"], [line]
            # no rule judged it from the text: the hosted model's rating replaces any earlier one
            if it is not None and line and " · read: " not in (why or ""):
                kept = (why or "").removeprefix("needs model: ").split(" · rated by ")[0]
                sets += ["base = %s", "materiality = %s", "reason = %s", "model = %s"]
                args += [round(it.materiality * 0.6), it.materiality, f"{kept} · rated by {model}", model]
            conn.execute(f"UPDATE filing_class SET {', '.join(sets)} WHERE filing_id = %s", (*args, fid))
            if line and RESULTS_LINE.search(line):
                # the filing is a results release after all: the results card already covers it
                conn.execute(
                    "UPDATE filing_class SET sub_type = 'press_release', base = LEAST(base, 20) "
                    "WHERE filing_id = %s",
                    (fid,),
                )
                counts["results_release"] += 1
            counts["lines" if line else "nothing_useful"] += 1
        conn.commit()
    return dict(counts)


# -- management-change headlines: who, what role, joining or leaving, from when ---------------------
MGMT_VERB = {
    "appointment": "appointed",
    "re-appointment": "re-appointed",
    "re-designation": "re-designated",
    "resignation": "resigns as",
    "cessation": "ceases to be",
    "retirement": "retires as",
}
MGMT_FACT = re.compile(
    r"\b(appoint\w*|re-?appoint\w*|resign\w*|retire\w*|steps? down|cease\w*|cessation|joins|leaves|"
    r"designat\w*|superannuat\w*|elevat\w*|names?|succeed\w*|takes? over|assum\w*|vacat\w*|in place of)\b",
    re.I,
)
HONORIFIC = re.compile(r"^(?:mr|ms|mrs|dr|shri|smt)\.?\s+", re.I)


def _short_role(role: str | None) -> str:
    r = re.split(r" - | – |\(|;", role or "")[0]
    r = re.sub(r"\s+(?:of|in|on) the (?:board|company|bank)\b.*$", "", r, flags=re.I).strip(" ,")
    words = r.split()
    return " ".join(words[:9]) + ("…" if len(words) > 9 else "")


def _when(d) -> str:
    return f" from {d.day} {d:%b %Y}" if d else ""


EVENT_WORDS = [
    ("retirement", re.compile(r"retire|complet\w*(?: of)? (?:his|her) (?:tenure|term)|superannuat", re.I)),
    ("resignation", re.compile(r"resign", re.I)),
    ("cessation", re.compile(r"cease|cessation", re.I)),
    ("re-appointment", re.compile(r"re-?appoint", re.I)),
    ("appointment", re.compile(r"\bappoint", re.I)),
]
BOILER_REASON = re.compile(
    r"(?:reason for change\s*)?viz\.?,?\s*appointment,?\s*re-?\s*appointment,?\s*"
    r"resignation,?\s*removal,?\s*death\s*or\s*otherwise",
    re.I,
)
DATE_PHRASE = re.compile(
    r"(?:w\.?e\.?f\.?|with effect from|effective(?: from)?|close of business hours (?:of|on)|from)\s+"
    r"(\d{1,2}(?:st|nd|rd|th)?\s+[A-Z][a-z]+,?\s+\d{4}|[A-Z][a-z]+\s+\d{1,2},?\s+\d{4})",
)


def _parse_day(s: str):
    from datetime import datetime as dt

    s = re.sub(r"(\d)(st|nd|rd|th)", r"", s).replace(",", "")
    for f in ("%d %B %Y", "%B %d %Y", "%d %b %Y", "%b %d %Y"):
        try:
            return dt.strptime(s, f).date()
        except ValueError:
            continue
    return None


def verify_mention(name: str, event: str, eff, text: str) -> tuple[str | None, object]:
    """Confirm, never override: the extracted event stands only if the filing says it right after
    the person's name ("Mr. Anup Bagchi is appointed as MD & CEO w.e.f. October 27, 2026"); the date
    is the one stated there. Unconfirmed → (None, None): the person is left out of the line."""
    rx = dict(EVENT_WORDS).get(event)
    if rx is None:
        return None, None
    text = BOILER_REASON.sub(" ", text)  # the SEBI table header lists every possible reason
    surname = HONORIFIC.sub("", name).split()[-1]
    for m in re.finditer(rf"\b{re.escape(surname)}\b", text):
        after = text[m.end() : m.end() + 160]
        # stop at the next person's honorific: their event isn't this person's
        after = re.split(r"\b(?:Mr|Ms|Mrs|Dr)\.?\s", after)[0]
        if rx.search(after):
            d = DATE_PHRASE.search(after)
            return event, eff or (_parse_day(d.group(1)) if d else None)
    return None, None


def mgmt_line(mentions: list[tuple]) -> str | None:
    """'Anup Bagchi appointed MD & CEO from 27 Oct 2026; Sashidhar Jagdishan retires as MD & CEO'."""
    parts, seen = [], set()
    for name, role, event, eff in mentions:
        key = (name, event)
        if key in seen or event not in MGMT_VERB:
            continue
        seen.add(key)
        parts.append(f"{HONORIFIC.sub('', name.strip())} {MGMT_VERB[event]} {_short_role(role)}{_when(eff)}")
    return "; ".join(parts[:2]) or None


def management_lines_stage(
    conn: Connection, router: Router, company_ids: list[int], days: int = 30
) -> dict[str, int]:
    """Every management-change card says who, what role, joining or leaving, from when: built from
    the people the filing names (no model) when they were extracted, else written by the hosted
    model from the filing text. A line that doesn't state a change is never used."""
    from finn.push import severity as sv

    rows = conn.execute(
        "SELECT f.id, f.exch_category, f.subject, f.text_pages, k.one_line FROM filings f "
        "JOIN filing_class k ON k.filing_id = f.id WHERE f.company_id = ANY(%s) AND f.dup_of IS NULL "
        "AND f.ts_ist >= now() - make_interval(days => %s) AND k.category = 'management_change' "
        "ORDER BY f.ts_ist",
        (company_ids, days),
    ).fetchall()
    counts: Counter = Counter()
    todo = []
    for fid, cat, subj, pages, one in rows:
        ms = conn.execute(
            "SELECT p.full_name, m.role, m.event, m.effective_date FROM person_mentions m "
            "JOIN persons p ON p.id = m.person_id WHERE m.filing_id = %s",
            (fid,),
        ).fetchall()
        if ms and pages:
            text = re.sub(r"\s+", " ", " ".join(pages))
            ms = [(n, r, *verify_mention(n, e, d, text)) for n, r, e, d in ms]
        # built from the named people only when every one has a stated date; else read the text
        line = mgmt_line(ms) if ms and all(m[3] for m in ms) else None
        if line:
            conn.execute("UPDATE filing_class SET one_line = %s WHERE filing_id = %s", (line, fid))
            counts["from_people"] += 1
        elif one and MGMT_FACT.search(one) and not cl.THIN.search(one):
            counts["kept"] += 1
        elif pages:
            todo.append((fid, cat, subj, pages, mgmt_line(ms) if ms else None))
        else:
            counts["no_text"] += 1
    conn.commit()
    for i in range(0, len(todo), cl.BATCH):
        batch = todo[i : i + cl.BATCH]
        payload = [
            {
                "ref": cl.ref_for(fid),
                "exch_category": cat,
                "subject": f"{subj} [one line: who, what role, joining or leaving, and from what date]",
                "text": _window(" ".join(pages), "appointment resignation cessation retirement"),
            }
            for fid, cat, subj, pages, _fallback in batch
        ]
        try:
            res = router.call(
                "EXTRACT",
                "mgmt_line",
                cl.PROMPT_VERSION,
                cl.SYSTEM,
                cl.render_batch(payload),
                cl.Batch,
                cache_payload=payload,
            )
            by_idx = {it.idx: it for it in res.data.items}  # type: ignore[attr-defined]
        except Exception:
            by_idx = {}
            counts["model_errors"] += 1
        for j, (fid, _cat, _subj, _pages, fallback) in enumerate(batch):
            it = by_idx.get(j)
            line = cl.clip_words(it.one_line) if it is not None and it.ref == cl.ref_for(fid) else None
            if line and not sv.grounded(line, " ".join(_pages or [])):
                line = None
            if not (line and MGMT_FACT.search(line)) and fallback:
                line = fallback  # the people the filing names, without a date it doesn't state
                counts["from_people_undated"] += 1
            if line:
                line = HONORIFIC.sub("", line)
            if line and MGMT_FACT.search(line):
                conn.execute("UPDATE filing_class SET one_line = %s WHERE filing_id = %s", (line, fid))
                counts["from_model"] += 1
            else:
                conn.execute("UPDATE filing_class SET one_line = NULL WHERE filing_id = %s", (fid,))
                counts["nothing_useful"] += 1
        conn.commit()
    return dict(counts)


def label_lines_stage(
    conn: Connection, router: Router, company_ids: list[int], days: int = 30
) -> dict[str, int]:
    """Any filing (every category but the results cards) whose headline would be the exchange's
    label or an empty phrase gets a one-line fact from its own text, by the hosted model."""
    from finn.push import severity as sv
    from finn.push.brief import clean_subject

    rows = conn.execute(
        "SELECT f.id, f.exch_category, f.subject, f.text_pages, k.one_line FROM filings f "
        "JOIN filing_class k ON k.filing_id = f.id WHERE f.company_id = ANY(%s) AND f.dup_of IS NULL "
        "AND f.ts_ist >= now() - make_interval(days => %s) AND f.text_pages IS NOT NULL "
        "AND NOT (k.category = 'results' AND coalesce(k.sub_type, '') = 'results_filing') ORDER BY f.ts_ist",
        (company_ids, days),
    ).fetchall()
    todo = [
        (fid, cat, subj, pages)
        for fid, cat, subj, pages, one in rows
        if sv.says_nothing(one or clean_subject(subj), cat)
    ]
    counts: Counter = Counter()
    for i in range(0, len(todo), cl.BATCH):
        batch = todo[i : i + cl.BATCH]
        payload = [
            {"ref": cl.ref_for(fid), "exch_category": cat, "subject": subj, "text": _text(pages)}
            for fid, cat, subj, pages in batch
        ]
        try:
            res = router.call(
                "EXTRACT",
                "label_line",
                cl.PROMPT_VERSION,
                cl.SYSTEM,
                cl.render_batch(payload),
                cl.Batch,
                cache_payload=payload,
            )
            by_idx = {it.idx: it for it in res.data.items}  # type: ignore[attr-defined]
        except Exception:
            by_idx = {}
            counts["model_errors"] += 1
        for j, (fid, cat, _s, _p) in enumerate(batch):
            it = by_idx.get(j)
            line = cl.clip_words(it.one_line) if it is not None and it.ref == cl.ref_for(fid) else None
            if line and not sv.says_nothing(line, cat) and sv.grounded(line, " ".join(_p or [])):
                conn.execute("UPDATE filing_class SET one_line = %s WHERE filing_id = %s", (line, fid))
                counts["lines"] += 1
            else:
                counts["nothing_useful"] += 1
        conn.commit()
    return dict(counts)


def ground_check_stage(conn: Connection, company_ids: list[int], days: int = 30) -> dict[str, int]:
    """Re-check every stored one-line summary against its filing's text: a period or number the
    filing doesn't contain means the line can't be trusted; it is cleared (and rewritten next run)."""
    from finn.push import severity as sv

    n = 0
    for fid, line, pages, subj in conn.execute(
        "SELECT f.id, k.one_line, f.text_pages, coalesce(f.subject, '') FROM filings f "
        "JOIN filing_class k ON k.filing_id = f.id "
        "WHERE f.company_id = ANY(%s) AND f.ts_ist >= now() - make_interval(days => %s) "
        "AND k.one_line IS NOT NULL",
        (company_ids, days),
    ).fetchall():
        # no text read: the line can only be as good as the subject it was written from
        if not sv.grounded(line, " ".join(pages) if pages else subj):
            conn.execute("UPDATE filing_class SET one_line = NULL WHERE filing_id = %s", (fid,))
            n += 1
    conn.commit()
    return {"cleared": n}
