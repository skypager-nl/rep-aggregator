"""Store browser-captured forum pages: raw archive + posts, authors, photos.

Idempotent: re-sending a page updates it in place, never duplicates.
"""

import gzip
import json
import math
import sqlite3
from datetime import date, datetime, timezone

from .config import RAW_DIR
from .rwi_parse import Post, ThreadPage, parse_thread

RWI = ("rwi", "forum", "RWI", "https://forum.replica-watch.info", 1.3)


def reputation(p: Post, today: date | None = None) -> float:
    """0.3..2.0 multiplier from tenure, activity, and review/certified status."""
    today = today or date.today()
    years = (today - date.fromisoformat(p.author_joined)).days / 365 if p.author_joined else 0
    rep = 0.5 + min(0.5, 0.1 * years) + min(0.5, 0.12 * math.log10(1 + (p.author_messages or 0)))
    banners = " ".join(p.author_banners).lower()
    if "review team" in banners:
        rep += 0.3
    if "certified" in banners:
        rep += 0.1
    return round(max(0.3, min(2.0, rep)), 2)


def ingest_rwi_page(conn: sqlite3.Connection, html: str, url: str, captured_at: str | None = None) -> dict:
    now = captured_at or datetime.now(timezone.utc).isoformat(timespec="seconds")
    page = parse_thread(html, url)
    conn.execute("INSERT OR IGNORE INTO source(id, kind, name, url, trust) VALUES (?, ?, ?, ?, ?)", RWI)

    raw = RAW_DIR / "rwi" / page.thread_id / f"p{page.page}.html.gz"
    raw.parent.mkdir(parents=True, exist_ok=True)
    raw.write_bytes(gzip.compress(html.encode("utf-8"), 6))

    _upsert_thread(conn, page, now)
    new_posts = photos = 0
    for p in page.posts:
        author_id = _upsert_author(conn, p)
        existed = conn.execute("SELECT id FROM post WHERE source_id = 'rwi' AND external_id = ?", (p.post_id,)).fetchone()
        values = dict(
            author_id=author_id, url=f"{page.url}post-{p.post_id}", thread_title=page.title, posted_at=p.posted_at,
            body=p.text, raw_path=str(raw.relative_to(RAW_DIR)), fetched_at=now, thread_id=page.thread_id, page=page.page,
            number=p.number, reactions=p.reactions, is_starter=int(p.is_starter),
            quotes=json.dumps([q.__dict__ for q in p.quotes]) if p.quotes else None,
        )
        if existed:
            post_id = existed[0]
            conn.execute(f"UPDATE post SET {', '.join(f'{k} = ?' for k in values)} WHERE id = ?", (*values.values(), post_id))
        else:
            cols = ["source_id", "external_id", *values]
            cur = conn.execute(f"INSERT INTO post({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})", ("rwi", p.post_id, *values.values()))
            post_id = cur.lastrowid
            new_posts += 1
        for img in p.images:
            cur = conn.execute("INSERT OR IGNORE INTO photo(post_id, url, path) VALUES (?, ?, '')", (post_id, img))
            photos += cur.rowcount
        # drop images no longer in the post (edited posts, older parser versions)
        keep = ",".join("?" * len(p.images)) or "''"
        conn.execute(f"DELETE FROM photo WHERE post_id = ? AND url NOT IN ({keep})", (post_id, *p.images))

    conn.execute(
        "INSERT INTO capture(source_id, thread_id, page, url, captured_at, posts, new_posts, photos, raw_path) VALUES ('rwi', ?, ?, ?, ?, ?, ?, ?, ?)",
        (page.thread_id, page.page, url, now, len(page.posts), new_posts, photos, str(raw.relative_to(RAW_DIR))),
    )
    conn.commit()
    wanted = [img for p in page.posts for img in p.images]
    stored = {r[0] for r in conn.execute(
        f"SELECT url FROM photo WHERE path != '' AND url IN ({','.join('?' * len(wanted))})", wanted)} if wanted else set()
    return {
        "thread_id": page.thread_id, "title": page.title, "forum": page.forum, "page": page.page, "pages": page.pages,
        "posts": len(page.posts), "new_posts": new_posts, "new_photos": photos,
        "missing_photos": list(dict.fromkeys(u for u in wanted if u not in stored)),
    }


