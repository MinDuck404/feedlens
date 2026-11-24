"""Search persistence for Database."""
from __future__ import annotations

import re
import heapq
import unicodedata
from datetime import date
from typing import Any
from sqlalchemy import select, text
from .tables import PostRow, RunRow


def _parse_post_date(posted_at: str | None, run_created_at: Any) -> date:
    from feedlens.routes.trends import parse_post_date
    return parse_post_date(posted_at, run_created_at)[0]


def _work_mode(value: str) -> str:
    value = value.casefold()
    aliases = {"remote": ("remote", "wfh", "từ xa", "远程"), "hybrid": ("hybrid", "kết hợp", "混合"), "onsite": ("onsite", "on-site", "tại văn phòng", "现场", "到岗")}
    return next((key for key, words in aliases.items() if any(word in value for word in words)), value)


def _location(value: str) -> str:
    folded = "".join(char for char in unicodedata.normalize("NFKD", value.casefold().replace("đ", "d")) if not unicodedata.combining(char))
    normalized = re.sub(r"[^a-z0-9\u4e00-\u9fff]", "", folded)
    return "hochiminh" if normalized in {"hcm", "tphcm", "saigon"} else normalized


def _salary_vnd(value: str) -> int | None:
    if re.search(r"\$|usd|/year|per year|per annum|annual|yearly|/năm|mỗi năm", value, re.I):
        return None  # No exchange-rate or annual-salary guesses.
    match = re.search(r"(\d[\d.,]*)(?:\s*[-–~]\s*(\d[\d.,]*))?\s*(triệu|tr\b|m\b|million|k\b|nghìn)?", value, re.I)
    if not match:
        return None
    number = match[1].rstrip(".,")
    if len(number) > 20:
        return None
    unit = (match[3] or "").lower()
    if unit:
        multiplier = 1000 if unit in {"k", "nghìn"} else 1_000_000
        return int(float(number.replace(",", ".")) * multiplier) if number.count(".") + number.count(",") <= 1 else None
    digits = re.sub(r"[.,]", "", number)
    return int(digits) if digits.isdigit() and int(digits) >= 1_000_000 else None


def _make_snippet(text: str, summary: str, words: list[str]) -> str:
    target = summary if summary else text
    if not words:
        return target[:200] + ("…" if len(target) > 200 else "")

    lower_target = target.lower()
    first_pos = -1
    for w in words:
        pos = lower_target.find(w.lower())
        if pos != -1 and (first_pos == -1 or pos < first_pos):
            first_pos = pos

    if first_pos == -1 and text and text != target:
        target = text
        lower_target = target.lower()
        for w in words:
            pos = lower_target.find(w.lower())
            if pos != -1 and (first_pos == -1 or pos < first_pos):
                first_pos = pos

    if first_pos == -1:
        return target[:200] + ("…" if len(target) > 200 else "")

    start = max(0, first_pos - 60)
    end = min(len(target), first_pos + 140)
    snip = target[start:end]
    if start > 0:
        snip = "…" + snip
    if end < len(target):
        snip = snip + "…"

    pattern = "|".join(re.escape(word) for word in sorted(set(words), key=len, reverse=True))
    snip = re.sub(pattern, lambda match: "«" + match[0] + "»", snip, flags=re.I)
    return snip


