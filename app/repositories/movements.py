from datetime import date as DateType

from sqlalchemy import func, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.models import Movement


def upsert_movements(db: Session, rows: list[dict]) -> int:
  """Bulk upsert. Preserves `status` on conflict so a re-run of detection
  doesn't reset 'analyzed' movements back to 'pending'."""
  if not rows:
    return 0
  stmt = sqlite_insert(Movement).values(rows)
  stmt = stmt.on_conflict_do_update(
    index_elements=["ticker", "date"],
    set_={
      "prev_close": stmt.excluded.prev_close,
      "close": stmt.excluded.close,
      "pct_change": stmt.excluded.pct_change,
      "direction": stmt.excluded.direction,
      "volume": stmt.excluded.volume,
      # status intentionally omitted — preserves prior "analyzed" state
    },
  )
  db.execute(stmt)
  db.commit()
  return len(rows)


def get_movements(
  db: Session,
  ticker: str,
  start: DateType,
  end: DateType,
  min_pct_change: float | None = None,
  direction: str | None = None,  # 'up' | 'down' | None
) -> list[Movement]:
  """Returns movements in [start, end] matching optional filters, ordered by date."""
  stmt = select(Movement).where(
    Movement.ticker == ticker,
    Movement.date >= start,
    Movement.date <= end,
  )
  if min_pct_change is not None:
    stmt = stmt.where(func.abs(Movement.pct_change) >= min_pct_change)
  if direction in ("up", "down"):
    stmt = stmt.where(Movement.direction == direction)
  stmt = stmt.order_by(Movement.date)
  return list(db.execute(stmt).scalars())


def get_movement_by_id(db: Session, movement_id: int) -> Movement | None:
  return db.get(Movement, movement_id)


def get_pending_movements(db: Session, ticker: str) -> list[Movement]:
  """Used by ingestion to find movements that still need news fetched + scored."""
  stmt = (
    select(Movement)
    .where(Movement.ticker == ticker, Movement.status == "pending")
    .order_by(Movement.date)
  )
  return list(db.execute(stmt).scalars())


def update_movement_status(db: Session, movement_id: int, status: str) -> None:
  movement = db.get(Movement, movement_id)
  if movement is None:
    return
  movement.status = status
  db.commit()