"""Telegram dealer channels via the official API (Telethon, the owner's own account).

Only broadcast channels the owner has joined and explicitly follows are read --
never group chats or private messages. Runs on its own asyncio loop thread;
the web API calls into it with `service.run(coro)`.
"""

import asyncio
import os
import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import db
from .config import DATA_DIR, DB_PATH, PHOTO_DIR, addon_options

SESSION_FILE = DATA_DIR / "telegram.session"
POLL_EVERY = timedelta(minutes=30)
FIRST_BACKFILL = 300         # messages read the first time a channel is followed
BACKFILL_STEP = 100          # older messages fetched per poll until BACKFILL_DAYS is covered
BACKFILL_DAYS = 365
MAX_PHOTOS_PER_POST = 10
MAX_PHOTO_BYTES = 10_000_000
DEALER_TRUST = 0.6

SCHEMA = """
CREATE TABLE IF NOT EXISTS tg_channel (
    id              INTEGER PRIMARY KEY,
    username        TEXT,
    title           TEXT NOT NULL,
    follow          INTEGER NOT NULL DEFAULT 0,
    newest_id       INTEGER NOT NULL DEFAULT 0,
    oldest_id       INTEGER,
    backfill_done   INTEGER NOT NULL DEFAULT 0,
    last_polled     TEXT,
    error           TEXT
);
"""


def credentials() -> tuple[int | None, str]:
    opts = addon_options()
    raw_id = str(opts.get("telegram_api_id") or os.environ.get("TELEGRAM_API_ID") or "").strip()
    api_hash = (opts.get("telegram_api_hash") or os.environ.get("TELEGRAM_API_HASH") or "").strip()
    return (int(raw_id) if raw_id.isdigit() else None), api_hash


def disk_used_gb() -> float:
    total = 0
    for root, _, files in os.walk(PHOTO_DIR):
        for f in files:
            try:
                total += os.path.getsize(os.path.join(root, f))
            except OSError:
                pass
    return total / 1e9


