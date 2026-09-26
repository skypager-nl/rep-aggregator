"""Synthetic dataset for building the UI before any scraping happens.

Reference specs are real Rolex catalogue facts. Everything else -- builds,
versions, scores, defects, prices, handles, quotes -- is invented, and the
database is flagged `dataset=demo` so the UI says so on every page.
"""

import json
import math
import random
import sqlite3
from datetime import date, timedelta

from . import db, scoring

TODAY = date(2026, 9, 26)

REFERENCES = [
    # id, family, name, size, material, movement, year, dial, bezel, metal
    ("126610LN", "Submariner", "Submariner Date", 41, "Oystersteel", "Cal. 3235", 2020, "#0d0d0f", "#111114", "#c9ccd1"),
    ("126610LV", "Submariner", "Submariner Date “Starbucks”", 41, "Oystersteel", "Cal. 3235", 2020, "#0d0d0f", "#1f5a3a", "#c9ccd1"),
    ("124060", "Submariner", "Submariner", 41, "Oystersteel", "Cal. 3230", 2020, "#0d0d0f", "#111114", "#c9ccd1"),
    ("116610LN", "Submariner", "Submariner Date (prev. gen)", 40, "Oystersteel", "Cal. 3135", 2010, "#0d0d0f", "#111114", "#c9ccd1"),
    ("126710BLRO", "GMT-Master II", "GMT-Master II “Pepsi”", 40, "Oystersteel", "Cal. 3285", 2018, "#0d0d0f", "#1d3f8a/#a3202b", "#c9ccd1"),
    ("126710BLNR", "GMT-Master II", "GMT-Master II “Batman”", 40, "Oystersteel", "Cal. 3285", 2019, "#0d0d0f", "#1d3f8a/#141416", "#c9ccd1"),
    ("126720VTNR", "GMT-Master II", "GMT-Master II “Sprite”", 40, "Oystersteel", "Cal. 3285", 2022, "#0d0d0f", "#1f5a3a/#141416", "#c9ccd1"),
    ("126500LN", "Daytona", "Cosmograph Daytona", 40, "Oystersteel", "Cal. 4131", 2023, "#ecebe6", "#111114", "#c9ccd1"),
    ("116500LN", "Daytona", "Cosmograph Daytona (prev. gen)", 40, "Oystersteel", "Cal. 4130", 2016, "#ecebe6", "#111114", "#c9ccd1"),
    ("126334", "Datejust", "Datejust 41", 41, "Oystersteel & white gold", "Cal. 3235", 2017, "#23407a", "fluted", "#c9ccd1"),
    ("124270", "Explorer", "Explorer 36", 36, "Oystersteel", "Cal. 3230", 2021, "#0d0d0f", "smooth", "#c9ccd1"),
    ("226570", "Explorer II", "Explorer II “Polar”", 42, "Oystersteel", "Cal. 3285", 2021, "#ecebe6", "#c9ccd1", "#c9ccd1"),
    ("126600", "Sea-Dweller", "Sea-Dweller", 43, "Oystersteel", "Cal. 3235", 2017, "#0d0d0f", "#111114", "#c9ccd1"),
    ("136660", "Deepsea", "Deepsea", 44, "Oystersteel & RLX titanium", "Cal. 3235", 2022, "#0d0d0f", "#111114", "#c9ccd1"),
    ("124300", "Oyster Perpetual", "Oyster Perpetual 41", 41, "Oystersteel", "Cal. 3230", 2020, "#2c5e8f", "smooth", "#c9ccd1"),
    ("228238", "Day-Date", "Day-Date 40", 40, "18 ct yellow gold", "Cal. 3255", 2015, "#c8b07a", "fluted", "#d4af6a"),
]

