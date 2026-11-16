"""Bộ lướt cho từng nền tảng.

Mỗi nền tảng khai báo: URL cần mở theo loại nguồn (feed/group/search) và một đoạn JS
trích xuất bài viết đang hiển thị. Vòng lặp cuộn chung xử lý nhịp độ giống người,
khử trùng lặp và dừng khi đủ số bài hoặc hết nội dung mới.

Selector của mạng xã hội thay đổi thường xuyên — khi một nền tảng ngừng trả bài,
hãy sửa đoạn JS tương ứng trong file này.
"""
from __future__ import annotations

import base64
import json
import os
import random
import re
import time
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone
from html import escape
from typing import Callable
from urllib.parse import parse_qsl, quote_plus, urlencode, urljoin, urlsplit, urlunsplit

from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError

from .models import RawPost

ProgressFn = Callable[[int, str], None]


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
    best_url, best_rank = "", (3, True)
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
        query = [(k, v) for k, v in parse_qsl(url.query, keep_blank_values=True)
                 if not k.startswith(("__cft__", "__tn__")) and k != "fbclid"]
        group = re.fullmatch(r"/groups/([\w.-]+)/?", url.path)
        multi = dict(query).get("multi_permalinks", "")
        if group and re.fullmatch(r"\d+", multi):
            url = url._replace(path=f"/groups/{group[1]}/posts/{multi}/")
            query = []
        post = bool(re.search(r"/(?:posts|permalink)/[^/]+|^/share/(?:[prv]/)?[^/]+", url.path)) or any(k == "story_fbid" and v for k, v in query)
        media = bool(re.search(r"/(?:photos?|videos?|reels?)(?:/|\.php$)|^/watch/?$", url.path)) or host == "fb.watch"
        rank = (0 if post else 1 if timestamp else 2 if media else 3, not timestamp)
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


def facebook_story_id(story: dict) -> str:
    value = str(story.get("post_id") or story.get("pfbid") or "")
    if re.fullmatch(r"(?:[0-9]+|pfbid[A-Za-z0-9]+)", value):
        return value
    feedback = story.get("feedback")
    if not isinstance(feedback, dict):
        return ""
    encoded = str(feedback.get("id") or "")
    if len(encoded) > 1024:
        return ""
    try:
        decoded = base64.b64decode(encoded + "===").decode("utf-8")
    except (ValueError, UnicodeError):
        return ""
    ids = set(re.findall(r"(?<![A-Za-z0-9_])(?i:feedback):(pfbid[A-Za-z0-9]+|[0-9]+)(?![A-Za-z0-9_])", decoded))
    return next(iter(ids)) if len(ids) == 1 else ""


