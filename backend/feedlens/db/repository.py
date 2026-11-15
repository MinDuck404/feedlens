"""Truy cập dữ liệu. Phần còn lại của app chỉ nói chuyện với lớp `Database` này.

Mọi truy vấn lượt/bài viết đều lọc theo user_id để user này không thấy dữ liệu của user khác.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import create_engine, delete, event, inspect, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from ..models import AnalyzedPost, Digest, JobInfo, RawPost, RunRequest, Topic
from .tables import JobProfileRow, ApiKeyRow, Base, PlatformSessionRow, PostRow, RunRow, TopicRow, UserRow

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
            "runs": {"user_id": "INTEGER REFERENCES users(id) ON DELETE CASCADE", "raw_posts": json_type},
            "users": {"preferences": json_type, "default_ai_provider": "VARCHAR(20)"},
            "posts": {"topic_ids": json_type, "topic_reason": "TEXT DEFAULT ''"},
        }
        insp = inspect(self.engine)
        for table, cols in wanted.items():
            have = {c["name"] for c in insp.get_columns(table)}
            for col, ddl in cols.items():
                if col not in have:
                    with self.engine.begin() as conn:
                        conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {ddl}"))

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
            row = s.scalar(select(ApiKeyRow).where(ApiKeyRow.user_id == user_id, ApiKeyRow.provider == provider))
            if row:
                row.ciphertext, row.hint = ciphertext, hint
            else:
                s.add(ApiKeyRow(user_id=user_id, provider=provider, ciphertext=ciphertext, hint=hint))

    def delete_key(self, user_id: int, provider: str) -> None:
        with self.Session.begin() as s:
            s.execute(delete(ApiKeyRow).where(ApiKeyRow.user_id == user_id, ApiKeyRow.provider == provider))

    def list_keys(self, user_id: int) -> list[ApiKeyRow]:
        with self.Session() as s:
            return list(s.scalars(select(ApiKeyRow).where(ApiKeyRow.user_id == user_id)))

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

    def claim_next_pending(self, user_id: int) -> dict | None:
        """Agent nhận lượt 'pending' cũ nhất của user và chuyển sang 'scraping'."""
        with self.Session.begin() as s:
            q = (select(RunRow).where(RunRow.user_id == user_id, RunRow.status == "pending")
                 .order_by(RunRow.id).limit(1))
            if self.engine.dialect.name == "postgresql":
                q = q.with_for_update(skip_locked=True)
            row = s.scalar(q)
            if not row:
                return None
            row.status = "scraping"
            s.flush()
            return _run_dict(row)

    # ---------------------------------------------------------------- posts
    def save_raw_posts(self, run_id: int, posts: list[RawPost]) -> None:
        self.update_run(run_id, raw_posts=[p.model_dump(include=set(RawPost.model_fields)) for p in posts], collected=len(posts))

    def get_raw_posts(self, run_id: int) -> list[RawPost]:
        with self.Session() as s:
            row = s.get(RunRow, run_id)
            return [RawPost(**p) for p in (row.raw_posts or [])] if row else []

    def get_analysis_posts(self, run_id: int) -> list[RawPost]:
        # Older runs may have analyzed rows but no raw_posts snapshot; their original text is still usable.
        return self.get_raw_posts(run_id) or [RawPost.model_validate(p.model_dump()) for p in self.get_posts(run_id)]

    def can_continue_analysis(self, run_id: int) -> bool:
        run = self.get_run(run_id)
        if not run or run["status"] in {"pending", "queued", "scraping", "analyzing"}:
            return False
        raw = self.get_analysis_posts(run_id)
        completed = {p.fingerprint for p in self.get_posts(run_id)}
        return bool(raw) and (not run["digest"] or any(p.fingerprint not in completed for p in raw))

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
                for key in RawPost.model_fields:
                    setattr(row, key, getattr(p, key))
                row.category, row.summary = p.category, p.summary
                row.job = p.job.model_dump() if p.job else None
                row.topic_ids, row.topic_reason = list(p.topic_ids), p.topic_reason

    def known_fingerprints(self, platform: str, user_id: int | None = None) -> set[str]:
        q = select(PostRow.fingerprint).where(PostRow.platform == platform)
        if user_id is not None:
            q = q.join(RunRow).where(RunRow.user_id == user_id)
        with self.Session() as s:
            return set(s.scalars(q))

    def save_posts(self, run_id: int, posts: list[AnalyzedPost]) -> None:
        with self.Session.begin() as s:
            s.execute(delete(PostRow).where(PostRow.run_id == run_id))
            s.add_all(PostRow(
                run_id=run_id, platform=p.platform, source=p.source, author=p.author, text=p.text,
                url=p.url, posted_at=p.posted_at, fingerprint=p.fingerprint, category=p.category,
                summary=p.summary, job=p.job.model_dump() if p.job else None,
                topic_ids=list(p.topic_ids), topic_reason=p.topic_reason,
            ) for p in posts)

    def get_posts(self, run_id: int, include_raw: bool = False) -> list[AnalyzedPost]:
        with self.Session() as s:
            rows = s.scalars(select(PostRow).where(PostRow.run_id == run_id).order_by(PostRow.id)).all()
            posts = [AnalyzedPost(
                id=r.id, platform=r.platform, source=r.source, author=r.author, text=r.text, url=r.url,
                posted_at=r.posted_at, category=r.category, summary=r.summary,
                job=JobInfo(**r.job) if r.job else None,
                topic_ids=list(r.topic_ids or []), topic_reason=r.topic_reason or "",
            ) for r in rows]
        if include_raw:
            by_fingerprint = {p.fingerprint: p for p in posts}
            raw = self.get_raw_posts(run_id)
            if raw:
                return [by_fingerprint.get(p.fingerprint) or AnalyzedPost(**p.model_dump(), id=-(i + 1), analyzed=False)
                        for i, p in enumerate(raw)]
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
            # Gỡ nhãn chủ đề đã xóa khỏi bài của user
            for p in s.scalars(select(PostRow).join(RunRow).where(RunRow.user_id == user_id)):
                if p.topic_ids and topic_id in p.topic_ids:
                    p.topic_ids = [i for i in p.topic_ids if i != topic_id]
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


def _topic(r: TopicRow) -> Topic:
    return Topic(id=r.id, name=r.name, description=r.description or "", include_keywords=list(r.include_keywords or []),
                 exclude_keywords=list(r.exclude_keywords or []), enabled=bool(r.enabled), color=r.color or "red")


def _run_dict(r: RunRow) -> dict:
    return {"id": r.id, "user_id": r.user_id, "created_at": r.created_at.isoformat(), "request": r.request,
            "status": r.status, "collected": r.collected, "ai_label": r.ai_label, "error": r.error,
            "digest": r.digest}