REFERENCE_ALIASES = {
    "126610LN": ["Sub Date", "126610", "LN", "Sub 41"],
    "126610LV": ["Starbucks", "Cermit", "LV"],
    "124060": ["No Date Sub", "ND Sub", "NDSub"],
    "116610LN": ["Sub 40", "116610"],
    "126710BLRO": ["Pepsi", "BLRO"],
    "126710BLNR": ["Batman", "Batgirl", "BLNR"],
    "126720VTNR": ["Sprite", "Lefty", "VTNR"],
    "126500LN": ["Daytona", "Panda", "New Daytona"],
    "116500LN": ["Old Daytona", "116500"],
    "126334": ["DJ41", "Datejust 41"],
    "124270": ["Explorer", "Explorer 36", "Ex1"],
    "226570": ["Polar", "Ex2", "Explorer II"],
    "126600": ["SD43", "Sea Dweller", "Red SD"],
    "136660": ["Deepsea", "DSSD"],
    "124300": ["OP41", "Oyster Perpetual"],
    "228238": ["Day Date", "DD40", "President"],
}

FACTORIES = [
    # id, name, status, founded, aliases
    ("clean", "Clean", "active", 2019, ["CF", "C Factory", "Clean Factory"]),
    ("vsf", "VSF", "active", 2017, ["VS", "VS Factory"]),
    ("ew", "EW", "active", 2018, ["EWF", "EW Factory"]),
    ("zf", "ZF", "active", 2016, ["ZF Factory"]),
    ("arf", "ARF", "active", 2016, ["AR", "AR Factory"]),
    ("bt", "BT", "active", 2019, ["BTF", "BT Factory"]),
    ("gm", "GM", "active", 2018, ["GMF", "GM Factory"]),
    ("cplus", "C+", "active", 2022, ["C+ Factory", "CPlus"]),
    ("qf", "QF", "active", 2020, ["QF Factory"]),
    ("aps", "APS", "active", 2021, ["APSF", "APS Factory"]),
    ("noob", "Noob", "closed", 2010, ["N Factory", "N"]),
]

MOVEMENTS = {
    "Cal. 3235": {"clean": "DD3235", "vsf": "VR3235", "ew": "E3235", "zf": "SH3235", "arf": "A3235", "cplus": "C3235", "aps": "A3235"},
    "Cal. 3230": {"clean": "DD3230", "vsf": "VR3230", "ew": "E3230", "zf": "SH3230", "arf": "A3230", "aps": "A3230"},
    "Cal. 3135": {"clean": "3135 clone", "vsf": "VS3135", "arf": "A3135", "noob": "A3135", "zf": "3135 clone"},
    "Cal. 3285": {"clean": "DD3285", "vsf": "VR3285", "gm": "SH3285", "arf": "A3285", "cplus": "C3285"},
    "Cal. 4131": {"clean": "4131 clone", "bt": "SA4131", "qf": "Q4131"},
    "Cal. 4130": {"clean": "4130 clone", "bt": "SA4130", "qf": "Q4130", "noob": "7750 mod"},
    "Cal. 3255": {"ew": "E3255", "gm": "SH3255", "aps": "A3255"},
}

# Which factories make which reference (demo mapping), with number of versions.
LINEUP = {
    "126610LN": {"clean": 4, "vsf": 3, "ew": 2, "zf": 1, "aps": 1},
    "126610LV": {"clean": 3, "vsf": 2, "ew": 1},
    "124060": {"clean": 2, "vsf": 2, "ew": 1},
    "116610LN": {"arf": 2, "noob": 2, "vsf": 1, "zf": 1},
    "126710BLRO": {"clean": 3, "gm": 2, "vsf": 2, "cplus": 1},
    "126710BLNR": {"clean": 2, "gm": 2, "vsf": 1},
    "126720VTNR": {"clean": 1, "gm": 1, "cplus": 1},
    "126500LN": {"clean": 2, "bt": 1, "qf": 1},
    "116500LN": {"clean": 3, "bt": 2, "noob": 1, "qf": 1},
    "126334": {"clean": 2, "vsf": 1, "ew": 1},
    "124270": {"clean": 1, "vsf": 1},
    "226570": {"clean": 1, "gm": 1},
    "126600": {"clean": 1, "arf": 1},
    "136660": {"aps": 1, "clean": 1},
    "124300": {"clean": 1, "vsf": 1, "ew": 1},
    "228238": {"gm": 1, "ew": 1, "aps": 1},
}