def facebook_actor_slug(actor: dict) -> str:
    if actor.get("__typename") == "Group":
        return ""
    url = actor.get("url")
    if isinstance(url, str):
        try:
            parsed = urlsplit(urljoin("https://www.facebook.com/", url))
            if parsed.scheme in {"http", "https"} and parsed.hostname in {"facebook.com", "www.facebook.com", "m.facebook.com"}:
                slug = parsed.path.strip("/")
                if slug == "profile.php":
                    slug = dict(parse_qsl(parsed.query)).get("id", "")
                if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", slug) and slug not in {"groups", "watch", "reel", "stories", "ads", "profile.php"}:
                    return slug
        except ValueError:
            pass
    for key in ("slug", "username", "id"):
        slug = str(actor.get(key) or "")
        if slug in {"groups", "watch", "reel", "stories", "ads", "profile.php", "permalink.php", "photo.php"}:
            continue
        if (key == "id" and slug.isascii() and slug.isdigit()) or (key != "id" and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", slug)):
            return slug
    return ""


_DEBUG_SECRET = re.compile(r"token|cookie|dtsg|auth|credential|secret|session|^__(?!typename$)|^(?:lsd|jazoest|c_user|xs)$", re.I)


def sanitize_facebook_debug(value: object) -> object:
    budget = 400
    def clean(item, key="", depth=0):
        nonlocal budget
        budget -= 1
        if budget < 0 or depth > 8:
            return "[truncated]"
        if isinstance(item, dict):
            preferred = {"__typename", "id", "post_id", "pfbid", "actors", "message", "feedback", "comet_sections", "attachments", "url", "permalink_url"}
            entries = sorted(item.items(), key=lambda kv: kv[0] not in preferred)
            return {str(k)[:80]: clean(v, str(k), depth + 1) for k, v in entries[:60] if not _DEBUG_SECRET.search(str(k))}
        if isinstance(item, list):
            return [clean(v, key, depth + 1) for v in item[:10]]
        if isinstance(item, str):
            if item.startswith(("https://", "http://")):
                try:
                    parsed = urlsplit(item)
                    safe = [(k, v) for k, v in parse_qsl(parsed.query) if k in {"id", "post_id", "story_fbid", "fbid", "set", "v", "multi_permalinks"} and not _DEBUG_SECRET.search(v)]
                    return urlunsplit((parsed.scheme, parsed.hostname or "", parsed.path[:1000], urlencode(safe), ""))
                except ValueError:
                    return "[invalid URL]"
            return item[:512] if key in {"id", "post_id", "pfbid"} or key.endswith("_id") else item[:60]
        return item if item is None or isinstance(item, (bool, int, float)) else str(item)[:60]
    return clean(value)


class FacebookStoryCache(dict):
    """Parsed records plus bounded, value-free shapes for unrecognized Page stories."""
    def __init__(self):
        super().__init__()
        self.author_keys: dict[str, list[dict]] = {}


def facebook_graphql_debug(post: RawPost, cache: dict) -> dict:
    record = match_facebook_story(post, cache)
    result = {"author": post.author[:60], "text": post.text[:60], "fingerprint": post.fingerprint}
    if record and record.get("_debug_story"):
        return {**result, "match": "matched", "story": record["_debug_story"]}
    author = clean_facebook_author(post.author).casefold()
    shapes = getattr(cache, "author_keys", {}).get(author, [])
    return {**result, "match": "none_or_ambiguous", "same_author_keys": shapes[:10]}


def facebook_stories(payload: object, group_url: str = "", author_keys: dict | None = None) -> list[dict]:
    """Read Story identity, never photo/comment IDs, from captured Facebook JSON."""
    found: dict[str, dict] = {}
    stack = [payload]
    visited = 0
    while stack and visited < 50000:
        node = stack.pop(); visited += 1
        if isinstance(node, list):
            stack.extend(node); continue
        if not isinstance(node, dict):
            continue
        stack.extend(value for value in node.values() if isinstance(value, (dict, list)))
        if node.get("__typename") != "Story":
            continue
        comet = node.get("comet_sections")
        comet = comet if isinstance(comet, dict) else {}
        section = comet.get("content")
        content = section.get("story") if isinstance(section, dict) else {}
        content = content if isinstance(content, dict) else {}
        views = [node, content]
        for section in comet.values():
            for part in section if isinstance(section, list) else [section]:
                related = part.get("story") if isinstance(part, dict) else None
                if isinstance(related, dict) and related not in views:
                    views.append(related)
        message = next((view["message"] for view in views if isinstance(view.get("message"), dict) and view["message"].get("text")), {})
        text = message.get("text", "") if isinstance(message, dict) else ""
        actors = next((view["actors"] for view in views if isinstance(view.get("actors"), list) and view["actors"]), [])
        actor = actors[0] if actors and isinstance(actors[0], dict) else {}
        author = clean_facebook_author(str(actor.get("name") or ""))
        if author_keys is not None and author:
            shape = {"keys": sorted(str(key) for key in node if not _DEBUG_SECRET.search(str(key))),
                     "comet_sections_keys": sorted(str(key) for key in comet if not _DEBUG_SECRET.search(str(key)))}
            shapes = author_keys.setdefault(author.casefold(), [])
            if shape not in shapes and len(shapes) < 10: shapes.append(shape)
            if len(author_keys) > 100: author_keys.pop(next(iter(author_keys)))
        if not isinstance(text, str) or len(text.strip()) < 15:
            continue
        urls = [(v, False) for n in views for k in ("url", "wwwURL", "permalink_url")
                if isinstance(v := n.get(k), str)]
        for view in views:
            for wrapper in view.get("attachments", []) if isinstance(view.get("attachments"), list) else []:
                if not isinstance(wrapper, dict):
                    continue
                styles = wrapper.get("styles")
                attachment = styles.get("attachment") if isinstance(styles, dict) else wrapper
                media = attachment.get("media") if isinstance(attachment, dict) else None
                if isinstance(media, dict) and media.get("__typename") in {"Video", "Reel", "XFBVideo"}:
                    urls.extend((media[key], False) for key in ("url", "wwwURL", "permalink_url") if isinstance(media.get(key), str))
        url = select_facebook_link([(href, timestamp) for href, timestamp in urls if is_facebook_content_url(href)])
        if not is_facebook_content_url(url):
            url = ""
            # Identity and owner must come from the same Story dictionary, never two views.
            for view in views:
                post_id = facebook_story_id(view)
                if not post_id:
                    continue
                target = view.get("to") or {}
                group_id = str(target.get("id") or "") if isinstance(target, dict) and target.get("__typename") == "Group" else ""
                group = re.search(r"/groups/([\w.-]+)", group_url)
                if re.fullmatch(r"\d+", group_id) or group:
                    slug = group_id if re.fullmatch(r"\d+", group_id) else group[1]
                    url = f"https://www.facebook.com/groups/{slug}/posts/{post_id}/"
                else:
                    owners = view.get("actors")
                    owner = owners[0] if isinstance(owners, list) and owners and isinstance(owners[0], dict) else {}
                    slug = facebook_actor_slug(owner)
                    if slug:
                        url = f"https://www.facebook.com/{slug}/posts/{post_id}/"
                if url:
                    break
        sponsored = any(n.get("sponsored_data") or n.get("is_sponsored") or n.get("ad_id") for n in views)
        if isinstance(comet, dict):
            for section in comet.values():
                story = section.get("story", {}) if isinstance(section, dict) else {}
                if isinstance(story, dict): sponsored |= bool(story.get("sponsored_data") or story.get("is_sponsored") or story.get("ad_id"))
        created = next((view["creation_time"] for view in views if view.get("creation_time")), None)
        try:
            posted_at = datetime.fromtimestamp(int(created), timezone.utc).isoformat() if created else ""
        except (ValueError, TypeError, OverflowError, OSError):
            posted_at = ""
        record = dict(text=text[:20000], author=clean_facebook_author(str(actor.get("name") or "")), url=url,
                      posted_at=posted_at,
                      sponsored=bool(sponsored or any(facebook_ad_link(h) for h, _ in urls)))
        record["_debug_story"] = sanitize_facebook_debug(node)
        fp = RawPost(platform="facebook", source="", **record).fingerprint
        previous = found.get(fp)
        if previous and previous["url"] and record["url"] and previous["url"].rstrip("/") != record["url"].rstrip("/"):
            previous["_conflict"] = True
        if not previous or (record["url"] and not previous["url"]) or record["sponsored"]:
            if previous:
                record["sponsored"] |= previous["sponsored"]
                record["_conflict"] = bool(record.get("_conflict") or previous.get("_conflict"))
            found[fp] = record
    return list(found.values())


def cache_facebook_stories(body: str, cache: dict, group_url: str = "") -> None:
    if len(body) > 8_000_000:
        return
    for line in body.removeprefix("for (;;);").splitlines():
        try:
            records = facebook_stories(json.loads(line), group_url, getattr(cache, "author_keys", None))
        except (ValueError, TypeError):
            continue
        for record in records:
            fp = RawPost(platform="facebook", source="", **record).fingerprint
            previous = cache.get(fp)
            if previous:
                record["sponsored"] |= previous["sponsored"]
                record["_conflict"] = bool(record.get("_conflict") or previous.get("_conflict") or
                    (previous["url"] and record["url"] and previous["url"].rstrip("/") != record["url"].rstrip("/")))
            if not previous or record["url"] or record["sponsored"]:
                record["_text_key"] = re.sub(r"\s+", " ", record["text"].lower()).strip()[:500]
                cache[fp] = record
            if len(cache) > 1500: cache.pop(next(iter(cache)))


def match_facebook_story(post: RawPost, cache: dict) -> dict | None:
    if post.fingerprint in cache:
        exact = cache[post.fingerprint]
        return ({**exact, "url": ""} if exact["sponsored"] else None) if exact.get("_conflict") else exact
    prefix = re.sub(r"\s+", " ", post.text.lower()).strip()
    prefix = re.sub(r"(?:…|\.\.\.)?\s*(?:see more|xem thêm|查看更多)$", "", prefix).strip()[:500]
    # A Page's short caption can be followed by a longer DOM link preview.
    # That reverse match additionally requires the exact author, and stays ambiguous if duplicated.
    author = clean_facebook_author(post.author).casefold()
    matches = [story for story in cache.values() if not story.get("_conflict") and (
               (len(prefix) >= 80 and story["_text_key"].startswith(prefix)) or
               (len(story["_text_key"]) >= 15 and author and
                author == clean_facebook_author(story["author"]).casefold() and
                prefix.startswith(story["_text_key"] + " ")))]
    return matches[0] if len(matches) == 1 else None


def capture_facebook_response(response, cache: dict, group_url: str = "") -> None:
    try:
        url = urlsplit(response.url)
        if url.hostname not in {"www.facebook.com", "facebook.com", "m.facebook.com"} or url.path.rstrip("/") != "/api/graphql" or response.status != 200:
            return
        cache_facebook_stories(response.text(), cache, group_url)
    except Exception:  # noqa: BLE001 — network enrichment must not interrupt DOM scraping
        return


# --- JS extractors: trả về [{author, text, url, posted_at}] ---------------------------

FB_NODE_SELECTOR = 'div[role="feed"] > div, [role="article"], [aria-posinset]'
FB_LINK_SELECTOR = 'a, [role="link"]'

FB_JS = r"""
(root) => {
  const out = [];
  if (!root) document.querySelectorAll('[data-feedlens-node]').forEach(n => n.removeAttribute('data-feedlens-node'));
  const nodes = root ? [root] : document.querySelectorAll('__NODES__');
  for (const [nodeIndex, n] of [...nodes].entries()) {
    // Feed wrappers and nested shared articles must not produce duplicate posts.
    const article = '[role="article"], [aria-posinset]';
    if (!root && !n.matches(article) && n.querySelector(article)) continue;
    if (!root && n.parentElement?.closest(article)) continue;
    if (!root) n.setAttribute('data-feedlens-node', String(nodeIndex));
    const msg = n.querySelector('[data-ad-preview="message"], [data-ad-comet-preview="message"]');
    let text = msg ? msg.innerText : '';
    if (!text) {
      const blocks = [...n.querySelectorAll('div[dir="auto"]')].map(d => d.innerText).filter(t => t && t.length > 20);
      text = blocks.sort((a, b) => b.length - a.length)[0] || '';
    }
    if (!text || text.length < 15) continue;
    const authorEl = n.querySelector('h2 a, h3 a, h4 a, strong a, h2, h3, h4');
    const anchors = [...n.querySelectorAll('__LINKS__')];
    const timestamp = a => {
      if (a.closest('h2, h3, h4, strong')) return false;
      if (a.querySelector('time, abbr, [data-utime]') || a.hasAttribute('data-utime') ||
          /timestamp/i.test(a.getAttribute('data-testid') || '')) return true;
      const referenced = (a.getAttribute('aria-labelledby') || '').split(/\s+/).map(id => document.getElementById(id)?.textContent || '').join(' ').trim();
      const label = (referenced || a.innerText || a.getAttribute('aria-label') || '').replace(/\s+/g, ' ').trim();
      return /^(?:\d+\s*(?:s|m|h|d|w|y|sec|min|hr|hrs|hours?|days?|weeks?|minutes?|秒|分钟|小时|天|周|年|giây|phút|giờ|ngày|tuần|năm)(?:\s*(?:ago|前|trước))?|just now|yesterday|vừa xong|hôm qua|刚刚|昨天)$/i.test(label) ||
        /\b(?:January|February|March|April|May|June|July|August|September|October|November|December|tháng)\b|\d{1,4}[\/-]\d{1,2}[\/-]\d{1,4}|\d+月\d+日/i.test(a.getAttribute('aria-label') || '');
    };
    const authorUrl = authorEl?.closest('a')?.getAttribute('href') || authorEl?.querySelector('a')?.getAttribute('href') || '';
    const links = anchors.flatMap(a => [...new Set(['href', 'data-href', 'data-url', 'ajaxify']
      .map(key => a.getAttribute(key)).filter(Boolean))].map(href => [href, timestamp(a)]));
    // Obfuscated timestamps fail the text test; their href is "#" or missing until hover.
    // Real feed (2026-11): the timestamp is <a aria-labelledby=… href="?__cft__…"> until hovered.
    const placeholder = h => !h || h === '#' || h.startsWith('?');
    const lazy = a => !a.closest('h2, h3, h4, strong') && placeholder(a.getAttribute('href'))
      && !a.querySelector('img, svg image') && (a.hasAttribute('aria-labelledby') || (a.innerText || '').trim().length <= 40);
    const hover = [...new Set([
      ...anchors.flatMap((a, i) => a.hasAttribute('aria-labelledby') && lazy(a) ? [i] : []),
      ...anchors.flatMap((a, i) => timestamp(a) ? [i] : []),
      ...anchors.flatMap((a, i) => lazy(a) ? [i] : [])])].slice(0, 3);
    const adWords = /^(?:sponsored|được tài trợ|赞助内容|广告)$/i;
    const sponsored = [...n.querySelectorAll('a, span')].some(el =>
      adWords.test((el.getAttribute('aria-label') || el.innerText || '').trim()))
      || anchors.some(a => /\/ads\/about|[?&]ad_id=/.test(a.getAttribute('href') || ''))
      // Real feed samples (runs 6–10): the obfuscated "Sponsored" label is a header link whose
      // only text is U+2060; organic posts put an aria-labelledby timestamp there instead.
      || anchors.some(a => !a.closest('h2, h3, h4') && (a.textContent || '').includes('⁠')
        && /^[⁠​\s]*$/.test(a.textContent || ''));
    out.push({ author: authorEl ? authorEl.innerText.split('\n')[0] : '', text, url: '', links,
      _node_index: nodeIndex, _node_marker: n.getAttribute('data-feedlens-node'), _hover: hover, _author_url: authorUrl, posted_at: '', sponsored });
  }
  return out;
}
""".replace("__NODES__", FB_NODE_SELECTOR).replace("__LINKS__", FB_LINK_SELECTOR)


POST_LINK_RE = re.compile(r"/(?:posts|permalink)/|story_fbid=|^https?://[^/]+/share/")

# Shrunk outerHTML of a post whose permalink was not found: structure only, short text, no tokens.
FB_HEADER_SNAPSHOT_JS = r"""
(n) => {
  const keep = new Set(['href', 'data-href', 'data-url', 'ajaxify', 'role', 'aria-label', 'aria-labelledby',
    'aria-hidden', 'data-ad-preview', 'data-ad-comet-preview', 'data-testid', 'data-utime', 'dir', 'id',
    'data-post-id', 'data-story-id', 'data-video-id']);
  const clean = root => {
    root.querySelectorAll('img, svg, video, picture, style, script, input').forEach(e => e.remove());
    for (const el of [root, ...root.querySelectorAll('*')]) {
      for (const at of [...el.attributes]) {
        if (!keep.has(at.name)) { el.removeAttribute(at.name); continue; }
        if (['href','data-href','data-url','ajaxify'].includes(at.name)) {
          try {
            const u = new URL(at.value, 'https://www.facebook.com/');
            if (!['https:', 'http:'].includes(u.protocol)) { el.removeAttribute(at.name); continue; }
            for (const k of [...u.searchParams.keys()]) if (/token|cookie|auth|session|secret|credential|dtsg|^__|^(?:fbclid|eav|paipv|_rdr|lsd|jazoest|h|u)$/i.test(k)) u.searchParams.delete(k);
            u.hash = ''; el.setAttribute(at.name, u.href);
          } catch { el.removeAttribute(at.name); }
        } else if (at.value.length > 200) el.setAttribute(at.name, at.value.slice(0, 200));
      }
    }
    const walk = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    for (let t = walk.nextNode(); t; t = walk.nextNode()) if (t.nodeValue.length > 30) t.nodeValue = t.nodeValue.slice(0, 30) + '…';
    return root;
  };
  const result = document.createElement('section');
  result.setAttribute('data-feedlens-snapshot', '2');
  const links = document.createElement('nav'); links.setAttribute('data-feedlens-links', '');
  // Preserve late permalinks before pruning noisy/obfuscated context; never slice raw HTML.
  const anchors = [...n.querySelectorAll('a, [role="link"]')];
  anchors.sort((a,b) => Number(/pfbid|story_fbid|fbid|\/posts\/|\/permalink\//i.test(b.getAttribute('href') || '')) - Number(/pfbid|story_fbid|fbid|\/posts\/|\/permalink\//i.test(a.getAttribute('href') || '')));
  for (const a of anchors.slice(0, 100)) {
    const c = a.cloneNode(false); c.textContent = (a.innerText || a.textContent || '').slice(0, 30);
    clean(c);
    if (links.outerHTML.length + c.outerHTML.length > 24000) continue;
    links.append(c);
    for (const id of (a.getAttribute('aria-labelledby') || '').split(/\s+/)) {
      const ref = document.getElementById(id);
      if (ref && links.outerHTML.length < 23000) {
        const label = document.createElement('span'); label.id = id; label.textContent = ref.textContent.slice(0, 30); links.append(clean(label));
      }
    }
  }
  result.append(links);
  const context = clean(n.cloneNode(true));
  context.querySelectorAll('blockquote').forEach(e => { if (e.textContent.trim() === 'Facebook') e.remove(); });
  [...context.querySelectorAll('*')].slice(300).forEach(e => e.remove());
  while (context.outerHTML.length > 12000 && context.lastElementChild) context.lastElementChild.remove();
  result.append(context);
  return result.outerHTML;
}
"""


def _facebook_items(page: Page, stories: dict | None = None) -> list[dict]:
    items = page.evaluate(FB_JS)
    if stories:
        for item in items:
            network = match_facebook_story(RawPost(platform="facebook", source="", **item), stories)
            if network:
                item["_network_url"] = network["url"]
                item["sponsored"] |= network["sponsored"]
    scroll_y = page.evaluate("() => window.scrollY")
    try:
        return _resolve_facebook_items(page, items)
    finally:
        page.evaluate("() => document.querySelectorAll('[data-feedlens-node]').forEach(n => n.removeAttribute('data-feedlens-node'))")
        page.evaluate("y => window.scrollTo(0, y)", scroll_y)


def _resolve_facebook_items(page: Page, items: list[dict]) -> list[dict]:
    hover_enabled = os.getenv("FEEDLENS_FB_HOVER", "1").strip() != "0"
    hover_budget = 3 if hover_enabled else 0
    deadline = time.monotonic() + 4
    jobs = []
    candidates = []
    candidate_ids = []
    for item in items:
        item["author"] = clean_facebook_author(item.get("author", ""))
        node_index = item.pop("_node_index", None)
        marker = item.pop("_node_marker", None)
        hover = item.pop("_hover", [])
        links = item.pop("links", [])
        item["sponsored"] = bool(item.get("sponsored") or any(facebook_ad_link(href) for href, _ in links))
        network_url = item.pop("_network_url", "")
        author_url = item.pop("_author_url", "")
        item["url"] = network_url or facebook_dom_permalink(links, author_url)
        if node_index is None:
            continue
        selector = f'[data-feedlens-node="{marker}"]' if str(marker).isdigit() else None
        node = page.locator(selector) if selector else page.locator(FB_NODE_SELECTOR).nth(node_index)
        jobs.append((item, node, hover, selector))
        if len(candidates) < 10 and not item["sponsored"] and not is_facebook_content_url(item["url"]):
            candidate_ids.append(id(item))
            candidates.append(dict(selector=selector, index=node_index, text=item["text"]))
    # Capture every candidate before any hover scrolls and virtualizes its siblings.
    snapshots = {}
    if candidates:
        try:
            captured = page.evaluate("(items) => { const snapshot = (" + FB_HEADER_SNAPSHOT_JS + "); "
                "return items.map(item => { const n = item.selector ? document.querySelector(item.selector) : "
                "document.querySelectorAll('" + FB_NODE_SELECTOR + "')[item.index]; "
                "if (!n || !n.innerText.includes(item.text)) return null; return snapshot(n); }); }", candidates)
            snapshots = dict(zip(candidate_ids, captured))
        except Exception:  # noqa: BLE001 — diagnostics must never interrupt collection
            pass
    for item, node, hover, selector in jobs:
        status = "no_timestamp" if hover_enabled else "hover_disabled"
        attempted = 0
        if not item["sponsored"] and not is_facebook_content_url(item["url"]):
            if hover and hover_budget > 0 and time.monotonic() < deadline:
                try:
                    node.scroll_into_view_if_needed(timeout=700)
                    if selector:
                        page.wait_for_function("args => document.querySelector(args.selector)?.innerText.includes(args.text)",
                            arg={"selector": selector, "text": item["text"]}, timeout=700)
                    else:
                        page.wait_for_timeout(100)
                    refreshed = node.evaluate(FB_JS, timeout=700)
                    if refreshed and refreshed[0]["text"] == item["text"]:
                        hover = refreshed[0]["_hover"]
                        item["sponsored"] |= refreshed[0]["sponsored"]
                        item["url"] = facebook_dom_permalink(refreshed[0]["links"], refreshed[0]["_author_url"])
                    else:
                        hover = []; status = "post_not_visible"
                except PlaywrightTimeoutError:
                    hover = []; status = "post_not_visible"
            for index in hover if hover_enabled and not is_facebook_content_url(item["url"]) and not item["sponsored"] else []:
                if hover_budget <= 0 or time.monotonic() >= deadline:
                    status = "budget_exhausted"; break
                anchor = node.locator(FB_LINK_SELECTOR).nth(index)
                try:
                    hover_budget -= 1; attempted += 1
                    anchor.hover(timeout=700)
                    page.wait_for_timeout(150)
                    links = node.evaluate(
                        "(n, args) => n.innerText.includes(args.text) ? "
                        "[...n.querySelectorAll('a, [role=link]')].flatMap((a, i) => "
                        "['href', 'data-href', 'data-url', 'ajaxify'].map(k => a.getAttribute(k))"
                        ".filter(Boolean).map(h => [h, i === args.index])) : []",
                        {"index": index, "text": item["text"]})
                    item["sponsored"] |= any(facebook_ad_link(href) for href, _ in links)
                    if any(timestamp and select_facebook_link([(href, True)]) for href, timestamp in links):
                        item["url"] = select_facebook_link([(item["url"], False), *links])
                        status = "resolved"; break
                    status = "hover_no_url"
                except PlaywrightTimeoutError:
                    status = "hover_timeout"
        if not item["sponsored"] and not is_facebook_content_url(item["url"]) and id(item) in candidate_ids:
            snapshot = snapshots.pop(id(item), None)
            if snapshot is None:
                snapshot = '<section data-feedlens-snapshot="3" data-feedlens-capture="not_visible"></section>'
            trace = escape(json.dumps(dict(status=status, attempts=attempted)), quote=True)
            item["_missing_header"] = ('<section data-feedlens-snapshot="3" data-feedlens-author="' + escape(item["author"], quote=True)
                + '" data-feedlens-hover="' + trace + '"><p>' + escape(item["text"][:30]) + '</p>' + snapshot + '</section>')
    return items


FB_EXPAND_JS = r"""
() => {
  const labels = ['See more', 'Xem thêm'];
  document.querySelectorAll('div[role="button"]').forEach(b => {
    if (labels.includes((b.innerText || '').trim())) { try { b.click(); } catch (e) {} }
  });
}
"""

LINKEDIN_JS = r"""
() => [...document.querySelectorAll('div.feed-shared-update-v2, div[data-urn^="urn:li:activity"]')].map(n => {
  const t = n.querySelector('.update-components-text, .feed-shared-update-v2__description');
  const a = n.querySelector('.update-components-actor__title span[aria-hidden="true"], .update-components-actor__name');
  const urn = n.getAttribute('data-urn') || (n.closest('[data-urn]') || {getAttribute: () => ''}).getAttribute('data-urn');
  return { author: a ? a.innerText.trim() : '', text: t ? t.innerText.trim() : '',
           url: urn ? 'https://www.linkedin.com/feed/update/' + urn + '/' : '', posted_at: '' };
}).filter(p => p.text.length > 15)
"""

LINKEDIN_EXPAND_JS = r"""
() => document.querySelectorAll('button.feed-shared-inline-show-more-text__see-more-less-toggle, .see-more').forEach(b => { try { b.click(); } catch (e) {} })
"""

X_JS = r"""
() => [...document.querySelectorAll('article[data-testid="tweet"]')].map(n => {
  const t = n.querySelector('[data-testid="tweetText"]');
  const u = n.querySelector('[data-testid="User-Name"]');
  const time = n.querySelector('time');
  const link = time && time.closest('a') ? time.closest('a').href : '';
  return { author: u ? u.innerText.split('\n').slice(0, 2).join(' ') : '', text: t ? t.innerText : '',
           url: link, posted_at: time ? time.getAttribute('datetime') : '' };
}).filter(p => p.text.length > 5)
"""

REDDIT_JS = r"""
() => [...document.querySelectorAll('shreddit-post')].map(n => {
  const body = n.querySelector('[slot="text-body"]');
  const title = n.getAttribute('post-title') || '';
  return { author: n.getAttribute('author') || '', text: (title + '\n' + (body ? body.innerText : '')).trim(),
           url: 'https://www.reddit.com' + (n.getAttribute('permalink') || ''),
           posted_at: n.getAttribute('created-timestamp') || '' };
}).filter(p => p.text.length > 5)
"""


def is_chronological_url(url: str) -> bool:
    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query))
    if parts.path in ("", "/"):
        return False  # Home feeds are ranked, even if an unrelated sort flag exists.
    return (query.get("sorting_setting", "").upper() == "CHRONOLOGICAL"
            or query.get("sort", "").strip('"').lower() in {"new", "latest", "date_posted"}
            or query.get("f") == "live")


