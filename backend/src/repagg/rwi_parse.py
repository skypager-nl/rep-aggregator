"""Parse XenForo 2 thread pages from RWI (as captured by the owner's browser).

Pure function of the HTML: no network access. Works on both the rendered DOM
the browser extension sends and on raw server HTML.
"""

import email
import re
from dataclasses import dataclass, field
from datetime import datetime
from email import policy
from pathlib import Path

from selectolax.parser import HTMLParser, Node

THREAD_URL = re.compile(r"/threads/(?:[^/]*\.)?(\d+)/?(?:page-(\d+))?")
MEMBER_ID = re.compile(r"/members/[^/]*\.(\d+)/?")


@dataclass
class Quote:
    author: str | None
    source_post_id: str | None
    text: str


@dataclass
class Post:
    post_id: str
    number: int | None           # "#12" position in thread
    author: str
    author_id: str | None
    author_joined: str | None    # ISO date
    author_messages: int | None
    author_reactions: int | None
    author_banners: list[str]
    posted_at: str               # ISO datetime with offset
    text: str                    # own words, quotes removed
    quotes: list[Quote]
    images: list[str]            # full-size URLs where the post links them
    reactions: int
    is_starter: bool


@dataclass
class ThreadPage:
    url: str                     # canonical thread URL (no page suffix)
    thread_id: str
    title: str
    forum: str | None
    breadcrumbs: list[str]
    page: int
    pages: int
    posts: list[Post] = field(default_factory=list)


def html_from_mhtml(path: Path) -> str:
    msg = email.message_from_binary_file(path.open("rb"), policy=policy.default)
    for part in msg.walk():
        if part.get_content_type() == "text/html":
            # Chrome's MHTML often omits the charset; the page itself is UTF-8.
            return part.get_payload(decode=True).decode(part.get_content_charset() or "utf-8", "replace")
    raise ValueError(f"no text/html part in {path}")


def parse_thread(html: str, url: str | None = None) -> ThreadPage:
    tree = HTMLParser(html)
    canonical = _attr(tree.css_first('link[rel="canonical"]'), "href") or url or ""
    m = THREAD_URL.search(url or "") or THREAD_URL.search(canonical)
    if not m:
        raise ValueError("not a thread page (no /threads/<id> URL)")
    thread_id = m.group(1)
    base = canonical.split("page-")[0] if canonical else ""

    page, pages = 1, 1
    nav = tree.css_first(".pageNavSimple-el--current")
    if nav and (pm := re.search(r"(\d+)\s+of\s+(\d+)", nav.text())):
        page, pages = int(pm.group(1)), int(pm.group(2))
    elif m.group(2):
        page = pages = int(m.group(2))

    crumbs = [_clean(n.text()) for n in tree.css(".p-breadcrumbs span[itemprop=name]")]
    return ThreadPage(
        url=base,
        thread_id=thread_id,
        title=_clean(_text(tree.css_first("h1.p-title-value"))),
        forum=crumbs[-1] if crumbs else None,
        breadcrumbs=crumbs,
        page=page,
        pages=pages,
        posts=[_post(a) for a in tree.css("article.message--post")],
    )


def _post(a: Node) -> Post:
    post_id = (a.attributes.get("data-content") or "").removeprefix("post-")
    author_link = a.css_first(".message-name a.username") or a.css_first(".message-name .username")
    extras = {}
    for dl in a.css(".message-userExtras dl"):
        label = _attr(dl.css_first("dt [data-original-title]"), "data-original-title") or _clean(_text(dl.css_first("dt")))
        extras[label] = _clean(_text(dl.css_first("dd")))

    body = a.css_first(".message-body .bbWrapper")
    quotes: list[Quote] = []
    if body:
        for bq in body.css("blockquote.bbCodeBlock--quote"):
            content = bq.css_first(".bbCodeBlock-expandContent") or bq.css_first(".bbCodeBlock-content")
            quotes.append(Quote(
                author=bq.attributes.get("data-quote"),
                source_post_id=(bq.attributes.get("data-source") or "").removeprefix("post: ") or None,
                text=_clean(content.text(separator=" ")) if content else "",
            ))
    images = _images(body) if body else []
    if body:
        for bq in body.css("blockquote.bbCodeBlock--quote"):
            bq.decompose()
    number = None
    for li in a.css(".message-attribution-opposite li a"):
        if (nm := re.fullmatch(r"#\s*(\d+)", _clean(li.text()))):
            number = int(nm.group(1))

    return Post(
        post_id=post_id,
        number=number,
        author=a.attributes.get("data-author") or _clean(_text(author_link)),
        author_id=_attr(author_link, "data-user-id") or _member_id(_attr(author_link, "href")),
        author_joined=_date(extras.get("Joined")),
        author_messages=_int(extras.get("Messages")),
        author_reactions=_int(extras.get("Reaction score")),
        author_banners=[_clean(b.text()) for b in a.css(".message-userBanner strong")],
        posted_at=_attr(a.css_first(".message-attribution-main time"), "datetime") or "",
        text=_clean(body.text(separator="\n")) if body else "",
        quotes=quotes,
        images=images,
        reactions=_reaction_count(a.css_first(".reactionsBar")),
        is_starter="message-threadStarterPost" in (a.attributes.get("class") or ""),
    )


def _images(body: Node) -> list[str]:
    """The images the post displays (what the browser loads), skipping smilies and data: URIs."""
    out: list[str] = []
    for img in body.css("img.bbImage"):
        src = img.attributes.get("data-url") or img.attributes.get("src") or ""
        if src.startswith("http") and src not in out:
            out.append(src)
    return out


def _reaction_count(bar: Node | None) -> int:
    if bar is None:
        return 0
    link = bar.css_first(".reactionsBar-link")
    if link is None:
        return 0
    names = len(link.css("bdi"))
    others = re.search(r"and\s+([\d,]+)\s+others?", link.text())
    return names + (int(others.group(1).replace(",", "")) if others else 0)


def _date(s: str | None) -> str | None:
    if not s:
        return None
    for fmt in ("%d/%m/%y", "%d/%m/%Y", "%b %d, %Y"):
        try:
            return datetime.strptime(s, fmt).date().isoformat()
        except ValueError:
            pass
    return None


def _int(s: str | None) -> int | None:
    if not s:
        return None
    s = s.replace(",", "").strip()
    if (m := re.fullmatch(r"([\d.]+)\s*([KkMm]?)", s)):
        return int(float(m.group(1)) * {"": 1, "k": 1_000, "m": 1_000_000}[m.group(2).lower()])
    return None


def _member_id(href: str | None) -> str | None:
    m = MEMBER_ID.search(href or "")
    return m.group(1) if m else None


def _attr(node: Node | None, name: str) -> str | None:
    return node.attributes.get(name) if node is not None else None


def _text(node: Node | None) -> str:
    return node.text() if node is not None else ""


def _clean(s: str) -> str:
    s = re.sub(r"[ \t\r\f\v ]+", " ", s)
    s = re.sub(r"\n\s*\n+", "\n\n", s)
    return s.strip()
