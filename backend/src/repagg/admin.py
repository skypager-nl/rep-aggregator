"""Factory review: confirm, rename, alias, merge, or discard factories.

Build ids embed the factory id ('clean-126610ln-v4'), so merging re-keys builds
and everything that points at them. Scores are recomputed afterwards.
"""

import json
import re
import sqlite3
from datetime import date

from . import db, scoring

# Tables whose build_id column points at build.id (score/tier are rebuilt instead).
BUILD_CHILDREN = ("claim", "defect", "photo", "price_point", "event", "qc_verdict")
STATUSES = ("active", "closed", "rebranded", "unknown")


def list_factories(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        """
        SELECT f.id, f.name, f.status, f.founded, f.notes, COALESCE(f.needs_review, 0) AS needs_review,
               (SELECT COUNT(*) FROM build b WHERE b.factory_id = f.id) AS builds,
               (SELECT COUNT(*) FROM claim c JOIN build b ON b.id = c.build_id WHERE b.factory_id = f.id) AS claims,
               (SELECT COUNT(DISTINCT p.thread_id) FROM claim c JOIN build b ON b.id = c.build_id JOIN post p ON p.id = c.post_id
                WHERE b.factory_id = f.id) AS threads
        FROM factory f ORDER BY needs_review DESC, claims DESC, f.name COLLATE NOCASE
        """
    ).fetchall()
    aliases: dict[str, list[str]] = {}
    for alias, fid in conn.execute("SELECT alias, factory_id FROM factory_alias ORDER BY alias COLLATE NOCASE"):
        aliases.setdefault(fid, []).append(alias)
    builds: dict[str, list[dict]] = {}
    for b in conn.execute("SELECT id, factory_id, reference_id, version FROM build ORDER BY reference_id, version"):
        builds.setdefault(b["factory_id"], []).append({"id": b["id"], "reference_id": b["reference_id"], "version": b["version"]})
    return [{**dict(r), "aliases": [a for a in aliases.get(r["id"], []) if a != r["name"]], "build_list": builds.get(r["id"], [])} for r in rows]


def update_factory(conn: sqlite3.Connection, factory_id: str, name: str | None = None, status: str | None = None, reviewed: bool | None = None) -> None:
    _require(conn, factory_id)
    if name is not None:
        name = name.strip()
        if not name:
            raise ValueError("name can't be empty")
        _check_alias_free(conn, name, factory_id)
        conn.execute("UPDATE factory SET name = ? WHERE id = ?", (name, factory_id))
        conn.execute("INSERT OR IGNORE INTO factory_alias VALUES (?, ?)", (name, factory_id))
    if status is not None:
        if status not in STATUSES:
            raise ValueError(f"status must be one of {STATUSES}")
        conn.execute("UPDATE factory SET status = ? WHERE id = ?", (status, factory_id))
    if reviewed is not None:
        conn.execute("UPDATE factory SET needs_review = ?, notes = CASE WHEN ? THEN NULL ELSE notes END WHERE id = ?",
                     (0 if reviewed else 1, reviewed, factory_id))
    conn.commit()


def add_alias(conn: sqlite3.Connection, factory_id: str, alias: str) -> None:
    _require(conn, factory_id)
    alias = alias.strip()
    if not alias:
        raise ValueError("alias can't be empty")
    _check_alias_free(conn, alias, factory_id)
    conn.execute("INSERT OR IGNORE INTO factory_alias VALUES (?, ?)", (alias, factory_id))
    conn.commit()


def remove_alias(conn: sqlite3.Connection, factory_id: str, alias: str) -> None:
    name = _require(conn, factory_id)["name"]
    if alias.lower() == name.lower():
        raise ValueError("can't remove the factory's own name; rename it instead")
    conn.execute("DELETE FROM factory_alias WHERE alias = ? AND factory_id = ?", (alias, factory_id))
    conn.commit()


def merge(conn: sqlite3.Connection, source_id: str, target_id: str) -> dict:
    """Fold `source` into `target`: builds, findings and aliases move; source is deleted."""
    if source_id == target_id:
        raise ValueError("can't merge a factory into itself")
    _require(conn, source_id)
    _require(conn, target_id)
    moved = 0
    for b in conn.execute("SELECT * FROM build WHERE factory_id = ?", (source_id,)).fetchall():
        new_id = _build_id(target_id, b["reference_id"], b["version"])
        if not conn.execute("SELECT 1 FROM build WHERE id = ?", (new_id,)).fetchone():
            conn.execute("INSERT INTO build(id, reference_id, factory_id, version, movement, released, status) VALUES (?, ?, ?, ?, ?, ?, ?)",
                         (new_id, b["reference_id"], target_id, b["version"], b["movement"], b["released"], b["status"]))
        else:
            conn.execute("UPDATE build SET movement = COALESCE(movement, ?) WHERE id = ?", (b["movement"], new_id))
        _rekey_build(conn, b["id"], new_id)
        moved += 1
    conn.execute("UPDATE factory_alias SET factory_id = ? WHERE factory_id = ?", (target_id, source_id))
    conn.execute("DELETE FROM factory WHERE id = ?", (source_id,))
    _rescore(conn)
    return {"moved_builds": moved, "into": target_id}