STOP_REASON_TEXT = {
    "target_reached": "đủ số bài",
    "caught_up": "đã gặp toàn bài cũ, coi như hết bài mới",
    "budget_exhausted": "hết giới hạn thời gian/số bài được duyệt",
    "no_more_posts": "trang không tải thêm bài",
    "interrupted": "bị gián đoạn",
}


def collection_message(report: dict) -> str:
    reason = STOP_REASON_TEXT.get(report.get("stop_reason") or "", "")
    return (f"Lấy được {report['collected']}/{report['target']} bài mới · bỏ qua {report['skipped_old']} bài đã có"
            + (f" · bỏ qua {report.get('skipped_ads', 0)} quảng cáo" if report.get("skipped_ads") else "")
            + (f" · dừng vì {reason}" if reason else ""))


@dataclass
class Scraper:
    platform: str
    extract_js: str
    expand_js: str | None = None

    def urls(self, source_type: str, sources: list[str]) -> list[tuple[str, str]]:
        """Trả về [(label, url)] cần lướt."""
        raise NotImplementedError

    # -- vòng lặp cuộn chung --
    def collect(self, page: Page, url: str, label: str, target: int,
                seen: set[str], progress: ProgressFn, speed: str = "fast", interactive: bool = True) -> list[RawPost]:
        pace = PACE.get(speed, PACE["fast"])
        posts: list[RawPost] = []
        collected: dict[str, RawPost] = {}
        encountered: set[str] = set()
        prior = set(seen)
        stale_rounds = consecutive_old = 0
        # Scale with the quota so large runs are not cut short; old-post streaks still end within minutes.
        deadline = time.monotonic() + (max(300, 8 * target) if speed == "careful" else max(180, 4 * target))
        max_examined = max(20, 4 * target)
        chronological = is_chronological_url(url)
        self.last_report = dict(target=target, collected=0, skipped_old=0, skipped_ads=0, examined=0, stop_reason=None)
        self.missing_headers: list[str] = []
        self.missing_graphql_samples: list[dict] = []
        debug_posts: dict[str, RawPost] = {}
        reason = None
        stories = FacebookStoryCache()
        listening = self.platform == "facebook" and hasattr(page, "on")
        def on_response(response):
            capture_facebook_response(response, stories, url)
        if listening:
            page.on("response", on_response)
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=60_000)
            self.ensure_access(page, url, progress, interactive)
            _human_pause(*pace["settle"])
            if listening:
                for body in page.evaluate("() => [...document.querySelectorAll('script[type=\"application/json\"], script[data-sjs]')].slice(0, 40).map(s => s.textContent).filter(t => t && t.length <= 8000000)"):
                    cache_facebook_stories(body, stories, url)
            while reason is None:
                if time.monotonic() >= deadline:
                    reason = "budget_exhausted"; break
                if self.ensure_access(page, url, progress, interactive):
                    stale_rounds = 0
                if self.expand_js:
                    page.evaluate(self.expand_js)
                    _human_pause(*pace["expand"])
                before = len(encountered)
                items = (_facebook_items(page, stories) if stories else _facebook_items(page)) if self.platform == "facebook" else page.evaluate(self.extract_js)
                for item in items:
                    header = item.pop("_missing_header", "")
                    p = RawPost(platform=self.platform, source=label, **item)
                    fp = p.fingerprint
                    network = match_facebook_story(p, stories)
                    if network:
                        p.sponsored |= network["sponsored"]
                        if network["url"]:
                            p.url = network["url"]
                            header = ""  # Network enrichment resolved the missing DOM permalink.
                        if not p.posted_at:
                            p.posted_at = network["posted_at"]
                    if fp in collected and not collected[fp].url and p.url:
                        collected[fp].url = p.url
                    if self.platform == "facebook":
                        if p.sponsored or is_facebook_content_url(p.url):
                            debug_posts.pop(fp, None)
                        elif fp in debug_posts or len(debug_posts) < 10:
                            debug_posts[fp] = p
                    if fp in encountered:
                        continue
                    encountered.add(fp)
                    if header and not p.sponsored and not facebook_ad_link(p.url) and len(self.missing_headers) < 10:
                        self.missing_headers.append(header)
                    if self.platform == "facebook" and (p.sponsored or facebook_ad_link(p.url)):
                        self.last_report["skipped_ads"] += 1
                        # Ads do not count as old-post streaks and never enter seen/history.
                    elif fp in seen:
                        if fp in prior:
                            self.last_report["skipped_old"] += 1
                            consecutive_old += 1
                    else:
                        consecutive_old = 0
                        seen.add(fp)
                        collected[fp] = p
                        posts.append(p)
                    self.last_report.update(collected=len(posts), examined=len(encountered))
                    if len(posts) >= target:
                        reason = "target_reached"; break
                    if chronological and consecutive_old >= 8:
                        reason = "caught_up"; break
                    if len(encountered) >= max_examined or time.monotonic() >= deadline:
                        reason = "budget_exhausted"; break
                stale_rounds = stale_rounds + 1 if len(encountered) == before else 0
                if stale_rounds >= pace["stale"]:
                    reason = "no_more_posts"
                self.last_report["stop_reason"] = reason
                progress(len(posts), collection_message(self.last_report))
                if reason:
                    break
                page.mouse.wheel(0, random.randint(*pace["scroll"]))
                _human_pause(*pace["pause"])
                if random.random() < pace["long_chance"]:
                    _human_pause(*pace["long"])
        finally:
            if listening:
                page.remove_listener("response", on_response)
            # Responses can arrive after a post was first seen; diagnose the final cache state.
            for fp, post in debug_posts.items():
                latest = match_facebook_story(post, stories)
                if latest and (latest["sponsored"] or is_facebook_content_url(latest["url"])):
                    if fp in collected and not latest["sponsored"] and latest["url"] and not collected[fp].url:
                        collected[fp].url = latest["url"]
                    continue
                self.missing_graphql_samples.append(facebook_graphql_debug(post, stories))
            self.last_report.update(collected=len(posts), stop_reason=reason or "interrupted")
            progress(len(posts), collection_message(self.last_report))
        return posts

    def blocked(self, url: str) -> bool:
        return is_blocked_url(self.platform, url)

    def blocked_page(self, page: Page) -> bool:
        """Bị đòi đăng nhập/xác minh: URL checkpoint, hoặc trang hiện form đăng nhập
        (Facebook hiện form ngay tại facebook.com/ khi cookie hỏng, URL không đổi)."""
        return self.blocked(page.url) or has_login_form(page)

    def ensure_access(self, page: Page, url: str, progress: ProgressFn, interactive: bool) -> bool:
        """Nếu nền tảng chuyển sang trang đăng nhập / xác minh 2 bước / checkpoint:
        - có cửa sổ: chờ người dùng tự xác minh (không tự giải CAPTCHA), rồi mở lại trang cần lướt;
        - chạy ẩn: báo lỗi rõ ràng thay vì lướt ra 0 bài.
        Trả về True nếu đã phải chờ và mở lại trang."""
        if not self.blocked_page(page):
            return False
        if not interactive:
            raise NeedsVerification(
                f"{self.platform} đang yêu cầu đăng nhập hoặc xác minh. Tắt chế độ chạy ẩn để xác minh "
                f"trong cửa sổ Chrome, hoặc chạy `feedlens login {self.platform}`.")
        deadline = time.time() + VERIFY_TIMEOUT
        while self.blocked_page(page):
            left = int(deadline - time.time())
            if left <= 0:
                raise NeedsVerification(f"Hết {VERIFY_TIMEOUT // 60} phút chờ xác minh {self.platform}. Hãy chạy lại.")
            progress(0, f"{self.platform} yêu cầu xác minh (2 bước / CAPTCHA). Hãy hoàn tất trong cửa sổ Chrome, "
                        f"bot sẽ tự lướt tiếp (còn {left // 60}:{left % 60:02d}).")
            page.wait_for_timeout(2000)  # page.is_closed() / lỗi Target closed nếu người dùng đóng cửa sổ
        page.wait_for_timeout(1500)
        page.goto(url, wait_until="domcontentloaded", timeout=60_000)
        return True


