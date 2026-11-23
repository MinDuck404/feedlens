"""Topics persistence for Database."""
from __future__ import annotations

from sqlalchemy import select
from ..models import Topic
from .tables import PostRow, RunRow, TopicRow


def _topic(r: TopicRow) -> Topic:
    return Topic(id=r.id, name=r.name, description=r.description or "", include_keywords=list(r.include_keywords or []),
                 exclude_keywords=list(r.exclude_keywords or []), enabled=bool(r.enabled), color=r.color or "red")


class TopicsMixin:
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

    def set_post_topics(self, user_id: int, updates: dict[int, tuple[list[int], str]]) -> None:
        if not updates:
            return
        with self.Session.begin() as s:
            q = select(PostRow).join(RunRow).where(RunRow.user_id == user_id, PostRow.id.in_(list(updates)))
            for p in s.scalars(q):
                p.topic_ids, p.topic_reason = updates[p.id]
