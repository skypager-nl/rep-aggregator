"""Slow, polite collector for RWG (rwg.bz): public brand and review sections only.

- Goes out ONLY through the VPN proxy after verify_egress (fails closed: no
  proxy, dead proxy or home-IP exit -> no requests at all).
- One request every 15-25 s, at most PER_CYCLE per 20-minute cycle and
  DAILY_CAP per day. Honest user agent. robots.txt respected (one topic is
  disallowed there).
- The first 403/429/503 or challenge page pauses the collector until the
  owner resumes it. No retries, no workarounds.
- Off unless enabled in the add-on options (collectors.rwg).
"""

import random
import sqlite3
import threading
import time
from datetime import datetime, timedelta, timezone

from . import db
from .config import DB_PATH, addon_options
from .net import EgressError, proxied_client, rwi_proxy_url, safe_proxy_label, verify_egress

BASE = "https://www.rwg.bz/board/index.php?"
# Public, content-bearing sections: brand-by-brand plus reviews.
FORUMS: dict[int, str] = {
    308: "308-watch-reviews-reference", 48: "48-by-tors-watch-reviews",
    29: "29-rolex", 26: "26-omega", 14: "14-audemars-piguet", 28: "28-patek-philippe", 373: "373-tudor",
    27: "27-panerai", 22: "22-iwc", 163: "163-hublot", 17: "17-breitling", 19: "19-cartier",
    367: "367-richard-mille", 32: "32-vacheron-constantin", 23: "23-jaeger-lecoultre", 15: "15-a-lange-et-sohne",
    16: "16-breguet", 21: "21-franck-muller", 54: "54-glashutte", 24: "24-longines", 25: "25-montblanc",
    30: "30-tag-heuer", 31: "31-tissot", 33: "33-other-brands",
}
REVIEW_FORUMS = {308, 48}
DISALLOWED_TOPICS = {"45872"}  # robots.txt: Disallow: /board/index.php?showtopic=45872
CYCLE = timedelta(minutes=20)
PER_CYCLE = 30
DAILY_CAP = 600
DELAY = (15.0, 25.0)
RESCAN = timedelta(hours=6)
MAX_TOPIC_PAGES_PER_CYCLE = 8
CHALLENGE = ("Just a moment...", "cf-chl-", "challenge-platform/h/", "Attention Required!")

SCHEMA = """
CREATE TABLE IF NOT EXISTS rwg_forum (
    id            INTEGER PRIMARY KEY,
    slug          TEXT NOT NULL,
    pages         INTEGER,
    backfill_page INTEGER NOT NULL DEFAULT 1,   -- next listing page to backfill (page 1 = newest)
    last_scan     TEXT
);
CREATE TABLE IF NOT EXISTS rwg_topic (
    id            TEXT PRIMARY KEY,
    forum_id      INTEGER NOT NULL,
    url           TEXT NOT NULL,
    title         TEXT NOT NULL,
    replies       INTEGER NOT NULL DEFAULT 0,
    last_post     TEXT,
    pinned        INTEGER NOT NULL DEFAULT 0,
    fetched_page  INTEGER NOT NULL DEFAULT 0,  -- highest topic page stored
    fetched_replies INTEGER,                   -- replies count when last completed
    priority      REAL NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS collector_state (
    key   TEXT PRIMARY KEY,
    value TEXT
);
"""


def init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    for fid, slug in FORUMS.items():
        conn.execute("INSERT OR IGNORE INTO rwg_forum(id, slug) VALUES (?, ?)", (fid, slug))
    conn.commit()


def enabled() -> bool:
    return bool((addon_options().get("collectors") or {}).get("rwg"))


def _get(conn, key, default=None):
    r = conn.execute("SELECT value FROM collector_state WHERE key = ?", (f"rwg.{key}",)).fetchone()
    return r[0] if r else default


def _set(conn, key, value) -> None:
    conn.execute("INSERT INTO collector_state VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value", (f"rwg.{key}", None if value is None else str(value)))
    conn.commit()


