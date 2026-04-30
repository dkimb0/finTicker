from contextlib import asynccontextmanager
import logging
from fastapi import FastAPI
from app.db import init_db
from app.routers import tickers, chat

logging.basicConfig(
  level=logging.INFO,
  format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

@asynccontextmanager
async def lifespan(app: FastAPI):
  init_db()
  yield

app = FastAPI(
  title='finTicker',
  description="Explains major stock price movements using relevant news.",
  version="0.1.0",
  lifespan=lifespan,
)

@app.get("/health")
def health() -> dict[str, str]:
  return {"status": "ok"}

# Routers (added as we build them)
# from app.routers import tickers, chat
app.include_router(tickers.router)
app.include_router(chat.router)
