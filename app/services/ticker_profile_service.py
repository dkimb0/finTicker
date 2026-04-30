from datetime import datetime, timedelta
from functools import lru_cache

from openai import OpenAI
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import settings
from app.models import TickerProfile
from app.repositories import profiles as profiles_repo

@lru_cache
def get_openai_client() -> OpenAI:
  return OpenAI(api_key=settings.OPENAI_API_KEY)

class _ProfilePayload(BaseModel):
  # structured output shape from the llm
  company_name: str
  sector: str
  macro_sensitivities: list[str]
  competitors: list[str]
  
_SYSTEM_PROMPT = """You are a financial analyst. Given a public-company stock ticker, return:

  - company_name: the company's full legal name
  - sector: GICS sector or general industry (e.g. "Technology", "Energy")
  - macro_sensitivities: 3-7 macro/political/economic topics that materially move this stock. Be SPECIFIC and SEARCHABLE — these will be used as news search queries. Examples: "China tariffs", "Fed interest rate decisions",
   "AI chip export controls", "consumer credit conditions". Avoid vague terms like "the economy" or "geopolitics".
  - competitors: 3-5 main publicly-traded competitors (company names or tickers)
  """
  
def ensure_profile(db: Session, ticker: str) -> TickerProfile:
  ticker = ticker.upper()
  existing = profiles_repo.get_profile(db,ticker)
  if existing is not None and _is_fresh(existing):
    return existing
  
  payload = _fetch_profile(ticker)
  return profiles_repo.upsert_profile(db, ticker, payload.model_dump())

def _is_fresh(profile: TickerProfile) -> bool:
  age = datetime.utcnow() - profile.updated_at
  return age < timedelta(days=settings.TICKER_PROFILE_TTL_DAYS)

def _fetch_profile(ticker: str) -> _ProfilePayload:
  client = get_openai_client()
  response = client.chat.completions.parse(
    model=settings.RELEVANCE_MODEL,
    messages=[
      {"role": "system", "content": _SYSTEM_PROMPT},
      {"role": "user", "content": f"Ticker: {ticker}"},
    ],
    response_format=_ProfilePayload,
  )
  parsed = response.choices[0].message.parsed
  if parsed is None:
    raise RuntimeError(f"OpenAI returned no structured payload for ticker {ticker}")
  return parsed

