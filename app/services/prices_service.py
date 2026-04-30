from datetime import date as DateType, timedelta
from app.config import settings
from typing import Any, cast
import pandas as pd

import yfinance as yf
from sqlalchemy.orm import Session

from app.repositories import prices as prices_repo


def fetch_prices(ticker: str, start: DateType, end: DateType) -> list[dict[str, Any]]:
  """Fetch daily OHLCV from yfinance for [start, end] inclusive. Returns normalized rows."""
  ticker = ticker.upper()

  # yfinance treats `end` as exclusive — bump a day so callers can think inclusive.
  df = yf.Ticker(ticker).history(
    start=start.isoformat(),
    end=(end + timedelta(days=1)).isoformat(),
    auto_adjust=True,
  )

  if df.empty:
    return []

  rows: list[dict[str, Any]] = []
  for ts, row in df.iterrows():
    ts = cast(pd.Timestamp, ts)
    rows.append(
      {
        "ticker": ticker,
        "date": pd.Timestamp(ts).date(),
        "open": round(float(row["Open"]), 2),
        "high": round(float(row["High"]), 2),
        "low": round(float(row["Low"]), 2),
        "close": round(float(row["Close"]), 2),
        "volume": int(row["Volume"]),
      }
    )
  return rows


def ensure_prices_for_range(
  db: Session,
  ticker: str,
  start: DateType,
  end: DateType,
  refresh: bool = False,
) -> int:
  """Cache-aware. Fetches with a lookback buffer so movement detection has
  valid prev_close at the requested start boundary."""
  ticker = ticker.upper()
  fetch_start = start - timedelta(days=settings.MOVEMENT_LOOKBACK_DAYS)
  if not refresh and prices_repo.has_prices_for_range(db, ticker, fetch_start, end):
    return 0
  rows = fetch_prices(ticker, fetch_start, end)
  return prices_repo.upsert_prices(db, rows)