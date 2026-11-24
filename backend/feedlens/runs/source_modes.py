"""Validated source planning shared by local, cookie and agent runners.

normalize(req) returns four-field SourceTargets; it never opens a browser or
mutates req. Each count is per source. Runners must additionally enforce their
configured global max_posts via total_target(req, max_posts).
"""
from __future__ import annotations

import re
from typing import NamedTuple
from urllib.parse import parse_qs
from urllib.parse import quote
from urllib.parse import urlencode
from urllib.parse import urlsplit

from feedlens.core.models import EmptyOptions
from feedlens.core.models import FacebookGroupOptions
from feedlens.core.models import LinkedInJobsOptions
from feedlens.core.models import LinkedInPostsOptions
from feedlens.core.models import RedditSearchOptions
from feedlens.core.models import RedditSubredditOptions
from feedlens.core.models import RunRequest

MODE_OPTIONS = {
    "facebook": {"feed": EmptyOptions, "group": FacebookGroupOptions,
                 "search": EmptyOptions, "page": EmptyOptions},
    "linkedin": {"jobs": LinkedInJobsOptions, "recruiting_posts": LinkedInPostsOptions,
                 "feed": EmptyOptions, "legacy_group": EmptyOptions},
    "reddit": {"subreddit": RedditSubredditOptions, "search": RedditSearchOptions, "home": EmptyOptions},
    "x": {"search": EmptyOptions, "account": EmptyOptions, "list": EmptyOptions,
          "feed": EmptyOptions, "legacy_group": EmptyOptions},
}
_HOSTS = {"facebook": {"facebook.com", "www.facebook.com", "m.facebook.com"},
          "linkedin": {"linkedin.com", "www.linkedin.com"},
          "reddit": {"reddit.com", "www.reddit.com", "old.reddit.com"},
          "x": {"x.com", "www.x.com", "twitter.com", "www.twitter.com"}}
_IDENTIFIER = r"[A-Za-z0-9_.-]+"


class SourceTarget(NamedTuple):
    label: str
    url: str
    chronological: bool
    per_target_count: int


def allocate_targets(targets: list[SourceTarget], max_posts: int) -> list[SourceTarget]:
    """Water-fill quotas; preserve source order and give remainders to earlier sources."""
    budget = min(max(0, max_posts), sum(t.per_target_count for t in targets))
    quotas = [0] * len(targets)
    pending = list(range(len(targets)))
    while pending:
        share, remainder = divmod(budget, len(pending))
        small = [i for i in pending if targets[i].per_target_count <= share]
        if small:
            for i in small:
                quotas[i] = targets[i].per_target_count
                budget -= quotas[i]
            pending = [i for i in pending if targets[i].per_target_count > share]
        else:
            for rank, i in enumerate(pending):
                quotas[i] = share + (rank < remainder)
            break
    return [t._replace(per_target_count=quota) for t, quota in zip(targets, quotas)]


def _path(value: str, platform: str) -> tuple[str, dict]:
    """Only approved hosts and public web URLs, never credentials or custom ports."""
    if re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", value) or value.startswith("//"):
        u = urlsplit(value)
        if (u.scheme not in {"http", "https"} or u.hostname not in _HOSTS[platform]
                or u.username is not None or u.password is not None or u.port not in {None, 80, 443}):
            raise ValueError(f"Invalid {platform} source host")
        return u.path.strip("/"), parse_qs(u.query)
    if ":" in value or "?" in value or "#" in value or "\\" in value:
        raise ValueError("Invalid source path")
    return value.strip("/"), {}


def _identifier(value: str, pattern: str = _IDENTIFIER) -> str:
    if not re.fullmatch(pattern, value) or value in {".", ".."}:
        raise ValueError("Invalid source identifier")
    return value


def _x_kind(source: str) -> str:
    path, _ = _path(source.strip(), "x")
    if re.fullmatch(r"i/lists/\d+", path) or path.isdigit():
        return "list"
    if re.fullmatch(r"@?[A-Za-z0-9_]{1,15}", path):
        return "account"
    return "legacy_group"


