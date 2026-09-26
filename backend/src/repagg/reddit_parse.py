"""Parse Reddit pages captured by the owner's browser: comment threads and wiki pages,
in both the current (shreddit web components) and old.reddit layouts. No network access."""

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone

from selectolax.parser import HTMLParser, Node

THREAD = re.compile(r"reddit\.com/r/([^/]+)/comments/([a-z0-9]+)", re.I)
WIKI = re.compile(r"reddit\.com/r/([^/]+)/wiki/([^?#]*)", re.I)
IMG_HOSTS = ("i.redd.it", "preview.redd.it", "i.imgur.com", "external-preview.redd.it")
WIKI_SECTION_CHARS = 6000  # split long wiki pages into pseudo-posts so the model can cite sections


@dataclass
class RedditPost:
    number: int
    external_id: str
    author: str | None
    posted_at: str
    text: str
    score: int | None
    images: list[str] = field(default_factory=list)
    parent: str | None = None


@dataclass
class RedditPage:
    kind: str                # "thread" | "wiki"
    subreddit: str
    thread_id: str           # t3 id, or "wiki:<page>"
    url: str
    title: str
    posts: list[RedditPost]


def parse_reddit(html: str, url: str) -> RedditPage:
    tree = HTMLParser(html)
    if (m := WIKI.search(url)):
        return _wiki(tree, url, m.group(1), m.group(2).strip("/") or "index")
    if not (m := THREAD.search(url)):
        raise ValueError("not a Reddit thread or wiki page")
    sub, tid = m.group(1), m.group(2).lower()
    if tree.css_first("shreddit-post"):
        return _shreddit(tree, url, sub, tid)
    if tree.css_first("div.thing.link"):
        return _old(tree, url, sub, tid)
    raise ValueError("unrecognised Reddit layout")


# ---- current Reddit (shreddit) ---------------------------------------------------

def _shreddit(tree: HTMLParser, url: str, sub: str, tid: str) -> RedditPage:
    post = tree.css_first("shreddit-post")
    a = post.attributes
    body = post.css_first('[slot="text-body"]')
    posts = [RedditPost(
        number=1, external_id=f"t3_{tid}", author=a.get("author"),
        posted_at=_iso(a.get("created-timestamp")), text=_text(body), score=_int(a.get("score")),
        images=_images(post),
    )]
    for i, c in enumerate(tree.css("shreddit-comment"), start=2):
        ca = c.attributes
        content = c.css_first('[slot="comment"]')
        ts = c.css_first("faceplate-timeago")
        posts.append(RedditPost(
            number=i, external_id=ca.get("thingid") or f"c{i}", author=ca.get("author"),
            posted_at=_iso(ca.get("created") or (ts.attributes.get("ts") if ts else None)),
            text=_text(content), score=_int(ca.get("score")), images=_images(content) if content else [],
            parent=ca.get("parentid"),
        ))
    title = a.get("post-title") or _text(tree.css_first("h1"))
    return RedditPage("thread", sub, tid, _canon(url), title, [p for p in posts if p.text or p.images])


# ---- old.reddit ---------------------------------------------------------------------

def _old(tree: HTMLParser, url: str, sub: str, tid: str) -> RedditPage:
    link = tree.css_first("div.thing.link")
    la = link.attributes
    body = link.css_first(".expando .usertext-body .md")
    posts = [RedditPost(
        number=1, external_id=la.get("data-fullname") or f"t3_{tid}", author=la.get("data-author"),
        posted_at=_iso_ms(la.get("data-timestamp")), text=_text(body), score=_int(la.get("data-score")),
        images=_images(link.css_first(".expando")) + ([la["data-url"]] if _is_img(la.get("data-url")) else []),
    )]
    for i, c in enumerate(tree.css("div.thing.comment"), start=2):
        ca = c.attributes
        entry = c.css_first(".entry")  # first .entry is the comment's own; replies follow in .child
        content = entry.css_first(".usertext-body .md") if entry else None
        t = entry.css_first("time[datetime]") if entry else None
        score = entry.css_first(".score.unvoted") if entry else None
        posts.append(RedditPost(
            number=i, external_id=ca.get("data-fullname") or f"c{i}", author=ca.get("data-author"),
            posted_at=_iso(t.attributes.get("datetime") if t else None), text=_text(content),
            score=_int((score.attributes.get("title") if score else None)), images=_images(content) if content else [],
        ))
    title = _text(link.css_first("a.title"))
    return RedditPage("thread", sub, tid, _canon(url), title, [p for p in posts if p.text or p.images])


# ---- wiki (both layouts) ---------------------------------------------------------------

def _wiki(tree: HTMLParser, url: str, sub: str, page: str) -> RedditPage:
    root = tree.css_first(".wiki-page-content .md") or tree.css_first(".md.wiki") or tree.css_first("[data-testid='wiki-page'] .md") \
        or tree.css_first("main .md") or tree.css_first("main")
    if root is None:
        raise ValueError("no wiki content found")
    rev = tree.css_first(".wiki-page-content time[datetime], time[datetime]")
    when = _iso(rev.attributes.get("datetime") if rev else None)
    # Split at headings into sections of manageable size.
    sections, cur = [], ""
    for node in root.iter(include_text=False):
        chunk = _text(node)
        if node.tag in ("h1", "h2", "h3") and len(cur) > 400:
            sections.append(cur)
            cur = ""
        cur += ("\n\n" if cur else "") + chunk
        if len(cur) > WIKI_SECTION_CHARS:
            sections.append(cur)
            cur = ""
    if cur.strip():
        sections.append(cur)
    posts = [RedditPost(number=i, external_id=f"wiki:{page}:{i}", author=None, posted_at=when, text=s.strip(), score=None)
             for i, s in enumerate(sections, start=1) if s.strip()]
    title = f"r/{sub} wiki: {page.replace('_', ' ')}"
    return RedditPage("wiki", sub, f"wiki:{page.lower()}", _canon(url), title, posts)


# ---- helpers -------------------------------------------------------------------------

def _images(node: Node | None) -> list[str]:
    out: list[str] = []
    if node is None:
        return out
    for img in node.css("img"):
        src = img.attributes.get("src") or img.attributes.get("data-lazy-src") or ""
        if _is_img(src) and src not in out:
            out.append(src)
    return out


def _is_img(u: str | None) -> bool:
    return bool(u) and u.startswith("http") and any(h in u for h in IMG_HOSTS)


def _text(node: Node | None) -> str:
    if node is None:
        return ""
    t = node.text(separator="\n")
    t = re.sub(r"[ \t ]+", " ", t)
    return re.sub(r"\n\s*\n+", "\n\n", t).strip()


def _int(s: str | None) -> int | None:
    try:
        return int(str(s).replace(",", "")) if s not in (None, "") else None
    except ValueError:
        return None


def _iso(s: str | None) -> str:
    if not s:
        return datetime.now(timezone.utc).isoformat(timespec="seconds")
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(timezone.utc).isoformat(timespec="seconds")
    except ValueError:
        return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _iso_ms(ms: str | None) -> str:
    try:
        return datetime.fromtimestamp(int(ms) / 1000, timezone.utc).isoformat(timespec="seconds")
    except (TypeError, ValueError):
        return _iso(None)


def _canon(url: str) -> str:
    return re.sub(r"https?://(old\.|new\.|np\.)?reddit\.com", "https://www.reddit.com", url.split("?")[0].split("#")[0])