class TelegramService:
    def __init__(self) -> None:
        self.loop = asyncio.new_event_loop()
        self.client = None
        self.login: dict = {}          # phone + phone_code_hash between login steps
        self.me: str | None = None
        self.polling = False
        self.warmed = False
        threading.Thread(target=self.loop.run_forever, name="telegram", daemon=True).start()
        self.run_soon(self._poll_forever())

    # ---- plumbing -------------------------------------------------------------

    def run(self, coro, timeout: float = 120):
        return asyncio.run_coroutine_threadsafe(coro, self.loop).result(timeout)

    def run_soon(self, coro) -> None:
        asyncio.run_coroutine_threadsafe(coro, self.loop)

    async def _client(self):
        from telethon import TelegramClient
        from telethon.sessions import StringSession

        api_id, api_hash = credentials()
        if not api_id or not api_hash:
            raise RuntimeError("Telegram api_id / api_hash not configured")
        if self.client is None:
            saved = SESSION_FILE.read_text().strip() if SESSION_FILE.exists() else ""
            self.client = TelegramClient(StringSession(saved), api_id, api_hash, device_model="Rep Index", system_version="Home Assistant")
        if not self.client.is_connected():
            await self.client.connect()
        return self.client

    def _save_session(self) -> None:
        SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
        SESSION_FILE.write_text(self.client.session.save())
        SESSION_FILE.chmod(0o600)

    # ---- login (the owner types phone, code and 2FA password in the UI) -------

    async def status(self) -> dict:
        api_id, api_hash = credentials()
        out = {"configured": bool(api_id and api_hash), "authorized": False, "account": None, "step": self.login.get("step"), "polling": self.polling}
        if not out["configured"]:
            return out
        try:
            c = await self._client()
            out["authorized"] = await c.is_user_authorized()
            if out["authorized"] and not self.me:
                me = await c.get_me()
                self.me = me.first_name or "your account"
            out["account"] = self.me if out["authorized"] else None
        except Exception as e:
            out["error"] = f"{type(e).__name__}: {e}"
        return out

    async def send_code(self, phone: str) -> dict:
        c = await self._client()
        sent = await c.send_code_request(phone)
        self.login = {"phone": phone, "hash": sent.phone_code_hash, "step": "code"}
        return {"step": "code"}

    async def submit_code(self, code: str) -> dict:
        from telethon.errors import SessionPasswordNeededError

        c = await self._client()
        try:
            await c.sign_in(phone=self.login.get("phone"), code=code.strip(), phone_code_hash=self.login.get("hash"))
        except SessionPasswordNeededError:
            self.login["step"] = "password"
            return {"step": "password"}
        return self._logged_in()

    async def submit_password(self, password: str) -> dict:
        c = await self._client()
        await c.sign_in(password=password)
        return self._logged_in()

    def _logged_in(self) -> dict:
        self._save_session()
        self.login = {}
        return {"step": "done"}

    async def logout(self) -> None:
        if self.client is not None:
            try:
                await self.client.log_out()
            finally:
                self.client = None
        SESSION_FILE.unlink(missing_ok=True)
        self.me, self.login, self.warmed = None, {}, False

    # ---- channels ---------------------------------------------------------------

    async def refresh_channels(self) -> int:
        """List broadcast channels the owner has joined. Groups and DMs are ignored."""
        c = await self._client()
        conn = _conn()
        n = 0
        async for d in c.iter_dialogs():
            ent = d.entity
            if not (d.is_channel and getattr(ent, "broadcast", False)):
                continue
            conn.execute(
                "INSERT INTO tg_channel(id, username, title) VALUES (?, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET username = excluded.username, title = excluded.title",
                (ent.id, getattr(ent, "username", None), d.name),
            )
            n += 1
        conn.commit()
        conn.close()
        self.warmed = True
        return n

    # ---- polling ------------------------------------------------------------------

    async def _poll_forever(self) -> None:
        await asyncio.sleep(20)
        while True:
            try:
                api_id, api_hash = credentials()
                if api_id and api_hash and SESSION_FILE.exists():
                    await self.poll()
            except Exception as e:
                print(f"[telegram] poll error: {type(e).__name__}: {e}", flush=True)
            await asyncio.sleep(POLL_EVERY.total_seconds())

    async def poll(self) -> dict:
        from telethon.errors import FloodWaitError

        if self.polling:
            return {"skipped": "already polling"}
        self.polling = True
        try:
            c = await self._client()
            if not await c.is_user_authorized():
                return {"skipped": "not logged in"}
            if not self.warmed:
                await c.get_dialogs()  # fills the entity cache so channels resolve by id
                self.warmed = True
            conn = _conn()
            photos_ok = disk_used_gb() < float(addon_options().get("max_disk_gb", 15))
            totals = {}
            for ch in conn.execute("SELECT * FROM tg_channel WHERE follow = 1").fetchall():
                try:
                    totals[ch["title"]] = await self._poll_channel(c, conn, ch, photos_ok)
                    conn.execute("UPDATE tg_channel SET last_polled = ?, error = NULL WHERE id = ?", (_now(), ch["id"]))
                except FloodWaitError as e:
                    conn.execute("UPDATE tg_channel SET error = ? WHERE id = ?", (f"Telegram asked to wait {e.seconds}s", ch["id"]))
                    await asyncio.sleep(min(e.seconds, 600))
                except Exception as e:
                    conn.execute("UPDATE tg_channel SET error = ? WHERE id = ?", (f"{type(e).__name__}: {e}"[:300], ch["id"]))
                conn.commit()
            conn.close()
            if totals:
                print(f"[telegram] polled: {totals}", flush=True)
            return totals
        finally:
            self.polling = False

    async def _poll_channel(self, c, conn: sqlite3.Connection, ch: sqlite3.Row, photos_ok: bool) -> int:
        from telethon.tl.types import PeerChannel

        entity = await c.get_entity(ch["username"] or PeerChannel(ch["id"]))
        source_id = f"tg:{ch['id']}"
        url = f"https://t.me/{ch['username']}" if ch["username"] else None
        conn.execute("INSERT OR IGNORE INTO source(id, kind, name, url, trust) VALUES (?, 'telegram', ?, ?, ?)", (source_id, ch["title"], url, DEALER_TRUST))
        conn.execute("UPDATE source SET name = ?, url = ? WHERE id = ?", (ch["title"], url, source_id))

        # New messages since last time (or the most recent FIRST_BACKFILL on first follow).
        if ch["newest_id"]:
            batch = [m async for m in c.iter_messages(entity, min_id=ch["newest_id"], reverse=True, limit=500)]
        else:
            batch = [m async for m in c.iter_messages(entity, limit=FIRST_BACKFILL)]
        # A slice of older history each poll, until BACKFILL_DAYS is covered.
        oldest = ch["oldest_id"] or (min((m.id for m in batch), default=None))
        if not ch["backfill_done"] and oldest:
            older = [m async for m in c.iter_messages(entity, offset_id=oldest, limit=BACKFILL_STEP)]
            cutoff = datetime.now(timezone.utc) - timedelta(days=BACKFILL_DAYS)
            if not older or older[-1].date < cutoff:
                conn.execute("UPDATE tg_channel SET backfill_done = 1 WHERE id = ?", (ch["id"],))
            batch += [m for m in older if m.date >= cutoff]

        stored = 0
        for group in _albums(batch):
            stored += await self._store_post(c, conn, source_id, ch, group, photos_ok)

        ids = [m.id for m in batch]
        if ids:
            conn.execute("UPDATE tg_channel SET newest_id = MAX(newest_id, ?), oldest_id = MIN(COALESCE(oldest_id, ?), ?) WHERE id = ?",
                         (max(ids), min(ids), min(ids), ch["id"]))
        if stored:
            now = _now()
            conn.execute(
                "INSERT INTO thread(source_id, external_id, url, title, forum, pages, first_seen, last_captured) VALUES (?, ?, ?, ?, 'Telegram', 1, ?, ?) "
                "ON CONFLICT(source_id, external_id) DO UPDATE SET title = excluded.title, url = excluded.url, last_captured = excluded.last_captured",
                (source_id, str(ch["id"]), url or "", ch["title"], now, now),
            )
        return stored

    async def _store_post(self, c, conn: sqlite3.Connection, source_id: str, ch: sqlite3.Row, msgs: list, photos_ok: bool) -> int:
        from .ingest import store_photo

        first = min(msgs, key=lambda m: m.id)
        text = "\n".join(m.message for m in sorted(msgs, key=lambda m: m.id) if m.message).strip()
        with_photo = [m for m in msgs if m.photo][:MAX_PHOTOS_PER_POST]
        if not text and not with_photo:
            return 0
        if conn.execute("SELECT 1 FROM post WHERE source_id = ? AND external_id = ?", (source_id, str(first.id))).fetchone():
            return 0
        cur = conn.execute(
            "INSERT INTO post(source_id, external_id, url, thread_title, posted_at, body, fetched_at, thread_id, page, number) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?)",
            (source_id, str(first.id), f"https://t.me/{ch['username']}/{first.id}" if ch["username"] else None, ch["title"],
             first.date.astimezone(timezone.utc).isoformat(timespec="seconds"), text, _now(), str(ch["id"]), first.id),
        )
        post_id = cur.lastrowid
        conn.commit()  # never hold the write lock while downloading photos
        if photos_ok:
            for m in with_photo:
                ref = f"tg://{ch['id']}/{m.id}"
                conn.execute("INSERT OR IGNORE INTO photo(post_id, url, path) VALUES (?, ?, '')", (post_id, ref))
                try:
                    data = await c.download_media(m, file=bytes)
                    if data and len(data) <= MAX_PHOTO_BYTES:
                        store_photo(conn, ref, data, "image/jpeg")
                except Exception as e:
                    print(f"[telegram] photo {ref} skipped: {e}", flush=True)
        return 1


