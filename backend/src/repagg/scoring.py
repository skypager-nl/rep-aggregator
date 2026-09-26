"""Turns claims into per-aspect scores and tiers.

Each claim maps sentiment (-2..2) onto a 0..10 value and carries a weight:

    weight = source trust x author reputation x evidence x recency

Scores are hierarchical Bayesian averages: a build's pooled score is shrunk
toward PRIOR_MEAN, and each aspect is shrunk toward that pooled score. So a
build with three glowing posts can't outrank one with two hundred solid ones,
and a rarely-discussed aspect inherits the build's overall reputation rather
than a generic default. Tiers are
assigned on the *lower* bound, which rewards consensus over hype.
"""

import math
import sqlite3
from collections import defaultdict
from datetime import date

ASPECTS: list[tuple[str, str, float]] = [
    # id, label, weight in overall score
    ("dial", "Dial", 0.20),
    ("movement", "Movement", 0.18),
    ("bezel", "Bezel", 0.14),
    ("case", "Case", 0.14),
    ("bracelet", "Bracelet", 0.12),
    ("crystal", "Crystal & date", 0.09),
    ("lume", "Lume", 0.07),
    ("crown", "Crown & tube", 0.06),
]
ASPECT_WEIGHT = {a: w for a, _, w in ASPECTS}

EVIDENCE_WEIGHT = {"opinion": 1.0, "photo": 1.6, "measurement": 2.0, "timegrapher": 2.0}
HALF_LIFE_DAYS = 540
PRIOR_MEAN = 6.0
PRIOR_WEIGHT = 1.5  # in claim-weight units; a typical claim weighs ~0.5-1.5
PRIOR_SD = 2.0
Z = 1.0  # ~one-sided 84% bound; conservative without being punishing

TIERS = [("S", 7.8), ("A", 7.0), ("B", 6.2), ("C", -math.inf)]


def claim_value(sentiment: float) -> float:
    return 5.0 + 2.5 * sentiment


def recency(posted_at: str, as_of: date) -> float:
    age = (as_of - date.fromisoformat(posted_at[:10])).days
    return 0.5 ** (max(age, 0) / HALF_LIFE_DAYS)


def shrunk(values: list[tuple[float, float]], prior: float = PRIOR_MEAN) -> tuple[float, float, int]:
    """(value, weight) pairs -> (score, lower bound, n), shrunk toward `prior`."""
    sw = sum(w for _, w in values)
    if sw == 0:
        return prior, prior - Z * PRIOR_SD / math.sqrt(PRIOR_WEIGHT), 0
    mean = (PRIOR_WEIGHT * prior + sum(v * w for v, w in values)) / (PRIOR_WEIGHT + sw)
    var = (PRIOR_WEIGHT * PRIOR_SD**2 + sum(w * (v - mean) ** 2 for v, w in values)) / (PRIOR_WEIGHT + sw)
    n_eff = sw**2 / sum(w * w for _, w in values)
    se = math.sqrt(var / (PRIOR_WEIGHT + n_eff))
    return mean, mean - Z * se, len(values)


def tier_for(lower: float) -> str:
    return next(t for t, cutoff in TIERS if lower >= cutoff)


def compute(conn: sqlite3.Connection, as_of: date) -> int:
    """Recompute score + tier tables using only claims posted on or before `as_of`."""
    key = as_of.isoformat()
    conn.execute("DELETE FROM score WHERE as_of = ?", (key,))
    conn.execute("DELETE FROM tier WHERE as_of = ?", (key,))

    rows = conn.execute(
        """
        SELECT c.build_id, c.aspect, c.sentiment, c.evidence, p.posted_at,
               s.trust, COALESCE(a.reputation, 1.0) AS rep
        FROM claim c
        JOIN post p   ON p.id = c.post_id
        JOIN source s ON s.id = p.source_id
        LEFT JOIN author a ON a.id = p.author_id
        JOIN build b  ON b.id = c.build_id
        WHERE p.posted_at <= ? AND (b.released IS NULL OR b.released <= ?)
        """,
        (key + "T23:59:59", key),
    ).fetchall()

    by_aspect: dict[str, dict[str, list[tuple[float, float]]]] = defaultdict(lambda: defaultdict(list))
    for r in rows:
        w = r["trust"] * r["rep"] * EVIDENCE_WEIGHT[r["evidence"]] * recency(r["posted_at"], as_of)
        by_aspect[r["build_id"]][r["aspect"]].append((claim_value(r["sentiment"]), w))

    overall: dict[str, tuple[float, float, float]] = {}
    for build_id, aspects in by_aspect.items():
        everything = [vw for vals in aspects.values() for vw in vals]
        pooled, _, _ = shrunk(everything)
        total = lower = 0.0
        for aspect, _, weight in ASPECTS:
            s, lo, n = shrunk(aspects.get(aspect, []), prior=pooled)
            conn.execute("INSERT INTO score VALUES (?, ?, ?, ?, ?, ?)", (build_id, key, aspect, round(s, 3), round(lo, 3), n))
            total += weight * s
            lower += weight * lo
        n = len(everything)
        conn.execute("INSERT INTO score VALUES (?, ?, 'overall', ?, ?, ?)", (build_id, key, round(total, 3), round(lower, 3), n))
        overall[build_id] = (total, lower, _controversy(everything))

    ref_of = dict(conn.execute("SELECT id, reference_id FROM build"))
    by_ref: dict[str, list[str]] = defaultdict(list)
    for build_id in overall:
        by_ref[ref_of[build_id]].append(build_id)
    for builds in by_ref.values():
        builds.sort(key=lambda b: overall[b][1], reverse=True)
        for rank, build_id in enumerate(builds, 1):
            _, lo, contro = overall[build_id]
            conn.execute("INSERT INTO tier VALUES (?, ?, ?, ?, ?)", (build_id, key, tier_for(lo), rank, round(contro, 3)))

    conn.commit()
    return len(overall)


def _controversy(values: list[tuple[float, float]]) -> float:
    """Weighted spread of opinion, normalised: 0 = consensus, 1 = split down the middle."""
    sw = sum(w for _, w in values)
    if sw == 0:
        return 0.0
    mean = sum(v * w for v, w in values) / sw
    sd = math.sqrt(sum(w * (v - mean) ** 2 for v, w in values) / sw)
    return min(sd / 5.0, 1.0)
