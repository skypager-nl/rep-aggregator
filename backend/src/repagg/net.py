"""Outbound HTTP.

Only the RWI crawler goes through the VPN proxy; everything else (Reddit, the
Claude API, photos) goes out directly. The proxied path fails closed: if the
proxy is missing, unreachable, or exits from the same address as home, the
crawler refuses to run -- it never falls back to a direct connection.
"""

import os
from urllib.parse import quote

import httpx

from .config import addon_options

IP_ECHO = "https://api.ipify.org"
USER_AGENT = "Mozilla/5.0 (compatible; RepIndex/0.1; personal, low-volume)"
TIMEOUT = httpx.Timeout(30.0, connect=15.0)


class EgressError(RuntimeError):
    """The proxied route isn't safe to use; the crawler must not run."""


def rwi_proxy_url() -> str | None:
    """socks5://user:pass@host:port, from env (dev) or the add-on's separate host/user/password fields."""
    if os.environ.get("REPAGG_RWI_PROXY"):
        return os.environ["REPAGG_RWI_PROXY"]
    opts = addon_options().get("rwi_proxy", {})
    host = (opts.get("host") or "").strip()
    if not host:
        return None
    if "://" not in host:
        host = f"socks5://{host}"
    user, password = opts.get("username") or "", opts.get("password") or ""
    if not user:
        return host
    scheme, rest = host.split("://", 1)
    return f"{scheme}://{quote(user, safe='')}:{quote(password, safe='')}@{rest}"


def direct_client() -> httpx.Client:
    # trust_env=False: ignore HTTP(S)_PROXY env vars so routing is always explicit.
    return httpx.Client(timeout=TIMEOUT, headers={"User-Agent": USER_AGENT}, trust_env=False, follow_redirects=True)


def proxied_client(proxy_url: str) -> httpx.Client:
    return httpx.Client(proxy=proxy_url, timeout=TIMEOUT, headers={"User-Agent": USER_AGENT}, trust_env=False, follow_redirects=True)


def _ip(client: httpx.Client) -> str:
    r = client.get(IP_ECHO)
    r.raise_for_status()
    return r.text.strip()


def verify_egress(proxy_url: str | None) -> str:
    """Return the proxy's exit address, or raise EgressError. Call before every crawl run."""
    if not proxy_url:
        raise EgressError("no proxy configured (rwi_proxy_url) — refusing to crawl from the home connection")
    with direct_client() as c:
        home = _ip(c)
    try:
        with proxied_client(proxy_url) as c:
            exit_ip = _ip(c)
    except Exception as e:  # any failure on the proxied path (incl. SOCKS protocol errors) blocks the crawl
        raise EgressError(f"proxy unreachable or rejected: {type(e).__name__}: {e}") from e
    if exit_ip == home:
        raise EgressError("proxy exits from the home address — refusing to crawl")
    return exit_ip


def safe_proxy_label(proxy_url: str) -> str:
    """For logs: scheme://host:port without credentials."""
    u = httpx.URL(proxy_url)
    return f"{u.scheme}://{u.host}:{u.port}"
