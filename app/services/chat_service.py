import asyncio
import json
import logging
from datetime import date as DateType
from functools import lru_cache
from typing import Any

from openai import AsyncOpenAI
from openai.types.chat import ChatCompletionToolParam
from sqlalchemy import func, or_, select

from app.config import settings
from app.db import SessionLocal
from app.models import Movement, MovementNews, NewsArticle
from app.repositories import movements as movements_repo
from app.repositories import news as news_repo
from app.repositories import prices as prices_repo
from app.schemas.chat import ChatMessageIn

logger = logging.getLogger(__name__)

MAX_ITERATIONS = 6

TOOLS: list[ChatCompletionToolParam] = [
  {
    "type": "function",
    "function": {
      "name": "list_movements",
      "description": "List notable price movements for a ticker, optionally filtered by date range, magnitude, or direction.",
      "parameters": {
        "type": "object",
        "properties": {
          "ticker": {"type": "string"},
          "start_date": {"type": "string", "description": "ISO date YYYY-MM-DD"},
          "end_date": {"type": "string", "description": "ISO date YYYY-MM-DD"},
          "min_pct_change": {"type": "number", "description": "Absolute % threshold"},
          "direction": {"type": "string", "enum": ["up", "down"]},
        },
        "required": ["ticker"],
      },
    },
  },
  {
    "type": "function",
    "function": {
      "name": "get_news_for_movement",
      "description": "Get news articles linked to a specific movement, ordered by relevance score.",
      "parameters": {
        "type": "object",
        "properties": {
          "movement_id": {"type": "integer"},
          "max_results": {"type": "integer"},
        },
        "required": ["movement_id"],
      },
    },
  },
  {
    "type": "function",
    "function": {
      "name": "get_price_on_date",
      "description": "Get OHLCV for a ticker on a specific date.",
      "parameters": {
        "type": "object",
        "properties": {
          "ticker": {"type": "string"},
          "date": {"type": "string", "description": "ISO date YYYY-MM-DD"},
        },
        "required": ["ticker", "date"],
      },
    },
  },
  {
    "type": "function",
    "function": {
      "name": "search_movements_by_keyword",
      "description": "Find movements for a ticker whose linked news titles or reasoning contain a keyword.",
      "parameters": {
        "type": "object",
        "properties": {
          "ticker": {"type": "string"},
          "keyword": {"type": "string"},
        },
        "required": ["ticker", "keyword"],
      },
    },
  },
]


_SYSTEM_PROMPT_TEMPLATE = """You are a financial analyst assistant helping the user understand stock price movements for {ticker}.

You have tools that query a local DB of detected price movements and relevance-scored news. Use them — do not speculate beyond what they return.

When answering:
- Cite specific dates and percentages from movement data.
- When discussing causes, reference article titles and sources from get_news_for_movement.
- Be concise. Short paragraphs or bullets, no fluff.
- If the database has nothing for what's asked, say so plainly.
- Movement IDs are internal — refer to movements by date and pct_change in user-facing text."""


@lru_cache
def get_async_openai_client() -> AsyncOpenAI:
  return AsyncOpenAI(api_key=settings.OPENAI_API_KEY)


async def chat(ticker: str, client_messages: list[ChatMessageIn]) -> dict[str, Any]:
  """Run a tool-use loop. Returns {content, tool_calls_made}."""
  ticker = ticker.upper()

  messages: list[Any] = [
    {"role": "system", "content": _SYSTEM_PROMPT_TEMPLATE.format(ticker=ticker)}
  ]
  for m in client_messages:
    messages.append({"role": m.role, "content": m.content})

  client = get_async_openai_client()
  tool_names_invoked: list[str] = []

  for _ in range(MAX_ITERATIONS):
    response = await client.chat.completions.create(
      model=settings.CHAT_MODEL,
      messages=messages,
      tools=TOOLS,
    )
    msg = response.choices[0].message

    if msg.tool_calls:
      messages.append(msg)
      function_calls = [c for c in msg.tool_calls if c.type == "function"]
      tool_results = await asyncio.gather(
        *[_run_tool(c.function.name, c.function.arguments) for c in function_calls]
      )
      for call, result in zip(function_calls, tool_results):
        tool_names_invoked.append(call.function.name)
        messages.append({
          "role": "tool",
          "tool_call_id": call.id,
          "content": json.dumps(result, default=str),
        })
      continue

    return {"content": msg.content or "", "tool_calls_made": tool_names_invoked}

  return {
    "content": "(Ran out of tool-use iterations without producing a final answer.)",
    "tool_calls_made": tool_names_invoked,
  }


