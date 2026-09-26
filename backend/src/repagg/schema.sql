-- Canonical entities ---------------------------------------------------------

CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS reference (
    id          TEXT PRIMARY KEY,          -- '126610LN'
    brand       TEXT NOT NULL,             -- 'Rolex'
    family      TEXT NOT NULL,             -- 'Submariner'
    name        TEXT NOT NULL,             -- 'Submariner Date'
    size_mm     REAL,
    material    TEXT,
    movement    TEXT,                      -- genuine calibre, e.g. 'Cal. 3235'
    year_intro  INTEGER,
    dial_color  TEXT,                      -- hex, used for renders
    bezel_color TEXT,                      -- hex or 'a/b' for two-tone bezels
    metal_color TEXT
);

CREATE TABLE IF NOT EXISTS factory (
    id       TEXT PRIMARY KEY,             -- 'clean'
    name     TEXT NOT NULL,                -- 'Clean'
    status   TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'closed', 'rebranded', 'unknown')),
    founded  INTEGER,
    notes    TEXT
);

-- Deterministic alias resolution: never let the LLM guess these.
CREATE TABLE IF NOT EXISTS factory_alias (
    alias      TEXT PRIMARY KEY COLLATE NOCASE,
    factory_id TEXT NOT NULL REFERENCES factory(id)
);

CREATE TABLE IF NOT EXISTS reference_alias (
    alias        TEXT PRIMARY KEY COLLATE NOCASE,
    reference_id TEXT NOT NULL REFERENCES reference(id)
);

-- A Build is what actually gets ranked: Reference x Factory x Version.
CREATE TABLE IF NOT EXISTS build (
    id           TEXT PRIMARY KEY,         -- 'clean-126610ln-v4'
    reference_id TEXT NOT NULL REFERENCES reference(id),
    factory_id   TEXT NOT NULL REFERENCES factory(id),
    version      TEXT NOT NULL,            -- 'V4'
    movement     TEXT,                     -- clone calibre, e.g. 'VR3235'
    released     TEXT,                     -- ISO date
    status       TEXT NOT NULL DEFAULT 'current' CHECK (status IN ('current', 'superseded', 'discontinued')),
    UNIQUE (reference_id, factory_id, version)
);

-- Raw material ---------------------------------------------------------------

CREATE TABLE IF NOT EXISTS source (
    id           TEXT PRIMARY KEY,         -- 'rwi', 'reddit:RepTime', 'tg:dealer_x'
    kind         TEXT NOT NULL CHECK (kind IN ('forum', 'reddit', 'blog', 'telegram')),
    name         TEXT NOT NULL,
    url          TEXT,
    trust        REAL NOT NULL DEFAULT 1.0 -- multiplier on claim weight
);

CREATE TABLE IF NOT EXISTS author (
    id          INTEGER PRIMARY KEY,
    source_id   TEXT NOT NULL REFERENCES source(id),
    handle      TEXT NOT NULL,
    joined      TEXT,
    post_count  INTEGER,
    reputation  REAL NOT NULL DEFAULT 1.0, -- derived multiplier, 0.3 .. 2.0
    UNIQUE (source_id, handle)
);

CREATE TABLE IF NOT EXISTS post (
    id           INTEGER PRIMARY KEY,
    source_id    TEXT NOT NULL REFERENCES source(id),
    external_id  TEXT NOT NULL,
    author_id    INTEGER REFERENCES author(id),
    url          TEXT,
    thread_title TEXT,
    posted_at    TEXT NOT NULL,
    body         TEXT,
    raw_path     TEXT,                     -- compressed raw HTML/JSON on disk
    fetched_at   TEXT NOT NULL,
    extracted_at TEXT,                     -- NULL = not yet run through the LLM
    UNIQUE (source_id, external_id)
);

-- Extracted knowledge --------------------------------------------------------

CREATE TABLE IF NOT EXISTS claim (
    id          INTEGER PRIMARY KEY,
    post_id     INTEGER NOT NULL REFERENCES post(id),
    build_id    TEXT NOT NULL REFERENCES build(id),
    aspect      TEXT NOT NULL,             -- see scoring.ASPECTS
    kind        TEXT NOT NULL CHECK (kind IN ('defect', 'praise', 'neutral')),
    sentiment   REAL NOT NULL CHECK (sentiment BETWEEN -2 AND 2),
    severity    INTEGER NOT NULL DEFAULT 0 CHECK (severity BETWEEN 0 AND 3),
    evidence    TEXT NOT NULL DEFAULT 'opinion' CHECK (evidence IN ('opinion', 'photo', 'measurement', 'timegrapher')),
    defect_id   INTEGER REFERENCES defect(id),
    quote       TEXT,
    model       TEXT,                      -- extraction model id, for re-runs
    created_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS claim_build ON claim(build_id, aspect);

CREATE TABLE IF NOT EXISTS defect (
    id               INTEGER PRIMARY KEY,
    build_id         TEXT NOT NULL REFERENCES build(id),
    aspect           TEXT NOT NULL,
    title            TEXT NOT NULL,
    description      TEXT,
    severity         INTEGER NOT NULL DEFAULT 1 CHECK (severity BETWEEN 1 AND 3),
    status           TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'fixed', 'disputed')),
    fixed_in_version TEXT
);