class NeedsVerification(RuntimeError):
    pass


VERIFY_TIMEOUT = 600

# Đường dẫn cho thấy nền tảng đang chặn để đăng nhập / xác minh
BLOCKED_PATHS: dict[str, tuple[str, ...]] = {
    "facebook": ("/checkpoint", "two_step_verification", "/login", "/recover", "/two_factor"),
    "linkedin": ("/checkpoint", "/login", "/authwall", "/uas/login"),
    "x": ("/i/flow/login", "/account/access", "/i/flow/two-factor"),
    "reddit": ("/login", "/account/login"),
}


def is_blocked_url(platform: str, url: str) -> bool:
    return any(p in url for p in BLOCKED_PATHS.get(platform, ()))


def has_login_form(page) -> bool:
    """Trang đang hiện ô nhập mật khẩu = chưa đăng nhập (dù URL trông bình thường)."""
    try:
        return page.locator("input[type=password]:visible").count() > 0
    except Exception:  # noqa: BLE001 — trang đang chuyển hoặc đối tượng giả trong test
        return False


# Nhịp lướt. "fast": mặc định, đủ nhanh mà vẫn có quãng nghỉ; "careful": chậm hơn, ít bị nghi ngờ hơn.
PACE: dict[str, dict] = {
    "fast": {"settle": (1.5, 2.5), "expand": (0.2, 0.5), "scroll": (1800, 2800), "pause": (0.8, 1.6),
             "long_chance": 0.04, "long": (2, 4), "stale": 5},
    "careful": {"settle": (3, 5), "expand": (0.6, 1.2), "scroll": (900, 1700), "pause": (1.8, 4.2),
                "long_chance": 0.12, "long": (5, 9), "stale": 6},
}


