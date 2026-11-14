"""Pre-call brief: replay cutoffs prevent future results from leaking into the setup."""

from datetime import date

import pytest
from psycopg.types.json import Jsonb
from test_phase0 import needs_db

from finn import db, pre_call


@pytest.fixture
def conn():
    with db.connection() as connection:
        db.migrate(connection)
        connection.execute("DELETE FROM views WHERE key = 'research:PRECALL'")
        connection.execute("DELETE FROM companies WHERE nse_symbol = 'PRECALL'")
        (company_id,) = connection.execute(
            "INSERT INTO companies (nse_symbol, name) VALUES ('PRECALL', 'Pre Call Limited') RETURNING id"
        ).fetchone()
        connection.execute(
            "INSERT INTO holdings (company_id, weight_pct, entry_date, theme, size) "
            "VALUES (%s, 5, '2025-01-01', 'Test', 'large')",
            (company_id,),
        )
        quarters = []
        filings = [
            (2025, "Q1 FY25", "2024-06-30", 100.0, "2024-07-20"),
            (2025, "Q2 FY25", "2024-09-30", 100.0, "2024-10-20"),
            (2025, "Q3 FY25", "2024-12-31", 100.0, "2025-01-20"),
            (2025, "Q4 FY25", "2025-03-31", 100.0, "2025-05-01"),
            (2026, "Q1 FY26", "2025-06-30", 112.0, "2025-07-20"),
            (2026, "Q2 FY26", "2025-09-30", 112.0, "2025-10-20"),
            (2026, "Q3 FY26", "2025-12-31", 112.0, "2026-01-20"),
            (2026, "Q4 FY26", "2026-03-31", 124.0, "2026-05-05"),
        ]
        for fy, label, period_end, revenue, filed_at in filings:
            url = f"https://example.test/{label.replace(' ', '-')}.xml"
            quarters.append(
                {"fy": fy, "label": label, "end": period_end, "revenue": revenue, "xbrl": url}
            )
            connection.execute(
                "INSERT INTO fin_filings "
                "(company_id, source, basis, period_end, filed_at, xbrl_url) "
                "VALUES (%s, 'nse_integrated', 'consolidated', %s, %s, %s)",
                (company_id, period_end, filed_at, url),
            )
        report = {
            "name": "Pre Call Limited",
            "symbol": "PRECALL",
            "provenance": {"reviewed": True},
            "quarters": quarters,
            "guidance": [
                {
                    "label": "Revenue growth",
                    "period": "FY26",
                    "verdict": "missed",
                    "points": [
                        {
                            "low": 15.0,
                            "high": 15.0,
                            "unit": "%",
                            "call": "Q2 FY26 call",
                            "call_date": "2025-10-25",
                            "page": 7,
                            "url": "https://example.test/transcript.pdf",
                        }
                    ],
                }
            ],
            "help": {
                "call": [
                    {
                        "name": "Test Contact",
                        "headline": "Former employee",
                        "why": "worked there before",
                        "synthetic": True,
                    }
                ]
            },
        }
        connection.execute(
            "INSERT INTO views (key, body, as_of) VALUES ('research:PRECALL', %s, now())",
            (Jsonb(report),),
        )
        connection.commit()
        yield connection
        connection.execute("DELETE FROM views WHERE key = 'research:PRECALL'")
        connection.execute("DELETE FROM companies WHERE nse_symbol = 'PRECALL'")
        connection.commit()


@needs_db
def test_replay_uses_only_results_available_before_event(conn):
    card = pre_call.build(conn, date(2026, 4, 30))
    assert card["mode"] == "replay"
    assert card["event"]["date"] == "2026-05-05"
    assert card["promises"][0]["guided"] == "15%"
    assert card["promises"][0]["run_rate"] == (
        "3Q YTD revenue +12% YoY; needs +24% YoY in Q4 to reach 15%"
    )
    assert len(card["questions"]) == 3
    assert all(question["sources"] for question in card["questions"])
