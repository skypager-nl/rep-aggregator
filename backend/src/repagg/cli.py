import argparse
import shutil
from datetime import date
from pathlib import Path

from . import db, scoring
from .config import DB_PATH, PHOTO_DIR


def main() -> None:
    parser = argparse.ArgumentParser(prog="repagg")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init", help="create the database schema")
    sub.add_parser("demo", help="replace the database with synthetic demo data")
    sub.add_parser("score", help="recompute scores and tiers as of today")
    photo = sub.add_parser("ref-photo", help="attach a photo of the genuine reference")
    photo.add_argument("reference")
    photo.add_argument("file")
    photo.add_argument("--view", default="front", choices=["front", "angle", "dial", "bezel", "lume", "side", "caseback", "clasp", "wrist"])
    photo.add_argument("--credit")
    photo.add_argument("--source-url")
    imp = sub.add_parser("import-photos", help="register a folder of <REF>-<view> genuine photos")
    imp.add_argument("dir")
    imp.add_argument("--credit", default="© Rolex")
    serve = sub.add_parser("serve", help="run the web app")
    serve.add_argument("--host", default="0.0.0.0")
    serve.add_argument("--port", type=int, default=8099)
    args = parser.parse_args()

    if args.cmd == "serve":
        import uvicorn

        uvicorn.run("repagg.api:app", host=args.host, port=args.port, log_level="info")
        return

    conn = db.connect(DB_PATH)
    db.init(conn)
    if args.cmd == "demo":
        from . import demo

        demo.seed(conn)
        print(f"demo data written to {DB_PATH}")
    elif args.cmd == "ref-photo":
        attach_ref_photo(conn, args.reference, Path(args.file), args.view, args.credit, args.source_url)
        conn.commit()
    elif args.cmd == "import-photos":
        # Files named <REFERENCE>-<view>.<ext>, e.g. 126610LN-front.webp
        n = 0
        for f in sorted(Path(args.dir).glob("*.*")):
            ref, _, view = f.stem.rpartition("-")
            if ref and conn.execute("SELECT 1 FROM reference WHERE id = ?", (ref,)).fetchone():
                attach_ref_photo(conn, ref, f, view, args.credit, None, quiet=True)
                n += 1
        conn.commit()
        print(f"registered {n} photos from {args.dir}")
    elif args.cmd == "score":
        today = date.today()
        previous = db.get_meta(conn, "latest_as_of")
        n = scoring.compute(conn, today)
        if previous and previous != today.isoformat():
            db.set_meta(conn, "previous_as_of", previous)
        db.set_meta(conn, "latest_as_of", today.isoformat())
        conn.commit()
        print(f"scored {n} builds as of {today}")


def attach_ref_photo(conn, reference: str, src: Path, view: str, credit: str | None, source_url: str | None, quiet: bool = False) -> None:
    if not conn.execute("SELECT 1 FROM reference WHERE id = ?", (reference,)).fetchone():
        raise SystemExit(f"unknown reference {reference}")
    rel = Path("genuine") / f"{reference}-{view}{src.suffix.lower()}"
    dest = PHOTO_DIR / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    if not dest.exists() or not dest.samefile(src):
        shutil.copyfile(src, dest)
    conn.execute("DELETE FROM reference_photo WHERE reference_id = ? AND view = ?", (reference, view))
    conn.execute(
        "INSERT INTO reference_photo(reference_id, view, path, credit, source_url) VALUES (?, ?, ?, ?, ?)",
        (reference, view, rel.as_posix(), credit, source_url),
    )
    if not quiet:
        print(f"attached {rel}")


if __name__ == "__main__":
    main()
