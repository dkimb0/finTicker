import sqlite3
from pathlib import Path

DB_PATH = Path("app.db")

def get_connection() -> sqlite3.Connection:
  conn = sqlite3.connect(DB_PATH)
  conn.row_factory =sqlite3.Row
  return conn

def init_db() -> None:
  with get_connection() as conn:
    conn.execute("""
      CREATE TABLE IF NOT EXISTS batches (
        id TEXT PRIMARY KEY,
        status TEXT NOT NULL,
        total_documents INTEGER NOT NULL,
        completed_documents INTEGER DEFAULT 0,
        failed_documents INTEGER DEFAULT 0,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP
      )           
    """
    )
    
    conn.execute("""
    CREATE TABLE IF NOT EXISTS documents (
      id TEXT PRIMARY KEY,
      batch_id TEXT,
      filename TEXT,
      status TEXT NOT NULL,
      ocr_text TEXT,
      analysis TEXT,
      error TEXT,
      created_at TEXT DEFAULT CURRENT_TIMESTAMP,
      updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
      FOREIGN KEY(batch_id) REFERENCES batches(id)
      )
    """)
    conn.commit()