"""One-off, owner-approved reachability probe for RWI (2026-09-26).

At most two GETs through the proxy, 15 s apart, after the egress check.
Stops at the first sign of a block or challenge. No retries, no workarounds.
"""

import json
import time
from datetime import datetime, timezone
from pathlib import Path

from .net import EgressError, proxied_client, rwi_proxy_url, safe_proxy_label, verify_egress

BASE = "https://forum.replica-watch.info"
TARGETS = [
    ("robots", "/robots.txt", "robots.txt"),
    ("rss", "/forums/replica-watch-general-discussion.103/index.rss", "rss.xml"),
]
KEEP_HEADERS = ("server", "content-type", "cf-ray", "cf-mitigated", "cf-cache-status", "retry-after", "x-robots-tag")


def looks_challenged(status: int, headers, body: str) -> bool:
    if headers.get("cf-mitigated") == "challenge":
        return True
    if status in (403, 429, 503):
        return True
    return any(m in body[:20000] for m in ("Just a moment...", "cf-chl-", "challenge-platform/h/", "Attention Required!"))


def run(out: Path, only: set[str] | None = None) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    report: dict = {"started": datetime.now(timezone.utc).isoformat(), "requests": []}
    url = rwi_proxy_url()
    try:
        report["exit_ip"] = verify_egress(url)
        report["proxy"] = safe_proxy_label(url)
    except EgressError as e:
        report["blocked_before_start"] = str(e)
        return _write(out, report)

    with proxied_client(url) as client:
        targets = [t for t in TARGETS if not only or t[0] in only]
        for i, (name, path, filename) in enumerate(targets):
            if i:
                time.sleep(15)
            entry = {"name": name, "url": BASE + path}
            try:
                r = client.get(BASE + path)
                body = r.text
                entry.update(
                    status=r.status_code,
                    headers={k: r.headers[k] for k in KEEP_HEADERS if k in r.headers},
                    bytes=len(r.content),
                    challenged=looks_challenged(r.status_code, r.headers, body),
                    saved=filename,
                )
                (out / filename).write_text(body)
            except Exception as e:
                entry.update(error=f"{type(e).__name__}: {e}", challenged=None)
            report["requests"].append(entry)
            if entry.get("challenged") or "error" in entry:
                report["stopped_early"] = True
                break
    return _write(out, report)


def _write(out: Path, report: dict) -> dict:
    report["finished"] = datetime.now(timezone.utc).isoformat()
    (out / "report.json").write_text(json.dumps(report, indent=2))
    return report
