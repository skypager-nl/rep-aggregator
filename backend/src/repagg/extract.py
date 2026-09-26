"""Thread-level extraction: Claude reads a captured thread and returns findings.

Findings (builds, per-aspect claims, defects, QC verdicts, prices, a neutral
summary) are written to the metrics tables; the site shows conclusions plus a
link to the source thread -- never posts, usernames or quotes. Usernames are
not even sent to the model: each post is labelled only by number, date and a
numeric credibility weight.
"""

import json
import os
import re
import sqlite3
from datetime import date, datetime, timezone

import anthropic

from . import db, scoring
from .config import addon_options

DEFAULT_MODEL = "claude-opus-5"
PRICES = {  # USD per 1M tokens: (input, output). Cache reads ~0.1x input, writes ~1.25x.
    "claude-opus-5": (5.0, 25.0),
    "claude-sonnet-5": (2.0, 10.0),
    "claude-haiku-4-5": (1.0, 5.0),
}
MAX_CHARS_PER_CALL = 350_000  # ~90k tokens of thread text; longer threads are split by page
ASPECT_IDS = [a for a, _, _ in scoring.ASPECTS]

SYSTEM = """You analyse replica-watch forum threads for a private buyer's database. Your output feeds \
aggregate quality scores per build (reference x factory x version). Report only what the thread's \
posts actually support.

How to read a thread
- Each post is labelled [#n | date | weight w]. Weight reflects the author's standing (0.3 new \
account ... 2.0 long-standing reviewer). You don't need to apply it; it's for your judgement of \
which claims are first-hand and informed.
- Quoted text ("> quoting #n") belongs to the quoted post, not the replying one.
- A post may discuss several builds (e.g. comparing factories). Attribute each claim to the right one.
- Skip jokes, greetings, off-topic chatter, dealer ads, and questions with no answer.

Builds
- reference: one of the known references listed below, or "OTHER" if the watch isn't among them.
- factory: the factory name as written (e.g. "Clean", "VSF", "RICH"); dealers are not factories.
- version: "V1", "V2", ... if stated or clearly implied by date/features; otherwise "unspecified".
- movement: the clone calibre if mentioned (e.g. "VR3235", "JH3235"), else "".

Claims (one per distinct opinion or observation about one aspect of one build in one post)
- aspect: one of {aspects}. "movement" covers timekeeping, amplitude, rotor, date change; \
"crystal" covers cyclops, AR coating, laser crown; "crown" covers crown, tube, crown guards.
- sentiment: -2 serious flaw, -1 noticeable flaw, 0 neutral/acceptable, 1 good, 2 excellent/gen-like.
- severity: 0 none, 1 cosmetic/minor, 2 visible at arm's length or affects wear, 3 functional or deal-breaking.
- evidence: "photo" if the post includes QC/review photos backing it, "measurement" for measured \
dimensions, "timegrapher" for timegrapher/rate data, otherwise "opinion".
- defect: if the claim reports a recurring, nameable flaw, give a short canonical title in the style \
"Cyclops ~2.0x instead of 2.5x" (reuse the same title for the same flaw), else "".
- Long reviews produce many claims (typically one per aspect covered). A one-line "looks great" \
produces at most one low-information claim, or none.

Defects: one entry per distinct flaw per build, with status "fixed" only if the thread says a later \
version fixed it (then give fixed_in_version).

QC verdicts: for "GL or RL?"-style requests, report the community verdict for the post that asked: \
GL (green light), RL (red light) or mixed, with counts of replies voting each way.

Prices: only explicit USD prices for a specific build (convert only if the thread gives the USD figure).

Summary: 2-3 neutral sentences stating the thread's conclusion about the build(s). No usernames.

Known references (id: name):
{references}

Known factories and aliases:
{factories}
"""

STR = {"type": "string"}
INT = {"type": "integer"}


def _enum(values, kind="string"):
    return {"type": kind, "enum": values}


def schema(ref_ids: list[str]) -> dict:
    obj = lambda props: {"type": "object", "properties": props, "required": list(props), "additionalProperties": False}  # noqa: E731
    return obj({
        "summary": STR,
        "builds": {"type": "array", "items": obj({
            "key": STR, "reference": _enum(ref_ids + ["OTHER"]), "factory": STR, "version": STR, "movement": STR,
        })},
        "claims": {"type": "array", "items": obj({
            "build": STR, "post": INT, "aspect": _enum(ASPECT_IDS),
            "sentiment": _enum([-2, -1, 0, 1, 2], "integer"), "severity": _enum([0, 1, 2, 3], "integer"),
            "evidence": _enum(["opinion", "photo", "measurement", "timegrapher"]), "defect": STR,
        })},
        "defects": {"type": "array", "items": obj({
            "build": STR, "aspect": _enum(ASPECT_IDS), "title": STR, "severity": _enum([1, 2, 3], "integer"),
            "status": _enum(["open", "fixed", "disputed"]), "fixed_in_version": STR,
        })},
        "qc": {"type": "array", "items": obj({
            "build": STR, "post": INT, "verdict": _enum(["GL", "RL", "mixed"]), "gl_votes": INT, "rl_votes": INT,
        })},
        "prices": {"type": "array", "items": obj({"build": STR, "post": INT, "dealer": STR, "price_usd": {"type": "number"}})},
    })


