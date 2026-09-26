"""Canonical brands, with the spellings dealers use as aliases.

Sources (2026-09-26, owner-requested): the brand menus of theonewatches.ws and
trustytime168.io. Dealer names are often deliberately disguised ("ROLXX",
"XHANEL", "DIFFANY & CO"); those map to the real brand here. Menu entries that
are not brands (specials, boxes, pens, factory names) are left out.
"""

# canonical name: dealer spellings / common shorthand
BRANDS: dict[str, list[str]] = {
    "A. Lange & Söhne": ["A. LANGE & SOHNE", "ALANGE & SOHNE", "Lange", "ALS"],
    "Audemars Piguet": ["AUDEMARS PIGUET", "A. PIGUET", "AP"],
    "Bell & Ross": ["BELL & ROSS", "B&R"],
    "Blancpain": ["BLANCPAIN"],
    "Breguet": ["BREGUET"],
    "Breitling": ["BREITLING"],
    "Bulgari": ["BVLGARI", "Bvlgari"],
    "Cartier": ["CARTIER"],
    "Chanel": ["CHANEL", "XHANEL"],
    "Chopard": ["CHOPARD"],
    "Corum": ["CORUM"],
    "Dior": ["DIOR", "CHRISTIAN DIOR"],
    "Franck Muller": ["FRANCK MULLER", "FM"],
    "Girard-Perregaux": ["GIRARD-PERREGAUX", "GIRARD PERREGAUX", "GP"],
    "Glashütte Original": ["GLASHUTTE", "Glashutte"],
    "Graham": ["GRAHAM"],
    "Grand Seiko": ["GRAND SEIKO", "GS"],
    "Hamilton": ["HAMILTON"],
    "Hermès": ["HERMES", "Hermes"],
    "Hublot": ["HUBLOT"],
    "Hysek": ["HYSEK"],
    "HYT": ["HYT"],
    "IWC": ["IWC", "IWC Schaffhausen"],
    "Jacob & Co.": ["JACOB & CO.", "JACOB & CO"],
    "Jaeger-LeCoultre": ["JAEGER LeCOULTRE", "JAEGER LE COULTRE", "JLC"],
    "Jaquet Droz": ["JAQUET DROZ"],
    "JeanRichard": ["JEANRICHARD"],
    "Konstantin Chaykin": ["KONSTANTIN CHAYKIN"],
    "Linde Werdelin": ["LINDE WERDELIN"],
    "Longines": ["LONGINES"],
    "Louis Vuitton": ["JOUIS VUITTON", "LV"],
    "Maurice Lacroix": ["MAURICE & LACROIX", "MAURICE LACROIX"],
    "MB&F": ["MB & F", "MBF"],
    "Mido": ["MIDO"],
    "Montblanc": ["MONT BLANC", "MONTBLANC"],
    "Movado": ["MOVADO"],
    "Nomos Glashütte": ["NOMOS", "Nomos"],
    "Nubeo": ["NUBEO"],
    "Omega": ["OMEGA"],
    "Oris": ["ORIS"],
    "Panerai": ["PANERAI", "Officine Panerai"],
    "Parmigiani Fleurier": ["PARMIGIANI FLEURIER", "Parmigiani"],
    "Patek Philippe": ["PATEK PHILIPPE", "PP", "Patek"],
    "Paul Picot": ["PAUL PICOT"],
    "Perrelet": ["PERRELET"],
    "Piaget": ["PIAGET"],
    "Porsche Design": ["PORSCHE DESIGN"],
    "Prada": ["PRADA"],
    "Rado": ["RADO"],
    "Raymond Weil": ["RAYMOND WEIL"],
    "Richard Mille": ["RICHARD MILLE", "RM"],
    "Roger Dubuis": ["ROGER DUBUIS", "RD"],
    "Rolex": ["ROLEX", "ROLXX", "RLX"],
    "Romain Jerome": ["ROMAIN JEROME"],
    "Seiko": ["SEIKO"],
    "SevenFriday": ["SEVENFRIDAY"],
    "Sinn": ["SINN"],
    "Swarovski": ["SWAROVSKI"],
    "TAG Heuer": ["TAG HEUER", "Tag"],
    "Tiffany & Co.": ["DIFFANY & CO", "TIFFANY & CO", "Tiffany"],
    "Tissot": ["TISSOT"],
    "Tudor": ["TUDOR"],
    "U-Boat": ["U-BOAT"],
    "Ulysse Nardin": ["ULYSSE NARDIN", "UN"],
    "Vacheron Constantin": ["VACHERON CONSTANTIN", "VACH. CONSTANTINE", "VC"],
    "Van Cleef & Arpels": ["VAN CLEEF & ARPELS", "VAN CLEEF", "VCA"],
    "Versace": ["VERSACE"],
    "Welder": ["WELDER"],
    "Zenith": ["ZENITH"],
}


def slug(name: str) -> str:
    import re
    import unicodedata

    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", ascii_name.lower()).strip("-")