async def _run_tool(name: str, raw_args: str) -> Any:
  try:
    args = json.loads(raw_args)
  except json.JSONDecodeError:
    return {"error": "invalid tool arguments"}
  return await asyncio.to_thread(_execute_tool, name, args)


def _execute_tool(name: str, args: dict) -> Any:
  try:
    if name == "list_movements":
      return _tool_list_movements(args)
    if name == "get_news_for_movement":
      return _tool_get_news_for_movement(args)
    if name == "get_price_on_date":
      return _tool_get_price_on_date(args)
    if name == "search_movements_by_keyword":
      return _tool_search_movements_by_keyword(args)
    return {"error": f"unknown tool: {name}"}
  except Exception as e:
    logger.exception("Tool '%s' failed with args=%s", name, args)
    return {"error": f"{type(e).__name__}: {e}"}


def _tool_list_movements(args: dict) -> list[dict]:
  ticker = args["ticker"].upper()
  start = DateType.fromisoformat(args["start_date"]) if args.get("start_date") else DateType(2000, 1, 1)
  end = DateType.fromisoformat(args["end_date"]) if args.get("end_date") else DateType.today()
  with SessionLocal() as db:
    rows = movements_repo.get_movements(
      db, ticker, start, end,
      min_pct_change=args.get("min_pct_change"),
      direction=args.get("direction"),
    )
    return [
      {
        "movement_id": m.id,
        "date": m.date.isoformat(),
        "pct_change": round(m.pct_change, 2),
        "direction": m.direction,
        "close": round(m.close, 2),
      }
      for m in rows
    ]


def _tool_get_news_for_movement(args: dict) -> list[dict]:
  movement_id = int(args["movement_id"])
  max_results = int(args.get("max_results") or 10)
  with SessionLocal() as db:
    links = news_repo.get_news_for_movement(db, movement_id, limit=max_results)
    return [
      {
        "title": link.article.title,
        "url": link.article.url,
        "source": link.article.source,
        "published_at": link.article.published_at.isoformat() if link.article.published_at else None,
        "category": link.category,
        "relevance_score": round(link.relevance_score, 2),
        "reasoning": link.reasoning,
      }
      for link in links
    ]


def _tool_get_price_on_date(args: dict) -> dict:
  ticker = args["ticker"].upper()
  date = DateType.fromisoformat(args["date"])
  with SessionLocal() as db:
    rows = prices_repo.get_prices(db, ticker, date, date)
    if not rows:
      return {"error": f"No price data for {ticker} on {date.isoformat()}"}
    p = rows[0]
    return {
      "open": round(p.open, 2),
      "high": round(p.high, 2),
      "low": round(p.low, 2),
      "close": round(p.close, 2),
      "volume": p.volume,
    }


def _tool_search_movements_by_keyword(args: dict) -> list[dict]:
  ticker = args["ticker"].upper()
  kw = args["keyword"].lower()
  with SessionLocal() as db:
    stmt = (
      select(Movement, NewsArticle)
      .join(MovementNews, MovementNews.movement_id == Movement.id)
      .join(NewsArticle, NewsArticle.id == MovementNews.article_id)
      .where(Movement.ticker == ticker)
      .where(or_(
        func.lower(NewsArticle.title).contains(kw),
        func.lower(MovementNews.reasoning).contains(kw),
      ))
      .order_by(Movement.date.desc())
    )
    seen: set[int] = set()
    out: list[dict] = []
    for m, art in db.execute(stmt).all():
      if m.id in seen:
        continue
      seen.add(m.id)
      out.append({
        "movement_id": m.id,
        "date": m.date.isoformat(),
        "pct_change": round(m.pct_change, 2),
        "direction": m.direction,
        "matched_article_title": art.title,
      })
    return out