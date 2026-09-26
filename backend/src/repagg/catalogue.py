"""Seed catalogue of genuine references across brands (the "gen" side).

Only well-established catalogue facts; size/calibre are left empty where not
certain. The analysis adds references it finds in threads (flagged for review),
so this is a starting point, not a limit. Idempotent: existing rows are kept.
"""

import sqlite3

# brand, family, reference id, display name, case mm, calibre, aliases
CATALOGUE: list[tuple[str, str, str, str, float | None, str | None, list[str]]] = [
    # Omega
    ("Omega", "Speedmaster", "310.30.42.50.01.001", "Speedmaster Moonwatch Professional", 42, "Cal. 3861", ["Moonwatch", "Speedy", "Speedmaster Pro", "Speedmaster Moonwatch"]),
    ("Omega", "Seamaster Diver 300M", "210.30.42.20.01.001", "Seamaster Diver 300M (black)", 42, "Cal. 8800", ["SMP", "Seamaster 300", "Diver 300M"]),
    ("Omega", "Seamaster Diver 300M", "210.30.42.20.03.001", "Seamaster Diver 300M (blue)", 42, "Cal. 8800", ["Blue SMP"]),
    ("Omega", "Seamaster Planet Ocean", "215.30.44.21.01.001", "Seamaster Planet Ocean 600M", 43.5, "Cal. 8900", ["Planet Ocean", "PO"]),
    ("Omega", "Seamaster Aqua Terra", "220.10.41.21.03.004", "Seamaster Aqua Terra 150M", 41, "Cal. 8900", ["Aqua Terra", "AT"]),
    # Tudor
    ("Tudor", "Black Bay", "M79030N-0001", "Black Bay Fifty-Eight (black)", 39, "MT5402", ["BB58", "Black Bay 58", "Fifty-Eight"]),
    ("Tudor", "Black Bay", "M79030B-0001", "Black Bay Fifty-Eight (blue)", 39, "MT5402", ["BB58 Blue", "Blue BB58"]),
    ("Tudor", "Black Bay", "M79830RB-0001", "Black Bay GMT", 41, "MT5652", ["BB GMT", "Tudor Pepsi"]),
    ("Tudor", "Pelagos", "M25600TN-0001", "Pelagos", 42, "MT5612", ["Pelagos"]),
    # Audemars Piguet
    ("Audemars Piguet", "Royal Oak", "15500ST.OO.1220ST.01", "Royal Oak Selfwinding 41", 41, "Cal. 4302", ["15500", "RO 41", "Royal Oak 41"]),
    ("Audemars Piguet", "Royal Oak", "15202ST.OO.1240ST.01", "Royal Oak “Jumbo” Extra-Thin", 39, "Cal. 2121", ["15202", "Jumbo"]),
    ("Audemars Piguet", "Royal Oak", "16202ST.OO.1240ST.01", "Royal Oak “Jumbo” Extra-Thin (50th)", 39, "Cal. 7121", ["16202", "New Jumbo"]),
    ("Audemars Piguet", "Royal Oak Offshore", "26470ST.OO.A027CA.01", "Royal Oak Offshore Chronograph 42", 42, None, ["26470", "ROO", "Offshore"]),
    # Patek Philippe
    ("Patek Philippe", "Nautilus", "5711/1A-010", "Nautilus (blue)", 40, "Cal. 26-330 S C", ["5711", "Nautilus"]),
    ("Patek Philippe", "Nautilus", "5711/1A-014", "Nautilus (olive green)", 40, "Cal. 26-330 S C", ["5711 Green", "Olive Nautilus"]),
    ("Patek Philippe", "Nautilus", "5712/1A-001", "Nautilus Moon Phase", 40, "Cal. 240 PS IRM C LU", ["5712"]),
    ("Patek Philippe", "Aquanaut", "5167A-001", "Aquanaut", 40, "Cal. 324 S C", ["5167", "Aquanaut"]),
    # Cartier
    ("Cartier", "Santos", "WSSA0018", "Santos de Cartier, large", None, "Cal. 1847 MC", ["Santos Large", "Santos"]),
    # Panerai
    ("Panerai", "Luminor", "PAM01312", "Luminor Marina 44", 44, "P.9010", ["PAM1312", "PAM 1312", "Luminor Marina"]),
    # IWC
    ("IWC", "Portugieser Chronograph", "IW371605", "Portugieser Chronograph", 41, "Cal. 69355", ["Portugieser Chrono", "IW3716"]),
    ("IWC", "Big Pilot", "IW501001", "Big Pilot's Watch", 46.2, "Cal. 52110", ["Big Pilot", "BP"]),
    # Vacheron Constantin
    ("Vacheron Constantin", "Overseas", "4500V/110A-B128", "Overseas Self-winding (blue)", 41, "Cal. 5100", ["Overseas", "4500V"]),
    # Hublot
    ("Hublot", "Big Bang", "411.NX.1170.RX", "Big Bang Unico Titanium 45", 45, "HUB1242", ["Big Bang Unico", "BBU"]),
    # Richard Mille
    ("Richard Mille", "RM 011", "RM 011", "RM 011 Flyback Chronograph", None, None, ["RM011", "RM11"]),
    ("Richard Mille", "RM 035", "RM 035", "RM 035", None, None, ["RM035", "RM35"]),
]