def _human_pause(lo: float, hi: float) -> None:
    time.sleep(random.uniform(lo, hi))


def _group_url(src: str) -> str:
    src = src.strip()
    return src if src.startswith("http") else f"https://www.facebook.com/groups/{src}"


class FacebookScraper(Scraper):
    def __init__(self):
        super().__init__("facebook", FB_JS, FB_EXPAND_JS)

    def urls(self, source_type, sources):
        if source_type == "feed" or not sources:
            return [("Bảng tin Facebook", "https://www.facebook.com/")]
        if source_type == "group":
            return [(s, _group_url(s)) for s in sources]
        # search: "group_url_or_id | từ khóa" hoặc chỉ từ khóa (tìm bài viết toàn FB)
        out = []
        for s in sources:
            if "|" in s:
                g, q = (x.strip() for x in s.split("|", 1))
                out.append((f"{g} · {q}", f"{_group_url(g).rstrip('/')}/search/?q={quote_plus(q)}"))
            else:
                out.append((f"Tìm: {s}", f"https://www.facebook.com/search/posts/?q={quote_plus(s)}"))
        return out


class LinkedInScraper(Scraper):
    def __init__(self):
        super().__init__("linkedin", LINKEDIN_JS, LINKEDIN_EXPAND_JS)

    def urls(self, source_type, sources):
        if source_type == "search" and sources:
            return [(f"Tìm: {s}", "https://www.linkedin.com/search/results/content/?keywords="
                     + quote_plus(s) + "&sortBy=%22date_posted%22") for s in sources]
        if source_type == "group" and sources:
            return [(s, s if s.startswith("http") else f"https://www.linkedin.com/groups/{s}/") for s in sources]
        return [("Bảng tin LinkedIn", "https://www.linkedin.com/feed/")]


