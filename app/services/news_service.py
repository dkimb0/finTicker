import asyncio
from datetime import date as DateType, datetime, timedelta
from functools import lru_cache
from typing import Any
from urllib.parse import urlparse

from exa_py import Exa

from app.config import settings


@lru_cache
def get_exa_client() -> Exa:
  return Exa(api_key=settings.EXA_API_KEY)


async def fetch_news_for_movement(
  ticker: str,
  company_name: str,
  sector: str | None,
  macro_sensitivities: list[str],
  movement_date: DateType,
) -> list[dict]:
  """Run 1 + N queries in parallel (company + per-topic macro), dedupe by URL."""
  start = movement_date - timedelta(days=settings.NEWS_BUFFER_BEFORE_DAYS)
  end = movement_date + timedelta(days=settings.NEWS_BUFFER_AFTER_DAYS)

  queries: list[tuple[str, str]] = [("company", f"{company_name} ({ticker}) news")]
  for topic in macro_sensitivities[:5]:
    label = f"{sector}: {topic}" if sector else topic
    queries.append(("macro", label))

  results_lists = await asyncio.gather(
    *[_run_query(q, start, end) for _, q in queries],
    return_exceptions=True,
  )

  candidates: dict[str, dict] = {}
  for results in results_lists:
    if isinstance(results, BaseException):
      continue  # silently drop failed queries; log when we add logging
    for r in results:
      candidates.setdefault(r["url"], r)
  return list(candidates.values())


async def _run_query(query: str, start: DateType, end: DateType) -> list[dict]:
  return await asyncio.to_thread(_run_query_sync, query, start, end)


def _run_query_sync(query: str, start: DateType, end: DateType) -> list[dict]:
  client = get_exa_client()
  response = client.search_and_contents(
    query,
    num_results=settings.NEWS_PER_QUERY,
    start_published_date=start.isoformat(),
    end_published_date=end.isoformat(),
    text=True,
  )
  return [_normalize(r) for r in response.results]


def _normalize(r: Any) -> dict:
  text = (getattr(r, "text", "") or "").strip()
  return {
    "url": r.url,
    "title": (r.title or "(untitled)").strip(),
    "source": _domain(r.url),
    "published_at": _parse_iso(getattr(r, "published_date", None)),
    "snippet": text[:500] if text else None,
    "content": text or None,
  }


def _parse_iso(s: str | None) -> datetime | None:
  if not s:
    return None
  try:
    dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    return dt.replace(tzinfo=None)
  except (ValueError, TypeError):
    return None


def _domain(url: str | None) -> str | None:
  if not url:
    return None
  try:
    return urlparse(url).netloc or None
  except Exception:
    return None