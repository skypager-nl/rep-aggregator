"""HTTP API + static site. Served behind Home Assistant ingress, so every URL the
frontend uses is relative -- ingress mounts us under /api/hassio_ingress/<token>/."""

import hmac
import json
import os
import secrets
import sqlite3
import threading
import time
from collections import defaultdict
from collections.abc import Iterator

from fastapi import Body, Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from . import db, scoring
from .config import DATA_DIR, DB_PATH, PHOTO_DIR, STATIC_DIR

app = FastAPI(title="repagg", docs_url="/api/docs", openapi_url="/api/openapi.json")


# HA ingress proxies from the Supervisor; it has already checked the HA login.
TRUSTED = set(os.environ.get("REPAGG_TRUSTED", "172.30.32.2,127.0.0.1,::1").split(","))
TOKEN_FILE = DATA_DIR / "capture_token"


def capture_token() -> str:
    if not TOKEN_FILE.exists():
        TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
        TOKEN_FILE.write_text(secrets.token_urlsafe(24))
        TOKEN_FILE.chmod(0o600)
    return TOKEN_FILE.read_text().strip()


def _trusted(request: Request) -> bool:
    return request.client is not None and request.client.host in TRUSTED


SESSION_COOKIE = "repagg_session"
SESSION_DAYS = 30
_login_failures: dict[str, list[float]] = {}


def _web_password() -> str:
    from .config import addon_options

    return (addon_options().get("web_password") or os.environ.get("REPAGG_WEB_PASSWORD") or "").strip()


def _valid_session(token: str | None) -> bool:
    if not token or not _web_password():
        return False
    c = db.connect(DB_PATH)
    try:
        row = c.execute("SELECT expires FROM web_session WHERE token = ?", (token,)).fetchone()
    finally:
        c.close()
    return bool(row) and row[0] > time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime())


@app.middleware("http")
async def gate(request: Request, call_next):
    """HA ingress is already authenticated. Direct access on the LAN port: captures need the token,
    everything else needs a login session (only once a web_password is set)."""
    if _trusted(request):
        return await call_next(request)
    path, method = request.url.path, request.method
    if path == "/api/health" and method == "GET":
        return await call_next(request)
    if path in ("/api/capture", "/api/capture/photo", "/api/capture/mhtml") and method == "POST":
        sent = request.headers.get("x-capture-token", "")
        if not hmac.compare_digest(sent, capture_token()):
            return JSONResponse({"detail": "bad capture token"}, status_code=401)
        return await call_next(request)
    if path in ("/login", "/logout"):
        return await call_next(request)
    if _valid_session(request.cookies.get(SESSION_COOKIE)):
        return await call_next(request)
    if path.startswith("/api/") or path.startswith("/photos/"):
        return JSONResponse({"detail": "login required"}, status_code=401)
    return RedirectResponse("/login", status_code=303)


