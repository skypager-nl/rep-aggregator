"""Parse RWG (Invision Community 4) topic and forum-listing pages. No network access."""

import math
import re
from dataclasses import dataclass

from selectolax.parser import HTMLParser, Node

from .rwi_parse import Post, Quote, ThreadPage

POSTS_PER_PAGE = 25
TOPIC_URL = re.compile(r"/topic/(\d+)-")


@dataclass
class TopicRow:
    topic_id: str
    url: str
    title: str
    replies: int
    last_post: str | None
    started: str | None
    pinned: bool

    @property
    def pages(self) -> int:
        return max(1, math.ceil((self.replies + 1) / POSTS_PER_PAGE))


def parse_forum(html: str) -> tuple[list[TopicRow], int]:
    """Topic rows on a forum listing page, plus the forum's total number of listing pages."""
    t = HTMLParser(html)
    rows = []
    for li in t.css("li.ipsDataItem"):
        tid = li.attributes.get("data-rowid") or li.attributes.get("data-rowID")
        link = li.css_first(".ipsDataItem_title a[href*='/topic/']")
        if not tid or not link:
            continue
        stats = [_int(n.text()) for n in li.css(".ipsDataItem_stats_number")]
        last = li.css_first(".ipsDataItem_lastPoster time[datetime]")
        started = li.css_first(".ipsDataItem_meta time[datetime]")
        rows.append(TopicRow(
            topic_id=tid,
            url=_clean_url(link.attributes.get("href", "")),
            title=_clean(link.attributes.get("title") or link.text()),
            replies=stats[0] if stats and stats[0] is not None else 0,
            last_post=last.attributes.get("datetime") if last else None,
            started=started.attributes.get("datetime") if started else None,
            pinned=li.css_first(".ipsBadge_positive[title='Pinned']") is not None,
        ))
    pages = max([int(p) for p in re.findall(r"data-pages=['\"](\d+)", html)] or [1])
    return rows, pages


def parse_topic(html: str, url: str) -> ThreadPage:
    t = HTMLParser(html)
    canonical = _attr(t.css_first('link[rel="canonical"]'), "href") or url
    m = TOPIC_URL.search(canonical) or TOPIC_URL.search(url)
    if not m:
        raise ValueError("not an RWG topic page")
    page = int(p.group(1)) if (p := re.search(r"[&?/]page[=/](\d+)", url)) else 1
    pages = max([int(p) for p in re.findall(r"data-pages=['\"](\d+)", html)] or [page])
    crumbs = [_clean(a.text()) for a in t.css("nav.ipsBreadcrumb li a span")] or [_clean(a.text()) for a in t.css("[data-role='breadcrumbList'] li a")]
    title = _clean(_text(t.css_first("h1.ipsType_pageTitle")) or _text(t.css_first("h1")))
    posts = [_post(a, (page - 1) * POSTS_PER_PAGE + i + 1) for i, a in enumerate(t.css("article[id^='elComment_']"))]
    return ThreadPage(
        url=re.sub(r"[&?]page=\d+", "", canonical).split("#")[0],
        thread_id=m.group(1),
        title=title,
        forum=crumbs[-1] if crumbs else None,
        breadcrumbs=crumbs,
        page=page,
        pages=pages,
        posts=[p for p in posts if p.text or p.images],
    )


def _post(a: Node, number: int) -> Post:
    post_id = (a.attributes.get("id") or "").removeprefix("elComment_")
    aside = a.css_first("aside.cAuthorPane") or a
    name = _clean(_text(aside.css_first("h3.cAuthorPane_author strong")) or _text(aside.css_first("h3.cAuthorPane_author")))
    info = [_clean(li.text()) for li in aside.css("ul.cAuthorPane_info li")]
    posts_count = next((_int(x.split()[0]) for x in info if re.fullmatch(r"[\d,]+ posts?", x)), None)
    rep = _int(_text(aside.css_first(".ipsRepBadge")))
    # Every short label in the author panel: member title, group ("RWG Trusted Dealer", "Mentor", ...).
    labels = [x for x in info if x and not re.search(r"posts?$|:|^[+-]?\d", x) and len(x) < 40]
    body = a.css_first("[data-role='commentContent']")
    quotes: list[Quote] = []
    if body:
        for bq in body.css("blockquote.ipsQuote"):
            content = bq.css_first(".ipsQuote_contents") or bq
            quotes.append(Quote(author=bq.attributes.get("data-ipsquote-username"),
                                source_post_id=bq.attributes.get("data-ipsquote-contentcommentid"),
                                text=_clean(content.text(separator=" "))))
    images = _images(body) if body else []
    if body:
        for bq in body.css("blockquote.ipsQuote"):
            bq.decompose()
        for junk in body.css("iframe, script, style"):
            junk.decompose()
    when = a.css_first(".ipsComment_meta time[datetime]") or a.css_first("time[datetime]")
    return Post(
        post_id=post_id,
        number=number,
        author=name or "?",
        author_id=None,
        author_joined=None,
        author_messages=posts_count,
        author_reactions=rep,
        author_banners=labels,
        posted_at=when.attributes.get("datetime") if when else "",
        text=_clean(body.text(separator="\n")) if body else "",
        quotes=quotes,
        images=images,
        reactions=0,
        is_starter=number == 1,
    )


def _images(body: Node) -> list[str]:
    out: list[str] = []
    for img in body.css("img"):
        src = img.attributes.get("data-src") or img.attributes.get("src") or ""
        cls = img.attributes.get("class") or ""
        if not src.startswith("http") or "emoticons" in src or "ipsEmoji" in cls or src.startswith("data:"):
            continue
        if src not in out:
            out.append(src)
    return out


def _clean_url(u: str) -> str:
    return u.replace("&amp;", "&").split("#")[0]


def _int(s: str | None) -> int | None:
    if not s:
        return None
    m = re.search(r"-?[\d,]+", s)
    return int(m.group(0).replace(",", "")) if m else None


def _attr(node: Node | None, name: str) -> str | None:
    return node.attributes.get(name) if node is not None else None


def _text(node: Node | None) -> str:
    return node.text() if node is not None else ""


def _clean(s: str) -> str:
    s = re.sub(r"[ \t\r\f\v ]+", " ", s or "")
    s = re.sub(r"\n\s*\n+", "\n\n", s)
    return s.strip()
