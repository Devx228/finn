"""Rules miss only: route a command to stored FINN tools and return cited typed blocks.

The model never answers the investor. It can only select up to two tools from a closed enum.
Code validates the plan, reads existing stored data, computes price statistics, and builds every
displayed line. No prompt, raw address or model-written research prose is persisted or returned.
"""

from __future__ import annotations

import json
from typing import Literal

from psycopg import Connection
from pydantic import BaseModel, ConfigDict, Field

from finn.jobs import JobError, requester_id

PER_REQUESTER_HOUR = 10
PER_REQUESTER_DAY = 30
GLOBAL_DAY = 200
MAX_PROMPT = 240

ToolName = Literal["brief", "filings", "research", "who_can_help", "paths", "price_stats"]
ResearchSection = Literal["summary", "promises", "business", "financials", "bull_bear"]
Window = Literal["24h", "3d", "7d", "30d"]


class ToolCall(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool: ToolName
    symbol: str | None = None
    section: ResearchSection = "summary"
    window: Window = "7d"
    limit: int = Field(default=3, ge=1, le=5)


class CommandPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    calls: list[ToolCall] = Field(min_length=1, max_length=2)


def catalog(conn: Connection) -> dict:
    rows = conn.execute(
        "SELECT nse_symbol, name, aliases FROM companies WHERE kind = 'equity' ORDER BY name"
    ).fetchall()
    return {
        "companies": [
            {"symbol": symbol, "name": name, "aliases": list(aliases or [])} for symbol, name, aliases in rows
        ]
    }


def _available(conn: Connection) -> list[dict]:
    rows = conn.execute(
        "SELECT DISTINCT c.nse_symbol, c.name FROM companies c WHERE "
        "EXISTS (SELECT 1 FROM views v WHERE v.key IN "
        "('research:' || c.nse_symbol, 'network:company:' || c.nse_symbol)) "
        "OR EXISTS (SELECT 1 FROM brief_items b WHERE b.company_id = c.id) "
        "ORDER BY c.name"
    ).fetchall()
    return [{"symbol": symbol, "name": name} for symbol, name in rows]


def _rate_limit(conn: Connection, ip: str | None) -> None:
    who = requester_id(ip)
    counts = conn.execute(
        "SELECT count(*) FILTER (WHERE requested_at > now() - interval '1 hour'), "
        "count(*) FILTER (WHERE requested_at > now() - interval '1 day') "
        "FROM command_requests WHERE requester = %s",
        (who,),
    ).fetchone()
    hour, day = counts if counts is not None else (0, 0)
    if hour >= PER_REQUESTER_HOUR or day >= PER_REQUESTER_DAY:
        raise JobError(
            429,
            "rate_limited",
            f"Command limit reached: {PER_REQUESTER_HOUR} an hour and {PER_REQUESTER_DAY} a day "
            "from one connection. Symbol and people-search routes still work without the model.",
        )
    total_row = conn.execute(
        "SELECT count(*) FROM command_requests WHERE requested_at > now() - interval '1 day'"
    ).fetchone()
    total = total_row[0] if total_row is not None else 0
    if total >= GLOBAL_DAY:
        raise JobError(
            429,
            "daily_cap",
            "FINN has reached today's command-model allowance. Symbol and people-search routes "
            "still work without the model.",
        )
    conn.execute("INSERT INTO command_requests (requester) VALUES (%s)", (who,))
    conn.commit()


def _view(conn: Connection, key: str) -> dict | None:
    row = conn.execute("SELECT body FROM views WHERE key = %s", (key,)).fetchone()
    return row[0] if row else None


def _source(label: str, url: str | None = None) -> dict:
    return {"label": label, "url": url if url and url != "-" else None}


def _empty(kind: ToolName, title: str, text: str) -> dict:
    return {"type": kind, "title": title, "items": [{"label": "Not available", "text": text}], "sources": []}


def _brief_rows(body: dict) -> list[dict]:
    rows = list(body.get("now", [])) + list(body.get("worth", []))
    for group in body.get("buried", []):
        rows.extend(group.get("items", []))
    return sorted(rows, key=lambda row: row.get("ts", ""), reverse=True)


def _brief(conn: Connection, call: ToolCall) -> dict:
    body = _view(conn, f"brief:{call.window}")
    if not body:
        return _empty("brief", "Brief", "The stored brief is not materialised yet.")
    rows = _brief_rows(body)
    if call.symbol:
        rows = [row for row in rows if row.get("symbol") == call.symbol]
    rows = rows[: call.limit]
    if not rows:
        return _empty("brief", "Brief", "No matching item is stored in this brief window.")
    return {
        "type": "brief",
        "title": f"{call.window} brief" + (f" · {call.symbol}" if call.symbol else ""),
        "subtitle": f"As of {body.get('as_of', 'not stated')}",
        "items": [
            {
                "label": f"{row.get('symbol')} · {row.get('category_label', row.get('category', 'Filing'))}",
                "text": row.get("headline") or "No stored summary.",
                "href": row.get("pdf_url") if row.get("pdf_url") != "-" else None,
            }
            for row in rows
        ],
        "sources": [
            _source("Company filing on NSE", row.get("pdf_url"))
            for row in rows
            if row.get("pdf_url") and row.get("pdf_url") != "-"
        ],
    }


def _filings(conn: Connection, call: ToolCall) -> dict:
    args: list[object] = []
    where = ""
    if call.symbol:
        where = "WHERE c.nse_symbol = %s"
        args.append(call.symbol)
    args.append(call.limit)
    rows = conn.execute(
        "SELECT c.nse_symbol, f.ts_ist, coalesce(fc.one_line, f.subject, f.exch_category), "
        "f.pdf_url FROM filings f JOIN companies c ON c.id = f.company_id "
        "LEFT JOIN filing_class fc ON fc.filing_id = f.id "
        f"{where} ORDER BY f.ts_ist DESC LIMIT %s",
        tuple(args),
    ).fetchall()
    if not rows:
        return _empty("filings", "Latest filings", "No matching stored filing was found.")
    return {
        "type": "filings",
        "title": "Latest filings" + (f" · {call.symbol}" if call.symbol else ""),
        "items": [
            {
                "label": f"{symbol} · {when.date().isoformat()}",
                "text": text or "Nothing beyond the exchange's label.",
                "href": url,
            }
            for symbol, when, text, url in rows
        ],
        "sources": [_source("Company filing on NSE", url) for _, _, _, url in rows if url],
    }


def _fmt_cr(value: float | int | None) -> str:
    if value is None:
        return "not stated"
    return f"₹{float(value):,.1f} cr"


def _research(conn: Connection, call: ToolCall) -> dict:
    if not call.symbol:
        return _empty("research", "Research", "Name a company or NSE symbol for stored research.")
    report = _view(conn, f"research:{call.symbol}")
    if not report:
        return _empty("research", f"Research · {call.symbol}", "No stored research report exists yet.")
    section = call.section
    items: list[dict] = []
    sources: list[dict] = []
    quarters = [q for q in report.get("quarters", []) if q.get("revenue") is not None]
    latest = quarters[-1] if quarters else None
    if section in ("summary", "financials"):
        chosen = quarters[-4:] if section == "financials" else ([latest] if latest else [])
        for q in chosen:
            yoy = q.get("revenue_yoy")
            items.append(
                {
                    "label": q.get("label", "Quarter"),
                    "text": f"Revenue {_fmt_cr(q.get('revenue'))}"
                    + (f" ({yoy:+g}% YoY)" if yoy is not None else "")
                    + f" · PAT {_fmt_cr(q.get('pat'))}",
                    "href": q.get("xbrl"),
                }
            )
            if q.get("xbrl"):
                sources.append(_source("XBRL results filing on NSE", q["xbrl"]))
        if section == "summary" and report.get("ledger", {}).get("pattern"):
            items.append(
                {
                    "label": "Promise ledger",
                    "text": report["ledger"]["pattern"],
                    "href": f"/research?s={call.symbol}#ledger",
                }
            )
    elif section == "promises":
        groups = sorted(report.get("groups", []), key=lambda group: not group.get("resolved", False))
        for group in groups[: call.limit]:
            verdicts = group.get("verdicts", [])
            text = " · ".join(v.get("line") or v.get("label", "") for v in verdicts)
            if not text:
                text = "Open promise; no reported outcome stored yet."
            step = next((s for s in group.get("steps", []) if s.get("url")), None)
            url = step.get("url") if step else None
            items.append(
                {
                    "label": group.get("title", group.get("period", "Promise")),
                    "text": text,
                    "href": url,
                }
            )
            if url:
                sources.append(_source("Earnings-call transcript", url))
    elif section == "business":
        business = report.get("business") or {}
        if business.get("what"):
            items.append({"label": "What it does", "text": business["what"]})
        for segment in business.get("segments", [])[: call.limit]:
            share = segment.get("share")
            items.append(
                {
                    "label": segment.get("name", "Segment"),
                    "text": f"{share}% of segment revenue" if share is not None else "Share not stated",
                    "href": (business.get("source") or {}).get("xbrl"),
                }
            )
        xbrl = (business.get("source") or {}).get("xbrl")
        if xbrl:
            sources.append(_source("Company's XBRL results filing", xbrl))
        about = business.get("about") or {}
        if about.get("url"):
            sources.append(_source("Company annual report", about["url"]))
    else:
        signals = report.get("signals", {})
        for label, key in (("Bull", "bull"), ("Bear", "bear")):
            for text in signals.get(key, [])[: call.limit]:
                items.append({"label": label, "text": text, "href": latest.get("xbrl") if latest else None})
        if latest and latest.get("xbrl"):
            sources.append(_source("Latest XBRL results filing on NSE", latest["xbrl"]))
    if not items:
        return _empty(
            "research",
            f"Research · {call.symbol}",
            f"No stored {section.replace('_', ' ')} evidence is available.",
        )
    return {
        "type": "research",
        "title": f"{report.get('name', call.symbol)} · {section.replace('_', ' ')}",
        "subtitle": (
            "Reviewed ledger"
            if report.get("provenance", {}).get("reviewed")
            else "Generated automatically; not reviewed"
        ),
        "items": items,
        "sources": sources,
    }


def _who_can_help(conn: Connection, call: ToolCall) -> dict:
    if not call.symbol:
        return _empty("who_can_help", "Who can help", "Name a company or NSE symbol.")
    network = _view(conn, f"network:company:{call.symbol}")
    research = _view(conn, f"research:{call.symbol}") or {}
    # Reviewed Research reports already put former employees first; keep that trusted order.
    people = ((research.get("help") or {}).get("call") or (network or {}).get("who", []))[: call.limit]
    if not people:
        return _empty("who_can_help", f"Who can help · {call.symbol}", "No matching contact is stored.")
    return {
        "type": "who_can_help",
        "title": f"Who can help · {(network or {}).get('company', call.symbol)}",
        "items": [
            {
                "label": person["name"] + (" · synthetic" if person.get("synthetic") else ""),
                "text": person.get("why") or person.get("what_theyd_know") or "No relevance note stored.",
            }
            for person in people
        ],
        "sources": [_source("Stored synthetic network (fictional people and careers; real organisations)")],
    }


def _paths(conn: Connection, call: ToolCall) -> dict:
    if not call.symbol:
        return _empty("paths", "Paths", "Name a company or NSE symbol.")
    network = _view(conn, f"network:company:{call.symbol}")
    people = (network or {}).get("people", [])[: call.limit]
    if not people:
        return _empty("paths", f"Paths · {call.symbol}", "No stored path to a disclosed executive was found.")
    items = []
    sources = []
    for person in people:
        best = person.get("best") or {}
        text = best.get("sentence") or ((person.get("you") or ["No path evidence stored."])[0])
        items.append(
            {
                "label": f"{person.get('name')} · {person.get('role') or 'role not stated'}",
                "text": text,
            }
        )
        dossier = _view(conn, f"network:person:{person.get('id')}") or {}
        mention = next((m for m in dossier.get("mentions", []) if m.get("url")), None)
        if mention:
            sources.append(_source("Career disclosed in company filing", mention["url"]))
    if not sources:
        sources.append(_source("Stored synthetic network and filed career evidence"))
    return {
        "type": "paths",
        "title": f"Paths · {(network or {}).get('company', call.symbol)}",
        "items": items,
        "sources": sources,
    }


def _pct(last: float, first: float) -> float | None:
    return round((last / first - 1) * 100, 1) if first else None


def _price_stats(conn: Connection, call: ToolCall) -> dict:
    if not call.symbol:
        return _empty("price_stats", "Price stats", "Name a company or NSE symbol.")
    body = _view(conn, "alerts:inputs") or {}
    company = next((row for row in body.get("companies", []) if row.get("symbol") == call.symbol), None)
    bars = (company or {}).get("bars", [])
    if len(bars) < 2:
        return _empty(
            "price_stats",
            f"Price stats · {call.symbol}",
            "No stored end-of-day price series was found.",
        )
    last = bars[-1]
    items = [{"label": f"Close · {last[0]}", "text": f"₹{float(last[1]):,.2f}"}]
    for label, sessions in (("1 session", 1), ("5 sessions", 5), ("20 sessions", 20)):
        if len(bars) > sessions:
            move = _pct(float(last[1]), float(bars[-1 - sessions][1]))
            items.append({"label": label, "text": "not computable" if move is None else f"{move:+.1f}%"})
    prior_volumes = [float(row[2]) for row in bars[-21:-1] if row[2] is not None]
    if prior_volumes and last[2] is not None:
        avg = sum(prior_volumes) / len(prior_volumes)
        if avg:
            items.append({"label": "Volume vs 20-session average", "text": f"{float(last[2]) / avg:.1f}×"})
    return {
        "type": "price_stats",
        "title": f"Price stats · {(company or {}).get('name', call.symbol)}",
        "items": items,
        "sources": [_source(body.get("credit", "Stored end-of-day price series"))],
    }


def execute(conn: Connection, call: ToolCall) -> dict:
    call.symbol = call.symbol.strip().upper() if call.symbol else None
    handlers = {
        "brief": _brief,
        "filings": _filings,
        "research": _research,
        "who_can_help": _who_can_help,
        "paths": _paths,
        "price_stats": _price_stats,
    }
    return handlers[call.tool](conn, call)


def answer(conn: Connection, prompt: str, ip: str | None, router) -> dict:
    q = (prompt or "").strip()
    if not q or len(q) > MAX_PROMPT:
        raise JobError(422, "bad_prompt", f"Enter between 1 and {MAX_PROMPT} characters.")
    _rate_limit(conn, ip)
    available = _available(conn)
    system = (
        "You are FINN's command router. Do not answer the question and do not write prose. "
        "Choose one or two calls from the supplied tool enum. Use only symbols in AVAILABLE. "
        "brief is the ranked Today brief; filings is latest exchange filings; research selects a "
        "stored section; who_can_help returns ranked contacts; paths returns disclosed career paths; "
        "price_stats computes stored EOD moves. If no company is named, omit symbol."
    )
    user = f"COMMAND: {q}\nAVAILABLE: {json.dumps(available, ensure_ascii=False)}"
    result = router.call(
        tier="COMMAND",
        purpose="command_route",
        prompt_version="command-v1",
        system=system,
        user=user,
        out=CommandPlan,
        cache_payload={"prompt": q, "available": available},
    )
    allowed = {row["symbol"] for row in available}
    blocks = []
    for call in result.data.calls:
        if call.symbol:
            call.symbol = call.symbol.strip().upper()
            if call.symbol not in allowed:
                blocks.append(
                    _empty(
                        call.tool,
                        call.tool.replace("_", " ").title(),
                        "That company has no stored data for this tool.",
                    )
                )
                continue
        blocks.append(execute(conn, call))
    return {"query": q, "blocks": blocks, "model_wrote_answer": False}
