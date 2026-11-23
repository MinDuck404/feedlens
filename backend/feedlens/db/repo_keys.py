"""Keys persistence for Database."""
from __future__ import annotations

from sqlalchemy import case, delete, func, select, true
from .tables import AIUsageRow, ApiKeyRow


class KeysMixin:
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
        if hasattr(self, "_quota_scheduler"):
            self._quota_scheduler.forget_key(row.id)  # A deleted SQLite row ID may be reused for a different credential.
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

    def release_ai_usage(self, key_id, model, day, tokens) -> None:
        """Undo a reservation for a rejected configuration, without resetting other requests or exhaustion."""
        from sqlalchemy import update
        with self.Session.begin() as s:
            s.execute(update(AIUsageRow).where(AIUsageRow.key_id == key_id, AIUsageRow.model == model,
                                              AIUsageRow.day == day).values(
                requests=case((AIUsageRow.requests > 0, AIUsageRow.requests - 1), else_=0),
                tokens=case((AIUsageRow.tokens >= tokens, AIUsageRow.tokens - tokens), else_=0)))
