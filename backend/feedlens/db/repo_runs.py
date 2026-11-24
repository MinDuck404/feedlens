"""Runs persistence for Database."""
from __future__ import annotations

from typing import Any
from sqlalchemy import select
from ..models import Digest, RawPost, RunRequest
from .tables import RunRow


def _run_dict(r: RunRow) -> dict:
    return {"id": r.id, "user_id": r.user_id, "created_at": r.created_at.isoformat(), "request": r.request,
            "status": r.status, "collected": r.collected, "ai_label": r.ai_label, "error": r.error,
            "digest": r.digest}


class RunsMixin:
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
        from feedlens.runs.source_modes import legacy_agent_compatible
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