def prepare_request(data: dict) -> dict:
    """Pydantic before-validator: infer legacy modes without rewriting stored rows.

    Legacy Facebook groups retain their old ranking (latest=False); an explicit
    group mode defaults to latest=True. Legacy LinkedIn search keeps its exact
    query and time range instead of silently appending hiring or a date filter.
    """
    result = dict(data)
    platform, source_type = result.get("platform"), result.get("source_type", "feed")
    if not isinstance(platform, str) or platform not in MODE_OPTIONS:
        raise ValueError("Invalid platform")
    if not isinstance(source_type, str) or source_type not in {"feed", "group", "search"}:
        raise ValueError("Invalid source_type")
    mode = result.get("mode")
    legacy = mode is None
    if not legacy and not isinstance(mode, str):
        raise ValueError("Mode must be a string")
    sources = result.get("sources") or []
    if legacy:
        if platform == "linkedin":
            mode = {"feed": "feed", "group": "legacy_group", "search": "recruiting_posts"}[source_type]
        elif platform == "reddit":
            mode = {"feed": "home", "group": "subreddit", "search": "search"}[source_type]
        elif platform == "x" and source_type == "group":
            kinds = {_x_kind(s) for s in sources if isinstance(s, str)}
            mode = next(iter(kinds)) if len(kinds) == 1 else "legacy_group"
        else:
            mode = source_type
    options_cls = MODE_OPTIONS[platform].get(mode)
    if options_cls is None:
        raise ValueError(f"Invalid mode for {platform}: {mode}")
    options = result.get("options", {})
    if isinstance(options, EmptyOptions):
        options = options.model_dump()
    if not isinstance(options, dict):
        raise ValueError("Mode options must be an object")
    if legacy and not options:
        if platform == "facebook" and mode == "group":
            options = {"latest": False}
        if platform == "linkedin" and mode == "recruiting_posts":
            options = {"posted_within": None, "hiring": False}
    result["mode"] = mode
    result["options"] = options_cls.model_validate(options)
    result["source_type"] = ("feed" if mode in {"feed", "home"} else
                             "search" if mode in {"search", "jobs", "recruiting_posts"} else "group")
    if platform == "linkedin" and mode == "jobs":
        keywords = result["options"].keywords.strip()
        if not keywords:
            raise ValueError("Job keywords must not be blank")
        result["options"].keywords = keywords
        result["sources"] = [keywords]
        result["job_mode"] = True
    return result


def effective_mode(req: RunRequest) -> str:
    return req.mode or prepare_request(req.model_dump())["mode"]