class XScraper(Scraper):
    def __init__(self):
        super().__init__("x", X_JS)

    def urls(self, source_type, sources):
        if source_type == "search" and sources:
            return [(f"Tìm: {s}", f"https://x.com/search?q={quote_plus(s)}&f=live") for s in sources]
        if source_type == "group" and sources:  # list hoặc community URL / @user
            return [(s, s if s.startswith("http") else f"https://x.com/{s.lstrip('@')}") for s in sources]
        return [("Bảng tin X", "https://x.com/home")]


class RedditScraper(Scraper):
    def __init__(self):
        super().__init__("reddit", REDDIT_JS)

    def urls(self, source_type, sources):
        if source_type == "search" and sources:
            return [(f"Tìm: {s}", f"https://www.reddit.com/search/?q={quote_plus(s)}&sort=new") for s in sources]
        if source_type == "group" and sources:
            return [(s, s if s.startswith("http") else f"https://www.reddit.com/r/{s.removeprefix('r/')}/new/")
                    for s in sources]
        return [("Trang chủ Reddit", "https://www.reddit.com/")]


SCRAPERS: dict[str, type[Scraper]] = {
    "facebook": FacebookScraper,
    "linkedin": LinkedInScraper,
    "x": XScraper,
    "reddit": RedditScraper,
}
