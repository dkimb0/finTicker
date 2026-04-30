from fastapi import FastAPI
from app.db import init_db


init_db()

app = FastAPI()

# app.include_router(documents.router)