LOGIN_PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>The Rep Index — sign in</title><style>
body{{margin:0;min-height:100vh;display:grid;place-items:center;background:#0a0a0b;color:#ece6da;font:15px/1.5 -apple-system,BlinkMacSystemFont,Inter,sans-serif}}
form{{width:min(340px,88vw)}} h1{{font:400 40px Georgia,serif;margin:0 0 6px}} p{{color:#8f8a80;margin:0 0 22px;font-size:13.5px}}
input{{width:100%;box-sizing:border-box;padding:11px 14px;border-radius:12px;border:1px solid rgba(255,255,255,.14);background:#121214;color:#ece6da;font:inherit;outline:none}}
input:focus{{border-color:rgba(255,255,255,.3)}} button{{margin-top:12px;width:100%;padding:11px;border-radius:999px;border:0;background:#ece6da;color:#0a0a0b;font:600 14px inherit;cursor:pointer}}
.err{{color:#d9826f;margin-top:12px;font-size:13px}}</style></head><body>
<form method="post" action="/login"><h1>The Rep Index</h1><p>{hint}</p>
<input type="password" name="password" autocomplete="current-password" placeholder="Password" autofocus {disabled}>
<button {disabled}>Sign in</button>{error}</form></body></html>"""


def _login_page(error: str = "") -> HTMLResponse:
    configured = bool(_web_password())
    hint = "Private dashboard." if configured else "Direct access is off. Set <b>web_password</b> in the Rep Index app configuration in Home Assistant."
    return HTMLResponse(LOGIN_PAGE.format(hint=hint, disabled="" if configured else "disabled", error=f'<div class="err">{error}</div>' if error else ""))


@app.get("/login")
def login_form():
    return _login_page()


@app.post("/login")
async def login(request: Request):
    ip = request.client.host if request.client else "?"
    now = time.time()
    recent = [t for t in _login_failures.get(ip, []) if now - t < 900]
    _login_failures[ip] = recent
    if len(recent) >= 10:
        return _login_page("Too many attempts — try again in 15 minutes.")
    form = await request.form()
    password = _web_password()
    if not password or not hmac.compare_digest(str(form.get("password", "")), password):
        _login_failures[ip].append(now)
        time.sleep(1.0)
        return _login_page("Wrong password.")
    token = secrets.token_urlsafe(32)
    c = db.connect(DB_PATH)
    try:
        c.execute("DELETE FROM web_session WHERE expires < ?", (time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()),))
        c.execute("INSERT INTO web_session VALUES (?, ?, ?)", (token, time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()),
                  time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(now + SESSION_DAYS * 86400))))
        c.commit()
    finally:
        c.close()
    resp = RedirectResponse("/", status_code=303)
    resp.set_cookie(SESSION_COOKIE, token, max_age=SESSION_DAYS * 86400, httponly=True, samesite="lax")
    return resp


@app.get("/logout")
def logout(request: Request):
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        c = db.connect(DB_PATH)
        c.execute("DELETE FROM web_session WHERE token = ?", (token,))
        c.commit()
        c.close()
    resp = RedirectResponse("/login", status_code=303)
    resp.delete_cookie(SESSION_COOKIE)
    return resp


@app.middleware("http")
async def no_cache_html(request: Request, call_next):
    response = await call_next(request)
    if response.headers.get("content-type", "").startswith("text/html"):
        response.headers["Cache-Control"] = "no-cache"
    return response


def conn() -> Iterator[sqlite3.Connection]:
    c = db.connect(DB_PATH)
    try:
        yield c
    finally:
        c.close()


def _as_of(c: sqlite3.Connection) -> tuple[str, str]:
    latest = db.get_meta(c, "latest_as_of")
    if latest is None:
        raise HTTPException(503, "No scores computed yet — run `repagg score`")
    return latest, db.get_meta(c, "previous_as_of", latest)


def _build_summaries(c: sqlite3.Connection, where: str = "1=1", params: tuple = ()) -> list[dict]:
    latest, previous = _as_of(c)
    rows = c.execute(
        f"""
        SELECT b.*, f.name AS factory, f.status AS factory_status,
               r.brand, r.family, r.name AS reference_name, r.dial_color, r.bezel_color, r.metal_color,
               (SELECT path FROM reference_photo rp WHERE rp.reference_id = r.id ORDER BY rp.view != 'front', rp.id LIMIT 1) AS ref_photo,
               t.tier, t.rank, t.controversy, pt.tier AS prev_tier,
               so.score, so.lower, so.n AS claims, bl.rank AS guide_rank, bl.quality AS guide_quality,
               (SELECT COUNT(*) FROM defect d WHERE d.build_id = b.id AND d.status != 'fixed') AS open_defects,
               (SELECT COUNT(*) FROM photo ph WHERE ph.build_id = b.id) AS photos,
               (SELECT COUNT(*) FROM qc_verdict q WHERE q.build_id = b.id AND q.verdict = 'GL') AS qc_gl,
               (SELECT COUNT(*) FROM qc_verdict q WHERE q.build_id = b.id AND q.verdict = 'RL') AS qc_rl,
               (SELECT COUNT(*) FROM qc_verdict q WHERE q.build_id = b.id AND q.verdict = 'mixed') AS qc_mixed
        FROM build b
        JOIN factory f   ON f.id = b.factory_id
        JOIN reference r ON r.id = b.reference_id
        LEFT JOIN tier t   ON t.build_id = b.id AND t.as_of = ?
        LEFT JOIN tier pt  ON pt.build_id = b.id AND pt.as_of = ?
        LEFT JOIN score so ON so.build_id = b.id AND so.as_of = ? AND so.aspect = 'overall'
        LEFT JOIN baseline bl ON bl.build_id = b.id
        WHERE {where}
        ORDER BY b.reference_id, t.rank
        """,
        (latest, previous, latest, *params),
    ).fetchall()
    builds = [dict(r) for r in rows]
    if not builds:
        return builds

    ids = [b["id"] for b in builds]
    marks = ",".join("?" * len(ids))
    aspects: dict[str, dict] = defaultdict(dict)
    for r in c.execute(f"SELECT build_id, aspect, score, lower, n FROM score WHERE as_of = ? AND aspect != 'overall' AND build_id IN ({marks})", (latest, *ids)):
        aspects[r["build_id"]][r["aspect"]] = {"score": r["score"], "lower": r["lower"], "n": r["n"]}
    prices = _latest_prices(c, ids)
    from .versions import current_releases, label

    current = current_releases(c)
    for b in builds:
        b["aspects"] = aspects.get(b["id"], {})
        b["price"] = prices.get(b["id"])
        b["variant"] = b["version"] or ""
        b["release"] = current.get(b["id"])
        b["label"] = label(b["release"], b["variant"])
    return builds


def _label_rows(c: sqlite3.Connection, rows: list[dict], id_key: str = "build_id") -> list[dict]:
    """Add the display label (known release + variant) to rows carrying a build id and its version."""
    from .versions import current_releases, label

    current = current_releases(c)
    for r in rows:
        r["label"] = label(current.get(r.get(id_key)), r.get("version") or "")
    return rows


def _latest_prices(c: sqlite3.Connection, ids: list[str]) -> dict[str, float]:
    marks = ",".join("?" * len(ids))
    rows = c.execute(
        f"""
        SELECT build_id, AVG(price_usd) AS price FROM (
            SELECT build_id, price_usd,
                   ROW_NUMBER() OVER (PARTITION BY build_id, dealer ORDER BY observed_at DESC) AS rn
            FROM price_point WHERE build_id IN ({marks})
        ) WHERE rn = 1 GROUP BY build_id
        """,
        ids,
    )
    return {r["build_id"]: round(r["price"]) for r in rows}


@app.get("/api/meta")
def meta(c: sqlite3.Connection = Depends(conn)):
    latest, previous = _as_of(c)
    count = lambda t: c.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]  # noqa: E731
    return {
        "dataset": db.get_meta(c, "dataset", "live"),
        "as_of": latest,
        "previous_as_of": previous,
        "counts": {t: count(t) for t in ("reference", "factory", "build", "post", "claim", "photo", "defect")},
        "aspects": [{"id": a, "label": label, "weight": w} for a, label, w in scoring.ASPECTS],
        "tiers": [t for t, _ in scoring.TIERS],
        "families": [r[0] for r in c.execute("SELECT DISTINCT family FROM reference ORDER BY family")],
        "brands": [dict(r) for r in c.execute(
            """SELECT r.brand, COUNT(DISTINCT r.id) AS references_, COUNT(DISTINCT b.id) AS builds
               FROM reference r LEFT JOIN build b ON b.reference_id = r.id GROUP BY r.brand ORDER BY builds DESC, r.brand""")],
        "references_to_review": c.execute("SELECT COUNT(*) FROM reference WHERE needs_review = 1").fetchone()[0]
            + c.execute("SELECT COUNT(*) FROM model WHERE needs_review = 1").fetchone()[0],
        "factories": [dict(r) for r in c.execute("SELECT id, name, status FROM factory ORDER BY name")],
        "factories_to_review": c.execute("SELECT COUNT(*) FROM factory WHERE needs_review = 1").fetchone()[0],
        "sources": [dict(r) for r in c.execute("SELECT id, kind, name, trust FROM source ORDER BY trust DESC")],
    }


@app.get("/api/references")
def references(c: sqlite3.Connection = Depends(conn)):
    refs = [dict(r) for r in c.execute(
        """SELECT r.*, (SELECT path FROM reference_photo rp WHERE rp.reference_id = r.id ORDER BY rp.view != 'front', rp.id LIMIT 1) AS ref_photo
           FROM reference r ORDER BY brand, family, id""")]
    by_ref = defaultdict(list)
    for b in _build_summaries(c):
        by_ref[b["reference_id"]].append(b)
    for r in refs:
        builds = by_ref[r["id"]]
        r["builds"] = [{k: b[k] for k in ("id", "factory", "factory_id", "version", "label", "tier", "rank", "score", "status", "claims")} for b in builds]
        r["claims"] = sum(b["claims"] or 0 for b in builds)
    return refs


@app.get("/api/references/{ref_id:path}")
def reference(ref_id: str, c: sqlite3.Connection = Depends(conn)):
    row = c.execute("SELECT * FROM reference WHERE id = ?", (ref_id,)).fetchone()
    if not row:
        raise HTTPException(404)
    out = dict(row)
    out["aliases"] = [r[0] for r in c.execute("SELECT alias FROM reference_alias WHERE reference_id = ?", (ref_id,))]
    out["photos"] = _ref_photos(c, ref_id)
    out["builds"] = _build_summaries(c, "b.reference_id = ?", (ref_id,))
    return out


def _ref_photos(c: sqlite3.Connection, ref_id: str) -> list[dict]:
    return [dict(r) for r in c.execute(
        "SELECT id, view, path, credit, source_url FROM reference_photo WHERE reference_id = ? ORDER BY view != 'front', id", (ref_id,))]


@app.get("/api/builds")
def builds(c: sqlite3.Connection = Depends(conn)):
    return _build_summaries(c)


@app.get("/api/builds/{build_id}")
def build(build_id: str, c: sqlite3.Connection = Depends(conn)):
    found = _build_summaries(c, "b.id = ?", (build_id,))
    if not found:
        raise HTTPException(404)
    out = found[0]
    latest, previous = _as_of(c)
    prev = {r["aspect"]: r["score"] for r in c.execute("SELECT aspect, score FROM score WHERE build_id = ? AND as_of = ?", (build_id, previous))}
    for aspect, s in out["aspects"].items():
        s["prev"] = prev.get(aspect)
    out["prev_score"] = prev.get("overall")
    out["reference"] = dict(c.execute("SELECT * FROM reference WHERE id = ?", (out["reference_id"],)).fetchone())
    out["ref_photos"] = _ref_photos(c, out["reference_id"])
    out["defects"] = [dict(r) for r in c.execute(
        """
        SELECT d.*, COUNT(cl.id) AS reports, MIN(p.posted_at) AS first_seen, MAX(p.posted_at) AS last_seen
        FROM defect d
        LEFT JOIN claim cl ON cl.defect_id = d.id
        LEFT JOIN post p ON p.id = cl.post_id
        WHERE d.build_id = ?
        GROUP BY d.id ORDER BY d.status = 'fixed', d.severity DESC, reports DESC
        """,
        (build_id,),
    )]
    out["photo_list"] = [dict(r) for r in c.execute("SELECT id, aspect, path, width, height FROM photo WHERE build_id = ?", (build_id,))]
    from .versions import release_key

    rel = [dict(r) for r in c.execute("SELECT release, first_seen, note FROM release WHERE build_id = ?", (build_id,))]
    for r in rel:
        r["fixed"] = [d["title"] for d in out["defects"] if d["status"] == "fixed" and d["fixed_in_version"] == r["release"]]
        r["findings"] = c.execute("SELECT COUNT(*) FROM claim WHERE build_id = ? AND release = ?", (build_id, r["release"])).fetchone()[0]
    out["releases"] = sorted(rel, key=lambda r: release_key(r["release"]))
    guide = db.get_meta(c, "guide_wmtb")
    out["guide"] = {**json.loads(guide), "entries": [dict(r) for r in c.execute(
        "SELECT model_text, movement, rank, quality, factory_raw, note FROM guide_entry WHERE build_id = ? ORDER BY rank", (build_id,))]} if guide else None
    out["prices"] = [dict(r) for r in c.execute(
        "SELECT dealer, price_usd AS price, observed_at FROM price_point WHERE build_id = ? ORDER BY observed_at", (build_id,))]
    out["sources"] = [dict(r) for r in c.execute(
        """
        SELECT t.url, t.title, t.forum, t.summary, t.last_captured, s.name AS source, COUNT(cl.id) AS findings,
               MIN(p.posted_at) AS first_post, MAX(p.posted_at) AS last_post
        FROM claim cl JOIN post p ON p.id = cl.post_id JOIN thread t ON t.source_id = p.source_id AND t.external_id = p.thread_id
        JOIN source s ON s.id = t.source_id
        WHERE cl.build_id = ? GROUP BY t.source_id, t.external_id ORDER BY last_post DESC
        """,
        (build_id,),
    )]
    out["qc"] = [dict(r) for r in c.execute(
        """
        SELECT q.verdict, q.gl_votes, q.rl_votes, q.flaws, q.decided_at, p.thread_title, s.name AS source
        FROM qc_verdict q JOIN post p ON p.id = q.post_id JOIN source s ON s.id = p.source_id
        WHERE q.build_id = ? ORDER BY q.decided_at DESC LIMIT 24
        """,
        (build_id,),
    )]
    out["qc_trend"] = [dict(r) for r in c.execute(
        """
        SELECT substr(decided_at, 1, 4) || '-Q' || ((CAST(substr(decided_at, 6, 2) AS INTEGER) + 2) / 3) AS period,
               ROUND(100.0 * AVG(verdict = 'GL'), 1) AS gl_rate, COUNT(*) AS n
        FROM qc_verdict WHERE build_id = ? GROUP BY period ORDER BY period
        """,
        (build_id,),
    )]
    out["siblings"] = [
        {k: b[k] for k in ("id", "factory", "factory_id", "version", "label", "tier", "rank", "score", "status")}
        for b in _build_summaries(c, "b.reference_id = ? AND b.id != ?", (out["reference_id"], build_id))
    ]
    return out


@app.get("/api/factories")
def factories(c: sqlite3.Connection = Depends(conn)):
    facs = {r["id"]: {**dict(r), "aliases": [], "builds": []} for r in c.execute("SELECT * FROM factory ORDER BY name")}
    for alias, fid in c.execute("SELECT alias, factory_id FROM factory_alias"):
        if alias != facs[fid]["name"]:
            facs[fid]["aliases"].append(alias)
    for b in _build_summaries(c):
        facs[b["factory_id"]]["builds"].append({k: b[k] for k in ("id", "reference_id", "family", "version", "label", "tier", "score", "status", "open_defects", "claims")})
    for f in facs.values():
        current = [b for b in f["builds"] if b["status"] == "current" and b["score"] is not None]
        f["avg_score"] = round(sum(b["score"] for b in current) / len(current), 2) if current else None
        f["references"] = sorted({b["reference_id"] for b in f["builds"]})
        f["tier_counts"] = {t: sum(1 for b in current if b["tier"] == t) for t, _ in scoring.TIERS}
        f["findings"] = sum(b.get("claims") or 0 for b in f["builds"])
        # One model and nothing but a guide mention: shown in the "niche" section until evidence arrives.
        f["niche"] = len(f["builds"]) <= 1 and f["findings"] == 0
    return sorted(facs.values(), key=lambda f: (f["avg_score"] is None, -(f["avg_score"] or 0)))


@app.get("/api/factories/{factory_id}")
def factory(factory_id: str, c: sqlite3.Connection = Depends(conn)):
    row = c.execute("SELECT * FROM factory WHERE id = ?", (factory_id,)).fetchone()
    if not row:
        raise HTTPException(404)
    out = dict(row)
    out["aliases"] = [r[0] for r in c.execute("SELECT alias FROM factory_alias WHERE factory_id = ? AND alias != ?", (factory_id, out["name"]))]
    out["builds"] = _build_summaries(c, "b.factory_id = ?", (factory_id,))
    out["reputation"] = [dict(r) for r in c.execute(
        """
        SELECT substr(p.posted_at, 1, 4) || '-Q' || ((CAST(substr(p.posted_at, 6, 2) AS INTEGER) + 2) / 3) AS period,
               ROUND(AVG(5 + 2.5 * cl.sentiment), 2) AS score, COUNT(*) AS n,
               ROUND(100.0 * AVG(cl.kind = 'defect'), 1) AS defect_rate
        FROM claim cl JOIN post p ON p.id = cl.post_id JOIN build b ON b.id = cl.build_id
        WHERE b.factory_id = ? GROUP BY period ORDER BY period
        """,
        (factory_id,),
    )]
    out["events"] = [dict(r) for r in c.execute(
        "SELECT e.*, s.name AS source FROM event e LEFT JOIN source s ON s.id = e.source_id WHERE e.factory_id = ? ORDER BY occurred_at DESC LIMIT 40",
        (factory_id,),
    )]
    return out


@app.get("/api/feed")
def feed(c: sqlite3.Connection = Depends(conn)):
    latest, previous = _as_of(c)
    events = [dict(r) for r in c.execute(
        """
        SELECT e.*, f.name AS factory, b.reference_id, b.version, s.name AS source, s.kind AS source_kind
        FROM event e LEFT JOIN factory f ON f.id = e.factory_id LEFT JOIN build b ON b.id = e.build_id
        LEFT JOIN source s ON s.id = e.source_id
        ORDER BY e.occurred_at DESC LIMIT 24
        """
    )]
    _label_rows(c, events)
    defects = [dict(r) for r in c.execute(
        """
        SELECT d.id, d.title, d.aspect, d.severity, d.status, d.build_id, b.reference_id, b.version, f.name AS factory,
               COUNT(cl.id) AS reports, MAX(p.posted_at) AS last_seen
        FROM defect d JOIN build b ON b.id = d.build_id JOIN factory f ON f.id = b.factory_id
        JOIN claim cl ON cl.defect_id = d.id JOIN post p ON p.id = cl.post_id
        WHERE d.status != 'fixed' AND b.status = 'current'
        GROUP BY d.id HAVING last_seen >= date(?, '-120 days')
        ORDER BY d.severity DESC, reports DESC LIMIT 12
        """,
        (latest,),
    )]
    _label_rows(c, defects)
    order = {t: i for i, (t, _) in enumerate(scoring.TIERS)}
    movers = [
        b for b in _build_summaries(c, "b.status = 'current'")
        if b["tier"] and b["prev_tier"] and b["tier"] != b["prev_tier"]
    ]
    movers.sort(key=lambda b: order[b["tier"]] - order[b["prev_tier"]])
    top = sorted((b for b in _build_summaries(c, "b.status = 'current'") if b["lower"] is not None), key=lambda b: -b["lower"])[:6]
    return {"events": events, "defects": defects, "movers": movers[:10], "top": top}


PIVOT_DIMS = {
    "brand": "r.brand",
    "factory": "f.name",
    "reference": "b.reference_id",
    "family": "r.family",
    "aspect": "cl.aspect",
    "version": "COALESCE(NULLIF(b.version, ''), 'standard')",
    "release": "COALESCE(cl.release, 'not stated')",
    "status": "b.status",
    "source": "s.name",
    "source_kind": "s.kind",
    "evidence": "cl.evidence",
    "kind": "cl.kind",
    "year": "substr(p.posted_at, 1, 4)",
    "quarter": "substr(p.posted_at, 1, 4) || '-Q' || ((CAST(substr(p.posted_at, 6, 2) AS INTEGER) + 2) / 3)",
}
PIVOT_MEASURES = {
    "score": "ROUND(AVG(5 + 2.5 * cl.sentiment), 2)",
    "claims": "COUNT(*)",
    "defect_rate": "ROUND(100.0 * AVG(cl.kind = 'defect'), 1)",
    "praise_rate": "ROUND(100.0 * AVG(cl.kind = 'praise'), 1)",
}
PIVOT_FILTERS = {"brand": "r.brand", "family": "r.family", "factory": "b.factory_id", "reference": "b.reference_id", "status": "b.status", "source_kind": "s.kind", "aspect": "cl.aspect"}


@app.get("/api/pivot")
def pivot(
    rows: str = "factory",
    cols: str | None = "aspect",
    measure: str = "score",
    brand: list[str] = Query(default=[]),
    family: list[str] = Query(default=[]),
    factory: list[str] = Query(default=[]),
    reference: list[str] = Query(default=[]),
    status: list[str] = Query(default=[]),
    source_kind: list[str] = Query(default=[]),
    aspect: list[str] = Query(default=[]),
    c: sqlite3.Connection = Depends(conn),
):
    if rows not in PIVOT_DIMS or (cols and cols not in PIVOT_DIMS) or measure not in PIVOT_MEASURES:
        raise HTTPException(400, "unknown dimension or measure")
    filters = {"brand": brand, "family": family, "factory": factory, "reference": reference, "status": status, "source_kind": source_kind, "aspect": aspect}
    where, params = ["1=1"], []
    for key, values in filters.items():
        if values:
            where.append(f"{PIVOT_FILTERS[key]} IN ({','.join('?' * len(values))})")
            params.extend(values)
    base = f"""
        FROM claim cl JOIN post p ON p.id = cl.post_id JOIN source s ON s.id = p.source_id
        JOIN build b ON b.id = cl.build_id JOIN factory f ON f.id = b.factory_id JOIN reference r ON r.id = b.reference_id
        WHERE {' AND '.join(where)}
    """
    m = PIVOT_MEASURES[measure]
    r_expr = PIVOT_DIMS[rows]
    c_expr = PIVOT_DIMS[cols] if cols else "'All'"
    cells = [dict(x) for x in c.execute(f"SELECT {r_expr} AS r, {c_expr} AS c, {m} AS v, COUNT(*) AS n {base} GROUP BY 1, 2", params)]
    row_totals = {x["k"]: {"v": x["v"], "n": x["n"]} for x in c.execute(f"SELECT {r_expr} AS k, {m} AS v, COUNT(*) AS n {base} GROUP BY 1", params)}
    col_totals = {x["k"]: {"v": x["v"], "n": x["n"]} for x in c.execute(f"SELECT {c_expr} AS k, {m} AS v, COUNT(*) AS n {base} GROUP BY 1", params)}
    grand = c.execute(f"SELECT {m} AS v, COUNT(*) AS n {base}", params).fetchone()
    return {
        "rows": sorted(row_totals),
        "cols": sorted(col_totals),
        "cells": cells,
        "row_totals": row_totals,
        "col_totals": col_totals,
        "grand": dict(grand),
        "dims": list(PIVOT_DIMS),
        "measures": list(PIVOT_MEASURES),
    }


@app.get("/api/health")
def health():
    return {"ok": True}


@app.post("/api/capture")
def capture(payload: dict = Body(...), c: sqlite3.Connection = Depends(conn)):
    """A page the owner viewed in their own browser, sent by the extension."""
    from .ingest import ingest_rwi_page

    url, html = payload.get("url") or "", payload.get("html") or ""
    if "forum.replica-watch.info/threads/" not in url or len(html) < 1000:
        raise HTTPException(400, "expected an RWI thread page")
    if len(html) > 8_000_000:
        raise HTTPException(413, "page too large")
    try:
        return ingest_rwi_page(c, html, url, payload.get("captured_at"))
    except ValueError as e:
        raise HTTPException(422, str(e))


@app.post("/api/capture/photo")
async def capture_photo(request: Request, url: str, c: sqlite3.Connection = Depends(conn)):
    """Photo bytes fetched by the owner's browser during a capture."""
    from .ingest import MAX_PHOTO_BYTES, store_photo

    data = await request.body()
    if len(data) > MAX_PHOTO_BYTES:
        raise HTTPException(413, "photo too large")
    if not c.execute("SELECT 1 FROM photo WHERE url = ?", (url,)).fetchone():
        raise HTTPException(404, "unknown photo — capture its page first")
    try:
        return store_photo(c, url, data, request.headers.get("content-type", ""))
    except ValueError as e:
        raise HTTPException(415, str(e))


@app.post("/api/capture/mhtml")
async def capture_mhtml(request: Request, c: sqlite3.Connection = Depends(conn)):
    """A whole page as Chrome saved it, including the photos it displayed."""
    from .ingest import ingest_mhtml

    data = await request.body()
    if len(data) > 150_000_000:
        raise HTTPException(413, "capture too large")
    try:
        result = ingest_mhtml(c, data)
    except ValueError as e:
        raise HTTPException(422, str(e))
    return result


@app.get("/api/capture/setup")
def capture_setup():
    """Token for the extension's settings. Only reachable through ingress (HA login)."""
    return {"token": capture_token(), "port": int(os.environ.get("REPAGG_CAPTURE_PORT", "8766"))}


@app.get("/api/captures")
def captures(source: str = "all", status: str = "all", q: str = "", limit: int = 100, offset: int = 0, c: sqlite3.Connection = Depends(conn)):
    """Collected threads/channels with analysis state and a cost estimate. Filters: source (all|capture|reddit|rwg|telegram),
    status (all|new|queued|analysed|stale|failed), q (title search)."""
    from .extract import estimate

    where, params = ["1=1"], []
    if source == "capture":
        where.append("t.source_id = 'rwi'")
    elif source in ("reddit", "rwg"):
        where.append("t.source_id LIKE ?")
        params.append(f"{source}%")
    elif source == "telegram":
        where.append("t.source_id LIKE 'tg:%'")
    if status == "new":
        where.append("t.extracted_at IS NULL AND COALESCE(t.analyse_requested, 0) = 0")
    elif status == "queued":
        where.append("t.analyse_requested = 1")
    elif status == "analysed":
        where.append("t.extracted_at IS NOT NULL AND t.extract_error IS NULL AND t.extracted_at >= t.last_captured")
    elif status == "stale":
        where.append("t.extracted_at IS NOT NULL AND t.extracted_at < t.last_captured")
    elif status == "failed":
        where.append("t.extract_error IS NOT NULL")
    if q.strip():
        where.append("t.title LIKE ?")
        params.append(f"%{q.strip()}%")
    total = c.execute(f"SELECT COUNT(*) FROM thread t WHERE {' AND '.join(where)}", params).fetchone()[0]
    threads = [dict(r) for r in c.execute(
        f"""
        SELECT t.source_id, (SELECT kind FROM source WHERE id = t.source_id) AS source_kind,
               t.external_id AS thread_id, t.url, t.title, t.forum, t.pages, t.first_seen, t.last_captured,
               t.summary, t.extracted_at, t.extract_error, t.extract_cost, t.extract_model, t.builds,
               COALESCE(t.analyse_requested, 0) AS analyse_requested, COALESCE(t.extract_cursor, 0) AS cursor,
               (SELECT COUNT(DISTINCT p.page) FROM post p WHERE p.source_id = t.source_id AND p.thread_id = t.external_id) AS pages_captured,
               (SELECT COUNT(*) FROM post p WHERE p.source_id = t.source_id AND p.thread_id = t.external_id) AS posts,
               0 AS photos, 0 AS photos_stored
        FROM thread t WHERE {' AND '.join(where)} ORDER BY t.last_captured DESC LIMIT ? OFFSET ?
        """,
        (*params, max(1, min(limit, 500)), max(0, offset)),
    )]
    for t in threads:
        after = t.pop("cursor") if t["source_id"].startswith("tg:") else 0
        t["chars"], t["estimate_usd"] = estimate(c, t["source_id"], t["thread_id"], after)
    log = [dict(r) for r in c.execute("SELECT * FROM capture ORDER BY id DESC LIMIT 50")]
    return {"threads": threads, "total": total, "log": log}


@app.post("/api/analyse")
def analyse(payload: dict = Body(...), c: sqlite3.Connection = Depends(conn)):
    """Queue threads for analysis: {"items": [[source_id, thread_id], ...]} — only what the owner picks."""
    n = 0
    for source_id, thread_id in payload.get("items", [])[:500]:
        n += c.execute("UPDATE thread SET analyse_requested = 1, extract_error = NULL WHERE source_id = ? AND external_id = ?",
                       (source_id, thread_id)).rowcount
    c.commit()
    return {"queued": n}


@app.post("/api/captures/{source_id}/{thread_id}/delete-analysis")
def delete_analysis(source_id: str, thread_id: str, c: sqlite3.Connection = Depends(conn)):
    """Retroactively discard a thread's analysis and its impact on scores; the collected posts stay."""
    from .extract import delete_analysis as undo

    if not c.execute("SELECT 1 FROM thread WHERE source_id = ? AND external_id = ?", (source_id, thread_id)).fetchone():
        raise HTTPException(404)
    return undo(c, source_id, thread_id)


@app.post("/api/analyse/cancel")
def analyse_cancel(payload: dict = Body(...), c: sqlite3.Connection = Depends(conn)):
    n = 0
    for source_id, thread_id in payload.get("items", [])[:500]:
        n += c.execute("UPDATE thread SET analyse_requested = 0 WHERE source_id = ? AND external_id = ?", (source_id, thread_id)).rowcount
    c.commit()
    return {"cancelled": n}


@app.post("/api/captures/{source_id}/{thread_id}/extract")
def reextract(source_id: str, thread_id: str, c: sqlite3.Connection = Depends(conn)):
    """Queue a thread for (re-)analysis; the worker picks it up within ~2 minutes."""
    n = c.execute("UPDATE thread SET analyse_requested = 1, extract_error = NULL WHERE source_id = ? AND external_id = ?",
                  (source_id, thread_id)).rowcount
    c.commit()
    if not n:
        raise HTTPException(404)
    return {"queued": thread_id}


# ---- factory review (ingress only: the LAN gate rejects everything but captures) ----

def _admin(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except LookupError as e:
        raise HTTPException(404, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.get("/api/admin/factories")
def admin_factories(c: sqlite3.Connection = Depends(conn)):
    from . import admin

    return {"factories": admin.list_factories(c), "blocked": admin.blocked(c), "statuses": list(admin.STATUSES)}


@app.post("/api/admin/factories/{factory_id}")
def admin_update(factory_id: str, payload: dict = Body(...), c: sqlite3.Connection = Depends(conn)):
    from . import admin

    _admin(admin.update_factory, c, factory_id, name=payload.get("name"), status=payload.get("status"), reviewed=payload.get("reviewed"))
    return {"ok": True}


@app.post("/api/admin/factories/{factory_id}/aliases")
def admin_add_alias(factory_id: str, payload: dict = Body(...), c: sqlite3.Connection = Depends(conn)):
    from . import admin

    _admin(admin.add_alias, c, factory_id, payload.get("alias", ""))
    return {"ok": True}


@app.delete("/api/admin/factories/{factory_id}/aliases/{alias}")
def admin_remove_alias(factory_id: str, alias: str, c: sqlite3.Connection = Depends(conn)):
    from . import admin

    _admin(admin.remove_alias, c, factory_id, alias)
    return {"ok": True}


@app.post("/api/admin/factories/{factory_id}/merge")
def admin_merge(factory_id: str, payload: dict = Body(...), c: sqlite3.Connection = Depends(conn)):
    from . import admin

    return _admin(admin.merge, c, factory_id, payload.get("into", ""))


@app.delete("/api/admin/factories/{factory_id}")
def admin_discard(factory_id: str, c: sqlite3.Connection = Depends(conn)):
    from . import admin

    return _admin(admin.discard, c, factory_id)


@app.get("/api/admin/references")
def admin_references(c: sqlite3.Connection = Depends(conn)):
    from . import admin

    return {"references": admin.list_references(c), "models": admin.list_new_models(c)}


@app.post("/api/admin/models/{model_id:path}/confirm")
def admin_model_confirm(model_id: str, c: sqlite3.Connection = Depends(conn)):
    from . import admin

    admin.confirm_model(c, model_id)
    return {"ok": True}


@app.post("/api/admin/references/{ref_id:path}/alias")
def admin_ref_alias(ref_id: str, payload: dict = Body(...), c: sqlite3.Connection = Depends(conn)):
    from . import admin

    _admin(admin.add_reference_alias, c, ref_id, payload.get("alias", ""))
    return {"ok": True}


@app.post("/api/admin/references/{ref_id:path}/merge")
def admin_ref_merge(ref_id: str, payload: dict = Body(...), c: sqlite3.Connection = Depends(conn)):
    from . import admin

    return _admin(admin.merge_reference, c, ref_id, payload.get("into", ""))


@app.post("/api/admin/references/{ref_id:path}/discard")
def admin_ref_discard(ref_id: str, c: sqlite3.Connection = Depends(conn)):
    from . import admin

    return _admin(admin.discard_reference, c, ref_id)


@app.post("/api/admin/references/{ref_id:path}")
def admin_ref_update(ref_id: str, payload: dict = Body(...), c: sqlite3.Connection = Depends(conn)):
    from . import admin

    _admin(admin.update_reference, c, ref_id, brand=payload.get("brand"), name=payload.get("name"),
           family=payload.get("family"), reviewed=payload.get("reviewed"))
    return {"ok": True}


@app.delete("/api/admin/blocked/{alias}")
def admin_unblock(alias: str, c: sqlite3.Connection = Depends(conn)):
    from . import admin

    admin.unblock(c, alias)
    return {"ok": True}


# ---- Telegram (ingress only) -------------------------------------------------

def _tg(coro_fn, *args, timeout: float = 120):
    from . import telegram

    try:
        return telegram.service().run(coro_fn(telegram.service(), *args), timeout=timeout)
    except RuntimeError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(400, f"{type(e).__name__}: {e}")


@app.get("/api/telegram")
def telegram_status(c: sqlite3.Connection = Depends(conn)):
    from . import telegram

    return {**_tg(telegram.TelegramService.status, timeout=30), "channels": telegram.channels(c)}


@app.post("/api/telegram/login")
def telegram_login(payload: dict = Body(...)):
    from . import telegram

    return _tg(telegram.TelegramService.send_code, (payload.get("phone") or "").strip())


@app.post("/api/telegram/code")
def telegram_code(payload: dict = Body(...)):
    from . import telegram

    return _tg(telegram.TelegramService.submit_code, payload.get("code") or "")


@app.post("/api/telegram/password")
def telegram_password(payload: dict = Body(...)):
    from . import telegram

    return _tg(telegram.TelegramService.submit_password, payload.get("password") or "")


@app.post("/api/telegram/logout")
def telegram_logout():
    from . import telegram

    _tg(telegram.TelegramService.logout)
    return {"ok": True}


@app.post("/api/telegram/refresh")
def telegram_refresh():
    from . import telegram

    return {"channels": _tg(telegram.TelegramService.refresh_channels)}


@app.post("/api/telegram/channels/{channel_id}")
def telegram_follow(channel_id: int, payload: dict = Body(...), c: sqlite3.Connection = Depends(conn)):
    from . import telegram

    telegram.init_schema(c)
    n = c.execute("UPDATE tg_channel SET follow = ? WHERE id = ?", (1 if payload.get("follow") else 0, channel_id)).rowcount
    c.commit()
    if not n:
        raise HTTPException(404)
    return {"ok": True}


@app.post("/api/telegram/poll")
def telegram_poll():
    from . import telegram

    telegram.service().run_soon(telegram.service().poll())
    return {"started": True}


# ---- RWG collector (ingress only) ------------------------------------------------

@app.get("/api/rwg")
def rwg_status(c: sqlite3.Connection = Depends(conn)):
    from . import rwg

    return rwg.status(c)


@app.post("/api/rwg/resume")
def rwg_resume(c: sqlite3.Connection = Depends(conn)):
    from . import rwg

    rwg.resume(c)
    return {"ok": True}


@app.post("/api/rwg/run")
def rwg_run():
    from . import rwg

    threading.Thread(target=lambda: rwg.collector().run_cycle(), daemon=True).start()
    return {"started": True}


@app.get("/api/extraction")
def extraction_status():
    from .extract import settings

    from .extract import daily_budget, pending, spent_today

    cfg = settings()
    c = db.connect(DB_PATH)
    try:
        queued = len(pending(c, settle_seconds=0))
        spent = round(spent_today(c), 2)
    finally:
        c.close()
    from .extract import auto_analyse

    return {"configured": bool(cfg["api_key"]), "model": cfg["model"], "effort": cfg["effort"], "busy": _worker_state.get("busy"), "auto": auto_analyse(),
            "spent_today": spent, "daily_budget": daily_budget(), "queued": queued, "budget_reached": bool(_worker_state.get("budget_reached")),
            "worker_error": _worker_state.get("error")}


_worker_state: dict = {}


def _worker() -> None:
    """Analyse newly captured threads in the background, one at a time."""
    from .extract import daily_budget, extract_thread, pending, record_error, settings, spent_today

    while True:
        time.sleep(20)
        if not settings()["api_key"]:
            _worker_state["error"] = "no Anthropic API key configured"
            continue
        try:
            c = db.connect(DB_PATH)
            for source_id, thread_id in pending(c, settle_seconds=90):
                if spent_today(c) >= daily_budget():
                    _worker_state["budget_reached"] = True
                    break
                _worker_state["budget_reached"] = False
                _worker_state["busy"] = thread_id
                try:
                    r = extract_thread(c, thread_id, source_id)
                    print(f"[extract] {source_id}/{thread_id}: {r['claims']} claims, {r['events']} events, {len(r['builds'])} builds, ${r['cost_usd']}", flush=True)
                except Exception as e:  # keep the worker alive; the error is shown on the Captures page
                    record_error(c, source_id, thread_id, f"{type(e).__name__}: {e}")
                    print(f"[extract] {source_id}/{thread_id} failed: {e}", flush=True)
                finally:
                    _worker_state["busy"] = None
            c.close()
            _worker_state["error"] = None
        except Exception as e:
            _worker_state["error"] = f"{type(e).__name__}: {e}"
            print(f"[extract] worker error: {e}", flush=True)


# Apply schema changes/migrations once at startup, before serving requests.
_c = db.connect(DB_PATH)
db.init(_c)
_c.close()

if os.environ.get("REPAGG_WORKER", "1") != "0":
    threading.Thread(target=_worker, name="extract-worker", daemon=True).start()
    from . import telegram as _telegram

    _telegram.service()  # polls followed channels once logged in
    from . import rwg as _rwg

    _rwg.collector()  # does nothing unless collectors.rwg is enabled and the VPN route verifies


PHOTO_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/photos", StaticFiles(directory=PHOTO_DIR), name="photos")
if STATIC_DIR.exists():
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="site")
