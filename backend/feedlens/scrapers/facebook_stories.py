"""Facebook GraphQL story capture and matching."""
from __future__ import annotations

import base64
import json
import re
from datetime import datetime, timezone
from difflib import SequenceMatcher
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit
from ..models import RawPost
from .facebook_links import (
    clean_facebook_author,
    facebook_ad_link,
    is_facebook_content_url,
    select_facebook_link,
)


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
        self.by_id: dict[str, dict] = {}
        self.link_resolve_s: float = 0.0
        self.track_timings: bool = False
        self.skip_keys: set[str] | None = None
        self.hover_attempts: dict[tuple, set[int]] = {}
        self.hover_links: dict[tuple, str] = {}
        self.response_count = 0


def _extract_facebook_post_id(url: str) -> str:
    if not url:
        return ""
    match = re.search(r"/(?:posts|permalink)/([0-9]+|pfbid[A-Za-z0-9]+)", url)
    if match:
        return match.group(1)
    match = re.search(r"[?&]story_fbid=([0-9]+|pfbid[A-Za-z0-9]+)", url)
    return match.group(1) if match else ""


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
        stack.extend(value for k, value in node.items() if k != "attached_story" and isinstance(value, (dict, list)))
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
        has_attachment = any(isinstance(view.get("attachments"), list) and len(view["attachments"]) > 0 for view in views)
        if not isinstance(text, str):
            text = ""
        if len(text.strip()) < 15:
            if not has_attachment:
                continue
            if not text.strip():
                for view in views:
                    for wrapper in view.get("attachments", []) if isinstance(view.get("attachments"), list) else []:
                        if not isinstance(wrapper, dict):
                            continue
                        styles = wrapper.get("styles")
                        att = styles.get("attachment") if isinstance(styles, dict) else wrapper
                        if not isinstance(att, dict):
                            continue
                        media = att.get("media") if isinstance(att.get("media"), dict) else {}
                        caption = (
                            (att.get("title") or {}).get("text") if isinstance(att.get("title"), dict) else ""
                        ) or media.get("accessibility_caption") or (
                            (att.get("description") or {}).get("text") if isinstance(att.get("description"), dict) else ""
                        )
                        if isinstance(caption, str) and caption.strip():
                            text = caption.strip()
                            break
                    if text.strip():
                        break
                if not text.strip():
                    text = "[Ảnh/Đính kèm]"
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
        group_id = ""
        group_url_target = ""
        for view in views:
            target = view.get("to")
            if isinstance(target, dict) and target.get("__typename") == "Group":
                if target.get("id"):
                    group_id = str(target["id"])
                if isinstance(target.get("url"), str):
                    group_url_target = target["url"]
                if group_id:
                    break
        has_group_identity = bool(group_id) or any("/groups/" in h for h, _ in urls)
        try:
            creation_ts = int(created) if created else 0
        except (ValueError, TypeError):
            creation_ts = 0
        post_id = _extract_facebook_post_id(url) or next((fid for v in views if (fid := facebook_story_id(v))), "")
        record = dict(text=text[:20000], author=clean_facebook_author(str(actor.get("name") or "")), url=url,
                      posted_at=posted_at,
                      sponsored=bool(sponsored or any(facebook_ad_link(h) for h, _ in urls)),
                      _group_id=group_id, _group_url=group_url_target,
                      _has_group_identity=has_group_identity,
                      _post_id=post_id, _creation_time=creation_ts)
        record["_debug_story"] = sanitize_facebook_debug(node)
        fp = RawPost(platform="facebook", source="", **record).fingerprint
        story_key = f"id:{post_id}" if post_id else f"fp:{fp}"
        previous = found.get(story_key)
        if previous and previous["url"] and record["url"] and previous["url"].rstrip("/") != record["url"].rstrip("/"):
            previous["_conflict"] = True
        if not previous or (record["url"] and not previous["url"]) or record["sponsored"]:
            if previous:
                record["sponsored"] |= previous["sponsored"]
                record["_conflict"] = bool(record.get("_conflict") or previous.get("_conflict"))
            found[story_key] = record
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
            record["_text_key"] = re.sub(r"\s+", " ", record["text"].lower()).strip()[:500]
            previous = cache.get(fp)
            if previous:
                record_for_fp = dict(record)
                record_for_fp["sponsored"] |= previous["sponsored"]
                record_for_fp["_conflict"] = bool(record.get("_conflict") or previous.get("_conflict") or
                    (previous["url"] and record["url"] and previous["url"].rstrip("/") != record["url"].rstrip("/")))
                if record["url"] or record["sponsored"]:
                    cache[fp] = record_for_fp
                else:
                    previous["_conflict"] = record_for_fp["_conflict"]
            else:
                cache[fp] = record
            if len(cache) > 1500: cache.pop(next(iter(cache)))
            by_id = getattr(cache, "by_id", None)
            if by_id is not None:
                story_key = f"id:{record['_post_id']}" if record.get("_post_id") else f"fp:{fp}"
                prev_id = by_id.get(story_key)
                if prev_id:
                    merged = dict(record)
                    merged["sponsored"] |= prev_id["sponsored"]
                    merged["_conflict"] = bool(merged.get("_conflict") or prev_id.get("_conflict") or (
                        merged["url"] and prev_id["url"] and merged["url"].rstrip("/") != prev_id["url"].rstrip("/")))
                    if not merged["url"] and prev_id["url"]:
                        merged["url"] = prev_id["url"]
                    if not merged["_creation_time"] and prev_id.get("_creation_time"):
                        merged["_creation_time"] = prev_id["_creation_time"]
                        merged["posted_at"] = prev_id["posted_at"]
                    by_id[story_key] = merged
                else:
                    by_id[story_key] = dict(record)
                if len(by_id) > 1500: by_id.pop(next(iter(by_id)))