def _albums(msgs: list) -> list[list]:
    """Group album parts (same grouped_id) into one post."""
    groups: dict = {}
    for m in msgs:
        groups.setdefault(m.grouped_id or f"single-{m.id}", []).append(m)
    return list(groups.values())


def _conn() -> sqlite3.Connection:
    conn = db.connect(DB_PATH)
    conn.executescript(SCHEMA)
    return conn


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)


_service: TelegramService | None = None


def service() -> TelegramService:
    global _service
    if _service is None:
        _service = TelegramService()
    return _service


def channels(conn: sqlite3.Connection) -> list[dict]:
    init_schema(conn)
    return [dict(r) for r in conn.execute(
        """
        SELECT ch.*, t.summary, t.extracted_at, t.extract_cost, t.extract_error,
               (SELECT COUNT(*) FROM post p WHERE p.source_id = 'tg:' || ch.id) AS messages,
               (SELECT COUNT(*) FROM claim cl JOIN post p ON p.id = cl.post_id WHERE p.source_id = 'tg:' || ch.id) AS findings,
               (SELECT COUNT(*) FROM event e WHERE e.source_id = 'tg:' || ch.id) AS events,
               (SELECT COUNT(*) FROM price_point pp WHERE pp.source_id = 'tg:' || ch.id) AS prices
        FROM tg_channel ch LEFT JOIN thread t ON t.source_id = 'tg:' || ch.id AND t.external_id = CAST(ch.id AS TEXT)
        ORDER BY ch.follow DESC, ch.title COLLATE NOCASE
        """
    )]
