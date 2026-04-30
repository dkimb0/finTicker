import asyncio
from datetime import date as DateType
from typing import Any

from app.config import settings
from app.db import SessionLocal
from app.repositories import movements as movements_repo
from app.repositories import news as news_repo
from app.services.movements_service import ensure_movements_for_range
from app.services.news_service import fetch_news_for_movement
from app.services.prices_service import ensure_prices_for_range
from app.services.relevance_service import score_articles
from app.services.ticker_profile_service import ensure_profile


async def ingest_ticker(
  ticker: str,
  start: DateType,
  end: DateType,
  refresh: bool = False,
  include_news: bool = True,
) -> dict[str, Any]:
  """Full pipeline. Idempotent — already-analyzed movements are skipped."""
  ticker = ticker.upper()

  counts = await asyncio.to_thread(_sync_prices_and_movements, ticker, start, end, refresh)

  if not include_news:
    return {**counts, "movements_analyzed": 0, "movements_failed": 0}

  profile_data, pending = await asyncio.to_thread(_load_profile_and_pending, ticker, start, end)

  if not pending:
    return {**counts, "movements_analyzed": 0, "movements_failed": 0}

  sem = asyncio.Semaphore(settings.INGEST_CONCURRENCY)
  results = await asyncio.gather(
    *[_process_movement(ticker, profile_data, m, sem) for m in pending],
    return_exceptions=True,
  )

  analyzed = sum(1 for r in results if r is True)
  failed = len(results) - analyzed
  return {**counts, "movements_analyzed": analyzed, "movements_failed": failed}


def _sync_prices_and_movements(
  ticker: str, start: DateType, end: DateType, refresh: bool
) -> dict[str, int]:
  with SessionLocal() as db:
    prices = ensure_prices_for_range(db, ticker, start, end, refresh=refresh)
    movements = ensure_movements_for_range(db, ticker, start, end)
  return {"prices_inserted": prices, "movements_detected": movements}


def _load_profile_and_pending(
  ticker: str, start: DateType, end: DateType
) -> tuple[dict, list[dict]]:
  """Loads what the async phase needs as plain dicts (so they survive past the session)."""
  with SessionLocal() as db:
    profile = ensure_profile(db, ticker)
    pending = movements_repo.get_pending_movements(db, ticker)
    pending = [m for m in pending if start <= m.date <= end]
    profile_data = {
      "company_name": profile.company_name,
      "sector": profile.sector,
      "macro_sensitivities": list(profile.macro_sensitivities or []),
    }
    pending_data = [
      {
        "id": m.id,
        "date": m.date,
        "pct_change": m.pct_change,
        "direction": m.direction,
      }
      for m in pending
    ]
  return profile_data, pending_data


async def _process_movement(
  ticker: str,
  profile_data: dict,
  movement: dict,
  sem: asyncio.Semaphore,
) -> bool:
  """Per-movement: fetch + score (async) → persist (sync, own session). Returns success bool."""
  async with sem:
    try:
      candidates = await fetch_news_for_movement(
        ticker=ticker,
        company_name=profile_data["company_name"],
        sector=profile_data["sector"],
        macro_sensitivities=profile_data["macro_sensitivities"],
        movement_date=movement["date"],
      )
      scored = await score_articles(
        ticker=ticker,
        company_name=profile_data["company_name"],
        sector=profile_data["sector"],
        movement_date=movement["date"].isoformat(),
        pct_change=movement["pct_change"],
        direction=movement["direction"],
        candidates=candidates,
      )

      await asyncio.to_thread(_persist_scored, movement["id"], candidates, scored)
      return True
    except Exception:
      # Movement stays 'pending' for retry on next ingest. Add real logging when we have it.
      return False


def _persist_scored(movement_id: int, candidates: list[dict], scored: list[dict]) -> None:
  scored_urls = {s["url"] for s in scored}
  articles_to_persist = [c for c in candidates if c["url"] in scored_urls]

  with SessionLocal() as db:
    if articles_to_persist:
      articles = news_repo.upsert_articles(db, articles_to_persist)
      url_to_id = {a.url: a.id for a in articles}

      links = [
        {
          "movement_id": movement_id,
          "article_id": url_to_id[s["url"]],
          "relevance_score": s["score"],
          "category": s["category"],
          "reasoning": s["reasoning"],
        }
        for s in scored
        if s["url"] in url_to_id
      ]
      if links:
        news_repo.link_movement_to_articles(db, links)

    movements_repo.update_movement_status(db, movement_id, "analyzed")