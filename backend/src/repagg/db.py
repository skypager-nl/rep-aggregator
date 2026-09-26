import sqlite3
from importlib.resources import files

from .config import DATA_DIR, DB_PATH


def connect(path=DB_PATH) -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    # WAL + batched commits keep SD-card writes down.
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


# Columns added after the first release; CREATE TABLE IF NOT EXISTS won't add them.
MIGRATIONS = {
    "post": {"thread_id": "TEXT", "page": "INTEGER", "number": "INTEGER", "reactions": "INTEGER", "is_starter": "INTEGER", "quotes": "TEXT"},
    "author": {"external_id": "TEXT", "reactions": "INTEGER", "banners": "TEXT"},
    "photo": {"url": "TEXT"},
    "thread": {"summary": "TEXT", "extracted_at": "TEXT", "extract_model": "TEXT", "extract_error": "TEXT", "extract_cost": "REAL", "builds": "TEXT", "extract_cursor": "INTEGER",
               "analyse_requested": "INTEGER"},
    "event": {"post_id": "INTEGER"},
    "price_point": {"thread_id": "TEXT"},
    "factory": {"needs_review": "INTEGER"},
    "reference": {"needs_review": "INTEGER", "notes": "TEXT", "kind": "TEXT", "model_id": "TEXT"},
}


def init(conn: sqlite3.Connection) -> None:
    conn.executescript(files("repagg").joinpath("schema.sql").read_text())
    for table, cols in MIGRATIONS.items():
        have = {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
        for col, typ in cols.items():
            if col not in have:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {typ}")
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS photo_post_url ON photo(post_id, url)")
    conn.execute("UPDATE factory SET needs_review = 1 WHERE needs_review IS NULL AND notes LIKE 'auto-added%'")
    conn.execute("CREATE INDEX IF NOT EXISTS post_thread ON post(source_id, thread_id)")
    conn.commit()


def get_meta(conn: sqlite3.Connection, key: str, default: str | None = None) -> str | None:
    row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    return row[0] if row else default


def set_meta(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute("INSERT INTO meta(key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value", (key, value))
