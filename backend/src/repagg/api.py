"""HTTP API + static site. Served behind Home Assistant ingress, so every URL the
frontend uses is relative -- ingress mounts us under /api/hassio_ingress/<token>/."""

import sqlite3
from collections import defaultdict
from collections.abc import Iterator

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.staticfiles import StaticFiles

from . import db, scoring
from .config import DB_PATH, PHOTO_DIR, STATIC_DIR

app = FastAPI(title="repagg", docs_url="/api/docs", openapi_url="/api/openapi.json")


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
               r.family, r.name AS reference_name, r.dial_color, r.bezel_color, r.metal_color,
               (SELECT path FROM reference_photo rp WHERE rp.reference_id = r.id ORDER BY rp.view != 'front', rp.id LIMIT 1) AS ref_photo,
               t.tier, t.rank, t.controversy, pt.tier AS prev_tier,
               so.score, so.lower, so.n AS claims,
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
    for b in builds:
        b["aspects"] = aspects.get(b["id"], {})
        b["price"] = prices.get(b["id"])
    return builds


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
        "factories": [dict(r) for r in c.execute("SELECT id, name, status FROM factory ORDER BY name")],
        "sources": [dict(r) for r in c.execute("SELECT id, kind, name, trust FROM source ORDER BY trust DESC")],
    }


@app.get("/api/references")
def references(c: sqlite3.Connection = Depends(conn)):
    refs = [dict(r) for r in c.execute(
        """SELECT r.*, (SELECT path FROM reference_photo rp WHERE rp.reference_id = r.id ORDER BY rp.view != 'front', rp.id LIMIT 1) AS ref_photo
           FROM reference r ORDER BY family, id""")]
    by_ref = defaultdict(list)
    for b in _build_summaries(c):
        by_ref[b["reference_id"]].append(b)
    for r in refs:
        builds = by_ref[r["id"]]
        r["builds"] = [{k: b[k] for k in ("id", "factory", "factory_id", "version", "tier", "rank", "score", "status", "claims")} for b in builds]
        r["claims"] = sum(b["claims"] or 0 for b in builds)
    return refs


@app.get("/api/references/{ref_id}")
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
    out["prices"] = [dict(r) for r in c.execute(
        "SELECT dealer, price_usd AS price, observed_at FROM price_point WHERE build_id = ? ORDER BY observed_at", (build_id,))]
    out["quotes"] = [dict(r) for r in c.execute(
        """
        SELECT cl.aspect, cl.kind, cl.sentiment, cl.evidence, cl.quote, p.posted_at, p.url, p.thread_title,
               s.name AS source, s.kind AS source_kind, a.handle, a.reputation
        FROM claim cl
        JOIN post p ON p.id = cl.post_id
        JOIN source s ON s.id = p.source_id
        LEFT JOIN author a ON a.id = p.author_id
        WHERE cl.build_id = ?
        ORDER BY p.posted_at DESC LIMIT 80
        """,
        (build_id,),
    )]
    out["qc"] = [dict(r) for r in c.execute(
        """
        SELECT q.verdict, q.gl_votes, q.rl_votes, q.flaws, q.decided_at, p.thread_title, p.url, s.name AS source
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
        {k: b[k] for k in ("id", "factory", "factory_id", "version", "tier", "rank", "score", "status")}
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
        facs[b["factory_id"]]["builds"].append({k: b[k] for k in ("id", "reference_id", "family", "version", "tier", "score", "status", "open_defects")})
    for f in facs.values():
        current = [b for b in f["builds"] if b["status"] == "current" and b["score"] is not None]
        f["avg_score"] = round(sum(b["score"] for b in current) / len(current), 2) if current else None
        f["references"] = sorted({b["reference_id"] for b in f["builds"]})
        f["tier_counts"] = {t: sum(1 for b in current if b["tier"] == t) for t, _ in scoring.TIERS}
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
    order = {t: i for i, (t, _) in enumerate(scoring.TIERS)}
    movers = [
        b for b in _build_summaries(c, "b.status = 'current'")
        if b["tier"] and b["prev_tier"] and b["tier"] != b["prev_tier"]
    ]
    movers.sort(key=lambda b: order[b["tier"]] - order[b["prev_tier"]])
    top = sorted((b for b in _build_summaries(c, "b.status = 'current'") if b["lower"] is not None), key=lambda b: -b["lower"])[:6]
    return {"events": events, "defects": defects, "movers": movers[:10], "top": top}


PIVOT_DIMS = {
    "factory": "f.name",
    "reference": "b.reference_id",
    "family": "r.family",
    "aspect": "cl.aspect",
    "version": "b.version",
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
PIVOT_FILTERS = {"family": "r.family", "factory": "b.factory_id", "reference": "b.reference_id", "status": "b.status", "source_kind": "s.kind", "aspect": "cl.aspect"}


@app.get("/api/pivot")
def pivot(
    rows: str = "factory",
    cols: str | None = "aspect",
    measure: str = "score",
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
    filters = {"family": family, "factory": factory, "reference": reference, "status": status, "source_kind": source_kind, "aspect": aspect}
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


PHOTO_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/photos", StaticFiles(directory=PHOTO_DIR), name="photos")
if STATIC_DIR.exists():
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="site")
