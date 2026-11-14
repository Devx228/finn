"""Web Push stores browser credentials safely and links a test to stored brief evidence."""

import pytest
from psycopg.types.json import Jsonb
from test_phase0 import needs_db

from finn import db, web_push


@pytest.fixture
def conn():
    with db.connection() as connection:
        db.migrate(connection)
        connection.execute("DELETE FROM web_push_test_requests")
        connection.execute("DELETE FROM web_push_deliveries")
        connection.execute("DELETE FROM web_push_subscriptions")
        connection.execute("DELETE FROM views WHERE key IN ('brief:7d', 'brief:24h')")
        connection.execute(
            "INSERT INTO views (key, body, as_of) VALUES ('brief:7d', %s, now())",
            (
                Jsonb(
                    {
                        "now": [
                            {
                                "id": 42,
                                "symbol": "TESTCO",
                                "headline": "Stored filing summary",
                                "ts": "2026-11-14T10:00:00+05:30",
                            }
                        ],
                        "worth": [],
                        "buried": [],
                    }
                ),
            ),
        )
        connection.commit()
        yield connection
        connection.execute("DELETE FROM web_push_test_requests")
        connection.execute("DELETE FROM web_push_deliveries")
        connection.execute("DELETE FROM web_push_subscriptions")
        connection.execute("DELETE FROM views WHERE key IN ('brief:7d', 'brief:24h')")
        connection.commit()


@needs_db
def test_test_alert_uses_stored_card_and_deep_link(conn, monkeypatch):
    monkeypatch.setattr(web_push, "config", lambda: {"available": True, "public_key": "public"})
    saved = web_push.subscribe(
        conn,
        {
            "endpoint": "https://push.example.test/device",
            "keys": {"p256dh": "browser-key", "auth": "browser-auth"},
        },
        "1.2.3.4",
    )
    sent = []
    result = web_push.send_test(
        conn,
        saved["subscription_id"],
        "1.2.3.4",
        sender=lambda subscription, payload: sent.append((subscription, payload)),
    )
    assert result == {"sent": True, "item_id": "42"}
    assert sent[0][1]["body"] == "Stored filing summary"
    assert sent[0][1]["url"] == "/?w=7d&item=42#brief-42"


@needs_db
def test_subscription_rejects_non_https_endpoint(conn):
    with pytest.raises(web_push.JobError) as error:
        web_push.subscribe(
            conn,
            {"endpoint": "http://push.test/device", "keys": {"p256dh": "x", "auth": "y"}},
            "1.2.3.4",
        )
    assert error.value.status == 422


@needs_db
def test_new_now_card_is_delivered_only_once(conn, monkeypatch):
    monkeypatch.setattr(web_push, "config", lambda: {"available": True, "public_key": "public"})
    web_push.subscribe(
        conn,
        {
            "endpoint": "https://push.example.test/automatic",
            "keys": {"p256dh": "browser-key", "auth": "browser-auth"},
        },
        "5.6.7.8",
    )
    conn.execute(
        "INSERT INTO views (key, body, as_of) VALUES ('brief:24h', %s, now())",
        (
            Jsonb(
                {
                    "now": [
                        {
                            "id": 99,
                            "symbol": "TESTCO",
                            "headline": "Stored material update",
                            "ts": "2026-11-14T11:00:00+05:30",
                        }
                    ]
                }
            ),
        ),
    )
    conn.commit()
    sent = []

    def sender(subscription, payload):
        sent.append((subscription, payload))

    assert web_push.deliver_new(conn, sender=sender) == {"sent": 1, "failed": 0}
    assert web_push.deliver_new(conn, sender=sender) == {"sent": 0, "failed": 0}
    assert sent[0][1]["url"] == "/?w=7d&item=99#brief-99"
