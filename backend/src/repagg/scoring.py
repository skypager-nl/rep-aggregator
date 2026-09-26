"""Turns claims into per-aspect scores and tiers.

Each claim maps sentiment (-2..2) onto a 0..10 value and carries a weight:

    weight = source trust x author reputation x evidence x recency

Scores are hierarchical Bayesian averages: a build's pooled score is shrunk
toward its prior -- the community guide's rating when the build is in the
baseline (see guide.py), else PRIOR_MEAN -- and each aspect is shrunk toward
that pooled score. So a
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


def shrunk(values: list[tuple[float, float]], prior: float = PRIOR_MEAN, prior_weight: float = PRIOR_WEIGHT) -> tuple[float, float, int]:
    """(value, weight) pairs -> (score, lower bound, n), shrunk toward `prior` held with `prior_weight`."""
    sw = sum(w for _, w in values)
    if sw == 0:
        return prior, prior - Z * PRIOR_SD / math.sqrt(prior_weight), 0
    mean = (prior_weight * prior + sum(v * w for v, w in values)) / (prior_weight + sw)
    var = (prior_weight * PRIOR_SD**2 + sum(w * (v - mean) ** 2 for v, w in values)) / (prior_weight + sw)
    n_eff = sw**2 / sum(w * w for _, w in values)
    se = math.sqrt(var / (prior_weight + n_eff))
    return mean, mean - Z * se, len(values)


def baselines(conn: sqlite3.Connection) -> dict[str, tuple[float, float]]:
    """Guide-derived starting points per build: {build_id: (prior mean, prior weight)}."""
    try:
        return {r[0]: (r[1], r[2]) for r in conn.execute("SELECT build_id, prior_mean, prior_weight FROM baseline")}
    except sqlite3.OperationalError:  # table not created yet
        return {}


OLDER_RELEASE = 0.5   # a finding about V2 once V3 is out
FIXED_DEFECT = 0.2    # a defect a later release fixed: history, barely counts


def release_factor(release, current, defect_status, fixed_in, release_key) -> float:
    """Findings count fully for the current release (or when no release was named); less for
    superseded releases; defects fixed by a later release barely count."""
    f = 1.0
    if release and current and release_key(release) < release_key(current):
        f *= OLDER_RELEASE
    if defect_status == "fixed":
        if not fixed_in or not current or release_key(fixed_in) <= release_key(current):
            f *= FIXED_DEFECT
    return f


def tier_for(lower: float) -> str:
    return next(t for t, cutoff in TIERS if lower >= cutoff)


def compute(conn: sqlite3.Connection, as_of: date) -> int:
    """Recompute score + tier tables using only claims posted on or before `as_of`."""
    key = as_of.isoformat()
    conn.execute("DELETE FROM score WHERE as_of = ?", (key,))
    conn.execute("DELETE FROM tier WHERE as_of = ?", (key,))

    rows = conn.execute(
        """
        SELECT c.build_id, c.aspect, c.sentiment, c.evidence, p.posted_at, c.release,
               d.status AS defect_status, d.fixed_in_version,
               s.trust, COALESCE(a.reputation, 1.0) AS rep
        FROM claim c
        JOIN post p   ON p.id = c.post_id
        JOIN source s ON s.id = p.source_id
        LEFT JOIN author a ON a.id = p.author_id
        LEFT JOIN defect d ON d.id = c.defect_id
        JOIN build b  ON b.id = c.build_id
        WHERE p.posted_at <= ? AND (b.released IS NULL OR b.released <= ?)
        """,
        (key + "T23:59:59", key),
    ).fetchall()

    from .versions import current_releases, release_key

    current = current_releases(conn)
    by_aspect: dict[str, dict[str, list[tuple[float, float]]]] = defaultdict(lambda: defaultdict(list))
    for r in rows:
        w = r["trust"] * r["rep"] * EVIDENCE_WEIGHT[r["evidence"]] * recency(r["posted_at"], as_of)
        w *= release_factor(r["release"], current.get(r["build_id"]), r["defect_status"], r["fixed_in_version"], release_key)
        by_aspect[r["build_id"]][r["aspect"]].append((claim_value(r["sentiment"]), w))

    base = baselines(conn)
    released = {r[0] for r in conn.execute("SELECT id FROM build WHERE released IS NULL OR released <= ?", (key,))}
    for build_id in base:
        if build_id in released:
            by_aspect.setdefault(build_id, defaultdict(list))  # guide-rated versions score even without findings

    overall: dict[str, tuple[float, float, float]] = {}
    for build_id, aspects in by_aspect.items():
        everything = [vw for vals in aspects.values() for vw in vals]
        prior, prior_w = base.get(build_id, (PRIOR_MEAN, PRIOR_WEIGHT))
        pooled, pooled_lo, _ = shrunk(everything, prior=prior, prior_weight=prior_w)
        total = lower = 0.0
        for aspect, _, weight in ASPECTS:
            vals = aspects.get(aspect, [])
            # An aspect nobody commented on inherits the version's overall estimate and uncertainty.
            s, lo, n = shrunk(vals, prior=pooled) if vals else (pooled, pooled_lo, 0)
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
