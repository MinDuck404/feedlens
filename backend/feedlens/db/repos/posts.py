"""Posts persistence for Database."""
from __future__ import annotations

from sqlalchemy import JSON
from sqlalchemy import Text
from sqlalchemy import case
from sqlalchemy import cast
from sqlalchemy import delete
from sqlalchemy import func
from sqlalchemy import or_
from sqlalchemy import select
from sqlalchemy import true
from feedlens.core.models import AnalyzedPost
from feedlens.core.models import JobInfo
from feedlens.core.models import JobSeed
from feedlens.core.models import PostGroup
from feedlens.core.models import RawPost
from feedlens.db.tables import PostRow
from feedlens.db.tables import RunRow


class PostsMixin:
    def save_raw_posts(self, run_id: int, posts: list[RawPost]) -> None:
        from feedlens.analysis.duplicates import preserve_post_identities
        posts = preserve_post_identities(posts)
        with self.Session.begin() as s:
            # Rekey legacy hash collisions in place before marking rows pending; preserve post IDs.
            existing = {}
            for row in s.scalars(select(PostRow).where(PostRow.run_id == run_id).order_by(PostRow.id)):
                key = (row.platform, row.source, row.url, row.text, row.author)
                existing.setdefault(key, []).append(row)
            for p in posts:
                matching = existing.get((p.platform, p.source, p.url, p.text, p.author), [])
                if matching:
                    matching.pop(0).fingerprint = p.fingerprint
            run = s.get(RunRow, run_id)
            if run:
                run.raw_posts = [p.model_dump(include=set(RawPost.model_fields)) for p in posts]
                run.raw_fingerprints = list(dict.fromkeys(p.fingerprint for p in posts))
                run.collected = len(posts)

    def get_raw_posts(self, run_id: int) -> list[RawPost]:
        with self.Session() as s:
            row = s.get(RunRow, run_id)
            return [RawPost(**p) for p in (row.raw_posts or [])] if row else []

    def save_post_groups(self, run_id: int, groups: list[PostGroup]) -> None:
        self.update_run(run_id, post_groups=[group.model_dump() for group in groups])

    def get_post_groups(self, run_id: int) -> list[PostGroup]:
        with self.Session() as s:
            row = s.get(RunRow, run_id)
            return [PostGroup.model_validate(group) for group in (row.post_groups or [])] if row else []

    def get_analysis_posts(self, run_id: int) -> list[RawPost]:
        # Older runs may have analyzed rows but no raw_posts snapshot; their original text is still usable.
        return self.get_raw_posts(run_id) or [RawPost.model_validate(p.model_dump()) for p in self.get_posts(run_id)]

    def can_continue_analysis(self, run_id: int, reanalyze_all: bool = False) -> bool:
        run = self.get_run(run_id)
        if not run or run["status"] in {"pending", "queued", "scraping", "analyzing"}:
            return False
        raw = self.get_analysis_posts(run_id)
        if reanalyze_all:
            return bool(raw)
        groups = self.get_post_groups(run_id)
        if groups:
            representatives = {group.fingerprint for group in groups}
            raw = [p for p in raw if p.fingerprint in representatives]
        request = run["request"]
        needs_ai = request.get("analysis_used_ai", request.get("ai_provider") != "offline" and not (
            run["status"] == "done" and run["ai_label"] == "bộ lọc từ khóa offline"))
        completed = {p.fingerprint for p in self.get_posts(run_id)
                     if p.analyzed and (not needs_ai or p.analyzed_by not in {"", "offline", "pending"})}
        return bool(raw) and (not run["digest"] or any(p.fingerprint not in completed for p in raw))

    def analysis_counts(self, run_id: int) -> dict[str, int]:
        with self.Session() as s:
            rows = s.execute(select(PostRow.fingerprint, PostRow.analyzed_by).where(PostRow.run_id == run_id))
            saved = set()
            ai = set()
            in_progress = set()
            for fingerprint, label in rows:
                saved.add(fingerprint)
                if label == "pending":
                    in_progress.add(fingerprint)
                elif label not in {"", "offline", "pending"}:
                    ai.add(fingerprint)
            raw_fingerprints = s.scalar(select(RunRow.raw_fingerprints).where(RunRow.id == run_id))
            if raw_fingerprints is None:
                raw = s.scalar(select(RunRow.raw_posts).where(RunRow.id == run_id)) or []
                raw_fingerprints = [RawPost.model_validate(p).fingerprint for p in raw]
        if fingerprints := set(raw_fingerprints):
            groups = self.get_post_groups(run_id)
            if groups:
                fingerprints = {group.fingerprint for group in groups}
            saved.intersection_update(fingerprints)
            ai.intersection_update(fingerprints)
            in_progress.intersection_update(fingerprints)
            pending = len(fingerprints - saved) + len(in_progress)
        else:
            pending = 0
        offline = len(saved - ai - in_progress)
        return {"ai": len(ai), "offline": offline, "pending": pending, "total": len(ai) + offline + pending}

    def mark_posts_pending(self, run_id: int) -> None:
        with self.Session.begin() as s:
            rows = s.scalars(select(PostRow).where(PostRow.run_id == run_id))
            for row in rows:
                row.analyzed_by = "pending"
                row.category, row.summary, row.job = "other", "", None
                row.topic_ids, row.topic_reason = [], ""
            run = s.get(RunRow, run_id)
            if run:
                run.ai_label = ""

    def save_batch(self, run_id: int, posts: list[AnalyzedPost]) -> None:
        """Checkpoint completed batches without replacing IDs used by applied-job markers."""
        with self.Session.begin() as s:
            rows = {}
            for row in s.scalars(select(PostRow).where(PostRow.run_id == run_id)):
                rows.setdefault(row.fingerprint, []).append(row)
            for p in posts:
                matching = rows.get(p.fingerprint)
                if not matching:
                    row = PostRow(run_id=run_id, fingerprint=p.fingerprint)
                    s.add(row)
                    matching = rows[p.fingerprint] = [row]
                for row in matching:
                    for key in RawPost.model_fields.keys() - {"job_seed", "storage_key"}:
                        setattr(row, key, getattr(p, key))
                    row.category, row.summary = p.category, p.summary
                    row.analyzed_by = "offline" if p.analyzed_by in {"", "bộ lọc từ khóa offline"} else p.analyzed_by
                    row.job = p.job.model_dump() if p.job else None
                    row.topic_ids, row.topic_reason = list(p.topic_ids), p.topic_reason
            run = s.get(RunRow, run_id)
            if run and rows:
                labels = {r.analyzed_by if r.analyzed_by != "offline" else "bộ lọc từ khóa offline"
                          for matching in rows.values() for r in matching if r.analyzed_by != "pending"}
                if labels:
                    run.ai_label = " + ".join(sorted(labels))
            self._keep_job_seeds(s, run_id, posts)

    def _keep_job_seeds(self, session, run_id: int, posts: list[AnalyzedPost]) -> None:
        # Seed identity must survive reload even for imports without a raw checkpoint.
        if not any(p.job_seed for p in posts):
            return
        run = session.get(RunRow, run_id)
        if run:
            raw = {RawPost(**p).fingerprint: p for p in (run.raw_posts or [])}
            for p in posts:
                if p.job_seed:
                    raw[p.fingerprint] = p.model_dump(include=set(RawPost.model_fields))
            run.raw_posts = list(raw.values())
            run.raw_fingerprints = list(raw)

    def known_fingerprints(self, platform: str, user_id: int | None = None) -> set[str]:
        q = (select(PostRow.fingerprint).join(RunRow)
             .where(PostRow.platform == platform, RunRow.user_id == user_id))
        sqlite = self.engine.dialect.name == "sqlite"
        array_type = func.json_type(RunRow.raw_posts) if sqlite else func.json_typeof(RunRow.raw_posts)
        unfinished = (select(RunRow.raw_posts).where(
            RunRow.user_id == user_id, RunRow.request["platform"].as_string() == platform,
            array_type == "array",
            or_(RunRow.status.in_(("analyzing", "analysis_failed")), RunRow.digest.is_(None),
                cast(RunRow.digest, Text).in_(("null", "{}", "[]", ""))),
        ).subquery())
        entries = (func.json_each(unfinished.c.raw_posts) if sqlite else
                   func.json_array_elements(unfinished.c.raw_posts)).table_valued("value")
        if sqlite:
            raw_platform = func.json_extract(entries.c.value, "$.platform")
            raw_text = func.json_extract(entries.c.value, "$.text")
            job_id = func.json_extract(entries.c.value, "$.job_seed.job_id")
        else:
            value = cast(entries.c.value, JSON)
            raw_platform, raw_text = value["platform"].as_string(), value["text"].as_string()
            job_id = value["job_seed"]["job_id"].as_string()
        # Legacy raw JSON has no stored hash. Project only its hash inputs, not whole run payloads.
        raw_query = (select(raw_text, job_id).select_from(unfinished.join(entries, true()))
                     .where(raw_platform == platform))
        with self.Session() as s:
            known = set(s.scalars(q))
            for body, external_id in s.execute(raw_query).yield_per(100):
                if isinstance(body, str):
                    seed = JobSeed(job_id=external_id) if external_id else None
                    known.add(RawPost(platform=platform, source="", text=body, job_seed=seed).fingerprint)
            return known

    def save_posts(self, run_id: int, posts: list[AnalyzedPost]) -> None:
        with self.Session.begin() as s:
            s.execute(delete(PostRow).where(PostRow.run_id == run_id))
            s.add_all(PostRow(
                run_id=run_id, platform=p.platform, source=p.source, author=p.author, text=p.text,
                url=p.url, posted_at=p.posted_at, fingerprint=p.fingerprint, category=p.category,
                summary=p.summary, job=p.job.model_dump() if p.job else None,
                analyzed_by="offline" if p.analyzed_by in {"", "bộ lọc từ khóa offline"} else p.analyzed_by,
                topic_ids=list(p.topic_ids), topic_reason=p.topic_reason,
            ) for p in posts)
            self._keep_job_seeds(s, run_id, posts)

    def get_posts(self, run_id: int, include_raw: bool = False) -> list[AnalyzedPost]:
        """Return canonical posts; unfinished groups can have analyzed=False placeholders."""
        with self.Session() as s:
            rows = s.scalars(select(PostRow).where(PostRow.run_id == run_id).order_by(PostRow.id)).all()
            posts = [AnalyzedPost(
                id=r.id, platform=r.platform, source=r.source, author=r.author, text=r.text, url=r.url,
                posted_at=r.posted_at, category=r.category, summary=r.summary,
                analyzed_by=r.analyzed_by or "offline",
                job=JobInfo(**r.job) if r.job else None,
                topic_ids=list(r.topic_ids or []), topic_reason=r.topic_reason or "",
            ) for r in rows]
            run = s.get(RunRow, run_id)
            # Optional raw metadata is absent on old runs; keep their existing identity.
            raw_by_fp = {p.fingerprint: p for p in (RawPost(**p) for p in ((run.raw_posts if run else None) or []))}
            for row, p in zip(rows, posts):
                raw = raw_by_fp.get(row.fingerprint)
                if raw:
                    p.sponsored, p.job_seed, p.storage_key = raw.sponsored, raw.job_seed, raw.storage_key
                p.analyzed = row.analyzed_by != "pending"
        groups = self.get_post_groups(run_id)
        if include_raw:
            by_fingerprint = {p.fingerprint: p for p in posts}
            if raw_by_fp:
                posts = [by_fingerprint.get(fp) or AnalyzedPost(**p.model_dump(), id=-(i + 1), analyzed=False)
                         for i, (fp, p) in enumerate(raw_by_fp.items())]
        if groups:
            by_fingerprint = {p.fingerprint: p for p in posts}
            posts = []
            raw_positions = {fp: i for i, fp in enumerate(raw_by_fp)}
            for group in groups:
                p = by_fingerprint.get(group.fingerprint)
                if p is None and (raw := raw_by_fp.get(group.fingerprint)) is not None:
                    p = AnalyzedPost(**raw.model_dump(), id=-(raw_positions[group.fingerprint] + 1), analyzed=False)
                if p is not None:
                    p.sources = group.sources
                    posts.append(p)
        return posts

    def representative_posts_filter(self):
        """SQL predicate for queries joining PostRow to RunRow; legacy runs keep every row."""
        sqlite = self.engine.dialect.name == "sqlite"
        data = RunRow.post_groups if sqlite else cast(RunRow.post_groups, JSON)
        kind = func.json_type(data) if sqlite else func.json_typeof(data)
        array = case((kind == "array", data), else_=None)
        entries = (func.json_each(array) if sqlite else func.json_array_elements(array)).table_valued("value")
        fingerprint = (func.json_extract(entries.c.value, "$.fingerprint") if sqlite else
                       cast(entries.c.value, JSON)["fingerprint"].as_string())
        groups = select(entries.c.value).select_from(entries).correlate(RunRow, PostRow)
        return or_(~groups.exists(), groups.where(fingerprint == PostRow.fingerprint).exists())

    def user_posts(self, user_id: int, limit: int = 2000) -> list[AnalyzedPost]:
        """Bài đã phân tích của user, mới nhất trước (dùng để gắn chủ đề lại)."""
        q = (select(PostRow).join(RunRow).where(RunRow.user_id == user_id, PostRow.analyzed_by != "pending", self.representative_posts_filter())
             .order_by(PostRow.id.desc()).limit(limit))
        with self.Session() as s:
            return [AnalyzedPost(id=r.id, platform=r.platform, source=r.source, author=r.author, text=r.text,
                                 url=r.url, posted_at=r.posted_at, category=r.category, summary=r.summary,
                                 topic_ids=list(r.topic_ids or []), topic_reason=r.topic_reason or "")
                    for r in s.scalars(q)]