def settings() -> dict:
    opts = addon_options()
    return {
        "api_key": opts.get("anthropic_api_key") or os.environ.get("ANTHROPIC_API_KEY") or "",
        "model": opts.get("claude_model") or os.environ.get("REPAGG_CLAUDE_MODEL") or DEFAULT_MODEL,
        "effort": opts.get("claude_effort") or "high",
    }


def _system_prompt(conn: sqlite3.Connection) -> tuple[str, list[str]]:
    refs = conn.execute("SELECT id, name FROM reference ORDER BY id").fetchall()
    aliases: dict[str, list[str]] = {}
    for alias, fid in conn.execute("SELECT alias, factory_id FROM factory_alias ORDER BY factory_id, alias"):
        aliases.setdefault(fid, []).append(alias)
    text = SYSTEM.format(
        aspects=", ".join(ASPECT_IDS),
        references="\n".join(f"- {r['id']}: {r['name']}" for r in refs),
        factories="\n".join(f"- {', '.join(a)}" for a in aliases.values()),
    )
    return text, [r["id"] for r in refs]


def _thread_text(conn: sqlite3.Connection, thread_id: str) -> list[tuple[list[int], str]]:
    """Posts rendered for the model, grouped into chunks of whole pages."""
    rows = conn.execute(
        """
        SELECT p.number, p.page, p.posted_at, p.body, p.quotes, COALESCE(a.reputation, 1.0) AS w,
               (SELECT COUNT(*) FROM photo ph WHERE ph.post_id = p.id) AS photos
        FROM post p LEFT JOIN author a ON a.id = p.author_id
        WHERE p.source_id = 'rwi' AND p.thread_id = ? ORDER BY p.page, p.number
        """,
        (thread_id,),
    ).fetchall()
    chunks: list[tuple[list[int], str]] = []
    pages: list[int] = []
    buf = ""
    for r in rows:
        quotes = json.loads(r["quotes"]) if r["quotes"] else []
        quoted = "".join(f"> quoting #{_post_no(conn, thread_id, q.get('source_post_id'))}: {q['text'][:400]}\n" for q in quotes)
        photos = f" | {r['photos']} photos" if r["photos"] else ""
        body = re.sub(r"[_=~*\-\u2013\u2014]{6,}|\u200b", "", r["body"] or "")
        body = re.sub(r"\n{3,}", "\n\n", body).strip()
        text = f"[#{r['number']} | {r['posted_at'][:10]} | weight {r['w']:.1f}{photos}]\n{quoted}{body}\n\n"
        if buf and len(buf) + len(text) > MAX_CHARS_PER_CALL and r["page"] not in pages:
            chunks.append((pages, buf))
            pages, buf = [], ""
        buf += text
        if r["page"] not in pages:
            pages.append(r["page"])
    if buf:
        chunks.append((pages, buf))
    return chunks


def _post_no(conn, thread_id, external_id) -> str:
    if not external_id:
        return "?"
    r = conn.execute("SELECT number FROM post WHERE source_id = 'rwi' AND external_id = ?", (external_id,)).fetchone()
    return str(r[0]) if r and r[0] else "?"


def _call(client: anthropic.Anthropic, model: str, effort: str, system: str, ref_ids: list[str], title: str, forum: str, pages: list[int], total: int, body: str):
    user = f"Thread: {title}\nForum: {forum}\nPages in this part: {pages} of {total}\n\n{body}"
    kwargs = dict(
        model=model,
        max_tokens=32000,
        system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": user}],
        output_config={"effort": effort, "format": {"type": "json_schema", "schema": schema(ref_ids)}},
    )
    try:
        # Server-side refusal fallback: a declined request is re-run on another model, not lost.
        with client.beta.messages.stream(betas=["server-side-fallback-2026-07-01"], fallbacks="default", **kwargs) as s:
            msg = s.get_final_message()
    except anthropic.BadRequestError as e:
        if "fallback" not in str(e).lower():
            raise
        with client.messages.stream(**kwargs) as s:  # fallbacks unavailable for this model/account
            msg = s.get_final_message()
    if msg.stop_reason == "refusal":
        raise RuntimeError("the model declined to analyse this thread")
    if msg.stop_reason == "max_tokens":
        raise RuntimeError("output hit max_tokens; thread too long for one call")
    text = next(b.text for b in msg.content if b.type == "text")
    return json.loads(text), msg.usage, msg.model


