"""Command bar: typed tool routing, stored-data execution and per-client limits."""

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from psycopg.types.json import Jsonb
from test_phase0 import needs_db

from finn import command, db
from finn.api.main import app


@pytest.fixture
def conn():
    with db.connection() as c:
        db.migrate(c)
        c.execute("DELETE FROM command_requests")
        c.execute("DELETE FROM views WHERE key LIKE 'research:CMDTEST%'")
        c.execute("DELETE FROM companies WHERE nse_symbol LIKE 'CMDTEST%'")
        c.execute("INSERT INTO companies (nse_symbol, name) VALUES ('CMDTEST', 'Command Test Limited')")
        c.execute(
            "INSERT INTO views (key, body, as_of) VALUES ('research:CMDTEST', %s, now())",
            (
                Jsonb(
                    {
                        "name": "Command Test Limited",
                        "provenance": {"reviewed": True},
                        "quarters": [
                            {
                                "label": "Q2 FY27",
                                "revenue": 100.0,
                                "revenue_yoy": 10.0,
                                "pat": 12.0,
                                "xbrl": "https://example.test/result.xml",
                            }
                        ],
                        "ledger": {"pattern": "1 resolved · 1 delivered"},
                    }
                ),
            ),
        )
        c.commit()
        yield c
        c.execute("DELETE FROM command_requests")
        c.execute("DELETE FROM views WHERE key LIKE 'research:CMDTEST%'")
        c.execute("DELETE FROM companies WHERE nse_symbol LIKE 'CMDTEST%'")
        c.commit()


class FakeRouter:
    def call(self, **_kwargs):
        plan = command.CommandPlan(
            calls=[command.ToolCall(tool="research", symbol="CMDTEST", section="summary")]
        )
        return SimpleNamespace(data=plan)


@needs_db
def test_model_only_routes_and_code_builds_cited_research(conn):
    out = command.answer(conn, "summarise Command Test", "1.2.3.4", FakeRouter())
    assert out["model_wrote_answer"] is False
    assert out["blocks"][0]["items"][0]["text"] == "Revenue ₹100.0 cr (+10% YoY) · PAT ₹12.0 cr"
    assert out["blocks"][0]["sources"][0]["url"] == "https://example.test/result.xml"


@needs_db
def test_command_limit_is_per_salted_client(conn, monkeypatch):
    monkeypatch.setattr(command, "PER_REQUESTER_HOUR", 1)
    command.answer(conn, "one", "5.5.5.5", FakeRouter())
    with pytest.raises(command.JobError) as error:
        command.answer(conn, "two", "5.5.5.5", FakeRouter())
    assert error.value.status == 429
    assert command.answer(conn, "other client", "6.6.6.6", FakeRouter())["blocks"]


@needs_db
def test_command_api_returns_typed_response(conn, monkeypatch):
    monkeypatch.setattr(
        command,
        "answer",
        lambda *_args: {"query": "x", "blocks": [], "model_wrote_answer": False},
    )
    response = TestClient(app).post("/api/command", json={"prompt": "x"})
    assert response.status_code == 200 and response.json()["model_wrote_answer"] is False
