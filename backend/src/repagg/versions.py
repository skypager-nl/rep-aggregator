"""What a "version" is.

A version is a factory's replica of one model (reference), optionally a named
*variant* sold alongside the standard one (e.g. "Youth" with a cheaper movement,
"Free Sprung", "Tungsten", "Weighted"). Its identity is factory x reference x
variant. Release numbers (V2, V3, ...) are NOT separate versions: they're the
version's history -- successive improvements of the same product -- kept in the
`release` table, and findings remember which release they were about.
"""

import re
import sqlite3

RELEASE = re.compile(r"^\s*V\s?(\d+(?:\.\d+)?)\b", re.I)


def split_label(label: str | None) -> tuple[str | None, str]:
    """'V2 Tungsten' -> ('V2', 'Tungsten'); 'Free Sprung' -> (None, 'Free Sprung'); 'unspecified' -> (None, '')."""
    text = (label or "").strip()
    if text.lower() in ("", "unspecified", "standard", "none", "n/a"):
        return None, ""
    m = RELEASE.match(text)
    if not m:
        return None, text
    variant = text[m.end():].strip(" -·,")
    return f"V{m.group(1)}", "" if variant.lower() in ("unspecified", "standard") else variant


def release_key(release: str | None) -> float:
    """Sort key: 'V2' < 'V3' < 'V10'; unknown -> -1."""
    m = RELEASE.match(release or "")
    return float(m.group(1)) if m else -1.0


def build_id(factory_id: str, reference_id: str, variant: str = "") -> str:
    slug = lambda s: re.sub(r"[^a-z0-9]+", "", s.lower())  # noqa: E731
    return f"{factory_id}-{slug(reference_id)}" + (f"-{slug(variant)}" if variant else "")


def ensure_build(conn: sqlite3.Connection, factory_id: str, reference_id: str, variant: str = "", movement: str | None = None) -> str:
    bid = build_id(factory_id, reference_id, variant)
    conn.execute(
        "INSERT OR IGNORE INTO build(id, reference_id, factory_id, version, movement, status) VALUES (?, ?, ?, ?, ?, 'current')",
        (bid, reference_id, factory_id, variant, movement or None),
    )
    if movement:
        conn.execute("UPDATE build SET movement = ? WHERE id = ? AND movement IS NULL", (movement, bid))
    return bid


def add_release(conn: sqlite3.Connection, build: str, release: str | None, seen: str | None = None, note: str | None = None) -> None:
    if not release:
        return
    conn.execute(
        """INSERT INTO release(build_id, release, first_seen, note) VALUES (?, ?, ?, ?)
           ON CONFLICT(build_id, release) DO UPDATE SET
               first_seen = CASE WHEN release.first_seen IS NULL OR (excluded.first_seen IS NOT NULL AND excluded.first_seen < release.first_seen)
                                 THEN excluded.first_seen ELSE release.first_seen END,
               note = COALESCE(release.note, excluded.note)""",
        (build, release, seen, note),
    )


def current_releases(conn: sqlite3.Connection) -> dict[str, str]:
    """Latest known release per version."""
    out: dict[str, str] = {}
    for bid, rel in conn.execute("SELECT build_id, release FROM release"):
        if release_key(rel) > release_key(out.get(bid)):
            out[bid] = rel
    return out


def label(release: str | None, variant: str | None) -> str:
    """Display label: a known release number and/or the variant; empty when neither is known."""
    return " · ".join(x for x in (release, (variant or "").strip()) if x)


def migrate(conn: sqlite3.Connection) -> dict:
    """One-time move from 'release in the version label' to 'release history per version'.
    Idempotent: versions already keyed factory x reference x variant are left alone."""
    from .admin import _rekey_build

    moved = merged = 0
    for b in conn.execute("SELECT * FROM build").fetchall():
        release, variant = split_label(b["version"])
        new = build_id(b["factory_id"], b["reference_id"], variant)
        if new == b["id"] and b["version"] == variant:
            continue
        if release:  # findings on the old id were about that release
            conn.execute("UPDATE claim SET release = ? WHERE build_id = ? AND release IS NULL", (release, b["id"]))
        if new == b["id"]:
            conn.execute("UPDATE build SET version = ? WHERE id = ?", (variant, b["id"]))
        else:
            exists = conn.execute("SELECT 1 FROM build WHERE id = ?", (new,)).fetchone()
            if not exists:
                conn.execute("INSERT INTO build(id, reference_id, factory_id, version, movement, released, status) VALUES (?, ?, ?, ?, ?, ?, ?)",
                             (new, b["reference_id"], b["factory_id"], variant, b["movement"], b["released"], b["status"]))
            else:
                merged += 1
                conn.execute("UPDATE build SET movement = COALESCE(movement, ?) WHERE id = ?", (b["movement"], new))
            _move_guide(conn, b["id"], new)
            _rekey_build(conn, b["id"], new)
        add_release(conn, new, release, b["released"])
        moved += 1
    conn.commit()
    return {"migrated": moved, "merged": merged}


def _move_guide(conn: sqlite3.Connection, old: str, new: str) -> None:
    """Carry guide baseline/entries across a re-key; keep the stronger prior when both exist."""
    try:
        conn.execute("UPDATE guide_entry SET build_id = ? WHERE build_id = ?", (new, old))
        a = conn.execute("SELECT prior_mean FROM baseline WHERE build_id = ?", (old,)).fetchone()
        b = conn.execute("SELECT prior_mean FROM baseline WHERE build_id = ?", (new,)).fetchone()
        if a and b:
            if a[0] > b[0]:
                conn.execute("DELETE FROM baseline WHERE build_id = ?", (new,))
                conn.execute("UPDATE baseline SET build_id = ? WHERE build_id = ?", (new, old))
            else:
                conn.execute("DELETE FROM baseline WHERE build_id = ?", (old,))
        elif a:
            conn.execute("UPDATE baseline SET build_id = ? WHERE build_id = ?", (new, old))
    except sqlite3.OperationalError:
        pass