class SearchMixin:
    def init_search_index(self) -> bool:
        """Thiết lập FTS5 cho SQLite nếu được hỗ trợ, đồng bộ bài cũ và trigger."""
        if self.engine.dialect.name != "sqlite":
            return False
        try:
            with self.engine.begin() as conn:
                conn.exec_driver_sql("BEGIN IMMEDIATE")  # Keep index repair and trigger replacement atomic for concurrent writers.
                conn.execute(text("""
                    CREATE VIRTUAL TABLE IF NOT EXISTS posts_fts USING fts5(
                        post_id UNINDEXED,
                        text,
                        summary,
                        author,
                        source,
                        tokenize = 'unicode61'
                    );
                """))
                # Older indexes used an unrelated FTS rowid and scanned post_id on every update.
                if conn.execute(text("SELECT 1 FROM posts_fts WHERE rowid != post_id LIMIT 1")).first():
                    conn.execute(text("DELETE FROM posts_fts"))
                for trigger in ("posts_ai", "posts_ad", "posts_au"):
                    conn.execute(text(f"DROP TRIGGER IF EXISTS {trigger}"))
                conn.execute(text("""
                    CREATE TRIGGER posts_ai AFTER INSERT ON posts BEGIN
                        INSERT INTO posts_fts(rowid, post_id, text, summary, author, source)
                        VALUES (new.id, new.id, new.text, new.summary, new.author, new.source);
                    END;
                """))
                conn.execute(text("""
                    CREATE TRIGGER posts_ad AFTER DELETE ON posts BEGIN
                        DELETE FROM posts_fts WHERE rowid = old.id;
                    END;
                """))
                conn.execute(text("""
                    CREATE TRIGGER posts_au AFTER UPDATE OF text, summary, author, source ON posts BEGIN
                        DELETE FROM posts_fts WHERE rowid = old.id;
                        INSERT INTO posts_fts(rowid, post_id, text, summary, author, source)
                        VALUES (new.id, new.id, new.text, new.summary, new.author, new.source);
                    END;
                """))
                conn.execute(text("""
                    INSERT INTO posts_fts(rowid, post_id, text, summary, author, source)
                    SELECT id, id, text, summary, author, source FROM posts
                    WHERE id NOT IN (SELECT rowid FROM posts_fts);
                """))
            return True
        except Exception:
            return False

    def search_posts(
        self,
        user_id: int,
        q: str = "",
        platform: str | None = None,
        categories: list[str] | None = None,
        topic_ids: list[int] | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        job_only: bool = False,
        work_modes: list[str] | None = None,
        min_score: int | None = None,
        min_salary_vnd: int | None = None,
        locations: list[str] | None = None,
        match_type: str | None = None,
        has_link: bool | None = None,
        has_github: bool | None = None,
        limit: int = 40,
        offset: int = 0,
        _use_fts: bool = True,
    ) -> tuple[list[dict], int]:
        if not hasattr(self, "_fts_ready"):
            self._fts_ready = self.init_search_index()

        words = [w for w in re.findall(r"[\w\.\-]+", q.strip()) if len(w) > 0] if q else []
        if q.strip() and not words:
            words = [q.strip()]
            _use_fts = False  # Preserve literal symbols instead of silently returning every post.

        stmt = (
            select(PostRow, RunRow.created_at)
            .join(RunRow, PostRow.run_id == RunRow.id)
            .where(RunRow.user_id == user_id)
            .where(self.representative_posts_filter())
        )

        if platform:
            stmt = stmt.where(PostRow.platform == platform)
        if categories:
            stmt = stmt.where(PostRow.category.in_(categories))

        try_fts = bool(words and self._fts_ready and _use_fts and not re.search(r"[\u3400-\u9fff]", q))
        if try_fts:
            # Prefix query for each word, combined with AND, safe from raw user input injection
            escaped = [w.replace('"', '""') for w in words[:40]]
            fts_query = " AND ".join(f'"{w}"*' for w in escaped)
            owned_matches = text("SELECT posts_fts.rowid AS post_id FROM posts_fts JOIN posts p ON p.id = posts_fts.rowid JOIN runs r ON r.id = p.run_id WHERE posts_fts MATCH :fts_query AND r.user_id = :fts_owner").bindparams(fts_query=fts_query, fts_owner=user_id).columns(post_id=PostRow.id.type)
            stmt = stmt.where(PostRow.id.in_(select(owned_matches.subquery().c.post_id)))
        elif words:
            for word in words[:40]:
                pattern = "%" + word.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
                stmt = stmt.where(PostRow.text.ilike(pattern, escape="\\") | PostRow.summary.ilike(pattern, escape="\\") | PostRow.author.ilike(pattern, escape="\\") | PostRow.source.ilike(pattern, escape="\\"))

        stmt = stmt.order_by(PostRow.id.desc())
        matched = []
        total = 0
        # Metadata dates/job text still need Python normalization; stream rows and retain only this page.
        with self.Session() as session:
            try:
                rows_iter = session.execute(stmt.execution_options(yield_per=500))
            except Exception:
                if try_fts:
                    return self.search_posts(
                        user_id=user_id, q=q, platform=platform, categories=categories,
                        topic_ids=topic_ids, date_from=date_from, date_to=date_to,
                        job_only=job_only, work_modes=work_modes, min_score=min_score,
                        min_salary_vnd=min_salary_vnd, locations=locations, match_type=match_type,
                        has_link=has_link, has_github=has_github, limit=limit, offset=offset,
                        _use_fts=False
                    )
                raise
            for post, r_created_at in rows_iter:
                p_date = _parse_post_date(post.posted_at, r_created_at)
                p_date_str = p_date.isoformat()

                if date_from and p_date_str < date_from:
                    continue
                if date_to and p_date_str > date_to:
                    continue

                if topic_ids:
                    p_topics = post.topic_ids or []
                    if not any(t in p_topics for t in topic_ids):
                        continue

                if job_only and post.category != "job" and not post.job:
                    continue
                if work_modes:
                    mode = (post.job or {}).get("work_mode", "").lower()
                    if not any(_work_mode(mode) == wm for wm in work_modes):
                        continue
                if min_score is not None:
                    score = (post.job or {}).get("match_score")
                    if score is None or score < min_score:
                        continue

                if min_salary_vnd is not None:
                    salary = _salary_vnd((post.job or {}).get("salary", ""))
                    if salary is None or salary < min_salary_vnd:
                        continue
                if locations and not any(_location(location) in _location((post.job or {}).get("location", "")) for location in locations):
                    continue
                if match_type and (post.job or {}).get("match_type") != match_type:
                    continue
                if has_link is not None:
                    has_u = bool(post.url and post.url.strip()) or "http://" in post.text or "https://" in post.text
                    if has_u != has_link:
                        continue
                if has_github is not None:
                    is_gh = bool(re.search(r"(?<![\w.-])(?:https?://)?(?:www\.)?github\.com(?=$|[/:?#\s)])", (post.url or "") + "\n" + post.text, re.I))
                    if is_gh != has_github:
                        continue

                total += 1
                if len(matched) >= offset + limit and (p_date_str, post.id) <= matched[0][:2]:
                    continue
                snippet = _make_snippet(post.text, post.summary, words)
                result = {
                    "id": post.id,
                    "run_id": post.run_id,
                    "platform": post.platform,
                    "source": post.source,
                    "author": post.author,
                    "text": post.text,
                    "summary": post.summary,
                    "snippet": snippet,
                    "url": post.url,
                    "posted_at": post.posted_at,
                    "date": p_date_str,
                    "category": post.category,
                    "job": post.job,
                    "topic_ids": list(post.topic_ids or []),
                    "topic_reason": post.topic_reason or "",
                }
                entry = (p_date_str, post.id, result)
                if len(matched) < offset + limit:
                    heapq.heappush(matched, entry)
                else:
                    heapq.heappushpop(matched, entry)

        matched.sort(reverse=True)
        return [entry[2] for entry in matched[offset:offset + limit]], total