# Rough house style per factory: (base quality, per-aspect strengths).
HOUSE = {
    "clean": (7.8, {"dial": 0.5, "bezel": 0.4, "case": 0.3}),
    "vsf": (7.6, {"movement": 0.7, "case": 0.2, "dial": -0.2}),
    "ew": (7.5, {"dial": 0.4, "case": 0.4, "movement": -0.3}),
    "zf": (6.8, {"bracelet": -0.4}),
    "arf": (7.0, {"bracelet": 0.3}),
    "bt": (7.4, {"movement": 0.6, "dial": 0.2}),
    "gm": (7.3, {"bezel": 0.5, "lume": 0.2}),
    "cplus": (7.1, {"movement": -0.4, "bezel": 0.2}),
    "qf": (6.6, {"movement": -0.5}),
    "aps": (7.2, {"case": 0.3, "crystal": -0.4}),
    "noob": (6.2, {"movement": -0.6, "lume": -0.4}),
}

DEFECTS = {
    "bezel": ["Bezel insert misaligned at 12", "Loose bezel action / wobble", "Numeral font too heavy on 40 & 50", "Pip sits off-centre"],
    "dial": ["Crown coronet too wide", "Rehaut engraving misaligned", "Date font off on 6 & 9", "Dial print too bold"],
    "crystal": ["Cyclops ~2.0x instead of 2.5x", "AR coating too blue", "Laser-etched crown missing at 6"],
    "movement": ["Audible rotor noise", "Amplitude drop after ~6 months", "Date change not instantaneous", "Seconds hand stutter"],
    "case": ["Lug width off by ~0.2 mm", "Crown guards slightly thick", "Soft chamfers on lugs"],
    "bracelet": ["Clasp logo too shallow", "Glidelock clicks inconsistent", "End-link gaps"],
    "lume": ["Uneven lume on 12 triangle", "Lume cast too green"],
    "crown": ["Crown tube colour wrong", "Triplock dots misprinted"],
}

PRAISE = {
    "dial": ["Dial print is crisp under a loupe", "Applied markers look spot on", "Dial colour matches gen in daylight"],
    "bezel": ["Bezel action is tight, 120 clean clicks", "Ceramic insert colour is right", "Engraving depth looks gen"],
    "case": ["Case finishing is excellent, brushing is sharp", "Proportions sit right on the wrist"],
    "movement": ["Running +3 s/day after a month", "Timegrapher shows solid amplitude", "Smooth winding, no rotor noise"],
    "bracelet": ["Bracelet is solid, no rattle", "Glidelock feels like gen"],
    "crystal": ["Cyclops magnification is right", "Laser crown is visible where it should be"],
    "lume": ["Lume is bright and even", "Chromalight blue looks right"],
    "crown": ["Crown screws down smoothly", "Triplock dots are correct"],
}
NEUTRAL = ["Can't see a difference vs the previous version here", "Fine for the price", "Nothing to report on this"]

SOURCES = [
    # id, kind, name, trust, share of posts
    ("rwi", "forum", "RWI", 1.3, 0.40),
    ("reddit:RepTime", "reddit", "r/RepTime", 1.0, 0.22),
    ("reddit:RepTimeQC", "reddit", "r/RepTimeQC", 0.9, 0.16),
    ("reddit:Rep_Watch_World", "reddit", "r/Rep_Watch_World", 0.9, 0.06),
    ("reddit:repbuilds", "reddit", "r/repbuilds", 0.8, 0.03),
    ("reddit:vintagerepwatches", "reddit", "r/vintagerepwatches", 0.9, 0.02),
    ("reddit:retrotime", "reddit", "r/retrotime", 0.9, 0.02),
    ("blog:demo-a", "blog", "Demo blog A", 0.5, 0.04),
    ("tg:dealer-a", "telegram", "Dealer A (Telegram)", 0.6, 0.025),
    ("tg:dealer-b", "telegram", "Dealer B (Telegram)", 0.6, 0.025),
]
DEALERS = ["tg:dealer-a", "tg:dealer-b"]

