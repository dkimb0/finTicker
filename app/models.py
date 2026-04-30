from datetime import date as Date
from datetime import datetime


from sqlalchemy import (
  JSON,
  Date as SADate,
  DateTime,
  Float,
  ForeignKey,
  Integer,
  String,
  Text,
  UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db import Base

class Price(Base):
  __tablename__ = "prices"
  __table_args__= (UniqueConstraint("ticker", "date", name="uq_prices_ticker_date"),)
  
  id: Mapped[int] = mapped_column(Integer, primary_key=True)
  ticker: Mapped[str] = mapped_column(String(16), index=True, nullable=False)
  date: Mapped[Date] = mapped_column(SADate, index=True, nullable=False)
  open: Mapped[float] = mapped_column(Float, nullable=False)
  high: Mapped[float] = mapped_column(Float, nullable=False)
  low: Mapped[float] = mapped_column(Float, nullable=False)
  close: Mapped[float] = mapped_column(Float, nullable=False)
  volume: Mapped[int] = mapped_column(Integer, nullable=False)
  
  
class Movement(Base):
  __tablename__ = "movements"
  __table_args__ = (UniqueConstraint("ticker", "date", name="uq_movements_ticker_date"),)

  id: Mapped[int] = mapped_column(Integer, primary_key=True)
  ticker: Mapped[str] = mapped_column(String(16), index=True, nullable=False)
  date: Mapped[Date] = mapped_column(SADate, index=True, nullable=False)
  prev_close: Mapped[float] = mapped_column(Float, nullable=False)
  close: Mapped[float] = mapped_column(Float, nullable=False)
  pct_change: Mapped[float] = mapped_column(Float, nullable=False)  # signed
  direction: Mapped[str] = mapped_column(String(4), nullable=False)  # 'up' | 'down'
  volume: Mapped[int] = mapped_column(Integer, nullable=False)
  status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")  # 'pending' | 'analyzed'

  news_links: Mapped[list["MovementNews"]] = relationship(
    back_populates="movement", cascade="all, delete-orphan"
  )
class NewsArticle(Base):
  __tablename__ = "news_articles"

  id: Mapped[int] = mapped_column(Integer, primary_key=True)
  url: Mapped[str] = mapped_column(String, unique=True, nullable=False)
  title: Mapped[str] = mapped_column(String, nullable=False)
  source: Mapped[str | None] = mapped_column(String, nullable=True)
  published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
  snippet: Mapped[str | None] = mapped_column(Text, nullable=True)
  content: Mapped[str | None] = mapped_column(Text, nullable=True)

  movement_links: Mapped[list["MovementNews"]] = relationship(back_populates="article")


class MovementNews(Base):
  __tablename__ = "movement_news"
  __table_args__ = (
    UniqueConstraint("movement_id", "article_id", name="uq_movement_article"),
  )

  id: Mapped[int] = mapped_column(Integer, primary_key=True)
  movement_id: Mapped[int] = mapped_column(
    ForeignKey("movements.id", ondelete="CASCADE"), index=True, nullable=False
  )
  article_id: Mapped[int] = mapped_column(
    ForeignKey("news_articles.id", ondelete="CASCADE"), index=True, nullable=False
  )
  relevance_score: Mapped[float] = mapped_column(Float, nullable=False)
  reasoning: Mapped[str | None] = mapped_column(Text, nullable=True)
  category: Mapped[str] = mapped_column(String(16), nullable=False)  # 'company' | 'industry' | 'macro'

  movement: Mapped["Movement"] = relationship(back_populates="news_links")
  article: Mapped["NewsArticle"] = relationship(back_populates="movement_links")


class TickerProfile(Base):
  __tablename__ = "ticker_profiles"

  ticker: Mapped[str] = mapped_column(String(16), primary_key=True)
  company_name: Mapped[str] = mapped_column(String, nullable=False)
  sector: Mapped[str | None] = mapped_column(String, nullable=True)
  macro_sensitivities: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
  competitors: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
  updated_at: Mapped[datetime] = mapped_column(
    DateTime, nullable=False, default=datetime.utcnow
  )