from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


class RunRow(Base):
    __tablename__ = "runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    request: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(20), default="queued")  # queued|scraping|analyzing|done|error
    collected: Mapped[int] = mapped_column(Integer, default=0)
    ai_label: Mapped[str] = mapped_column(String(120), default="")
    error: Mapped[Optional[str]] = mapped_column(Text)
    digest: Mapped[Optional[dict]] = mapped_column(JSON)

    posts: Mapped[list["PostRow"]] = relationship(back_populates="run", cascade="all, delete-orphan",
                                                  order_by="PostRow.id")


class PostRow(Base):
    __tablename__ = "posts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), index=True)
    platform: Mapped[str] = mapped_column(String(20), index=True)
    source: Mapped[str] = mapped_column(String(500), default="")
    author: Mapped[str] = mapped_column(String(300), default="")
    text: Mapped[str] = mapped_column(Text)
    url: Mapped[str] = mapped_column(String(1000), default="")
    posted_at: Mapped[str] = mapped_column(String(64), default="")
    fingerprint: Mapped[str] = mapped_column(String(40), index=True)
    category: Mapped[str] = mapped_column(String(30), default="other", index=True)
    summary: Mapped[str] = mapped_column(Text, default="")
    job: Mapped[Optional[dict]] = mapped_column(JSON)

    run: Mapped[RunRow] = relationship(back_populates="posts")
