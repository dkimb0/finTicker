from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models import MovementNews, NewsArticle


def upsert_article(db: Session, data: dict) -> NewsArticle:
  """Insert by URL or update existing. Returns the live article with id populated."""
  existing = db.execute(
    select(NewsArticle).where(NewsArticle.url == data["url"])
  ).scalar_one_or_none()
  if existing is None:
    existing = NewsArticle(url=data["url"])
    db.add(existing)
  existing.title = data["title"]
  existing.source = data.get("source")
  existing.published_at = data.get("published_at")
  existing.snippet = data.get("snippet")
  existing.content = data.get("content")
  db.flush()
  return existing


def upsert_articles(db: Session, rows: list[dict]) -> list[NewsArticle]:
  """Per-row upsert, single commit. Returns articles in input order."""
  articles = [upsert_article(db, r) for r in rows]
  db.commit()
  return articles


def link_movement_to_article(
  db: Session,
  movement_id: int,
  article_id: int,
  relevance_score: float,
  category: str,
  reasoning: str | None = None,
) -> MovementNews:
  """Idempotent. If link already exists, latest scoring wins."""
  existing = db.execute(
    select(MovementNews).where(
      MovementNews.movement_id == movement_id,
      MovementNews.article_id == article_id,
    )
  ).scalar_one_or_none()
  if existing is None:
    existing = MovementNews(movement_id=movement_id, article_id=article_id)
    db.add(existing)
  existing.relevance_score = relevance_score
  existing.category = category
  existing.reasoning = reasoning
  db.flush()
  return existing


def link_movement_to_articles(db: Session, links: list[dict]) -> int:
  """Bulk-flavored. Each dict: movement_id, article_id, relevance_score, category, reasoning."""
  for link in links:
    link_movement_to_article(db, **link)
  db.commit()
  return len(links)


def get_news_for_movement(
  db: Session, movement_id: int, limit: int = 10
) -> list[MovementNews]:
  """Returns MovementNews rows with article eagerly loaded, ordered by relevance desc."""
  stmt = (
    select(MovementNews)
    .options(joinedload(MovementNews.article))
    .where(MovementNews.movement_id == movement_id)
    .order_by(MovementNews.relevance_score.desc())
    .limit(limit)
  )
  return list(db.execute(stmt).scalars())