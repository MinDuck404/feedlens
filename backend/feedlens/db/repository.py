"""Truy cập dữ liệu. Phần còn lại của app chỉ nói chuyện với lớp `Database` này.

Mọi truy vấn lượt/bài viết đều lọc theo user_id để user này không thấy dữ liệu của user khác.
"""
from __future__ import annotations

import re
import heapq
import unicodedata
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import JSON, Text, cast, create_engine, delete, event, func, inspect, or_, select, text, true
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from ..models import AnalyzedPost, Digest, JobInfo, JobSeed, RawPost, RunRequest, Topic
from .tables import AIUsageRow, JobProfileRow, ApiKeyRow, Base, PlatformSessionRow, PostRow, RunRow, TopicRow, UserRow

LOCAL_EMAIL = "local@feedlens"


class EmailTaken(Exception):
    pass


class Database:
    def __init__(self, url: str):
        is_sqlite = url.startswith("sqlite")
        self.engine = create_engine(
            url, future=True, pool_pre_ping=True,
            connect_args={"check_same_thread": False} if is_sqlite else {},
        )
        if is_sqlite:
            @event.listens_for(self.engine, "connect")
            def _fk_on(dbapi_conn, _):  # SQLite cần bật FK thủ công để cascade hoạt động
                dbapi_conn.execute("PRAGMA foreign_keys = ON")
        Base.metadata.create_all(self.engine)
        self._migrate()
        self.Session = sessionmaker(self.engine, expire_on_commit=False)

    def _migrate(self) -> None:
        """Nâng cấp nhẹ cho DB tạo từ phiên bản trước: thêm cột còn thiếu."""
        json_type = "JSONB" if self.engine.dialect.name == "postgresql" else "JSON"
        wanted = {
            "runs": {"user_id": "INTEGER REFERENCES users(id) ON DELETE CASCADE", "raw_posts": json_type,
                     "raw_fingerprints": json_type},
            "users": {"preferences": json_type, "default_ai_provider": "VARCHAR(20)"},
            "posts": {"topic_ids": json_type, "topic_reason": "TEXT DEFAULT ''",
                      "analyzed_by": "VARCHAR(120) NOT NULL DEFAULT ''"},
            "api_keys": {"label": "VARCHAR(80) NOT NULL DEFAULT ''", "priority": "INTEGER NOT NULL DEFAULT 0",
                         "enabled": "BOOLEAN NOT NULL DEFAULT TRUE", "tier": "VARCHAR(8) NOT NULL DEFAULT 'free'"},
            "ai_usage": {"exhausted": "BOOLEAN NOT NULL DEFAULT FALSE"},
        }
        insp = inspect(self.engine)
        for table, cols in wanted.items():
            have = {c["name"] for c in insp.get_columns(table)}
            for col, ddl in cols.items():
                if col not in have:
                    with self.engine.begin() as conn:
                        conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {ddl}"))
                        if table == "posts" and col == "analyzed_by":
                            conn.execute(text("""UPDATE posts SET analyzed_by = COALESCE(
                                (SELECT CASE WHEN ai_label = '' OR ai_label = :offline_label THEN 'offline'
                                             ELSE ai_label END FROM runs WHERE runs.id = posts.run_id), 'offline')"""),
                                         {"offline_label": "bộ lọc từ khóa offline"})
        constraints = [c for c in inspect(self.engine).get_unique_constraints("api_keys")
                       if set(c["column_names"]) == {"user_id", "provider"}]
        if constraints and self.engine.dialect.name == "sqlite":
            # SQLite cannot drop a UNIQUE constraint. Rebuild only this table, preserving IDs and usage FKs.
            with self.engine.connect() as conn:
                conn.exec_driver_sql("PRAGMA foreign_keys=OFF")
                conn.commit()
                try:
                    with conn.begin():
                        conn.exec_driver_sql("BEGIN IMMEDIATE")
                        conn.exec_driver_sql("CREATE TABLE api_keys_new (id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, provider VARCHAR(20) NOT NULL, ciphertext TEXT NOT NULL, hint VARCHAR(16), created_at DATETIME NOT NULL, label VARCHAR(80) NOT NULL DEFAULT '', priority INTEGER NOT NULL DEFAULT 0, enabled BOOLEAN NOT NULL DEFAULT TRUE, tier VARCHAR(8) NOT NULL DEFAULT 'free')")
                        cols = "id,user_id,provider,ciphertext,hint,created_at,label,priority,enabled,tier"
                        conn.exec_driver_sql(f"INSERT INTO api_keys_new ({cols}) SELECT {cols} FROM api_keys")
                        conn.exec_driver_sql("DROP TABLE api_keys")
                        conn.exec_driver_sql("ALTER TABLE api_keys_new RENAME TO api_keys")
                        conn.exec_driver_sql("CREATE INDEX ix_api_keys_user_id ON api_keys(user_id)")
                finally:
                    conn.exec_driver_sql("PRAGMA foreign_keys=ON")
                    conn.commit()
        elif constraints:
            quote = self.engine.dialect.identifier_preparer.quote
            with self.engine.begin() as conn:
                for constraint in constraints:
                    conn.execute(text(f"ALTER TABLE api_keys DROP CONSTRAINT IF EXISTS {quote(constraint['name'])}"))

    # ---------------------------------------------------------------- users
    def create_user(self, email: str, password_hash: str) -> int:
        try:
            with self.Session.begin() as s:
                row = UserRow(email=email.lower().strip(), password_hash=password_hash)
                s.add(row)
                s.flush()
                return row.id
        except IntegrityError as e:
            raise EmailTaken(email) from e

    def get_user_by_email(self, email: str) -> UserRow | None:
        with self.Session() as s:
            return s.scalar(select(UserRow).where(UserRow.email == email.lower().strip()))

    def get_user(self, user_id: int) -> UserRow | None:
        with self.Session() as s:
            return s.get(UserRow, user_id)

    def local_user_id(self) -> int:
        """Chế độ local: một user ngầm định, không cần đăng nhập."""
        u = self.get_user_by_email(LOCAL_EMAIL)
        if u:
            return u.id
        try:
            return self.create_user(LOCAL_EMAIL, "!")
        except EmailTaken:
            return self.get_user_by_email(LOCAL_EMAIL).id

    def get_preferences(self, user_id: int) -> dict:
        with self.Session() as s:
            u = s.get(UserRow, user_id)
            return dict(u.preferences or {}) if u else {}

    def set_preferences(self, user_id: int, prefs: dict) -> None:
        with self.Session.begin() as s:
            s.get(UserRow, user_id).preferences = prefs

    def get_default_ai(self, user_id: int) -> str | None:
        with self.Session() as s:
            user = s.get(UserRow, user_id)
            return user.default_ai_provider if user else None

    def set_default_ai(self, user_id: int, provider: str | None) -> None:
        with self.Session.begin() as s:
            s.get(UserRow, user_id).default_ai_provider = provider

    def set_agent_token_hash(self, user_id: int, token_hash: str) -> None:
        with self.Session.begin() as s:
            s.get(UserRow, user_id).agent_token_hash = token_hash

    def user_by_agent_hash(self, token_hash: str) -> UserRow | None:
        with self.Session() as s:
            return s.scalar(select(UserRow).where(UserRow.agent_token_hash == token_hash))

    def touch_agent(self, user_id: int) -> None:
        with self.Session.begin() as s:
            s.get(UserRow, user_id).agent_last_seen = datetime.now(timezone.utc)

    # ---------------------------------------------------------------- API keys
    def upsert_key(self, user_id: int, provider: str, ciphertext: str, hint: str) -> None:
        with self.Session.begin() as s:
            row = s.scalar(select(ApiKeyRow).where(ApiKeyRow.user_id == user_id, ApiKeyRow.provider == provider)
                           .order_by(ApiKeyRow.priority, ApiKeyRow.id).limit(1))
            if row:
                row.ciphertext, row.hint, row.enabled, row.priority = ciphertext, hint, True, 0
            else:
                s.add(ApiKeyRow(user_id=user_id, provider=provider, ciphertext=ciphertext, hint=hint))

    def delete_key(self, user_id: int, provider: str) -> None:
        with self.Session.begin() as s:
            ids = list(s.scalars(select(ApiKeyRow.id).where(ApiKeyRow.user_id == user_id, ApiKeyRow.provider == provider)))
            s.execute(delete(ApiKeyRow).where(ApiKeyRow.user_id == user_id, ApiKeyRow.provider == provider))
        if hasattr(self, "_quota_scheduler"):
            for key_id in ids:
                self._quota_scheduler.forget_key(key_id)

    def list_keys(self, user_id: int) -> list[ApiKeyRow]:
        with self.Session() as s:
            return list(s.scalars(select(ApiKeyRow).where(ApiKeyRow.user_id == user_id)
                                  .order_by(ApiKeyRow.priority, ApiKeyRow.id)))

    def add_key(self, user_id, provider, ciphertext, hint, label="", tier="free") -> ApiKeyRow:
        with self.Session.begin() as s:
            priority = s.scalar(select(func.max(ApiKeyRow.priority)).where(ApiKeyRow.user_id == user_id, ApiKeyRow.provider == provider))
            row = ApiKeyRow(user_id=user_id, provider=provider, ciphertext=ciphertext, hint=hint,
                            label=label, tier=tier, priority=0 if priority is None else priority + 1)
            s.add(row); s.flush()
            return row

    def update_key(self, user_id, key_id, changes) -> bool:
        with self.Session.begin() as s:
            row = s.scalar(select(ApiKeyRow).where(ApiKeyRow.id == key_id, ApiKeyRow.user_id == user_id))
            if row is None:
                return False
            for field in ("label", "enabled", "tier"):
                if field in changes:
                    setattr(row, field, changes[field])
            return True

    def order_keys(self, user_id, provider, ids) -> None:
        with self.Session.begin() as s:
            rows = list(s.scalars(select(ApiKeyRow).where(ApiKeyRow.user_id == user_id, ApiKeyRow.provider == provider)))
            if len(set(ids)) != len(ids) or set(ids) != {r.id for r in rows}:
                raise ValueError("Key order must contain every key of this provider exactly once")
            order = {key_id: i for i, key_id in enumerate(ids)}
            for row in rows:
                row.priority = order[row.id]

    def delete_key_id(self, user_id, key_id) -> bool:
        with self.Session.begin() as s:
            result = s.execute(delete(ApiKeyRow).where(ApiKeyRow.id == key_id, ApiKeyRow.user_id == user_id))
            deleted = result.rowcount > 0
        if deleted and hasattr(self, "_quota_scheduler"):
            self._quota_scheduler.forget_key(key_id)
        return deleted

    def ai_usage(self, key_id, day) -> dict:
        with self.Session() as s:
            rows = s.scalars(select(AIUsageRow).where(AIUsageRow.key_id == key_id, AIUsageRow.day == day))
            return {r.model: {"requests": r.requests, "tokens": r.tokens, "exhausted": r.exhausted} for r in rows}

    def exhaust_ai_usage(self, key_id, model, day) -> None:
        from sqlalchemy import update
        with self.Session.begin() as s:
            s.execute(update(AIUsageRow).where(AIUsageRow.key_id == key_id, AIUsageRow.model == model,
                                             AIUsageRow.day == day).values(exhausted=True))

    def reserve_ai_usage(self, key_id, model, day, tokens, limit=None) -> bool:
        if self.engine.dialect.name == "sqlite":
            from sqlalchemy.dialects.sqlite import insert
        else:
            from sqlalchemy.dialects.postgresql import insert
        statement = insert(AIUsageRow).values(key_id=key_id, model=model, day=day, requests=1, tokens=tokens)
        statement = statement.on_conflict_do_update(index_elements=["key_id", "model", "day"],
            set_={"requests": AIUsageRow.requests + 1, "tokens": AIUsageRow.tokens + tokens},
            where=(AIUsageRow.exhausted.is_(False) & (AIUsageRow.requests < limit if limit is not None else true())))
        if limit is not None and limit <= 0:
            return False
        with self.Session.begin() as s:
            return s.execute(statement).rowcount > 0

    # ---------------------------------------------------------------- cookie mạng xã hội
    def upsert_session(self, user_id: int, platform: str, ciphertext: str, hint: str) -> None:
        with self.Session.begin() as s:
            row = s.scalar(select(PlatformSessionRow).where(
                PlatformSessionRow.user_id == user_id, PlatformSessionRow.platform == platform))
            if not row:
                row = PlatformSessionRow(user_id=user_id, platform=platform)
                s.add(row)
            row.ciphertext, row.hint = ciphertext, hint
            row.saved_at = datetime.now(timezone.utc)
            row.status, row.status_message, row.checked_at = "unchecked", "", None

    def get_session(self, user_id: int, platform: str) -> PlatformSessionRow | None:
        with self.Session() as s:
            return s.scalar(select(PlatformSessionRow).where(
                PlatformSessionRow.user_id == user_id, PlatformSessionRow.platform == platform))

    def list_sessions(self, user_id: int) -> list[PlatformSessionRow]:
        with self.Session() as s:
            return list(s.scalars(select(PlatformSessionRow).where(PlatformSessionRow.user_id == user_id)))

    def delete_session(self, user_id: int, platform: str) -> None:
        with self.Session.begin() as s:
            s.execute(delete(PlatformSessionRow).where(
                PlatformSessionRow.user_id == user_id, PlatformSessionRow.platform == platform))

    def set_session_status(self, user_id: int, platform: str, status: str, message: str = "") -> None:
        with self.Session.begin() as s:
            row = s.scalar(select(PlatformSessionRow).where(
                PlatformSessionRow.user_id == user_id, PlatformSessionRow.platform == platform))
            if row:
                row.status, row.status_message = status, message[:500]
                row.checked_at = datetime.now(timezone.utc)

    # ---------------------------------------------------------------- runs
    def create_run(self, req: RunRequest, user_id: int | None = None, status: str = "queued") -> int:
        with self.Session.begin() as s:
            row = RunRow(request=req.model_dump(), user_id=user_id, status=status)
            s.add(row)
            s.flush()
            return row.id

    def update_run(self, run_id: int, **fields: Any) -> None:
        if isinstance(fields.get("digest"), Digest):
            fields["digest"] = fields["digest"].model_dump()
        if "raw_posts" in fields and "raw_fingerprints" not in fields:
            fields["raw_fingerprints"] = list(dict.fromkeys(
                RawPost.model_validate(p).fingerprint for p in fields["raw_posts"] or [] if isinstance(p, dict)))
        with self.Session.begin() as s:
            row = s.get(RunRow, run_id)
            for k, v in fields.items():
                setattr(row, k, v)

    def get_run(self, run_id: int, user_id: int | None = None) -> dict | None:
        with self.Session() as s:
            row = s.get(RunRow, run_id)
            if not row or (user_id is not None and row.user_id != user_id):
                return None
            return _run_dict(row)

    def list_runs(self, user_id: int | None = None, limit: int = 50) -> list[dict]:
        q = select(RunRow).order_by(RunRow.id.desc()).limit(limit)
        if user_id is not None:
            q = q.where(RunRow.user_id == user_id)
        with self.Session() as s:
            return [_run_dict(r) for r in s.scalars(q).all()]

    def delete_run(self, run_id: int, user_id: int | None = None) -> bool:
        with self.Session.begin() as s:
            row = s.get(RunRow, run_id)
            if not row or (user_id is not None and row.user_id != user_id):
                return False
            s.delete(row)
            return True

    def fail_interrupted(self) -> int:
        """Gọi lúc server khởi động: lượt đang phân tích dở không còn luồng nào chạy tiếp."""
        with self.Session.begin() as s:
            rows = list(s.scalars(select(RunRow).where(RunRow.status.in_(("analyzing", "queued")))))
            for r in rows:
                r.status = "analysis_failed" if r.raw_posts else "error"
                r.error = "Server khởi động lại giữa lúc đang phân tích."
            return len(rows)

    def claim_analysis(self, run_id: int, req: RunRequest) -> bool:
        from sqlalchemy import update
        with self.Session.begin() as s:
            result = s.execute(update(RunRow).where(RunRow.id == run_id,
                RunRow.status.notin_(("pending", "queued", "scraping", "analyzing"))).values(
                    status="analyzing", request=req.model_dump(), error=None, digest=None))
            return result.rowcount == 1

    def claim_next_pending(self, user_id: int, protocol_version: int = 1) -> dict | None:
        """Old agents only claim legacy-equivalent requests; never silently run a new mode."""
        from ..source_modes import legacy_agent_compatible
        with self.Session.begin() as s:
            q = (select(RunRow).where(RunRow.user_id == user_id, RunRow.status == "pending")
                 .order_by(RunRow.id))
            if self.engine.dialect.name == "postgresql":
                q = q.with_for_update(skip_locked=True)
            for row in s.scalars(q).yield_per(20):
                if protocol_version < 2 and not legacy_agent_compatible(RunRequest(**row.request)):
                    continue
                row.status = "scraping"
                s.flush()
                return _run_dict(row)
            return None

    # ---------------------------------------------------------------- posts
    def save_raw_posts(self, run_id: int, posts: list[RawPost]) -> None:
        self.update_run(run_id, raw_posts=[p.model_dump(include=set(RawPost.model_fields)) for p in posts],
                        raw_fingerprints=list(dict.fromkeys(p.fingerprint for p in posts)), collected=len(posts))

    def get_raw_posts(self, run_id: int) -> list[RawPost]:
        with self.Session() as s:
            row = s.get(RunRow, run_id)
            return [RawPost(**p) for p in (row.raw_posts or [])] if row else []

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
        request = run["request"]
        needs_ai = request.get("analysis_used_ai", request.get("ai_provider") != "offline" and not (
            run["status"] == "done" and run["ai_label"] == "bộ lọc từ khóa offline"))
        completed = {p.fingerprint for p in self.get_posts(run_id)
                     if not needs_ai or p.analyzed_by not in {"", "offline", "pending"}}
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
            rows = {r.fingerprint: r for r in s.scalars(select(PostRow).where(PostRow.run_id == run_id))}
            for p in posts:
                row = rows.get(p.fingerprint)
                if row is None:
                    row = PostRow(run_id=run_id, fingerprint=p.fingerprint)
                    s.add(row)
                    rows[p.fingerprint] = row
                for key in RawPost.model_fields.keys() - {"job_seed"}:
                    setattr(row, key, getattr(p, key))
                row.category, row.summary = p.category, p.summary
                row.analyzed_by = "offline" if p.analyzed_by in {"", "bộ lọc từ khóa offline"} else p.analyzed_by
                row.job = p.job.model_dump() if p.job else None
                row.topic_ids, row.topic_reason = list(p.topic_ids), p.topic_reason
            run = s.get(RunRow, run_id)
            if run and rows:
                labels = {r.analyzed_by if r.analyzed_by != "offline" else "bộ lọc từ khóa offline"
                          for r in rows.values() if r.analyzed_by != "pending"}
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
                    p.sponsored, p.job_seed = raw.sponsored, raw.job_seed
                p.analyzed = row.analyzed_by != "pending"
        if include_raw:
            by_fingerprint = {p.fingerprint: p for p in posts}
            if raw_by_fp:
                return [by_fingerprint.get(fp) or AnalyzedPost(**p.model_dump(), id=-(i + 1), analyzed=False)
                        for i, (fp, p) in enumerate(raw_by_fp.items())]
        return posts


    def get_job_profile(self, user_id: int) -> str | None:
        with self.Session() as s:
            row = s.get(JobProfileRow, user_id)
            return row.payload if row else None

    def set_job_profile(self, user_id: int, payload: str) -> None:
        with self.Session.begin() as s:
            row = s.get(JobProfileRow, user_id)
            if row:
                row.payload = payload
            else:
                s.add(JobProfileRow(user_id=user_id, payload=payload))

    def delete_job_profile(self, user_id: int) -> None:
        with self.Session.begin() as s:
            s.execute(delete(JobProfileRow).where(JobProfileRow.user_id == user_id))

    # ---------------------------------------------------------------- topics
    def list_topics(self, user_id: int, enabled_only: bool = False) -> list[Topic]:
        q = select(TopicRow).where(TopicRow.user_id == user_id).order_by(TopicRow.id)
        if enabled_only:
            q = q.where(TopicRow.enabled.is_(True))
        with self.Session() as s:
            return [_topic(r) for r in s.scalars(q)]

    def create_topic(self, user_id: int, t: Topic) -> Topic:
        with self.Session.begin() as s:
            row = TopicRow(user_id=user_id, **t.model_dump(exclude={"id"}))
            s.add(row)
            s.flush()
            return _topic(row)

    def update_topic(self, user_id: int, topic_id: int, t: Topic) -> Topic | None:
        with self.Session.begin() as s:
            row = s.get(TopicRow, topic_id)
            if not row or row.user_id != user_id:
                return None
            for k, v in t.model_dump(exclude={"id"}).items():
                setattr(row, k, v)
            return _topic(row)

    def delete_topic(self, user_id: int, topic_id: int) -> bool:
        with self.Session.begin() as s:
            row = s.get(TopicRow, topic_id)
            if not row or row.user_id != user_id:
                return False
            s.delete(row)
            # Gỡ nhãn chủ đề đã xóa khỏi bài và khỏi bản tin của user
            for p in s.scalars(select(PostRow).join(RunRow).where(RunRow.user_id == user_id)):
                if p.topic_ids and topic_id in p.topic_ids:
                    p.topic_ids = [i for i in p.topic_ids if i != topic_id]
            for r in s.scalars(select(RunRow).where(RunRow.user_id == user_id)):
                if r.digest and any(t.get("topic_id") == topic_id for t in r.digest.get("topics", [])):
                    r.digest = {**r.digest, "topics": [t for t in r.digest["topics"] if t.get("topic_id") != topic_id]}
            return True

    def user_posts(self, user_id: int, limit: int = 2000) -> list[AnalyzedPost]:
        """Bài đã phân tích của user, mới nhất trước (dùng để gắn chủ đề lại)."""
        q = (select(PostRow).join(RunRow).where(RunRow.user_id == user_id)
             .order_by(PostRow.id.desc()).limit(limit))
        with self.Session() as s:
            return [AnalyzedPost(id=r.id, platform=r.platform, source=r.source, author=r.author, text=r.text,
                                 url=r.url, posted_at=r.posted_at, category=r.category, summary=r.summary,
                                 topic_ids=list(r.topic_ids or []), topic_reason=r.topic_reason or "")
                    for r in s.scalars(q)]

    def set_post_topics(self, user_id: int, updates: dict[int, tuple[list[int], str]]) -> None:
        if not updates:
            return
        with self.Session.begin() as s:
            q = select(PostRow).join(RunRow).where(RunRow.user_id == user_id, PostRow.id.in_(list(updates)))
            for p in s.scalars(q):
                p.topic_ids, p.topic_reason = updates[p.id]

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



def _parse_post_date(posted_at: str | None, run_created_at: Any) -> date:
    from ..trends_api import parse_post_date
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


def _topic(r: TopicRow) -> Topic:
    return Topic(id=r.id, name=r.name, description=r.description or "", include_keywords=list(r.include_keywords or []),
                 exclude_keywords=list(r.exclude_keywords or []), enabled=bool(r.enabled), color=r.color or "red")


def _run_dict(r: RunRow) -> dict:
    return {"id": r.id, "user_id": r.user_id, "created_at": r.created_at.isoformat(), "request": r.request,
            "status": r.status, "collected": r.collected, "ai_label": r.ai_label, "error": r.error,
            "digest": r.digest}