def seed(conn: sqlite3.Connection) -> int:
    """Brands, models (each with a model-level reference so model-only mentions have a home),
    then the specific references, linked to their model."""
    from .brands import BRANDS, slug
    from .models import MODELS

    for name, aliases in BRANDS.items():
        bid = slug(name)
        conn.execute("INSERT OR IGNORE INTO brand(id, name) VALUES (?, ?)", (bid, name))
        conn.executemany("INSERT OR IGNORE INTO brand_alias VALUES (?, ?)", [(a, bid) for a in {name, *aliases}])
    for brand, models in MODELS.items():
        bid = slug(brand)
        for model, aliases in models.items():
            mid = f"{bid}/{slug(model)}"
            conn.execute("INSERT OR IGNORE INTO model(id, brand_id, name) VALUES (?, ?, ?)", (mid, bid, model))
            conn.executemany("INSERT OR IGNORE INTO model_alias VALUES (?, ?)", [(a, mid) for a in {model, *aliases}])
            ensure_model_reference(conn, brand, model, mid)
    added = 0
    for brand, family, ref, name, size, cal, aliases in CATALOGUE:
        cur = conn.execute(
            "INSERT OR IGNORE INTO reference(id, brand, family, name, size_mm, movement) VALUES (?, ?, ?, ?, ?, ?)",
            (ref, brand, family, name, size, cal),
        )
        added += cur.rowcount
        conn.executemany("INSERT OR IGNORE INTO reference_alias VALUES (?, ?)", [(a, ref) for a in [ref, *aliases]])
    # Link every specific reference (catalogue, Rolex set, auto-added) to its brand's model by family name.
    for rid, brand, family in conn.execute("SELECT id, brand, family FROM reference WHERE COALESCE(kind, 'reference') = 'reference' AND model_id IS NULL").fetchall():
        m = find_model(conn, brand, family)
        if m:
            conn.execute("UPDATE reference SET model_id = ?, kind = 'reference' WHERE id = ?", (m, rid))
    conn.execute("UPDATE reference SET kind = 'reference' WHERE kind IS NULL")
    conn.commit()
    return added


def ensure_model_reference(conn: sqlite3.Connection, brand: str, model: str, model_id: str) -> str:
    """The model-level entry: where findings land when a thread names the model but no reference."""
    rid = f"{brand} {model}"
    conn.execute(
        "INSERT OR IGNORE INTO reference(id, brand, family, name, kind, model_id) VALUES (?, ?, ?, ?, 'model', ?)",
        (rid, brand, model, f"{model} (any reference)", model_id),
    )
    conn.execute("INSERT OR IGNORE INTO reference_alias VALUES (?, ?)", (rid, rid))
    return rid


def canonical_brand(conn: sqlite3.Connection, name: str) -> str | None:
    row = conn.execute("SELECT b.name FROM brand_alias a JOIN brand b ON b.id = a.brand_id WHERE a.alias = ?", (name.strip(),)).fetchone()
    return row[0] if row else None


def find_model(conn: sqlite3.Connection, brand: str, name: str) -> str | None:
    """Model id for a brand + model name/alias (case-insensitive), or None."""
    if not brand or not name:
        return None
    row = conn.execute(
        """SELECT m.id FROM model m JOIN brand b ON b.id = m.brand_id JOIN model_alias ma ON ma.model_id = m.id
           WHERE b.name = ? AND ma.alias = ?""",
        (brand, name.strip()),
    ).fetchone()
    return row[0] if row else None
