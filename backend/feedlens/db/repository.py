"""Truy cập dữ liệu. Phần còn lại của app chỉ nói chuyện với lớp `Database` này."""
from __future__ import annotations

from typing import Any

from sqlalchemy import create_engine, delete, event, select
from sqlalchemy.orm import sessionmaker

from ..models import AnalyzedPost, Digest, JobInfo, RunRequest
from .tables import Base, PostRow, RunRow


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
        self.Session = sessionmaker(self.engine, expire_on_commit=False)

    # ---------------------------------------------------------------- runs
    def create_run(self, req: RunRequest) -> int:
        with self.Session.begin() as s:
            row = RunRow(request=req.model_dump())
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

    def get_run(self, run_id: int) -> dict | None:
        with self.Session() as s:
            row = s.get(RunRow, run_id)
            return _run_dict(row) if row else None

    def list_runs(self, limit: int = 50) -> list[dict]:
        with self.Session() as s:
            rows = s.scalars(select(RunRow).order_by(RunRow.id.desc()).limit(limit)).all()
            return [_run_dict(r) for r in rows]

    def delete_run(self, run_id: int) -> None:
        with self.Session.begin() as s:
            row = s.get(RunRow, run_id)
            if row:
                s.delete(row)

    # ---------------------------------------------------------------- posts
    def known_fingerprints(self, platform: str) -> set[str]:
        with self.Session() as s:
            return set(s.scalars(select(PostRow.fingerprint).where(PostRow.platform == platform)))

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


def _run_dict(r: RunRow) -> dict:
    return {"id": r.id, "created_at": r.created_at.isoformat(), "request": r.request, "status": r.status,
            "collected": r.collected, "ai_label": r.ai_label, "error": r.error, "digest": r.digest}
