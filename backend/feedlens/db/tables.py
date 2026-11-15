from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


class UserRow(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    agent_token_hash: Mapped[Optional[str]] = mapped_column(String(64), index=True)
    agent_last_seen: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    # Cài đặt "Lướt mới" lần trước + danh sách group đã lưu (frontend quyết định cấu trúc)
    preferences: Mapped[Optional[dict]] = mapped_column(JSON)
    default_ai_provider: Mapped[Optional[str]] = mapped_column(String(20))


class ApiKeyRow(Base):
    __tablename__ = "api_keys"
    __table_args__ = (UniqueConstraint("user_id", "provider"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    provider: Mapped[str] = mapped_column(String(20))
    ciphertext: Mapped[str] = mapped_column(Text)
    hint: Mapped[str] = mapped_column(String(16), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class PlatformSessionRow(Base):
    """Cookie mạng xã hội (đã mã hóa) để server lướt thay user ở chế độ 'Server'."""
    __tablename__ = "platform_sessions"
    __table_args__ = (UniqueConstraint("user_id", "platform"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    platform: Mapped[str] = mapped_column(String(20))
    ciphertext: Mapped[str] = mapped_column(Text)
    hint: Mapped[str] = mapped_column(String(32), default="")
    saved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    status: Mapped[str] = mapped_column(String(20), default="unchecked")  # unchecked | ok | invalid
    status_message: Mapped[str] = mapped_column(Text, default="")
    checked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))


class RunRow(Base):
    __tablename__ = "runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    request: Mapped[dict] = mapped_column(JSON)
    # pending (chờ agent) | queued | scraping | analyzing | done | analysis_failed | error
    status: Mapped[str] = mapped_column(String(20), default="queued", index=True)
    collected: Mapped[int] = mapped_column(Integer, default=0)
    ai_label: Mapped[str] = mapped_column(String(120), default="")
    error: Mapped[Optional[str]] = mapped_column(Text)
    digest: Mapped[Optional[dict]] = mapped_column(JSON)
    raw_posts: Mapped[Optional[list]] = mapped_column(JSON)

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


class JobProfileRow(Base):
    __tablename__ = "job_profiles"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    payload: Mapped[str] = mapped_column(Text)