PHOTO_TYPES = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp", "image/gif": ".gif"}
MAX_PHOTO_BYTES = 15_000_000


def store_photo(conn: sqlite3.Connection, url: str, data: bytes, content_type: str) -> dict:
    """Save bytes for a photo the owner's browser fetched; content-addressed, deduplicated."""
    import hashlib

    from .config import PHOTO_DIR

    ext = PHOTO_TYPES.get(content_type.split(";")[0].strip().lower())
    if not ext:
        raise ValueError(f"not an image: {content_type}")
    if not data or len(data) > MAX_PHOTO_BYTES:
        raise ValueError("empty or too large")
    digest = hashlib.sha256(data).hexdigest()
    rel = f"rwi/{digest[:2]}/{digest}{ext}"
    dest = PHOTO_DIR / rel
    if not dest.exists():
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
    # sha256 is UNIQUE; only the first row per image carries it, all rows share the path.
    n = conn.execute("UPDATE photo SET path = ? WHERE url = ?", (rel, url)).rowcount
    conn.execute("UPDATE photo SET sha256 = ? WHERE id = (SELECT MIN(id) FROM photo WHERE url = ?) "
                 "AND NOT EXISTS (SELECT 1 FROM photo WHERE sha256 = ?)", (digest, url, digest))
    conn.commit()
    return {"stored": rel, "rows": n, "bytes": len(data)}


def _upsert_thread(conn: sqlite3.Connection, page: ThreadPage, now: str) -> None:
    conn.execute(
        """
        INSERT INTO thread(source_id, external_id, url, title, forum, pages, first_seen, last_captured)
        VALUES ('rwi', ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(source_id, external_id) DO UPDATE SET
            url = excluded.url, title = excluded.title, forum = excluded.forum,
            pages = MAX(thread.pages, excluded.pages), last_captured = excluded.last_captured
        """,
        (page.thread_id, page.url, page.title, page.forum, page.pages, now, now),
    )


def _upsert_author(conn: sqlite3.Connection, p: Post) -> int:
    conn.execute(
        """
        INSERT INTO author(source_id, handle, external_id, joined, post_count, reactions, banners, reputation)
        VALUES ('rwi', ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(source_id, handle) DO UPDATE SET
            external_id = excluded.external_id, joined = excluded.joined, post_count = excluded.post_count,
            reactions = excluded.reactions, banners = excluded.banners, reputation = excluded.reputation
        """,
        (p.author, p.author_id, p.author_joined, p.author_messages, p.author_reactions, json.dumps(p.author_banners), reputation(p)),
    )
    return conn.execute("SELECT id FROM author WHERE source_id = 'rwi' AND handle = ?", (p.author,)).fetchone()[0]


def ingest_mhtml(conn: sqlite3.Connection, data: bytes, captured_at: str | None = None) -> dict:
    """A page saved by the owner's Chrome (chrome.pageCapture): HTML plus the images it displayed."""
    import email
    from email import policy

    msg = email.message_from_bytes(data, policy=policy.default)
    url = msg.get("Snapshot-Content-Location", "")
    html, images = None, {}
    for part in msg.walk():
        ct = part.get_content_type()
        if ct == "text/html" and html is None:
            html = part.get_payload(decode=True).decode(part.get_content_charset() or "utf-8", "replace")
        elif ct in PHOTO_TYPES and part.get("Content-Location"):
            images[part["Content-Location"]] = (part.get_payload(decode=True), ct)
    if html is None:
        raise ValueError("no HTML in capture")
    result = ingest_rwi_page(conn, html, url, captured_at)
    stored = 0
    for u in result["missing_photos"]:
        if u in images:
            try:
                store_photo(conn, u, *images[u])
                stored += 1
            except ValueError:
                pass
    result["stored_photos"] = stored
    result["missing_photos"] = [u for u in result["missing_photos"] if u not in images]
    return result
