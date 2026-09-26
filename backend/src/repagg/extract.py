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

SYSTEM = """You analyse replica-watch forum and Reddit threads for a private buyer's database. Your output feeds \
aggregate quality scores per build (reference x factory x version). Report only what the thread's \
posts actually support.

How to read a thread
- Each post is labelled [#n | date | weight w] (forum: the author's standing, 0.3 new account ... \
2.0 long-standing reviewer) or [#n | date | score s] (Reddit: community upvotes). Use these to judge \
which claims are first-hand, informed and agreed with. Reddit wiki pages arrive as numbered sections; \
treat them as curated community consensus.
- Quoted text ("> quoting #n") belongs to the quoted post, not the replying one.
- A post may discuss several builds (e.g. comparing factories). Attribute each claim to the right one.
- Skip jokes, greetings, off-topic chatter, dealer ads, and questions with no answer.

Versions (a factory's replica of one reference; the database calls them builds)
- brand: the genuine brand (e.g. "Rolex", "Omega", "Audemars Piguet").
- reference: the genuine reference number if stated or unambiguous from the known list below \
(use the listed id), else "" — never invent one. model: the model as named (e.g. "Submariner Date", \
"Speedmaster Moonwatch", "Nautilus 5711"). Use a listed nickname's reference when the post uses it.
- Skip versions of watches that are not replicas of a genuine model (homages, DIY builds).
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

Events: dated news the posts report — a factory releasing a new build or version ("release"), restocks ("restock"), notable price changes ("price"), a factory closing ("closure") or rebranding ("rebrand"). Give a short neutral title; build may be "" for factory-level news (then name the factory).

Summary: 2-3 neutral sentences stating the thread's conclusion about the build(s). No usernames.

Known references by brand (id: name — nicknames):
{references}

Known factories and aliases:
{factories}
"""

SYSTEM_TELEGRAM = """You analyse messages from a replica-watch dealer's Telegram channel for a private buyer's database. Dealers announce releases and restocks, post price lists, share QC photos of pieces they ship, and relay factory news. Treat quality statements as the dealer's (biased) opinion.

How to read the messages
- Each message is labelled [#id | date | n photos]. Albums are merged into one message.
- Skip greetings, payment/shipping admin, and generic promotion without concrete facts.

Builds: as in forum threads — reference is one of the known references below or "OTHER"; factory as written (dealers are not factories); version "V1"/"V2"/... or "unspecified"; movement if named.

Events (the main output): "release" (new build or version available), "restock", "price" (a price change), "closure"/"rebrand" (factory news). Short neutral titles; build "" for factory-level news (then name the factory).

Prices: explicit USD prices per build from price lists or offers (post = the message id).

Claims: only when a message makes a concrete, checkable quality statement about one aspect (e.g. "V3 fixes the bezel alignment"); use evidence "photo" when QC photos are attached. Aspects: {aspects}. Sentiment -2..2, severity 0..3 as usual. Most dealer messages yield no claims.

Defects: only flaws the dealer explicitly acknowledges, with status "fixed" if a new version fixes them.

QC verdicts: none (return an empty list).

Summary: one or two neutral sentences on what this batch of messages announced.

Known references by brand (id: name — nicknames):
{references}

Known factories and aliases:
{factories}
"""

STR = {"type": "string"}
INT = {"type": "integer"}


def _enum(values, kind="string"):
    return {"type": kind, "enum": values}


