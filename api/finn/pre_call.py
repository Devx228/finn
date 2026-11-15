"""A cited pre-results brief reconstructed only from stored reviewed research evidence."""

from __future__ import annotations

import re
from datetime import date, timedelta

from psycopg import Connection


def _number(value: float) -> str:
    return f"{value:.1f}".rstrip("0").rstrip(".")


def _human(value: date) -> str:
    return f"{value.day} {value.strftime('%b %Y')}"


def _band(point: dict) -> str:
    low, high, unit = float(point["low"]), float(point["high"]), point.get("unit") or ""
    values = _number(low) if low == high else f"{_number(low)}–{_number(high)}"
    return f"{values}{unit}"


def _filing_dates(conn: Connection, urls: list[str]) -> dict[str, date]:
    if not urls:
        return {}
    rows = conn.execute(
        "SELECT xbrl_url, filed_at::date FROM fin_filings WHERE xbrl_url = ANY(%s) AND filed_at IS NOT NULL",
        (urls,),
    ).fetchall()
    return {url: filed for url, filed in rows}


def _guidance(report: dict, period: str, as_of: date) -> tuple[dict, dict] | None:
    for track in report.get("guidance", []):
        if track.get("period") != period or track.get("verdict") == "not scored":
            continue
        points = [
            point
            for point in track.get("points", [])
            if point.get("call_date") and date.fromisoformat(point["call_date"]) <= as_of
        ]
        if points:
            return track, max(points, key=lambda point: point["call_date"])
    return None


def _run_rate(
    report: dict,
    fy: int,
    as_of: date,
    filed: dict[str, date],
    point: dict,
) -> dict | None:
    current = [
        q
        for q in report.get("quarters", [])
        if q.get("fy") == fy
        and q.get("revenue") is not None
        and q.get("xbrl") in filed
        and filed[q["xbrl"]] <= as_of
        and not str(q.get("label", "")).startswith("Q4")
    ]
    if not current:
        return None
    quarter_numbers = {str(q["label"]).split()[0] for q in current}
    prior = [
        q
        for q in report.get("quarters", [])
        if q.get("fy") == fy - 1
        and q.get("revenue") is not None
        and str(q.get("label", "")).split()[0] in quarter_numbers
    ]
    prior_full = [
        q for q in report.get("quarters", []) if q.get("fy") == fy - 1 and q.get("revenue") is not None
    ]
    if len(prior) != len(current) or len(prior_full) != 4:
        return None
    current_sum = sum(float(q["revenue"]) for q in current)
    prior_sum = sum(float(q["revenue"]) for q in prior)
    prior_year = sum(float(q["revenue"]) for q in prior_full)
    remaining_prior = prior_year - prior_sum
    if not prior_sum or not remaining_prior:
        return None
    ytd = round((current_sum / prior_sum - 1) * 100, 1)
    needs = []
    for target in (float(point["low"]), float(point["high"])):
        remaining = prior_year * (1 + target / 100) - current_sum
        needs.append(round((remaining / remaining_prior - 1) * 100, 1))
    stage = f"{len(current)}Q YTD"
    need_band = _number(needs[0]) if needs[0] == needs[1] else f"{_number(needs[0])}–{_number(needs[1])}"
    urls = [q["xbrl"] for q in current + prior]
    return {
        "text": (
            f"{stage} revenue +{_number(ytd)}% YoY; needs +{need_band}% YoY in Q4 to reach {_band(point)}"
        ),
        "stage": stage,
        "ytd": ytd,
        "needed": need_band,
        "sources": [{"label": f"{q['label']} XBRL results on NSE", "url": q["xbrl"]} for q in current],
        "calculation_sources": urls,
    }


