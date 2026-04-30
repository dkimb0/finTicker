from functools import lru_cache
from typing import Literal

from openai import AsyncOpenAI
from pydantic import BaseModel

from app.config import settings


@lru_cache
def get_async_openai_client() -> AsyncOpenAI:
  return AsyncOpenAI(api_key=settings.OPENAI_API_KEY)


class _ScoredArticle(BaseModel):
  url: str
  score: float  # 0..1
  category: Literal["company", "industry", "macro"]
  reasoning: str


class _RelevanceResponse(BaseModel):
  scores: list[_ScoredArticle]


_SYSTEM_PROMPT = """You are a financial analyst evaluating which news articles likely explain a stock price movement.

For each article, return:
- score: 0.0 to 1.0. How likely is this article to explain the price movement?
  - 1.0: clearly explains the movement (e.g. earnings miss on a -5% day, with the article published before the move)
  - 0.5-0.8: probably contributes (e.g. industry news plausibly affecting this company)
  - 0.0-0.3: irrelevant, coincidental, or generic background
- category:
  - 'company': specifically about this company (earnings, lawsuits, product launches, executive changes)
  - 'industry': competitor moves or sector-wide news
  - 'macro': Fed/rates, policy, regulation, geopolitics
- reasoning: ONE sentence explaining your score, citing what in the article does or doesn't connect to the movement.

Be strict. Most news in a date window is NOT causal. Only score >0.7 when the article concretely describes an event that would plausibly move the stock by the observed magnitude and direction."""


async def score_articles(
  ticker: str,
  company_name: str,
  sector: str | None,
  movement_date: str,
  pct_change: float,
  direction: str,
  candidates: list[dict],
) -> list[dict]:
  """Score candidates against a movement. Returns list of dicts {url, score, category,
  reasoning} for articles meeting the relevance threshold."""
  if not candidates:
    return []

  user_content = _build_user_prompt(
    ticker, company_name, sector, movement_date, pct_change, direction, candidates
  )

  client = get_async_openai_client()
  response = await client.chat.completions.parse(
    model=settings.RELEVANCE_MODEL,
    messages=[
      {"role": "system", "content": _SYSTEM_PROMPT},
      {"role": "user", "content": user_content},
    ],
    response_format=_RelevanceResponse,
  )
  parsed = response.choices[0].message.parsed
  if parsed is None:
    return []

  input_urls = {c["url"] for c in candidates}
  return [
    s.model_dump()
    for s in parsed.scores
    if s.url in input_urls and s.score >= settings.RELEVANCE_THRESHOLD
  ]


def _build_user_prompt(
  ticker: str,
  company_name: str,
  sector: str | None,
  movement_date: str,
  pct_change: float,
  direction: str,
  candidates: list[dict],
) -> str:
  sector_str = f" ({sector})" if sector else ""
  header = (
    f"Movement: {company_name} [{ticker}]{sector_str}\n"
    f"Date: {movement_date}\n"
    f"Change: {pct_change:+.2f}% ({direction})\n\n"
    f"Score the following {len(candidates)} candidate articles:\n"
  )
  items = []
  for i, c in enumerate(candidates, 1):
    title = c.get("title", "(untitled)")
    snippet = (c.get("snippet") or "").strip()[:400]
    url = c["url"]
    items.append(f"[{i}] {title}\n    URL: {url}\n    {snippet}")
  return header + "\n\n".join(items)