def _match_facebook_story_by_id(post_id: str, cache: dict) -> dict | None:
    story = getattr(cache, "by_id", {}).get(f"id:{post_id}") if post_id else None
    return story if story and not story.get("_conflict") else None


def match_facebook_story(post: RawPost, cache: dict) -> dict | None:
    post_id = _extract_facebook_post_id(post.url)
    def consistent(story):
        return not post_id or not story.get("_post_id") or story["_post_id"] == post_id

    if post.fingerprint in cache:
        exact = cache[post.fingerprint]
        if not consistent(exact):
            return None
        return ({**exact, "url": ""} if exact["sponsored"] else None) if exact.get("_conflict") else exact
    prefix = re.sub(r"\s+", " ", post.text.lower()).strip()
    prefix = re.sub(r"(?:…|\.\.\.)?\s*(?:see more|xem thêm|查看更多)$", "", prefix).strip()[:500]
    # A Page's short caption can be followed by a longer DOM link preview.
    # That reverse match additionally requires the exact author, and stays ambiguous if duplicated.
    author = clean_facebook_author(post.author).casefold()
    matches = [story for story in cache.values() if consistent(story) and not story.get("_conflict") and (
               (len(prefix) >= 80 and story["_text_key"].startswith(prefix)) or
               (len(story["_text_key"]) >= 15 and author and
                author == clean_facebook_author(story["author"]).casefold() and
                prefix.startswith(story["_text_key"] + " ")))]
    return matches[0] if len(matches) == 1 else None


def _normalize_fb_prefix(text: str) -> str:
    cleaned = re.sub(r"[\u200b\u2060\ufeff]", "", text)
    norm = re.sub(r"\s+", " ", cleaned).strip()
    norm = re.sub(r"(?:…|\.\.\.)?\s*(?:see more|xem thêm|查看更多)$", "", norm, flags=re.IGNORECASE).strip()
    return re.sub(r"(?:…|\.\.\.)+$", "", norm).strip()


def _facebook_story_belongs_to_group(story: dict, group_url: str) -> bool:
    src_match = re.search(r"/groups/([\w.-]+)", group_url)
    if not src_match or not story.get("_has_group_identity"):
        return False
    src_slug = src_match.group(1)
    story_url = story.get("url") or ""
    if not is_facebook_content_url(story_url):
        return False
    st_match = re.search(r"/groups/([\w.-]+)", story_url)
    st_slug = st_match.group(1) if st_match else (story.get("_group_id") or "")
    if not st_slug:
        return False
    if src_slug.isdigit() and st_slug.isdigit():
        return src_slug == st_slug
    if not src_slug.isdigit() and not st_slug.isdigit():
        return src_slug.casefold() == st_slug.casefold()
    target_url = story.get("_group_url") or ""
    t_match = re.search(r"/groups/([\w.-]+)", target_url)
    if t_match and not t_match.group(1).isdigit() and not src_slug.isdigit():
        return t_match.group(1).casefold() == src_slug.casefold()
    return True


def _is_other_facebook_group(source_url: str, story: dict) -> bool:
    src_match = re.search(r"/groups/([\w.-]+)", source_url)
    if not src_match:
        return False
    src_slug = src_match.group(1)
    story_url = story.get("url") or ""
    st_match = re.search(r"/groups/([\w.-]+)", story_url)
    st_slug = st_match.group(1) if st_match else (story.get("_group_id") or "")
    if not st_slug:
        return False
    if src_slug.isdigit() and st_slug.isdigit():
        return src_slug != st_slug
    if not src_slug.isdigit() and not st_slug.isdigit():
        return src_slug.casefold() != st_slug.casefold()
    return False


def _should_use_story_text(dom_text: str, story: dict, source_url: str = "") -> bool:
    story_text = story.get("text") or ""
    if not story_text or _is_other_facebook_group(source_url, story):
        return False
    if len(story_text.strip()) <= len(dom_text.strip()):
        return False
    dom_norm = _normalize_fb_prefix(dom_text).casefold()
    story_norm = re.sub(r"[\u200b\u2060\ufeff]", "", re.sub(r"\s+", " ", story_text)).strip().casefold()
    if len(story_norm) <= len(dom_norm) or not dom_norm:
        return False
    if story_norm.startswith(dom_norm):
        return True
    if len(dom_norm) >= 80:
        return SequenceMatcher(None, dom_norm, story_norm[:len(dom_norm)]).ratio() >= 0.9
    return False


def capture_facebook_response(response, cache: dict, group_url: str = "") -> None:
    try:
        url = urlsplit(response.url)
        if url.hostname not in {"www.facebook.com", "facebook.com", "m.facebook.com"} or url.path.rstrip("/") != "/api/graphql" or response.status != 200:
            return
        if isinstance(cache, FacebookStoryCache):
            cache.response_count += 1
        cache_facebook_stories(response.text(), cache, group_url)
    except Exception:  # noqa: BLE001 — network enrichment must not interrupt DOM scraping
        return
