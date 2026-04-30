import os
from dotenv import load_dotenv

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
EXA_API_KEY = os.getenv("EXA_API_KEY")
if not OPENAI_API_KEY:
  raise RuntimeError("OPENAI_API_KEY is missing")
if not EXA_API_KEY:
  raise RuntimeError("EXA_API_KEY is missing")

DATABASE_URL = os.getenv("DATABASE_URL", 'sqlite:///./app.db')