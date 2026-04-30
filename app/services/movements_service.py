from datetime import date as DateType, timedelta
from typing import Any

from sqlalchemy.orm import Session

from app.config import settings
from app.models import Price
from app.repositories import movements as movements_repo
from app.repositories import prices as prices_repo


def detect_movements(
  ticker: str,
  prices: list[Price],
  threshold_pct: float,
) -> list[dict[str, Any]]:
  """Pure function. Given a date-ordered list of prices, returns rows where
  |daily pct_change| >= threshold_pct.

  threshold_pct is a percent (2.0 means 2%), matching what users pass via the API.
  """
  if len(prices) < 2:
    return []

  movements: list[dict[str, Any]] = []
  for i in range(1, len(prices)):
    prev = prices[i - 1]
    curr = prices[i]
    if prev.close == 0:
      continue
    pct = ((curr.close - prev.close) / prev.close) * 100.0
    if abs(pct) < threshold_pct:
      continue
    movements.append(
      {
        "ticker": ticker,
        "date": curr.date,
        "prev_close": prev.close,
        "close": curr.close,
        "pct_change": round(pct, 4),
        "direction": "up" if pct > 0 else "down",
        "volume": curr.volume,
        "status": "pending",
      }
    )
  return movements


def ensure_movements_for_range(
  db: Session, ticker: str, start: DateType, end: DateType
) -> int:
  """Detect movements in [start, end] from cached prices (using lookback for
  boundary prev_close). Upserts only movements within [start, end]."""
  ticker = ticker.upper()
  query_start = start - timedelta(days=settings.MOVEMENT_LOOKBACK_DAYS)
  prices = prices_repo.get_prices(db, ticker, query_start, end)
  rows = detect_movements(ticker, prices, settings.DEFAULT_MIN_PCT)
  return movements_repo.upsert_movements(db, rows)