def schema(ref_ids: list[str] | None = None) -> dict:
    obj = lambda props: {"type": "object", "properties": props, "required": list(props), "additionalProperties": False}  # noqa: E731
    return obj({
        "summary": STR,
        "builds": {"type": "array", "items": obj({
            "key": STR, "brand": STR, "reference": STR, "model": STR, "factory": STR, "version": STR, "movement": STR,
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
        "events": {"type": "array", "items": obj({
            "build": STR, "factory": STR, "post": INT, "kind": _enum(["release", "restock", "price", "closure", "rebrand"]), "title": STR,
        })},
    })


def settings() -> dict:
    opts = addon_options()
    return {
        "api_key": opts.get("anthropic_api_key") or os.environ.get("ANTHROPIC_API_KEY") or "",
        "model": opts.get("claude_model") or os.environ.get("REPAGG_CLAUDE_MODEL") or DEFAULT_MODEL,
        "effort": opts.get("claude_effort") or "high",
    }


def _system_prompt(conn: sqlite3.Connection, kind: str = "forum") -> tuple[str, list[str]]:  # noqa: C901
    refs = conn.execute("SELECT id, brand, name FROM reference WHERE COALESCE(kind, 'reference') = 'reference' ORDER BY brand, id").fetchall()
    models: dict[str, list[str]] = {}
    for brand, name in conn.execute("SELECT b.name, m.name FROM model m JOIN brand b ON b.id = m.brand_id ORDER BY b.name, m.name"):
        models.setdefault(brand, []).append(name)
    ref_alias: dict[str, list[str]] = {}
    for alias, rid in conn.execute("SELECT alias, reference_id FROM reference_alias ORDER BY alias"):
        if alias != rid:
            ref_alias.setdefault(rid, []).append(alias)
    lines, brand = [], None
    for r in refs:
        if r["brand"] != brand:
            brand = r["brand"]
            lines.append(f"{brand}:")
        nick = f" — {', '.join(ref_alias[r['id']])}" if r["id"] in ref_alias else ""
        lines.append(f"- {r['id']}: {r['name']}{nick}")
    aliases: dict[str, list[str]] = {}
    for alias, fid in conn.execute("SELECT alias, factory_id FROM factory_alias ORDER BY factory_id, alias"):
        aliases.setdefault(fid, []).append(alias)
    lines.append("")
    lines.append("Models by brand (use these names for model when no reference is given):")
    lines += [f"{b}: {', '.join(ms)}" for b, ms in models.items()]
    text = (SYSTEM_TELEGRAM if kind == "telegram" else SYSTEM).format(
        aspects=", ".join(ASPECT_IDS),
        references="\n".join(lines),
        factories="\n".join(f"- {', '.join(a)}" for a in aliases.values()),
    )
    return text, [r["id"] for r in refs]


def _thread_text(conn: sqlite3.Connection, source_id: str, thread_id: str, after_post: int = 0, telegram: bool = False) -> list[tuple[list[int], str]]:
    """Posts rendered for the model, grouped into chunks of whole pages."""
    rows = conn.execute(
        """
        SELECT p.id, p.number, COALESCE(p.page, 1) AS page, p.posted_at, p.body, p.quotes, p.external_id, p.reactions,
               COALESCE(a.reputation, 1.0) AS w, (SELECT COUNT(*) FROM photo ph WHERE ph.post_id = p.id) AS photos
        FROM post p LEFT JOIN author a ON a.id = p.author_id
        WHERE p.source_id = ? AND p.thread_id = ? AND p.id > ? ORDER BY page, p.number
        """,
        (source_id, thread_id, after_post),
    ).fetchall()
    chunks: list[tuple[list[int], str]] = []
    pages: list[int] = []
    buf = ""
    for r in rows:
        quotes = json.loads(r["quotes"]) if r["quotes"] else []
        quoted = "".join(f"> quoting #{_post_no(conn, source_id, q.get('source_post_id'))}: {q['text'][:400]}\n" for q in quotes)
        photos = f" | {r['photos']} photos" if r["photos"] else ""
        body = re.sub(r"[_=~*\-\u2013\u2014]{6,}|\u200b", "", r["body"] or "")
        body = re.sub(r"\n{3,}", "\n\n", body).strip()
        if telegram:
            label = f"[#{r['number']} | {r['posted_at'][:10]}{photos}]"
        elif source_id.startswith("reddit:"):
            score = f" | score {r['reactions']}" if r["reactions"] is not None else ""
            label = f"[#{r['number']} | {r['posted_at'][:10]}{score}{photos}]"
        else:
            label = f"[#{r['number']} | {r['posted_at'][:10]} | weight {r['w']:.1f}{photos}]"
        text = f"{label}\n{quoted}{body}\n\n"
        if buf and len(buf) + len(text) > MAX_CHARS_PER_CALL and r["page"] not in pages:
            chunks.append((pages, buf))
            pages, buf = [], ""
        buf += text
        if r["page"] not in pages:
            pages.append(r["page"])
    if buf:
        chunks.append((pages, buf))
    return chunks


def _post_no(conn, source_id, external_id) -> str:
    if not external_id:
        return "?"
    r = conn.execute("SELECT number FROM post WHERE source_id = ? AND external_id = ?", (source_id, external_id)).fetchone()
    return str(r[0]) if r and r[0] else "?"


def _call(client: anthropic.Anthropic, model: str, effort: str, system: str, ref_ids: list[str], header: str, body: str):
    user = f"{header}\n\n{body}"
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


def extract_thread(conn: sqlite3.Connection, thread_id: str, source_id: str = "rwi") -> dict:
    """Analyse a thread (forum/Reddit: whole thread, replacing earlier findings) or a Telegram
    channel (incremental: only messages after the last analysed one, findings appended)."""
    cfg = settings()
    if not cfg["api_key"]:
        raise RuntimeError("no Anthropic API key configured")
    t = conn.execute("SELECT * FROM thread WHERE source_id = ? AND external_id = ?", (source_id, thread_id)).fetchone()
    if not t:
        raise ValueError(f"unknown thread {source_id}/{thread_id}")
    kind = conn.execute("SELECT kind FROM source WHERE id = ?", (source_id,)).fetchone()[0]
    telegram = kind == "telegram"
    cursor = (t["extract_cursor"] or 0) if telegram else 0

    client = anthropic.Anthropic(api_key=cfg["api_key"], max_retries=3)
    system, ref_ids = _system_prompt(conn, "telegram" if telegram else "forum")
    merged = {k: [] for k in ("summary", "builds", "claims", "defects", "qc", "prices", "events")}
    cost = 0.0
    model_used = cfg["model"]
    chunks = _thread_text(conn, source_id, thread_id, after_post=cursor, telegram=telegram)
    for pages, body in chunks:
        header = (f"Telegram channel: {t['title']}" if telegram
                  else f"Thread: {t['title']}\nForum: {t['forum'] or ''}\nPages in this part: {pages} of {t['pages']}")
        out, usage, model_used = _call(client, cfg["model"], cfg["effort"], system, ref_ids, header, body)
        merged["summary"].append(out["summary"])
        for k in merged:
            if k != "summary":
                merged[k].extend(out[k])
        cost += _cost(cfg["model"], usage)

    new_cursor = conn.execute("SELECT MAX(id) FROM post WHERE source_id = ? AND thread_id = ?", (source_id, thread_id)).fetchone()[0] or cursor
    summary = merged["summary"][-1] if merged["summary"] else (t["summary"] or "")
    result = _store(conn, t, merged, model_used, replace=not telegram, after_post=cursor)
    builds = sorted(set(result["builds"]) | (set(json.loads(t["builds"])) if telegram and t["builds"] else set()))
    conn.execute(
        "UPDATE thread SET summary = ?, extracted_at = ?, extract_model = ?, extract_error = NULL, extract_cost = COALESCE(extract_cost, 0) + ?, "
        "builds = ?, extract_cursor = ?, analyse_requested = 0 WHERE source_id = ? AND external_id = ?",
        (summary, _now(), model_used, round(cost, 4), json.dumps(builds), new_cursor, source_id, thread_id),
    )
    conn.execute("INSERT INTO cost_log(at, source_id, thread_id, usd) VALUES (?, ?, ?, ?)", (_now(), source_id, thread_id, round(cost, 4)))
    conn.commit()
    _rescore(conn)
    return {**result, "summary": summary, "cost_usd": round(cost, 4), "model": model_used, "chunks": len(chunks)}


def spent_today(conn: sqlite3.Connection) -> float:
    today = datetime.now(timezone.utc).date().isoformat()
    return conn.execute("SELECT COALESCE(SUM(usd), 0) FROM cost_log WHERE at >= ?", (today,)).fetchone()[0]


def daily_budget() -> float:
    try:
        return float(addon_options().get("claude_daily_budget") or 3.0)
    except (TypeError, ValueError):
        return 3.0


def _store(conn: sqlite3.Connection, t: sqlite3.Row, out: dict, model: str, replace: bool = True, after_post: int = 0) -> dict:
    source_id, thread_id = t["source_id"], t["external_id"]
    post_ids = {r["number"]: (r["id"], r["posted_at"]) for r in conn.execute(
        "SELECT id, number, posted_at FROM post WHERE source_id = ? AND thread_id = ? AND id > ?", (source_id, thread_id, after_post))}
    ids = [v[0] for v in post_ids.values()]
    marks = ",".join("?" * len(ids)) or "NULL"
    # Findings are keyed to the posts analysed: re-analysis replaces them, never duplicates.
    conn.execute(f"DELETE FROM claim WHERE post_id IN ({marks})", ids)
    conn.execute(f"DELETE FROM qc_verdict WHERE post_id IN ({marks})", ids)
    conn.execute(f"DELETE FROM event WHERE post_id IN ({marks})", ids)
    if replace:
        conn.execute("DELETE FROM price_point WHERE source_id = ? AND thread_id = ?", (source_id, thread_id))

    builds: dict[str, str] = {}
    for b in out["builds"]:
        if (build_id := _resolve_build(conn, b)):
            builds[b["key"]] = build_id

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
            conn.execute("INSERT INTO price_point(build_id, source_id, dealer, price_usd, observed_at, thread_id) VALUES (?, ?, ?, ?, ?, ?)",
                         (build_id, source_id, p["dealer"] or (t["title"] if source_id.startswith("tg:") else None), p["price_usd"], post[1][:10], thread_id))

    n_events = 0
    for e in out.get("events", []):
        post = post_ids.get(e["post"])
        if not post:
            continue
        build_id = builds.get(e["build"])
        factory_id = conn.execute("SELECT factory_id FROM build WHERE id = ?", (build_id,)).fetchone()[0] if build_id else None
        if not factory_id and e["factory"]:
            row = conn.execute("SELECT factory_id FROM factory_alias WHERE alias = ?", (e["factory"].strip(),)).fetchone()
            factory_id = row[0] if row else None
        if not (build_id or factory_id):
            continue
        conn.execute("INSERT INTO event(kind, factory_id, build_id, title, occurred_at, source_id, post_id) VALUES (?, ?, ?, ?, ?, ?, ?)",
                     (e["kind"], factory_id, build_id, e["title"], post[1][:10], source_id, post[0]))
        n_events += 1

    return {"builds": sorted(set(builds.values())), "claims": n_claims, "defects": len(defect_ids), "qc": len(out["qc"]),
            "prices": len(out["prices"]), "events": n_events}


def _resolve_build(conn: sqlite3.Connection, b: dict) -> str | None:
    """Deterministic mapping via the alias tables; unknown factories and references are added
    and flagged for review."""
    name = b["factory"].strip()
    if not name or conn.execute("SELECT 1 FROM factory_block WHERE alias = ?", (name,)).fetchone():
        return None  # owner marked this name "not a factory"
    reference_id = _resolve_reference(conn, b.get("brand", ""), b.get("reference", ""), b.get("model", ""))
    if not reference_id:
        return None
    row = conn.execute("SELECT factory_id FROM factory_alias WHERE alias = ?", (name,)).fetchone()
    if row:
        factory_id = row[0]
    else:
        factory_id = re.sub(r"[^a-z0-9]+", "", name.lower()) or "unknown"
        conn.execute("INSERT OR IGNORE INTO factory(id, name, status, notes, needs_review) VALUES (?, ?, 'unknown', 'auto-added by extraction', 1)", (factory_id, name))
        conn.execute("INSERT OR IGNORE INTO factory_alias VALUES (?, ?)", (name, factory_id))
    version = b["version"].strip().upper() if re.fullmatch(r"\s*[Vv]\d+(\.\d+)?\s*", b["version"]) else "unspecified"
    build_id = f"{factory_id}-{_slug(reference_id)}-{version.lower()}"
    conn.execute(
        "INSERT OR IGNORE INTO build(id, reference_id, factory_id, version, movement, status) VALUES (?, ?, ?, ?, ?, 'current')",
        (build_id, reference_id, factory_id, version, b["movement"] or None),
    )
    if b["movement"]:
        conn.execute("UPDATE build SET movement = ? WHERE id = ? AND movement IS NULL", (b["movement"], build_id))
    return build_id


def _resolve_reference(conn: sqlite3.Connection, brand: str, ref: str, model: str) -> str | None:
    """Reference number or nickname -> its id; else the brand's model -> the model-level entry.
    New reference numbers and new models are added and flagged for review; nothing is guessed."""
    from .brands import slug
    from .catalogue import canonical_brand, ensure_model_reference, find_model

    ref, model = ref.strip(), model.strip()
    brand = canonical_brand(conn, brand) or brand.strip()
    for key in (ref, _norm_ref(ref)):
        if key:
            row = conn.execute("SELECT reference_id FROM reference_alias WHERE alias = ?", (key,)).fetchone()
            if row:
                return row[0]
    if model and not ref:  # a nickname that points at a specific reference ("BB58", "Pepsi")
        row = conn.execute("SELECT ra.reference_id FROM reference_alias ra JOIN reference r ON r.id = ra.reference_id "
                           "WHERE ra.alias = ? AND (r.brand = ? OR ? = '')", (model, brand, brand)).fetchone()
        if row:
            return row[0]
    if not brand:
        return None
    model_id = find_model(conn, brand, model) if model else None
    if model and not model_id and conn.execute("SELECT 1 FROM brand WHERE name = ?", (brand,)).fetchone():
        family = re.split(r"\s+(?=\d)|\s*[“\"(]", model)[0].strip() or model
        model_id = find_model(conn, brand, family)
        if not model_id:  # a model we don't know yet: add it, flagged
            bid = slug(brand)
            model_id = f"{bid}/{slug(family)}"
            conn.execute("INSERT OR IGNORE INTO model(id, brand_id, name, needs_review) VALUES (?, ?, ?, 1)", (model_id, bid, family))
            conn.execute("INSERT OR IGNORE INTO model_alias VALUES (?, ?)", (family, model_id))
    if ref and len(_norm_ref(ref)) >= 3:  # a new reference number: add it under its model
        ref_id = _norm_ref(ref)
        family = conn.execute("SELECT name FROM model WHERE id = ?", (model_id,)).fetchone()[0] if model_id else (model or brand)
        conn.execute(
            "INSERT OR IGNORE INTO reference(id, brand, family, name, kind, model_id, needs_review, notes) "
            "VALUES (?, ?, ?, ?, 'reference', ?, 1, 'auto-added by extraction')",
            (ref_id, brand, family, model or ref_id, model_id),
        )
        conn.executemany("INSERT OR IGNORE INTO reference_alias VALUES (?, ?)", [(a, ref_id) for a in {ref, ref_id} if a])
        return ref_id
    if model_id:
        name = conn.execute("SELECT name FROM model WHERE id = ?", (model_id,)).fetchone()[0]
        return ensure_model_reference(conn, brand, name, model_id)
    return None


def _norm_ref(ref: str) -> str:
    return re.sub(r"^(ref\.?|reference)\s*", "", ref.strip(), flags=re.I).upper()


def _slug(ref_id: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", ref_id.lower())


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


def auto_analyse() -> bool:
    return bool(addon_options().get("auto_analyse"))


def pending(conn: sqlite3.Connection, settle_seconds: int = 90) -> list[tuple[str, str]]:
    """(source_id, thread_id) the owner queued for analysis (or, only if auto_analyse is on,
    anything with new material). Waits until a capture run / multi-page topic is complete."""
    where = "analyse_requested = 1" if not auto_analyse() else "(analyse_requested = 1 OR extracted_at IS NULL OR extracted_at < last_captured)"
    rows = conn.execute(
        f"""SELECT source_id, external_id, last_captured, extracted_at FROM thread WHERE {where}
            ORDER BY CASE WHEN source_id IN ('rwi') OR source_id LIKE 'reddit:%' THEN 0 WHEN source_id LIKE 'tg:%' THEN 1 ELSE 2 END,
                     last_captured DESC"""
    ).fetchall()
    now = datetime.now(timezone.utc)
    out = []
    for source_id, thread_id, captured, extracted in rows:
        if (now - _dt(captured)).total_seconds() < settle_seconds:
            continue
        if source_id == "rwg":
            from .rwg import topic_complete

            if not topic_complete(conn, thread_id):  # wait for every page, so a topic is paid for once
                continue
        out.append((source_id, thread_id))
    return out


def estimate(conn: sqlite3.Connection, source_id: str, thread_id: str, after_post: int = 0) -> tuple[int, float]:
    """(characters to analyse, rough USD) for the current model: thread text + the cached instructions."""
    chars = conn.execute("SELECT COALESCE(SUM(LENGTH(body)), 0) FROM post WHERE source_id = ? AND thread_id = ? AND id > ?",
                         (source_id, thread_id, after_post)).fetchone()[0]
    pin, pout = PRICES.get(settings()["model"], PRICES[DEFAULT_MODEL])
    tokens_in = chars / 3.5 + 3000
    tokens_out = 1500 + tokens_in * 0.08  # findings JSON + reasoning, roughly
    return chars, round((tokens_in * pin + tokens_out * pout) / 1_000_000, 3)


def _dt(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def record_error(conn: sqlite3.Connection, source_id: str, thread_id: str, error: str) -> None:
    conn.execute("UPDATE thread SET extract_error = ?, extracted_at = ?, analyse_requested = 0 WHERE source_id = ? AND external_id = ?",
                 (error[:500], _now(), source_id, thread_id))
    conn.commit()
