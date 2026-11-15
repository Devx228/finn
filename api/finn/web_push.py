"""Standards-based browser push, limited to stored FINN brief evidence."""

from __future__ import annotations

import json
import secrets
from collections.abc import Callable

from psycopg import Connection
from psycopg.types.json import Jsonb

from finn.config import get_settings
from finn.jobs import JobError, requester_id

PER_REQUESTER_HOUR = 5
PER_REQUESTER_DAY = 10
GLOBAL_DAY = 200


def config() -> dict:
    settings = get_settings()
    ready = bool(settings.vapid_public_key and settings.vapid_private_key)
    return {"available": ready, "public_key": settings.vapid_public_key if ready else None}


def subscribe(conn: Connection, subscription: dict, ip: str | None) -> dict:
    endpoint = subscription.get("endpoint", "")
    keys = subscription.get("keys") or {}
    if not (
        isinstance(endpoint, str)
        and endpoint.startswith("https://")
        and len(endpoint) <= 2048
        and isinstance(keys.get("p256dh"), str)
        and isinstance(keys.get("auth"), str)
    ):
        raise JobError(422, "bad_subscription", "The browser returned an invalid push subscription.")
    token = secrets.token_urlsafe(24)
    row = conn.execute(
        "INSERT INTO web_push_subscriptions (token, endpoint, subscription, requester) "
        "VALUES (%s, %s, %s, %s) ON CONFLICT (endpoint) DO UPDATE SET "
        "subscription = EXCLUDED.subscription, requester = EXCLUDED.requester, "
        "updated_at = now(), disabled_at = NULL RETURNING token",
        (token, endpoint, Jsonb(subscription), requester_id(ip)),
    ).fetchone()
    conn.commit()
    assert row is not None
    return {"subscription_id": row[0]}


def unsubscribe(conn: Connection, token: str) -> dict:
    conn.execute("DELETE FROM web_push_subscriptions WHERE token = %s", (token,))
    conn.commit()
    return {"unsubscribed": True}


def _latest_brief_item(conn: Connection) -> dict | None:
    row = conn.execute("SELECT body FROM views WHERE key = 'brief:7d'").fetchone()
    if not row:
        return None
    body = row[0]
    items = list(body.get("now", [])) + list(body.get("worth", []))
    if not items:
        for group in body.get("buried", []):
            items.extend(group.get("items", []))
    return max(items, key=lambda item: item.get("ts", ""), default=None)


def _rate_limit(conn: Connection, ip: str | None) -> str:
    who = requester_id(ip)
    counts = conn.execute(
        "SELECT count(*) FILTER (WHERE requested_at > now() - interval '1 hour'), "
        "count(*) FILTER (WHERE requested_at > now() - interval '1 day') "
        "FROM web_push_test_requests WHERE requester = %s",
        (who,),
    ).fetchone()
    hour, day = counts if counts is not None else (0, 0)
    total_row = conn.execute(
        "SELECT count(*) FROM web_push_test_requests WHERE requested_at > now() - interval '1 day'"
    ).fetchone()
    total = total_row[0] if total_row is not None else 0
    if hour >= PER_REQUESTER_HOUR or day >= PER_REQUESTER_DAY or total >= GLOBAL_DAY:
        raise JobError(429, "rate_limited", "Test-alert limit reached. Try again later.")
    conn.execute("INSERT INTO web_push_test_requests (requester) VALUES (%s)", (who,))
    conn.commit()
    return who


def _send(subscription: dict, payload: dict) -> None:
    from pywebpush import webpush

    settings = get_settings()
    webpush(
        subscription_info=subscription,
        data=json.dumps(payload),
        vapid_private_key=settings.vapid_private_key,
        vapid_claims={"sub": settings.vapid_subject},
    )


def _payload(item: dict) -> dict:
    item_id = str(item.get("id", ""))
    headline = item.get("headline") or (item.get("card") or {}).get("take")
    if not item_id or not headline:
        raise JobError(409, "no_brief_item", "The stored brief card has no alert text.")
    return {
        "title": f"FINN · {item.get('symbol', 'brief')}",
        "body": headline,
        "url": f"/?w=7d&item={item_id}#brief-{item_id}",
        "tag": f"finn-brief-{item_id}",
    }


def deliver_new(
    conn: Connection,
    sender: Callable[[dict, dict], None] = _send,
) -> dict:
    """Send each new 24-hour Now card once per subscribed device after brief materialisation."""
    if not config()["available"]:
        return {"sent": 0, "failed": 0, "reason": "not configured"}
    view = conn.execute("SELECT body FROM views WHERE key = 'brief:24h'").fetchone()
    subscriptions = conn.execute(
        "SELECT token, subscription FROM web_push_subscriptions WHERE disabled_at IS NULL"
    ).fetchall()
    items = (view[0].get("now", []) if view else [])[:3]
    sent = failed = 0
    for token, subscription in subscriptions:
        for item in items:
            item_id = str(item.get("id", ""))
            if (
                not item_id
                or conn.execute(
                    "SELECT 1 FROM web_push_deliveries WHERE subscription_token = %s AND item_id = %s",
                    (token, item_id),
                ).fetchone()
            ):
                continue
            try:
                sender(subscription, _payload(item))
            except Exception:
                failed += 1
                continue
            conn.execute(
                "INSERT INTO web_push_deliveries (subscription_token, item_id) VALUES (%s, %s)",
                (token, item_id),
            )
            conn.commit()
            sent += 1
    return {"sent": sent, "failed": failed}


def send_test(
    conn: Connection,
    token: str,
    ip: str | None,
    sender: Callable[[dict, dict], None] = _send,
) -> dict:
    if not config()["available"]:
        raise JobError(503, "push_unavailable", "Push delivery is not configured on this server yet.")
    who = _rate_limit(conn, ip)
    row = conn.execute(
        "SELECT subscription FROM web_push_subscriptions "
        "WHERE token = %s AND requester = %s AND disabled_at IS NULL",
        (token, who),
    ).fetchone()
    if not row:
        raise JobError(404, "no_subscription", "Enable alerts on this device first.")
    item = _latest_brief_item(conn)
    if not item:
        raise JobError(409, "no_brief_item", "No stored brief card is available for a test alert.")
    payload = _payload(item)
    try:
        sender(row[0], payload)
    except Exception as exc:
        raise JobError(502, "push_failed", "The push service did not accept the test alert.") from exc
    return {"sent": True, "item_id": str(item.get("id", ""))}