def normalize(req: RunRequest, max_posts: int = 500) -> list[SourceTarget]:
    """Return [(label, url, chronological, per_target_count)], validating every source.

    Validates model_copy updates too. Empty source lists are accepted only for
    feed/home (Jobs creates its one query source from options). Removes duplicate
    canonical URLs, preserves order and shares the cap fairly across all sources.
    Reddit is additionally capped at 100, X search at 60.
    Raises ValueError/Pydantic ValidationError before any browser side effect.
    """
    req = RunRequest.model_validate(req.model_dump())
    platform, mode, opts = req.platform, req.mode, req.options
    bases = {"facebook": "https://www.facebook.com", "linkedin": "https://www.linkedin.com",
             "reddit": "https://www.reddit.com", "x": "https://x.com"}
    base = bases[platform]
    cap = min(max_posts, 100) if platform == "reddit" else min(max_posts, 60) if platform == "x" and mode == "search" else max_posts
    if mode in {"feed", "home"}:
        suffix = {"facebook": "/", "linkedin": "/feed/", "reddit": "/", "x": "/home"}[platform]
        return allocate_targets([SourceTarget(platform, base + suffix, False, req.count)], cap)
    if not req.sources:
        raise ValueError("At least one source is required")
    result, seen = [], set()
    for value in req.sources:
        source = value.strip()
        if not source or len(source) > 2000:
            raise ValueError("Invalid source length")
        chronological = False
        if platform == "facebook":
            if mode == "search":
                if "|" in source:
                    group, query = (s.strip() for s in source.split("|", 1))
                    path, _ = _path(group, platform)
                    group_id = _identifier(path.removeprefix("groups/"))
                    if not query:
                        raise ValueError("Search keywords must not be blank")
                    url = f"{base}/groups/{group_id}/search/?{urlencode({'q': query})}"
                else:
                    url = f"{base}/search/posts/?{urlencode({'q': source})}"
            else:
                path, query = _path(source, platform)
                if mode == "group":
                    group_id = _identifier(path.removeprefix("groups/"))
                    url = f"{base}/groups/{group_id}"
                    chronological = opts.latest
                    if opts.latest:
                        url += "?sorting_setting=CHRONOLOGICAL"
                    elif query.get("sorting_setting") == ["CHRONOLOGICAL"]:
                        url += "?sorting_setting=CHRONOLOGICAL"
                        chronological = True
                else:
                    if path == "profile.php":
                        ids = query.get("id", [])
                        if len(ids) != 1:
                            raise ValueError("Expected one Facebook Page id")
                        page_id = _identifier(ids[0], r"\d+")
                        url = f"{base}/profile.php?{urlencode({'id': page_id})}"
                    else:
                        slug = _identifier(path)
                        if slug.lower() in {"groups", "search", "home.php", "login", "login.php", "watch", "ads", "reel", "photo.php", "profile.php"}:
                            raise ValueError("Expected a Facebook Page slug")
                        url = f"{base}/{quote(slug)}/"
                    chronological = True
        elif platform == "linkedin":
            if mode == "jobs":
                params = {"keywords": opts.keywords,
                          "f_TPR": {"day": "r86400", "week": "r604800", "month": "r2592000"}[opts.posted_within],
                          "sortBy": "DD"}
                if opts.location.strip():
                    params["location"] = opts.location.strip()
                if opts.work_modes:
                    params["f_WT"] = ",".join(dict.fromkeys({"onsite": "1", "remote": "2", "hybrid": "3"}[m] for m in opts.work_modes))
                url, chronological = f"{base}/jobs/search/?{urlencode(params)}", True
            elif mode == "recruiting_posts":
                query = source + (" hiring" if opts.hiring and not re.search(r"\bhiring\b", source, re.I) else "")
                params = {"keywords": query, "sortBy": '"date_posted"'}
                if opts.posted_within:
                    params["datePosted"] = '"past-24h"' if opts.posted_within == "day" else '"past-week"'
                url, chronological = f"{base}/search/results/content/?{urlencode(params)}", True
            else:
                path, _ = _path(source, platform)
                group_id = _identifier(path.removeprefix("groups/"))
                url = f"{base}/groups/{group_id}/"
        elif platform == "reddit":
            if mode == "search":
                url = f"{base}/search/?{urlencode({'q': source, 'sort': opts.sort})}"
                chronological = opts.sort == "new"
            else:
                path, _ = _path(source, platform)
                match = re.fullmatch(r"(?:r/)?([A-Za-z0-9_]{1,21})(?:/(?:new|top))?", path)
                if not match:
                    raise ValueError("Expected a subreddit name or URL")
                slug = match[1]
                chronological = opts.sort == "new"
                url = f"{base}/r/{slug}/new/" if chronological else f"{base}/r/{slug}/top/?t={'day' if opts.sort == 'top_day' else 'week'}"
        else:
            if mode == "search":
                url, chronological = f"{base}/search?{urlencode({'q': source, 'f': 'live'})}", True
            else:
                path, _ = _path(source, platform)
                kind = _x_kind(source) if mode == "legacy_group" else mode
                if kind == "list":
                    list_id = _identifier(path.removeprefix("i/lists/"), r"\d+")
                    url, chronological = f"{base}/i/lists/{list_id}", True
                elif kind == "account":
                    handle = _identifier(path.lstrip("@"), r"[A-Za-z0-9_]{1,15}")
                    if handle.lower() in {"home", "search", "login", "logout", "settings", "explore", "notifications", "messages", "i"}:
                        raise ValueError("Expected an X account handle")
                    url, chronological = f"{base}/{handle}", True
                elif re.fullmatch(r"i/communities/\d+", path):
                    url = f"{base}/{path}"
                else:
                    raise ValueError("Invalid legacy X source")
        if url in seen:
            continue
        seen.add(url)
        result.append(SourceTarget(source, url, chronological, req.count))
    return allocate_targets(result, cap)


def total_target(req: RunRequest, max_posts: int = 500) -> int:
    """Effective total after duplicate-source, per-platform and global caps."""
    return sum(t.per_target_count for t in normalize(req, max_posts))


def legacy_agent_compatible(req: RunRequest) -> bool:
    """Only permit modes whose options have identical legacy scraper semantics."""
    req = RunRequest.model_validate(req.model_dump())
    if req.platform == "reddit" or req.platform == "x" and req.mode == "search":
        cap = 100 if req.platform == "reddit" else 60
        source_count = 1 if req.mode in {"feed", "home"} else len(req.sources)
        if req.count * source_count > cap:
            return False
    if req.mode in {"page", "jobs"}:
        return False
    if req.platform == "facebook" and req.mode == "group":
        return not req.options.latest
    if req.platform == "linkedin" and req.mode == "recruiting_posts":
        return not req.options.hiring and req.options.posted_within is None
    if req.platform == "reddit" and req.mode in {"subreddit", "search"}:
        return req.options.sort == "new"
    # A bare List ID was not a supported legacy group source (it became /<id>).
    if req.platform == "x" and req.mode in {"list", "legacy_group"}:
        return not any(s.strip().isdigit() for s in req.sources)
    return True
