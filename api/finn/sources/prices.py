"""End-of-day prices from Yahoo Finance (yfinance). Called only from the ingest job, never from
a user request. On failure the caller keeps the last good data."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

NIFTY = "^NSEI"


@dataclass(frozen=True)
class Bar:
    ticker: str
    date: date
    open: float | None
    high: float | None
    low: float | None
    close: float | None
    adj_close: float | None
    volume: int | None


def yahoo_ticker(nse_symbol: str) -> str:
    return nse_symbol if nse_symbol.startswith("^") else f"{nse_symbol}.NS"


def download(tickers: list[str], period: str = "1y") -> list[Bar]:
    import math

    import yfinance as yf

    df = yf.download(
        tickers,
        period=period,
        interval="1d",
        auto_adjust=False,
        progress=False,
        group_by="ticker",
        threads=False,
    )
    out: list[Bar] = []

    def num(v):
        return None if v is None or (isinstance(v, float) and math.isnan(v)) else float(v)

    for t in tickers:
        if t not in df.columns.get_level_values(0):
            continue
        sub = df[t].dropna(how="all")
        for ts, row in sub.iterrows():
            vol = num(row.get("Volume"))
            out.append(
                Bar(
                    ticker=t,
                    date=ts.date(),
                    open=num(row.get("Open")),
                    high=num(row.get("High")),
                    low=num(row.get("Low")),
                    close=num(row.get("Close")),
                    adj_close=num(row.get("Adj Close")),
                    volume=int(vol) if vol is not None else None,
                )
            )
    return out
