import asyncio
from datetime import date as DateType, timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.repositories import movements as movements_repo
from app.repositories import news as news_repo
from app.repositories import prices as prices_repo
from app.schemas.ticker import DateRange, Filters, MovementOut, NewsOut, TickerDataResponse
from app.services.ingestion_service import ingest_ticker

router = APIRouter(prefix="/tickers", tags=["tickers"])


@router.get("/{symbol}", response_model=TickerDataResponse)
async def get_ticker_data(
  symbol: str,
  db: Annotated[Session, Depends(get_db)],
  start: Annotated[DateType | None, Query(description="Default: end - DEFAULT_HISTORY_DAYS")] = None,
  end: Annotated[DateType | None, Query(description="Default: today")] = None,
  min_pct_change: Annotated[float | None, Query(ge=0, description="Absolute %, e.g. 2.0")] = None,
  direction: Annotated[Literal["up", "down", "both"], Query()] = "both",
  include_news: Annotated[bool, Query()] = True,
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

  await ingest_ticker(ticker, start, end, refresh=refresh, include_news=include_news)

  if not prices_repo.has_prices_for_range(db, ticker, start, end):
    raise HTTPException(status_code=404, detail=f"No price data found for ticker '{ticker}'")

  direction_filter = direction if direction in ("up", "down") else None
  movement_orms = movements_repo.get_movements(
    db, ticker, start, end, min_pct_change=min_pct_change, direction=direction_filter
  )

  movements_out: list[MovementOut] = []
  for m in movement_orms:
    news_out: list[NewsOut] = []
    if include_news:
      for link in news_repo.get_news_for_movement(db, m.id, limit=10):
        news_out.append(
          NewsOut(
            url=link.article.url,
            title=link.article.title,
            source=link.article.source,
            published_at=link.article.published_at,
            category=link.category,  # type: ignore[arg-type]
            relevance_score=link.relevance_score,
            reasoning=link.reasoning,
          )
        )
    movements_out.append(
      MovementOut(
        date=m.date,
        pct_change=m.pct_change,
        direction=m.direction,  # type: ignore[arg-type]
        prev_close=m.prev_close,
        close=m.close,
        volume=m.volume,
        news=news_out,
      )
    )

  return TickerDataResponse(
    ticker=ticker,
    range=DateRange(start=start, end=end),
    filters=Filters(min_pct_change=min_pct_change, direction=direction),
    movements=movements_out,
  )