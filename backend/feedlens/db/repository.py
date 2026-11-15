"""Truy cập dữ liệu. Phần còn lại của app chỉ nói chuyện với lớp `Database` này.

Mọi truy vấn lượt/bài viết đều lọc theo user_id để user này không thấy dữ liệu của user khác.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import create_engine, delete, event, inspect, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from ..models import AnalyzedPost, Digest, JobInfo, RunRequest
from .tables import JobProfileRow, ApiKeyRow, Base, PlatformSessionRow, PostRow, RunRow, UserRow

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
            "runs": {"user_id": "INTEGER REFERENCES users(id) ON DELETE CASCADE"},
            "users": {"preferences": json_type},
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
                r.status = "error"
                r.error = "Server khởi động lại giữa lúc đang phân tích. Hãy tạo lượt mới."
            return len(rows)

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
            ) for p in posts)

    def get_posts(self, run_id: int) -> list[AnalyzedPost]:
        with self.Session() as s:
            rows = s.scalars(select(PostRow).where(PostRow.run_id == run_id).order_by(PostRow.id)).all()
            return [AnalyzedPost(
                id=r.id, platform=r.platform, source=r.source, author=r.author, text=r.text, url=r.url,
                posted_at=r.posted_at, category=r.category, summary=r.summary,
                job=JobInfo(**r.job) if r.job else None,
            ) for r in rows]


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


def _run_dict(r: RunRow) -> dict:
    return {"id": r.id, "user_id": r.user_id, "created_at": r.created_at.isoformat(), "request": r.request,
            "status": r.status, "collected": r.collected, "ai_label": r.ai_label, "error": r.error,
            "digest": r.digest}
