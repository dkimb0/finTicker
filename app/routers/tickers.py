from datetime import date as DateType, timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.repositories import movements as movements_repo
from app.repositories import prices as prices_repo
from app.schemas.ticker import DateRange, Filters, MovementOut, TickerDataResponse
from app.services.movements_service import ensure_movements_for_range
from app.services.prices_service import ensure_prices_for_range

router = APIRouter(prefix="/tickers", tags=["tickers"])

@router.get("/{symbol}", response_model=TickerDataResponse)
def get_ticker_data(
  symbol: str,
  db: Annotated[Session, Depends(get_db)],
  start: Annotated[DateType | None, Query(description="Default: end - DEFAULT_HISTORY_DAYS")] = None,
  end: Annotated[DateType | None, Query(description="Default: today")] = None,
  min_pct_change: Annotated[float | None, Query(ge=0, description="Absolute %, e.g. 2.0")] = None,
  direction: Annotated[Literal["up", "down", "both"], Query()] = "both",
  include_news: Annotated[bool, Query(description="Reserved; news pipeline not wired yet")] = True,
  refresh: Annotated[bool, Query(description="Force re-fetch from yfinance")] = False,
) -> TickerDataResponse:
  ticker = symbol.upper()
  
  if end is None:
    end = DateType.today()
  if start is None:
    start = end - timedelta(days=settings.DEFAULT_HISTORY_DAYS)
  if start > end:
    raise HTTPException(status_code=400, detail="start must be on or before end")
  if min_pct_change is None:
    min_pct_change = settings.DEFAULT_MIN_PCT

  ensure_prices_for_range(db, ticker, start, end, refresh=refresh)
  
  if not prices_repo.has_prices_for_range(db, ticker, start, end):
    raise HTTPException(status_code=404, detail=f"No price data found for ticker '{ticker}'")
  
  ensure_movements_for_range(db, ticker, start, end)
  
  direction_filter = direction if direction in ("up", "down") else None
  movement_orms = movements_repo.get_movements(
    db, ticker, start, end, min_pct_change=min_pct_change, direction=direction_filter
  )
  
  return TickerDataResponse(
    ticker=ticker,
    range=DateRange(start=start, end=end),
    filters=Filters(min_pct_change=min_pct_change, direction=direction),
    movements=[MovementOut.model_validate(m) for m in movement_orms]
  )