CREATE TABLE IF NOT EXISTS photo (
    id        INTEGER PRIMARY KEY,
    post_id   INTEGER REFERENCES post(id),
    build_id  TEXT REFERENCES build(id),
    aspect    TEXT,                        -- 'dial', 'bezel', 'wrist', ... tagged by vision model
    path      TEXT NOT NULL,               -- relative to photo dir; 'render:<focus>' for demo renders
    width     INTEGER,
    height    INTEGER,
    sha256    TEXT UNIQUE
);

CREATE TABLE IF NOT EXISTS price_point (
    id          INTEGER PRIMARY KEY,
    build_id    TEXT NOT NULL REFERENCES build(id),
    source_id   TEXT NOT NULL REFERENCES source(id),
    dealer      TEXT,
    price_usd   REAL NOT NULL,
    observed_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS event (
    id          INTEGER PRIMARY KEY,
    kind        TEXT NOT NULL CHECK (kind IN ('release', 'closure', 'rebrand', 'restock', 'price', 'defect')),
    factory_id  TEXT REFERENCES factory(id),
    build_id    TEXT REFERENCES build(id),
    title       TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    source_id   TEXT REFERENCES source(id)
);

-- Computed (rebuilt by `repagg score`) ----------------------------------------

CREATE TABLE IF NOT EXISTS score (
    build_id  TEXT NOT NULL REFERENCES build(id),
    as_of     TEXT NOT NULL,
    aspect    TEXT NOT NULL,               -- aspect name, or 'overall'
    score     REAL NOT NULL,               -- 0..10, shrunk toward prior
    lower     REAL NOT NULL,               -- conservative bound used for tiering
    n         INTEGER NOT NULL,
    PRIMARY KEY (build_id, as_of, aspect)
);

CREATE TABLE IF NOT EXISTS tier (
    build_id  TEXT NOT NULL REFERENCES build(id),
    as_of     TEXT NOT NULL,
    tier      TEXT NOT NULL,               -- S A B C
    rank      INTEGER NOT NULL,            -- within reference
    controversy REAL NOT NULL DEFAULT 0,   -- spread of opinion, 0..1
    PRIMARY KEY (build_id, as_of)
);

-- QC verdicts (r/RepTimeQC style "GL or RL?" threads) --------------------------

CREATE TABLE IF NOT EXISTS qc_verdict (
    post_id    INTEGER PRIMARY KEY REFERENCES post(id),
    build_id   TEXT NOT NULL REFERENCES build(id),
    verdict    TEXT NOT NULL CHECK (verdict IN ('GL', 'RL', 'mixed')),
    gl_votes   INTEGER NOT NULL DEFAULT 0,   -- comments voting green light
    rl_votes   INTEGER NOT NULL DEFAULT 0,   -- comments voting red light
    flaws      TEXT,                         -- JSON list of aspects called out
    decided_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS qc_build ON qc_verdict(build_id);

-- Incremental collection: fetch new items forward, backfill history slowly ----

CREATE TABLE IF NOT EXISTS crawl_state (
    source_id     TEXT PRIMARY KEY REFERENCES source(id),
    newest_seen   TEXT,                      -- forward cursor (timestamp / id)
    oldest_seen   TEXT,                      -- backfill cursor; walks back each run
    backfill_done INTEGER NOT NULL DEFAULT 0,
    last_run      TEXT,
    notes         TEXT
);

-- Photos of the genuine reference (the "gen" in gen-vs-rep) --------------------

CREATE TABLE IF NOT EXISTS reference_photo (
    id           INTEGER PRIMARY KEY,
    reference_id TEXT NOT NULL REFERENCES reference(id),
    view         TEXT NOT NULL DEFAULT 'front',  -- front, side, caseback, clasp, wrist, dial
    path         TEXT NOT NULL,                  -- relative to photo dir
    credit       TEXT,
    source_url   TEXT,
    UNIQUE (reference_id, view, path)
);

-- Browser captures (owner's own visits, sent by the extension) -----------------

CREATE TABLE IF NOT EXISTS thread (
    source_id     TEXT NOT NULL REFERENCES source(id),
    external_id   TEXT NOT NULL,
    url           TEXT NOT NULL,
    title         TEXT NOT NULL,
    forum         TEXT,
    pages         INTEGER NOT NULL DEFAULT 1,
    first_seen    TEXT NOT NULL,
    last_captured TEXT NOT NULL,
    PRIMARY KEY (source_id, external_id)
);

CREATE TABLE IF NOT EXISTS capture (
    id            INTEGER PRIMARY KEY,
    source_id     TEXT NOT NULL REFERENCES source(id),
    thread_id     TEXT NOT NULL,
    page          INTEGER NOT NULL,
    url           TEXT NOT NULL,
    captured_at   TEXT NOT NULL,
    posts         INTEGER NOT NULL,
    new_posts     INTEGER NOT NULL,
    photos        INTEGER NOT NULL,
    raw_path      TEXT,
    status        TEXT NOT NULL DEFAULT 'ok',
    error         TEXT
);