SYL = ["tick", "tock", "rep", "crown", "sub", "dial", "lume", "bez", "oyst", "jub", "cal", "rotor", "gmt", "polar", "coro", "hk", "sea"]


def seed(conn: sqlite3.Connection) -> None:
    rng = random.Random(7)
    db.init(conn)
    for table in ("qc_verdict", "crawl_state", "tier", "score", "event", "price_point", "photo", "claim", "defect", "post", "author", "build",
                  "reference_alias", "factory_alias", "source", "factory", "meta"):
        conn.execute(f"DELETE FROM {table}")

    conn.executemany("INSERT OR IGNORE INTO reference VALUES (?, 'Rolex', ?, ?, ?, ?, ?, ?, ?, ?, ?)", REFERENCES)
    for ref, aliases in REFERENCE_ALIASES.items():
        conn.executemany("INSERT INTO reference_alias VALUES (?, ?)", [(a, ref) for a in aliases])
    for fid, name, status, founded, aliases in FACTORIES:
        conn.execute("INSERT INTO factory(id, name, status, founded) VALUES (?, ?, ?, ?)", (fid, name, status, founded))
        conn.executemany("INSERT INTO factory_alias VALUES (?, ?)", [(a, fid) for a in [name, *aliases]])
    conn.executemany("INSERT INTO source(id, kind, name, trust) VALUES (?, ?, ?, ?)", [s[:4] for s in SOURCES])

    authors = _authors(conn, rng)
    ref_info = {r[0]: r for r in REFERENCES}
    post_seq = 0

    for ref, lineup in LINEUP.items():
        _, _, _, _, _, movement, year, *_ = ref_info[ref]
        for fid, versions in lineup.items():
            base, strengths = HOUSE[fid]
            start = max(date(year, 1, 1), date(2019, 6, 1)) + timedelta(days=rng.randint(60, 400))
            if fid == "noob":
                start = date(2019, 3, 1)
            for v in range(1, versions + 1):
                released = start + timedelta(days=int((v - 1) * rng.randint(220, 420)))
                if released > TODAY - timedelta(days=45):
                    released = TODAY - timedelta(days=rng.randint(45, 120))
                build_id = f"{fid}-{ref.lower()}-v{v}"
                status = "current" if v == versions else "superseded"
                if fid == "noob":
                    status = "discontinued"
                conn.execute(
                    "INSERT INTO build VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (build_id, ref, fid, f"V{v}", MOVEMENTS.get(movement, {}).get(fid, "clone"), released.isoformat(), status),
                )
                quality = {
                    a: base + 0.4 + strengths.get(a, 0) + 0.3 * (v - 1) + rng.gauss(0, 0.45)
                    for a, _, _ in scoring.ASPECTS
                }
                defects = _defects(conn, rng, build_id, quality, v, versions)
                end = TODAY if status == "current" else min(TODAY, released + timedelta(days=700))
                popularity = {"126610LN": 2.2, "126710BLRO": 1.8, "126500LN": 1.6, "116500LN": 1.3}.get(ref, 1.0)
                n_posts = int(rng.randint(10, 32) * popularity * (1.3 if status == "current" else 0.8))
                for _ in range(n_posts):
                    post_seq += 1
                    _post(conn, rng, post_seq, build_id, ref, fid, v, released, end, quality, defects, authors)
                _prices(conn, rng, build_id, fid, ref, released, end)
                conn.execute(
                    "INSERT INTO event(kind, factory_id, build_id, title, occurred_at, source_id) VALUES ('release', ?, ?, ?, ?, ?)",
                    (fid, build_id, f"{dict((f[0], f[1]) for f in FACTORIES)[fid]} releases {ref} V{v}", released.isoformat(), rng.choice(DEALERS)),
                )

    conn.execute(
        "INSERT INTO event(kind, factory_id, title, occurred_at, source_id) VALUES ('closure', 'noob', 'Noob stops production (demo event)', '2021-11-02', 'rwi')"
    )
    for _ in range(8):
        b = conn.execute("SELECT id, factory_id, reference_id FROM build WHERE status = 'current' ORDER BY random() LIMIT 1").fetchone()
        when = TODAY - timedelta(days=rng.randint(2, 120))
        kind = rng.choice(["restock", "price"])
        title = f"{b['reference_id']} restocked at dealers" if kind == "restock" else f"{b['reference_id']} price moves ±$20"
        conn.execute(
            "INSERT INTO event(kind, factory_id, build_id, title, occurred_at, source_id) VALUES (?, ?, ?, ?, ?, ?)",
            (kind, b["factory_id"], b["id"], title, when.isoformat(), rng.choice(DEALERS)),
        )

    db.set_meta(conn, "dataset", "demo")
    conn.commit()

    previous = TODAY - timedelta(days=90)
    scoring.compute(conn, previous)
    scoring.compute(conn, TODAY)
    db.set_meta(conn, "latest_as_of", TODAY.isoformat())
    db.set_meta(conn, "previous_as_of", previous.isoformat())
    conn.commit()


