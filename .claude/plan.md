# finTicker — Implementation Plan

## Goal

Build a FastAPI service that explains major stock price movements using relevant news. For a given ticker, fetch historical prices, identify days with significant moves, retrieve news from that window, score relevance with an LLM, and expose the data via REST + a chat endpoint.

## Stack

- **API**: FastAPI + Pydantic v2
- **Prices**: `yfinance`
- **News**: Exa (`exa-py`)
- **LLM**: OpenAI SDK
  - Relevance scoring: `gpt-5.4-nano` (cheap, structured output)
  - Chat: `gpt-5.4-pro` (tool-use loop)
- **Storage**: SQLite via SQLAlchemy
- **Deps**: `pip + requirements.txt`
- **No background tasks for v1** — ingestion is synchronous, results cached in DB

## Decisions

| Decision | Choice | Reasoning |
|---|---|---|
| Sync vs async ingestion | Sync + DB caching | Cold path slow once, warm fast. No worker process needed. |
| Schema | Normalized (5 tables, no chat persistence) | Articles dedupe globally; many-to-many movement↔news; easy filtering. |
| Chat state | Stateless — client sends `messages[]` each request | Persisting chat without a user model is security-theater. Aligns with how OpenAI/Anthropic chat APIs work. |
| Movement definition | Single trading day where `\|pct_change\| >= threshold` | Simple. Clustering can be a later post-hoc pass. |
| News window per movement | `[T-2, T+1]` | Asymmetric buffer: pre-market press + intraday + retrospective coverage. |
| Macro/industry retrieval | Per-ticker "sensitivities profile" → second Exa query | Keyword search by ticker won't surface Fed/policy news. Need exposure-aware queries. |
| Relevance | LLM-scored, structured output, drop < 0.3 | Cheap pass; better signal than raw time-windowed news. |
| Default history | 90 days | 7d often has 0 movements. |
| Default min pct change | 2.0 (absolute) | Per spec. |
| Ticker profile TTL | 30 days | Macro sensitivities don't shift fast. |
| Chat | OpenAI tool-use loop, DB-only reads | Scales to multi-turn / multi-ticker without ballooning context. |

## File layout

```
finTicker/
├── app/
│   ├── main.py                       # FastAPI app, lifespan (init_db), router registration
│   ├── config.py                     # Pydantic Settings
│   ├── db.py                         # SQLAlchemy engine, session, Base, init_db()
│   ├── models.py                     # ORM models
│   ├── schemas/
│   │   ├── ticker.py                 # TickerDataResponse, MovementOut, NewsOut, query params
│   │   └── chat.py                   # ChatRequest, ChatResponse, ChatMessageIn/Out
│   ├── repositories/
│   │   ├── prices.py                 # upsert_prices, get_prices(ticker, range)
│   │   ├── movements.py              # upsert_movements, get_movements (with filters)
│   │   └── news.py                   # upsert_article (by URL), link_to_movement, get_news_for_movement
│   ├── services/
│   │   ├── prices_service.py         # yfinance fetch, normalize OHLCV
│   │   ├── movements_service.py      # detect_movements(prices, threshold)
│   │   ├── ticker_profile_service.py # one-time LLM call: company name, sector, sensitivities, competitors
│   │   ├── news_service.py           # Exa wrapper: company query + macro/industry query, dedupe
│   │   ├── relevance_service.py      # OpenAI structured-output: score articles vs movement
│   │   ├── ingestion_service.py      # orchestrator (idempotent)
│   │   └── chat_service.py           # OpenAI tool-use loop + tool implementations
│   └── routers/
│       ├── tickers.py                # GET /tickers/{symbol}
│       └── chat.py                   # POST /tickers/{symbol}/chat (stateless)
├── requirements.txt
├── .env                              # EXA_API_KEY, OPENAI_API_KEY
└── README.md
```

## Config (env vars)

```
OPENAI_API_KEY            # required
EXA_API_KEY               # required
DB_URL                    # default: sqlite:///./finticker.db
DEFAULT_HISTORY_DAYS      # default: 90
DEFAULT_MIN_PCT           # default: 2.0
NEWS_BUFFER_BEFORE_DAYS   # default: 2
NEWS_BUFFER_AFTER_DAYS    # default: 1
NEWS_PER_QUERY            # default: 10
RELEVANCE_THRESHOLD       # default: 0.3
RELEVANCE_MODEL           # default: gpt-5.4-nano
CHAT_MODEL                # default: gpt-5.4-pro
TICKER_PROFILE_TTL_DAYS   # default: 30
INGEST_CONCURRENCY        # default: 5
```

## Database schema

```
prices
  id              INTEGER PK
  ticker          TEXT
  date            DATE
  open, high, low, close   REAL
  volume          INTEGER
  UNIQUE(ticker, date)

movements
  id              INTEGER PK
  ticker          TEXT
  date            DATE
  prev_close      REAL
  close           REAL
  pct_change      REAL          -- signed
  direction       TEXT          -- 'up' | 'down'
  volume          INTEGER
  status          TEXT          -- 'pending' | 'analyzed'
  UNIQUE(ticker, date)

news_articles
  id              INTEGER PK
  url             TEXT UNIQUE
  title           TEXT
  source          TEXT
  published_at    DATETIME
  snippet         TEXT
  content         TEXT          -- optional, from Exa text content

movement_news
  id              INTEGER PK
  movement_id     INTEGER FK → movements.id
  article_id      INTEGER FK → news_articles.id
  relevance_score REAL          -- 0..1
  reasoning       TEXT
  category        TEXT          -- 'company' | 'industry' | 'macro'
  UNIQUE(movement_id, article_id)

ticker_profiles
  ticker          TEXT PK
  company_name    TEXT
  sector          TEXT
  macro_sensitivities  JSON     -- list[str]
  competitors     JSON          -- list[str]
  updated_at      DATETIME
```