def extract_thread(conn: sqlite3.Connection, thread_id: str) -> dict:
    cfg = settings()
    if not cfg["api_key"]:
        raise RuntimeError("no Anthropic API key configured")
    t = conn.execute("SELECT * FROM thread WHERE source_id = 'rwi' AND external_id = ?", (thread_id,)).fetchone()
    if not t:
        raise ValueError(f"unknown thread {thread_id}")
    client = anthropic.Anthropic(api_key=cfg["api_key"], max_retries=3)
    system, ref_ids = _system_prompt(conn)

    merged = {"summary": [], "builds": [], "claims": [], "defects": [], "qc": [], "prices": []}
    cost = 0.0
    model_used = cfg["model"]
    for pages, body in _thread_text(conn, thread_id):
        out, usage, model_used = _call(client, cfg["model"], cfg["effort"], system, ref_ids, t["title"], t["forum"] or "", pages, t["pages"], body)
        merged["summary"].append(out["summary"])
        for k in ("builds", "claims", "defects", "qc", "prices"):
            merged[k].extend(out[k])
        cost += _cost(cfg["model"], usage)

    summary = " ".join(merged["summary"]) if len(merged["summary"]) == 1 else " ".join(merged["summary"][-1:])
    result = _store(conn, t, merged, summary, model_used)
    conn.execute(
        "UPDATE thread SET summary = ?, extracted_at = ?, extract_model = ?, extract_error = NULL, extract_cost = COALESCE(extract_cost, 0) + ?, "
        "builds = ? WHERE source_id = 'rwi' AND external_id = ?",
        (summary, _now(), model_used, round(cost, 4), json.dumps(result["builds"]), thread_id),
    )
    conn.commit()
    _rescore(conn)
    return {**result, "summary": summary, "cost_usd": round(cost, 4), "model": model_used}


def _store(conn: sqlite3.Connection, t: sqlite3.Row, out: dict, summary: str, model: str) -> dict:
    thread_id = t["external_id"]
    post_ids = {r["number"]: (r["id"], r["posted_at"]) for r in conn.execute(
        "SELECT id, number, posted_at FROM post WHERE source_id = 'rwi' AND thread_id = ?", (thread_id,))}
    ids = [v[0] for v in post_ids.values()]
    marks = ",".join("?" * len(ids)) or "NULL"
    # Re-extraction replaces this thread's previous findings.
    conn.execute(f"DELETE FROM claim WHERE post_id IN ({marks})", ids)
    conn.execute(f"DELETE FROM qc_verdict WHERE post_id IN ({marks})", ids)
    conn.execute("DELETE FROM price_point WHERE source_id = 'rwi' AND thread_id = ?", (thread_id,))

    builds: dict[str, str] = {}
    for b in out["builds"]:
        if b["reference"] == "OTHER":
            continue
        builds[b["key"]] = _resolve_build(conn, b)

    defect_ids: dict[tuple[str, str], int] = {}
    for d in out["defects"]:
        build_id = builds.get(d["build"])
        if build_id:
            defect_ids[(build_id, d["title"].lower())] = _upsert_defect(conn, build_id, d)

    n_claims = 0
    now = _now()
    for c in out["claims"]:
        build_id, post = builds.get(c["build"]), post_ids.get(c["post"])
        if not build_id or not post:
            continue
        defect_id = None
        if c["defect"]:
            key = (build_id, c["defect"].lower())
            defect_id = defect_ids.get(key) or _upsert_defect(
                conn, build_id, {"aspect": c["aspect"], "title": c["defect"], "severity": max(1, c["severity"]), "status": "open", "fixed_in_version": ""})
            defect_ids[key] = defect_id
        kind = "defect" if c["sentiment"] < 0 else "praise" if c["sentiment"] > 0 else "neutral"
        conn.execute(
            "INSERT INTO claim(post_id, build_id, aspect, kind, sentiment, severity, evidence, defect_id, quote, model, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?)",
            (post[0], build_id, c["aspect"], kind, c["sentiment"], c["severity"], c["evidence"], defect_id, model, now),
        )
        n_claims += 1

    for q in out["qc"]:
        build_id, post = builds.get(q["build"]), post_ids.get(q["post"])
        if build_id and post:
            conn.execute("INSERT OR REPLACE INTO qc_verdict VALUES (?, ?, ?, ?, ?, NULL, ?)",
                         (post[0], build_id, q["verdict"], q["gl_votes"], q["rl_votes"], post[1][:10]))

    for p in out["prices"]:
        build_id, post = builds.get(p["build"]), post_ids.get(p["post"])
        if build_id and post and 50 <= p["price_usd"] <= 5000:
            conn.execute("INSERT INTO price_point(build_id, source_id, dealer, price_usd, observed_at, thread_id) VALUES (?, 'rwi', ?, ?, ?, ?)",
                         (build_id, p["dealer"] or None, p["price_usd"], post[1][:10], thread_id))

    return {"builds": sorted(set(builds.values())), "claims": n_claims, "defects": len(defect_ids), "qc": len(out["qc"]), "prices": len(out["prices"])}