def _authors(conn, rng) -> dict[str, list[int]]:
    out: dict[str, list[int]] = {}
    for sid, *_ in SOURCES:
        ids = []
        for i in range(40 if sid in ("rwi", "reddit:RepTime") else 12):
            handle = f"{rng.choice(SYL)}{rng.choice(SYL)}{rng.randint(1, 99)}" if not sid.startswith(("tg:", "blog:")) else sid.split(":")[1]
            joined = date(rng.randint(2012, 2025), rng.randint(1, 12), 1)
            posts = int(rng.paretovariate(1.2) * 40)
            rep = min(2.0, max(0.3, 0.5 + 0.4 * ((TODAY - joined).days / 1500) + 0.15 * (posts > 500)))
            cur = conn.execute(
                "INSERT OR IGNORE INTO author(source_id, handle, joined, post_count, reputation) VALUES (?, ?, ?, ?, ?)",
                (sid, handle, joined.isoformat(), posts, round(rep, 2)),
            )
            if cur.lastrowid:
                ids.append(cur.lastrowid)
            if sid.startswith(("tg:", "blog:")):
                break
        out[sid] = ids
    return out


def _defects(conn, rng, build_id, quality, v, versions) -> dict[str, int]:
    out = {}
    weakest = sorted(quality, key=quality.get)[: rng.randint(1, 3)]
    for aspect in weakest:
        if quality[aspect] > 8.4:
            continue
        title = rng.choice(DEFECTS[aspect])
        severity = 3 if quality[aspect] < 6.4 else 2 if quality[aspect] < 7.4 else 1
        fixed = v < versions and rng.random() < 0.6
        cur = conn.execute(
            "INSERT INTO defect(build_id, aspect, title, severity, status, fixed_in_version) VALUES (?, ?, ?, ?, ?, ?)",
            (build_id, aspect, title, severity, "fixed" if fixed else rng.choice(["open", "open", "disputed"]), f"V{v + 1}" if fixed else None),
        )
        out[aspect] = cur.lastrowid
    return out