Chat is stateless — no DB tables. Clients send the full `messages[]` array each request.

## API surface

### `GET /tickers/{symbol}`

Query params:
- `start` (date, default `today - DEFAULT_HISTORY_DAYS`)
- `end` (date, default `today`)
- `min_pct_change` (float, default `DEFAULT_MIN_PCT`, absolute value)
- `direction` (`up` | `down` | `both`, default `both`)
- `include_news` (bool, default `true`)
- `refresh` (bool, default `false`) — force re-ingest of the range

Behavior: if any day in `[start, end]` is missing from cache, or `refresh=true`, run ingestion. Then return movements in range matching filters, with linked news sorted by `relevance_score desc`.

### `POST /tickers/{symbol}/chat`

Body:
```json
{
  "messages": [
    {"role": "user", "content": "why did AAPL drop on March 15?"}
  ]
}
```

Behavior: stateless. Server appends a system prompt scoped to `{symbol}`, runs the OpenAI tool-use loop with tools below, returns the new assistant message. No persistence; client maintains history and resends on the next turn.

Response:
```json
{
  "message": {"role": "assistant", "content": "..."},
  "tool_calls_made": [ ... ]   // optional, for debugging
}
```

### Response shape (`GET /tickers/{symbol}`)

```json
{
  "ticker": "AAPL",
  "range": {"start": "2026-01-30", "end": "2026-04-30"},
  "filters": {"min_pct_change": 2.0, "direction": "both"},
  "movements": [
    {
      "date": "2026-03-15",
      "pct_change": -3.21,
      "direction": "down",
      "prev_close": 180.10,
      "close": 174.32,
      "volume": 98234100,
      "news": [
        {
          "url": "...",
          "title": "Apple cuts iPhone production guidance",
          "source": "Reuters",
          "published_at": "2026-03-14T22:10:00Z",
          "category": "company",
          "relevance_score": 0.94,
          "reasoning": "Direct guidance cut explains the next-day drop"
        }
      ]
    }
  ]
}
```

## Ingestion orchestration

`ingestion_service.ingest(ticker, start, end, refresh=False)`:

1. **Prices** — yfinance for `[start, end]`. Upsert into `prices` (idempotent on `ticker+date`).
2. **Movements** — compute `pct_change = (close - prev_close) / prev_close`. Days where `|pct_change| >= threshold` upserted into `movements` with `status='pending'`.
3. **Ticker profile** — if missing or older than `TICKER_PROFILE_TTL_DAYS`, one OpenAI call returning structured JSON: `{company_name, sector, macro_sensitivities[], competitors[]}`. Cached.
4. **For each pending movement** (parallel via `asyncio.gather`, capped at `INGEST_CONCURRENCY`):
   - Exa query A — company: `"{company_name} {ticker}"`, date range `[T-2, T+1]`, `num_results=NEWS_PER_QUERY`, include text content.
   - Exa query B — macro/industry: built from `sector` + `macro_sensitivities`, same date range.
   - Dedupe candidates by URL. Upsert into `news_articles`.
   - One OpenAI structured-output call: score all candidates vs `{ticker, date, pct_change, direction}`. Returns `[{url, score, reasoning, category}]`.
   - Drop scores below `RELEVANCE_THRESHOLD`. Insert `movement_news` rows.
   - Mark movement `status='analyzed'`.

Cold cache: 90 days × ~5-10 movements × 2 Exa calls + 1 LLM call ≈ 30-60s. Warm cache: sub-second DB read.

## Chat tools

```
list_movements(ticker, start_date?, end_date?, min_pct_change?, direction?)
  → [{movement_id, date, pct_change, direction, close}]

get_news_for_movement(movement_id, max_results=10)
  → [{title, url, source, published_at, relevance_score, reasoning, category}]

get_price_on_date(ticker, date)
  → {open, close, pct_change, volume}

search_movements_by_keyword(ticker, keyword)
  → movements whose linked news titles/reasoning contain the keyword
```

Tool implementations are pure DB reads — no live API calls in chat path. Loop capped at ~6 iterations.

## Build order

1. Skeleton: `config.py`, `db.py`, `models.py`, `main.py`. `uvicorn app.main:app` boots.
2. `prices_service` + `movements_service` + repo + `GET /tickers/{symbol}` returning prices/movements only. Smoke test with AAPL.
3. `ticker_profile_service` + `news_service` (Exa wrapper). Verify Exa returns sane results.
4. `relevance_service` + wire into `ingestion_service`. End-to-end ingest with news.
5. Chat: tools, OpenAI loop, stateless endpoint.
6. README + curl examples.

## Out of scope for v1

- Background tasks / job queue
- Multi-day movement clustering
- Authentication / rate limiting
- Streaming chat responses
- Multi-ticker portfolios