def _resolve_build(conn: sqlite3.Connection, b: dict) -> str:
    """Deterministic mapping via the alias tables; unknown factories are added and flagged for review."""
    name = b["factory"].strip()
    row = conn.execute("SELECT factory_id FROM factory_alias WHERE alias = ?", (name,)).fetchone()
    if row:
        factory_id = row[0]
    else:
        factory_id = re.sub(r"[^a-z0-9]+", "", name.lower()) or "unknown"
        conn.execute("INSERT OR IGNORE INTO factory(id, name, status, notes) VALUES (?, ?, 'unknown', 'auto-added by extraction — review')", (factory_id, name))
        conn.execute("INSERT OR IGNORE INTO factory_alias VALUES (?, ?)", (name, factory_id))
    version = b["version"].strip().upper() if re.fullmatch(r"\s*[Vv]\d+(\.\d+)?\s*", b["version"]) else "unspecified"
    build_id = f"{factory_id}-{b['reference'].lower()}-{version.lower()}"
    conn.execute(
        "INSERT OR IGNORE INTO build(id, reference_id, factory_id, version, movement, status) VALUES (?, ?, ?, ?, ?, 'current')",
        (build_id, b["reference"], factory_id, version, b["movement"] or None),
    )
    if b["movement"]:
        conn.execute("UPDATE build SET movement = ? WHERE id = ? AND movement IS NULL", (b["movement"], build_id))
    return build_id


def _upsert_defect(conn: sqlite3.Connection, build_id: str, d: dict) -> int:
    row = conn.execute("SELECT id FROM defect WHERE build_id = ? AND lower(title) = lower(?)", (build_id, d["title"])).fetchone()
    if row:
        conn.execute("UPDATE defect SET severity = MAX(severity, ?), status = ?, fixed_in_version = COALESCE(NULLIF(?, ''), fixed_in_version) WHERE id = ?",
                     (d["severity"], d["status"], d["fixed_in_version"], row[0]))
        return row[0]
    cur = conn.execute("INSERT INTO defect(build_id, aspect, title, severity, status, fixed_in_version) VALUES (?, ?, ?, ?, ?, NULLIF(?, ''))",
                       (build_id, d["aspect"], d["title"], d["severity"], d["status"], d["fixed_in_version"]))
    return cur.lastrowid


def _rescore(conn: sqlite3.Connection) -> None:
    today = date.today()
    latest = db.get_meta(conn, "latest_as_of")
    scoring.compute(conn, today)
    if latest and latest != today.isoformat():
        db.set_meta(conn, "previous_as_of", latest)
    db.set_meta(conn, "latest_as_of", today.isoformat())
    conn.commit()


def _cost(model: str, usage) -> float:
    pin, pout = PRICES.get(model, PRICES[DEFAULT_MODEL])
    read = getattr(usage, "cache_read_input_tokens", 0) or 0
    write = getattr(usage, "cache_creation_input_tokens", 0) or 0
    return (usage.input_tokens * pin + read * pin * 0.1 + write * pin * 1.25 + usage.output_tokens * pout) / 1_000_000


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def pending(conn: sqlite3.Connection, settle_seconds: int = 90) -> list[str]:
    """Threads with new captures since their last extraction, idle long enough that a capture run has finished."""
    rows = conn.execute(
        """
        SELECT external_id, last_captured FROM thread
        WHERE source_id = 'rwi' AND (extracted_at IS NULL OR extracted_at < last_captured)
        """
    ).fetchall()
    now = datetime.now(timezone.utc)
    return [r[0] for r in rows if (now - datetime.fromisoformat(r[1])).total_seconds() >= settle_seconds]


def record_error(conn: sqlite3.Connection, thread_id: str, error: str) -> None:
    conn.execute("UPDATE thread SET extract_error = ?, extracted_at = ? WHERE source_id = 'rwi' AND external_id = ?", (error[:500], _now(), thread_id))
    conn.commit()
