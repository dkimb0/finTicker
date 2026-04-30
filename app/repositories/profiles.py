from datetime import datetime
from sqlalchemy.orm import Session
from app.models import TickerProfile

def get_profile(db: Session, ticker: str) -> TickerProfile | None:
  return db.get(TickerProfile, ticker.upper())


def upsert_profile(db: Session, ticker: str, data: dict) -> TickerProfile:
  """Single-row upsert. Bumps updated_at on every write."""
  ticker = ticker.upper()
  profile = db.get(TickerProfile, ticker)
  if profile is None:
    profile = TickerProfile(ticker=ticker)
    db.add(profile)

  profile.company_name = data["company_name"]
  profile.sector = data.get("sector")
  profile.macro_sensitivities = list(data.get("macro_sensitivities") or [])
  profile.competitors = list(data.get("competitors") or [])
  profile.updated_at = datetime.utcnow()

  db.commit()
  return profile