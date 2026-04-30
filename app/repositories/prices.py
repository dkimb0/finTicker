from datetime import date as DateType

from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.models import Price


def upsert_prices(db: Session, rows: list[dict]) -> int:
  """Bulk upsert price rows. Each row must have ticker, date, open, high, low, close, volume."""
  if not rows:
    return 0
  stmt = sqlite_insert(Price).values(rows)
  stmt = stmt.on_conflict_do_update(
    index_elements=["ticker", "date"],
    set_={
      "open": stmt.excluded.open,
      "high": stmt.excluded.high,
      "low": stmt.excluded.low,
      "close": stmt.excluded.close,
      "volume": stmt.excluded.volume,
    },
  )
  db.execute(stmt)
  db.commit()
  return len(rows)


def get_prices(db: Session, ticker: str, start: DateType, end: DateType) -> list[Price]:
  stmt = (
    select(Price)
    .where(Price.ticker == ticker, Price.date >= start, Price.date <= end)
    .order_by(Price.date)
  )
  return list(db.execute(stmt).scalars())


def has_prices_for_range(db: Session, ticker: str, start: DateType, end: DateType) -> bool:
  """Quick check used by the cache-miss path. True if we have at least one price in the range."""
  stmt = select(Price.id).where(
    Price.ticker == ticker, Price.date >= start, Price.date <= end
  ).limit(1)
  return db.execute(stmt).scalar_one_or_none() is not None