def status(conn: sqlite3.Connection) -> dict:
    init_schema(conn)
    today = datetime.now(timezone.utc).date().isoformat()
    topics = conn.execute(
        """SELECT COUNT(*), SUM(fetched_replies IS NOT NULL AND fetched_replies >= replies AND fetched_page > 0),
                  SUM(fetched_page > 0) FROM rwg_topic"""
    ).fetchone()
    forums = conn.execute("SELECT COUNT(*), SUM(pages IS NOT NULL AND backfill_page > pages), SUM(COALESCE(pages, 0)) FROM rwg_forum").fetchone()
    return {
        "enabled": enabled(),
        "paused": _get(conn, "paused") == "1",
        "pause_reason": _get(conn, "pause_reason"),
        "last_error": _get(conn, "last_error"),
        "last_run": _get(conn, "last_run"),
        "exit": _get(conn, "exit"),
        "requests_today": int(_get(conn, f"requests.{today}", 0) or 0),
        "daily_cap": DAILY_CAP,
        "topics_known": topics[0] or 0,
        "topics_complete": topics[1] or 0,
        "topics_started": topics[2] or 0,
        "forums": forums[0] or 0,
        "forums_backfilled": forums[1] or 0,
        "listing_pages": forums[2] or 0,
    }


class Paused(Exception):
    pass