def discard(conn: sqlite3.Connection, factory_id: str) -> dict:
    """'Not a factory' (e.g. a dealer name): drop its builds and their findings, and block its
    names so future extractions skip them instead of re-adding the factory."""
    _require(conn, factory_id)
    ids = [r[0] for r in conn.execute("SELECT id FROM build WHERE factory_id = ?", (factory_id,))]
    marks = ",".join("?" * len(ids)) or "NULL"
    counts = {"builds": len(ids)}
    for table in ("claim", "qc_verdict", "price_point", "event", "score", "tier"):
        counts[table] = conn.execute(f"DELETE FROM {table} WHERE build_id IN ({marks})", ids).rowcount
    conn.execute(f"UPDATE photo SET build_id = NULL WHERE build_id IN ({marks})", ids)
    counts["defect"] = conn.execute(f"DELETE FROM defect WHERE build_id IN ({marks})", ids).rowcount
    conn.execute(f"DELETE FROM build WHERE id IN ({marks})", ids)
    names = [r[0] for r in conn.execute("SELECT alias FROM factory_alias WHERE factory_id = ?", (factory_id,))]
    conn.executemany("INSERT OR IGNORE INTO factory_block(alias) VALUES (?)", [(n,) for n in names])
    conn.execute("DELETE FROM factory_alias WHERE factory_id = ?", (factory_id,))
    conn.execute("DELETE FROM factory WHERE id = ?", (factory_id,))
    _drop_from_thread_builds(conn, set(ids))
    _rescore(conn)
    return counts


# ---- internals -----------------------------------------------------------------

def _rekey_build(conn: sqlite3.Connection, old: str, new: str) -> None:
    if old == new:
        return
    # Defects: fold duplicates (same title) into the target build's defect.
    for d in conn.execute("SELECT id, title FROM defect WHERE build_id = ?", (old,)).fetchall():
        dup = conn.execute("SELECT id FROM defect WHERE build_id = ? AND lower(title) = lower(?)", (new, d["title"])).fetchone()
        if dup:
            conn.execute("UPDATE claim SET defect_id = ? WHERE defect_id = ?", (dup[0], d["id"]))
            conn.execute("DELETE FROM defect WHERE id = ?", (d["id"],))
    for table in BUILD_CHILDREN:
        conn.execute(f"UPDATE {table} SET build_id = ? WHERE build_id = ?", (new, old))
    conn.execute("DELETE FROM score WHERE build_id = ?", (old,))
    conn.execute("DELETE FROM tier WHERE build_id = ?", (old,))
    conn.execute("DELETE FROM build WHERE id = ?", (old,))
    for tid, builds in conn.execute("SELECT external_id, builds FROM thread WHERE builds LIKE ?", (f'%"{old}"%',)).fetchall():
        ids = [new if b == old else b for b in json.loads(builds)]
        conn.execute("UPDATE thread SET builds = ? WHERE external_id = ?", (json.dumps(sorted(set(ids))), tid))


def _drop_from_thread_builds(conn: sqlite3.Connection, removed: set[str]) -> None:
    for tid, builds in conn.execute("SELECT external_id, builds FROM thread WHERE builds IS NOT NULL").fetchall():
        ids = [b for b in json.loads(builds) if b not in removed]
        conn.execute("UPDATE thread SET builds = ? WHERE external_id = ?", (json.dumps(ids), tid))


def _build_id(factory_id: str, reference_id: str, version: str) -> str:
    return f"{factory_id}-{reference_id.lower()}-{version.lower()}"


def _require(conn: sqlite3.Connection, factory_id: str) -> sqlite3.Row:
    row = conn.execute("SELECT * FROM factory WHERE id = ?", (factory_id,)).fetchone()
    if not row:
        raise LookupError(f"unknown factory {factory_id}")
    return row


def _check_alias_free(conn: sqlite3.Connection, alias: str, factory_id: str) -> None:
    other = conn.execute("SELECT factory_id FROM factory_alias WHERE alias = ? AND factory_id != ?", (alias, factory_id)).fetchone()
    if other:
        raise ValueError(f"“{alias}” already belongs to factory “{other[0]}” — merge instead")


def _rescore(conn: sqlite3.Connection) -> None:
    today = date.today()
    conn.execute("DELETE FROM score WHERE as_of = ?", (today.isoformat(),))
    scoring.compute(conn, today)
    db.set_meta(conn, "latest_as_of", today.isoformat())
    conn.commit()


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", name.lower()) or "unknown"


def blocked(conn: sqlite3.Connection) -> list[str]:
    return [r[0] for r in conn.execute("SELECT alias FROM factory_block ORDER BY alias COLLATE NOCASE")]


def unblock(conn: sqlite3.Connection, alias: str) -> None:
    conn.execute("DELETE FROM factory_block WHERE alias = ?", (alias,))
    conn.commit()
