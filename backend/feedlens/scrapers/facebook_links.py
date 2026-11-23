"""Facebook author and permalink normalization."""
from __future__ import annotations

import re
import unicodedata
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit


AD_QUERY_KEYS = {"ad_id", "adgroup_id", "adset_id", "campaign_id", "fb_ad_id", "adgroupid"}


def clean_facebook_author(author: str) -> str:
    name = re.sub(r"\s+", " ", unicodedata.normalize("NFC", author)).strip()
    name = re.sub(r"Tài khoản đã xác minh|Verified account|已验证账户", "", name, flags=re.IGNORECASE)
    name = re.sub(r"[·•]\s*(?:Theo dõi|Follow|关注)\s*$", "", name, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", name).strip(" ·•")


def facebook_ad_link(href: str) -> bool:
    try:
        url = urlsplit(urljoin("https://www.facebook.com/", href))
        return bool(re.match(r"^/ads/about(?:/|$)", url.path) or
                    any(k.lower() in AD_QUERY_KEYS and v for k, v in parse_qsl(url.query)))
    except ValueError:
        return False


def select_facebook_link(links: list[tuple[str, bool]]) -> str:
    """Prefer post permalinks, then timestamp anchors, then media fallbacks."""
    best_url, best_rank = "", (3, False, True)
    for href, timestamp in links:
        if not href or href.startswith("#") or facebook_ad_link(href):
            continue
        try:
            url = urlsplit(urljoin("https://www.facebook.com/", href))
        except ValueError:
            continue
        host = (url.hostname or "").lower()
        if url.scheme not in ("http", "https") or not (host == "facebook.com" or host.endswith(".facebook.com") or host == "fb.watch"):
            continue
        if host in {"l.facebook.com", "lm.facebook.com"} or url.path == "/l.php" or url.path.startswith("/ads/"):
            continue
        if url.path in ("", "/"):
            continue
        raw_query = parse_qsl(url.query, keep_blank_values=True)
        has_comment = any(k in {"comment_id", "reply_comment_id"} for k, _ in raw_query)
        query = [(k, v) for k, v in raw_query
                 if not k.startswith(("__cft__", "__tn__")) and k not in {"fbclid", "comment_id", "reply_comment_id"}]
        group = re.fullmatch(r"/groups/([\w.-]+)/?", url.path)
        multi = dict(query).get("multi_permalinks", "")
        if group and re.fullmatch(r"\d+", multi):
            url = url._replace(path=f"/groups/{group[1]}/posts/{multi}/")
            query = []
        elif re.fullmatch(r"(?:/groups/[\w.-]+)?/(?:posts|permalink)/[^/]+/?", url.path):
            query = []
        post = bool(re.search(r"/(?:posts|permalink)/[^/]+|^/share/(?:[prv]/)?[^/]+", url.path)) or any(k == "story_fbid" and v for k, v in query)
        media = bool(re.search(r"/(?:photos?|videos?|reels?)(?:/|\.php$)|^/watch/?$", url.path)) or host == "fb.watch"
        rank = (0 if post else 1 if timestamp else 2 if media else 3, has_comment, not timestamp)
        if rank < best_rank:
            best_url = urlunsplit((url.scheme, url.netloc, url.path, urlencode(query), url.fragment))
            best_rank = rank
    return best_url


def is_facebook_content_url(href: str) -> bool:
    chosen = select_facebook_link([(href, False)])
    if not chosen:
        return False
    url = urlsplit(chosen)
    return bool(re.search(r"/(?:posts|permalink|reels?|videos?)/[^/]+|^/share/[^/]+", url.path)
                or dict(parse_qsl(url.query)).get("story_fbid")
                or (url.path.rstrip("/") == "/watch" and dict(parse_qsl(url.query)).get("v"))
                or url.hostname == "fb.watch")


def facebook_dom_permalink(links: list[tuple[str, bool]], author_url: str = "") -> str:
    chosen = select_facebook_link(links)
    if POST_LINK_RE.search(chosen):
        return chosen
    group = ""
    try:
        actor = urlsplit(urljoin("https://www.facebook.com/", author_url))
    except ValueError:
        actor = urlsplit("")
    for href, _ in links:
        try:
            url = urlsplit(urljoin("https://www.facebook.com/", href))
            if (url.hostname or "").removeprefix("www.") not in {"facebook.com", "m.facebook.com"}:
                continue
            match = re.fullmatch(r"/groups/([\w.-]+)/?", url.path)
            if match:
                group = match[1]; break
        except ValueError:
            continue
    for href, _ in links:
        if not select_facebook_link([(href, False)]):
            continue
        url = urlsplit(urljoin("https://www.facebook.com/", href))
        match = re.fullmatch(r"(gm|pcb)\.(\d+)", dict(parse_qsl(url.query)).get("set", ""))
        if not match:
            continue
        header_group = actor.hostname in {"www.facebook.com", "facebook.com", "m.facebook.com"} and actor.path.strip("/") == f"groups/{group}"
        if group and (match[1] == "gm" or header_group):
            return f"https://www.facebook.com/groups/{group}/posts/{match[2]}/"
        if match[1] == "pcb" and author_url:
            if actor.hostname not in {"www.facebook.com", "facebook.com", "m.facebook.com"}:
                continue
            slug = actor.path.strip("/")
            if slug == "profile.php":
                slug = dict(parse_qsl(actor.query)).get("id", "")
            if re.fullmatch(r"[\w.-]+", slug) and slug not in {"photo.php", "watch", "groups", "ads", "reel"}:
                return f"https://www.facebook.com/{slug}/posts/{match[2]}/"
    # set=a.* is an album ID, and fbid is a photo ID: neither identifies the post.
    return chosen


POST_LINK_RE = re.compile(r"/(?:posts|permalink)/|story_fbid=|^https?://[^/]+/share/")
