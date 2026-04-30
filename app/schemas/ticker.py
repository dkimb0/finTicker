from datetime import date as DateType, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class NewsOut(BaseModel):
  model_config = ConfigDict(from_attributes=True)

  url: str
  title: str
  source: str | None = None
  published_at: datetime | None = None
  category: Literal["company", "industry", "macro"]
  relevance_score: float
  reasoning: str | None = None


class MovementOut(BaseModel):
  model_config = ConfigDict(from_attributes=True)

  date: DateType
  pct_change: float
  direction: Literal["up", "down"]
  prev_close: float
  close: float
  volume: int
  news: list[NewsOut] = Field(default_factory=list)


class DateRange(BaseModel):
  start: DateType
  end: DateType


class Filters(BaseModel):
  min_pct_change: float
  direction: Literal["up", "down", "both"]


class TickerDataResponse(BaseModel):
  ticker: str
  range: DateRange
  filters: Filters
  movements: list[MovementOut]