class RwgCollector:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        threading.Thread(target=self._loop, name="rwg", daemon=True).start()

    def _loop(self) -> None:
        time.sleep(60)
        while True:
            try:
                self.run_cycle()
            except Exception as e:  # never kill the thread
                print(f"[rwg] cycle error: {type(e).__name__}: {e}", flush=True)
            time.sleep(CYCLE.total_seconds())

    def run_cycle(self, force: bool = False) -> dict:
        if not self.lock.acquire(blocking=False):
            return {"skipped": "already running"}
        try:
            conn = db.connect(DB_PATH)
            init_schema(conn)
            if not (enabled() or force):
                return {"skipped": "disabled"}
            if _get(conn, "paused") == "1":
                return {"skipped": "paused"}
            today = datetime.now(timezone.utc).date().isoformat()
            used = int(_get(conn, f"requests.{today}", 0) or 0)
            if used >= DAILY_CAP:
                return {"skipped": "daily cap reached"}
            url = rwi_proxy_url()
            try:
                exit_ip = verify_egress(url)  # VPN only: raises unless the proxy works and isn't home
            except EgressError as e:
                _set(conn, "last_error", f"VPN route not available — not collecting: {e}")
                return {"skipped": "no VPN route"}
            _set(conn, "exit", f"{safe_proxy_label(url)} → {exit_ip}")
            budget = min(PER_CYCLE, DAILY_CAP - used)
            done = {"requests": 0, "topics": 0, "listing": 0}
            with proxied_client(url) as client:
                fetch = self._fetcher(conn, client, today, done)
                try:
                    budget = self._discover(conn, fetch, budget, done)
                    budget = self._backfill(conn, fetch, budget, done)
                    self._topics(conn, fetch, budget, done)
                    _set(conn, "last_error", None)
                except Paused as e:
                    _set(conn, "paused", "1")
                    _set(conn, "pause_reason", str(e))
                    print(f"[rwg] PAUSED: {e}", flush=True)
            _set(conn, "last_run", datetime.now(timezone.utc).isoformat(timespec="seconds"))
            if done["requests"]:
                print(f"[rwg] cycle: {done}", flush=True)
            conn.close()
            return done
        finally:
            self.lock.release()

    def _fetcher(self, conn, client, today, done):
        def fetch(url: str) -> str:
            time.sleep(random.uniform(*DELAY))
            r = client.get(url)
            done["requests"] += 1
            _set(conn, f"requests.{today}", int(_get(conn, f"requests.{today}", 0) or 0) + 1)
            body = r.text
            if r.status_code in (403, 429, 503) or r.headers.get("cf-mitigated") or any(m in body[:30000] for m in CHALLENGE):
                raise Paused(f"RWG answered {r.status_code}{' (challenge)' if r.headers.get('cf-mitigated') else ''} on {url[:90]} — paused, not retrying")
            r.raise_for_status()
            return body
        return fetch

    def _listing(self, conn, fetch, forum_id: int, slug: str, page: int, done) -> None:
        from .rwg_parse import parse_forum

        rows, pages = parse_forum(fetch(f"{BASE}/forum/{slug}/&page={page}"))
        done["listing"] += 1
        conn.execute("UPDATE rwg_forum SET pages = ? WHERE id = ?", (pages, forum_id))
        for r in rows:
            if r.topic_id in DISALLOWED_TOPICS:
                continue
            prio = r.replies + (1000 if forum_id in REVIEW_FORUMS else 0) + (400 if _reviewish(r.title) else 0) + (150 if r.pinned else 0)
            conn.execute(
                """INSERT INTO rwg_topic(id, forum_id, url, title, replies, last_post, pinned, priority) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(id) DO UPDATE SET title = excluded.title, replies = excluded.replies, last_post = excluded.last_post,
                       pinned = excluded.pinned, priority = excluded.priority, url = excluded.url""",
                (r.topic_id, forum_id, r.url, r.title, r.replies, r.last_post, int(r.pinned), prio),
            )
        conn.commit()

    def _discover(self, conn, fetch, budget, done) -> int:
        """Page 1 (most recent activity) of each forum, every RESCAN."""
        cutoff = (datetime.now(timezone.utc) - RESCAN).isoformat()
        order = " ".join(f"WHEN {fid} THEN {i}" for i, fid in enumerate(FORUMS))  # reviews, then the busiest brands
        for f in conn.execute(f"SELECT id, slug FROM rwg_forum WHERE last_scan IS NULL OR last_scan < ? "
                              f"ORDER BY last_scan IS NOT NULL, CASE id {order} END, last_scan", (cutoff,)).fetchall():
            if budget <= 0:
                break
            self._listing(conn, fetch, f["id"], f["slug"], 1, done)
            conn.execute("UPDATE rwg_forum SET last_scan = ?, backfill_page = MAX(backfill_page, 2) WHERE id = ?",
                         (datetime.now(timezone.utc).isoformat(timespec="seconds"), f["id"]))
            conn.commit()
            budget -= 1
        return budget

    def _backfill(self, conn, fetch, budget, done) -> int:
        """One older listing page per cycle, for the forum with the most left to discover."""
        if budget <= 0:
            return budget
        f = conn.execute("SELECT id, slug, backfill_page FROM rwg_forum WHERE pages IS NOT NULL AND backfill_page <= pages "
                         "ORDER BY id IN (308, 48) DESC, backfill_page ASC LIMIT 1").fetchone()
        if f:
            self._listing(conn, fetch, f["id"], f["slug"], f["backfill_page"], done)
            conn.execute("UPDATE rwg_forum SET backfill_page = backfill_page + 1 WHERE id = ?", (f["id"],))
            conn.commit()
            budget -= 1
        return budget

    def _topics(self, conn, fetch, budget, done) -> None:
        """New or changed topics, highest priority first; long topics continue next cycle."""
        from .ingest import ingest_rwg_page
        from .rwg_parse import POSTS_PER_PAGE

        todo = conn.execute(
            """SELECT * FROM rwg_topic WHERE fetched_replies IS NULL OR fetched_replies < replies
               ORDER BY priority DESC, last_post DESC LIMIT 20"""
        ).fetchall()
        for t in todo:
            pages = max(1, -(-(t["replies"] + 1) // POSTS_PER_PAGE))
            start = t["fetched_page"] + 1 if t["fetched_replies"] is None else max(1, (t["fetched_replies"] // POSTS_PER_PAGE) + 1)
            start = min(start, pages)
            for page in range(start, min(pages, start + MAX_TOPIC_PAGES_PER_CYCLE - 1) + 1):
                if budget <= 0:
                    return
                url = t["url"] + (f"&page={page}" if page > 1 else "")
                ingest_rwg_page(conn, fetch(url), url)
                budget -= 1
                conn.execute("UPDATE rwg_topic SET fetched_page = MAX(fetched_page, ?) WHERE id = ?", (page, t["id"]))
                if page >= pages:
                    conn.execute("UPDATE rwg_topic SET fetched_replies = replies WHERE id = ?", (t["id"],))
                    done["topics"] += 1
                conn.commit()


def topic_complete(conn: sqlite3.Connection, topic_id: str) -> bool:
    """Extraction waits until every page of a topic is stored (avoids paying twice)."""
    init_schema(conn)
    r = conn.execute("SELECT fetched_replies, replies FROM rwg_topic WHERE id = ?", (topic_id,)).fetchone()
    return r is None or (r[0] is not None and r[0] >= r[1])


def _reviewish(title: str) -> bool:
    t = title.lower()
    return any(k in t for k in ("review", "comparison", " vs", "qc", "long term", "vs.", "v2", "v3", "which is best", "best "))


_collector: RwgCollector | None = None


def collector() -> RwgCollector:
    global _collector
    if _collector is None:
        _collector = RwgCollector()
    return _collector


def resume(conn: sqlite3.Connection) -> None:
    _set(conn, "paused", "0")
    _set(conn, "pause_reason", None)
