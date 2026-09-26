"""Genuine reference photos from rolex.com's media CDN.

    python scripts/rolex_photos.py list       # HEAD-check every file, print sizes (downloads nothing)
    python scripts/rolex_photos.py download   # fetch slowly into data/photos/genuine/ and register them

Personal, private use only: the images are Rolex's copyright and the site sits
behind Home Assistant's login.
"""

import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "scripts" / "rolex_photos.tsv"
OUT = ROOT / "data" / "photos" / "genuine"
URL = "https://media.rolex.com/image/upload/q_auto/f_webp/t_v7/c_limit,w_1600/v1/a677b2c664f6/catalogue/2026/{view}/{model}"
VIEWS = {  # our view name -> Rolex catalogue folder
    "front": "upright-c",
    "angle": "upright-bba-with-shadow",
    "dial": "raw-dial-constant-size-with-shadow",
    "bezel": "bezel-constant-size-with-shadow",
    "lume": "luminescence",
}
UA = {"User-Agent": "Mozilla/5.0 (personal reference-photo fetch)"}


def entries():
    for line in MANIFEST.read_text().splitlines():
        if line and not line.startswith("#"):
            ref, model, desc = line.split("\t")
            yield ref, model, desc


def head(url: str) -> tuple[int, int]:
    req = urllib.request.Request(url, method="HEAD", headers=UA)
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status, int(r.headers.get("Content-Length", 0))
    except urllib.error.HTTPError as e:
        return e.code, 0


def main(cmd: str) -> None:
    total = count = 0
    for ref, model, desc in entries():
        row = []
        for view, folder in VIEWS.items():
            url = URL.format(view=folder, model=model)
            if cmd == "list":
                status, size = head(url)
                time.sleep(0.3)
                if status == 200:
                    total += size
                    count += 1
                    row.append(f"{view} {size // 1024}K")
                else:
                    row.append(f"{view} —")
            elif cmd == "download":
                dest = OUT / f"{ref}-{view}.webp"
                if dest.exists():
                    continue
                status, _ = head(url)
                if status != 200:
                    continue
                dest.parent.mkdir(parents=True, exist_ok=True)
                with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r:
                    dest.write_bytes(r.read())
                subprocess.run(
                    ["uv", "run", "--project", str(ROOT / "backend"), "repagg", "ref-photo", ref, str(dest), "--view", view,
                     "--credit", "© Rolex", "--source-url", f"https://www.rolex.com (model {model})"],
                    check=True, capture_output=True,
                )
                count += 1
                total += dest.stat().st_size
                print(f"  {dest.name}")
                time.sleep(1.5)
        if cmd == "list":
            print(f"{ref:<11} {model:<18} {desc:<24} {' · '.join(row)}")
    print(f"\n{count} files, {total / 1048576:.1f} MB")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "list")