def _card(report: dict, event: dict, as_of: date, filed: dict[str, date]) -> dict | None:
    match = re.fullmatch(r"Q4 FY(\d{2})", event["label"])
    if not match:
        return None
    fy = 2000 + int(match.group(1))
    period = f"FY{match.group(1)}"
    chosen = _guidance(report, period, as_of)
    if not chosen:
        return None
    track, point = chosen
    run_rate = _run_rate(report, fy, as_of, filed, point)
    if not run_rate:
        return None
    contact = ((report.get("help") or {}).get("call") or [None])[0]
    if not contact:
        return None
    guide_source = {
        "label": f"{point.get('call', 'Earnings call')}, p. {point.get('page', 'not stated')}",
        "url": point["url"],
    }
    run_sources = run_rate["sources"]
    band = _band(point)
    label = track.get("label") or point.get("label") or "Guidance"
    questions = [
        {
            "text": (
                f"Management held {period} {label.lower()} at {band}. "
                "What assumptions still have to land in Q4?"
            ),
            "sources": [guide_source],
        },
        {
            "text": (
                f"Revenue was +{_number(run_rate['ytd'])}% YoY through {run_rate['stage']}; "
                f"reaching {band} needs about +{run_rate['needed']}% in Q4. "
                "Where should that acceleration come from?"
            ),
            "sources": run_sources,
        },
        {
            "text": (
                f"What would make management revise the {band} {period} {label.lower()} guidance at results?"
            ),
            "sources": [guide_source, run_sources[-1]],
        },
    ]
    return {
        "mode": "replay" if event["date"] < date.today() else "live",
        "as_of": as_of.isoformat(),
        "company": report.get("name"),
        "symbol": report.get("symbol"),
        "event": {
            "date": event["date"].isoformat(),
            "label": f"{event['label']} results",
            "source": {"label": "XBRL results filing on NSE", "url": event["xbrl"]},
        },
        "promises": [
            {
                "label": f"{period} {label}",
                "due": f"Due with {event['label']} results",
                "guided": band,
                "run_rate": run_rate["text"],
                "sources": [guide_source, *run_sources],
            }
        ],
        "questions": questions,
        "help": {
            "name": contact["name"],
            "headline": contact.get("headline") or contact.get("what_theyd_know"),
            "why": contact.get("why") or contact.get("what_theyd_know"),
            "synthetic": bool(contact.get("synthetic")),
            "href": f"/research?s={report.get('symbol')}#people",
        },
    }


def build(conn: Connection, requested_as_of: date | None = None) -> dict:
    rows = conn.execute(
        "SELECT v.body FROM holdings h JOIN companies c ON c.id = h.company_id "
        "JOIN views v ON v.key = 'research:' || c.nse_symbol"
    ).fetchall()
    reports = [row[0] for row in rows if (row[0].get("provenance") or {}).get("reviewed")]
    urls = [q["xbrl"] for report in reports for q in report.get("quarters", []) if q.get("xbrl")]
    filed = _filing_dates(conn, urls)
    candidates = []
    for report in reports:
        for quarter in report.get("quarters", []):
            event_date = filed.get(quarter.get("xbrl"))
            if event_date and str(quarter.get("label", "")).startswith("Q4 FY"):
                candidates.append(
                    (
                        event_date,
                        report,
                        {"date": event_date, "label": quarter["label"], "xbrl": quarter["xbrl"]},
                    )
                )
    candidates.sort(key=lambda row: row[0], reverse=True)
    if requested_as_of:
        windows = [
            (requested_as_of, row)
            for row in candidates
            if requested_as_of <= row[0] <= requested_as_of + timedelta(days=7)
        ]
    else:
        today = date.today()
        windows = [(today, row) for row in candidates if today <= row[0] <= today + timedelta(days=7)]
    for as_of, (_, report, event) in windows:
        card = _card(report, event, as_of, filed)
        if card:
            return card
    for event_date, report, event in candidates:
        if event_date >= date.today():
            continue
        replay = event_date - timedelta(days=5)
        card = _card(report, event, replay, filed)
        if card:
            card["mode"] = "replay"
            card["replay_reason"] = (
                "No stored reviewed holding has a results or earnings-call date in the next 7 days. "
                f"Showing the last comparable setup as of {_human(replay)}."
            )
            return card
    return {
        "mode": "empty",
        "message": "No reviewed holding has enough stored evidence for a pre-call brief.",
    }
