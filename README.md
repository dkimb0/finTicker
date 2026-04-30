# finTicker

A FastAPI service that explains major stock price movements using relevant news.

Given a ticker and a date range, finTicker:

1. Fetches OHLCV history from yfinance.
2. Detects significant daily movements (configurable % threshold).
3. Builds a profile of the company (sector, macro sensitivities, competitors) using an LLM.
4. Searches news around each movement via Exa, scores each article's relevance with an LLM, and links the top articles to the movement (categorized as `company`, `industry`, or `macro`).
5. Exposes a chat endpoint that answers questions about the ticker's movements using the stored data as tools.

## Stack

- Python / FastAPI / Uvicorn
- SQLAlchemy 2.x + SQLite
- Pydantic v2 + pydantic-settings
- yfinance for prices, Exa for news search, OpenAI for relevance scoring and chat

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Create a `.env` in the repo root:

```
OPENAI_API_KEY=sk-...
EXA_API_KEY=...
```

Run:

```bash
uvicorn app.main:app --reload
```

The DB (`app.db`) is created automatically on startup. Interactive docs at `http://localhost:8000/docs`.

## Endpoints

### `GET /tickers/{symbol}`

Returns detected movements for a ticker, optionally with linked news.

Query parameters:

| Param | Default | Description |
| --- | --- | --- |
| `start` | `end - DEFAULT_HISTORY_DAYS` | Range start (YYYY-MM-DD) |
| `end` | today | Range end (YYYY-MM-DD) |
| `min_pct_change` | `DEFAULT_MIN_PCT` (2.0) | Absolute % threshold |
| `direction` | `both` | `up`, `down`, or `both` |
| `include_news` | `true` | Include linked articles per movement |
| `refresh` | `false` | Force re-fetch from yfinance |

Example:

```bash
curl "http://localhost:8000/tickers/NVDA?start=2025-01-01&end=2025-03-31&min_pct_change=3"
```

### `POST /tickers/{symbol}/chat`

Multi-turn chat about a ticker. The model has tool access to the stored movements, news, and profile.

```bash
curl -X POST http://localhost:8000/tickers/NVDA/chat \
  -H 'Content-Type: application/json' \
  -d '{"messages":[{"role":"user","content":"Why did NVDA drop on Jan 27?"}]}'
```

### `GET /health`

Liveness probe.

## Configuration

All settings live in `app/config.py` and can be overridden via env vars:

- `DEFAULT_HISTORY_DAYS`, `DEFAULT_MIN_PCT`, `MOVEMENT_LOOKBACK_DAYS`
- `NEWS_BUFFER_BEFORE_DAYS`, `NEWS_BUFFER_AFTER_DAYS`, `NEWS_PER_QUERY`
- `RELEVANCE_MODEL`, `CHAT_MODEL`, `RELEVANCE_THRESHOLD`
- `TICKER_PROFILE_TTL_DAYS`, `INGEST_CONCURRENCY`
- `DATABASE_URL` (default `sqlite:///./app.db`)

## Layout

```
app/
  main.py              FastAPI app + lifespan
  config.py            Settings
  db.py                SQLAlchemy engine/session
  models.py            ORM models (Price, Movement, NewsArticle, MovementNews, TickerProfile)
  routers/             tickers, chat
  schemas/             Pydantic request/response models
  repositories/        DB access (prices, movements, news, profiles)
  services/            ingestion, prices, movements, news, relevance, ticker_profile, chat
```