def _post(conn, rng, seq, build_id, ref, fid, v, released, end, quality, defects, authors) -> None:
    sources = [s[0] for s in SOURCES]
    sid = rng.choices(sources, weights=[s[4] for s in SOURCES])[0]
    author = rng.choice(authors[sid])
    span = max((end - released).days, 1)
    posted = released + timedelta(days=int(span * rng.random() ** 0.8))
    factory = dict((f[0], f[1]) for f in FACTORIES)[fid]
    qc = sid == "reddit:RepTimeQC"
    title = f"GL or RL? {factory} {ref} V{v}" if qc else rng.choice([f"{factory} {ref} V{v} QC", f"Review: {factory} {ref} after {rng.randint(2, 18)} months",
                        f"{factory} vs others — {ref}", f"First impressions {factory} {ref}"])
    cur = conn.execute(
        "INSERT INTO post(source_id, external_id, author_id, url, thread_title, posted_at, body, fetched_at, extracted_at) "
        "VALUES (?, ?, ?, NULL, ?, ?, NULL, ?, ?)",
        (sid, f"demo-{seq}", author, title, posted.isoformat() + "T12:00:00", TODAY.isoformat(), TODAY.isoformat()),
    )
    post_id = cur.lastrowid
    flaws = []
    for aspect in rng.sample(list(quality), rng.randint(1, 3)):
        q = quality[aspect] + rng.gauss(0, 1.1)
        sentiment = max(-2.0, min(2.0, round((q - 5) / 2.5 * 2) / 2))
        defect_id = None
        if aspect in defects and rng.random() < 0.55:
            sentiment = min(sentiment, rng.choice([-0.5, -1.0, -1.5]))
            defect_id = defects[aspect]
        kind = "defect" if sentiment < 0 else "praise" if sentiment >= 1 else "neutral"
        if defect_id:
            quote = conn.execute("SELECT title FROM defect WHERE id = ?", (defect_id,)).fetchone()[0]
        elif kind == "praise":
            quote = rng.choice(PRAISE[aspect])
        elif kind == "defect":
            quote = rng.choice(DEFECTS[aspect])
        else:
            quote = rng.choice(NEUTRAL)
        evidence = rng.choices(["opinion", "photo", "measurement", "timegrapher"], weights=[5, 4, 1, 1 if aspect == "movement" else 0])[0]
        conn.execute(
            "INSERT INTO claim(post_id, build_id, aspect, kind, sentiment, severity, evidence, defect_id, quote, model, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'demo', ?)",
            (post_id, build_id, aspect, kind, sentiment, 0 if sentiment >= 0 else min(3, int(-sentiment + 0.5)),
             evidence, defect_id, quote, TODAY.isoformat()),
        )
        if sentiment < 0:
            flaws.append(aspect)
    if qc:
        mean_q = sum(quality.values()) / len(quality)
        p_gl = 1 / (1 + math.exp(-(mean_q - 7.2) * 1.6)) * (0.55 if flaws else 1.0)
        total = rng.randint(2, 16)
        gl = sum(rng.random() < p_gl for _ in range(total))
        share = gl / total
        verdict = "GL" if share >= 0.65 else "RL" if share <= 0.35 else "mixed"
        conn.execute(
            "INSERT INTO qc_verdict VALUES (?, ?, ?, ?, ?, ?, ?)",
            (post_id, build_id, verdict, gl, total - gl, json.dumps(flaws), (posted + timedelta(days=1)).isoformat()),
        )


def _prices(conn, rng, build_id, fid, ref, released, end) -> None:
    base = {"clean": 520, "vsf": 500, "ew": 480, "zf": 420, "arf": 430, "bt": 560, "gm": 470, "cplus": 450, "qf": 400, "aps": 520, "noob": 380}[fid]
    base += {"126500LN": 90, "116500LN": 60, "228238": 140, "136660": 60}.get(ref, 0)
    for dealer in DEALERS:
        price = base + rng.randint(-30, 30)
        d = max(released, TODAY - timedelta(days=540))
        while d <= end:
            price = max(300, price + rng.choice([-10, 0, 0, 0, 5, 10, 15]))
            conn.execute(
                "INSERT INTO price_point(build_id, source_id, dealer, price_usd, observed_at) VALUES (?, ?, ?, ?, ?)",
                (build_id, dealer, dealer.split(":")[1], price, d.isoformat()),
            )
            d += timedelta(days=30)
