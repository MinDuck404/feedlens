"""Users persistence for Database."""
from __future__ import annotations

from datetime import datetime
from datetime import timezone
from sqlalchemy import delete
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from feedlens.db.tables import JobProfileRow
from feedlens.db.tables import PlatformSessionRow
from feedlens.db.tables import UserRow


LOCAL_EMAIL = "local@feedlens"


class EmailTaken(Exception):
    pass


class UsersMixin:
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
