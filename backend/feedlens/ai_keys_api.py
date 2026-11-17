"""Multiple encrypted keys; responses contain metadata and hints only."""
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, ConfigDict, Field

from .ai.registry import forget_models, list_models
from .ai.scheduler import Candidate, pacific_day, scheduler_for
from .auth import CurrentUser, current_user
from .crypto import encrypt, key_hint


class NewKey(BaseModel):
    model_config = ConfigDict(extra="forbid")
    provider: Literal["gemini", "openai", "anthropic"]
    api_key: str = Field(min_length=8, max_length=500)
    label: str = Field("", max_length=80)
    tier: Literal["free", "paid"] = "free"


class KeyPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    label: str = Field("", max_length=80)
    enabled: bool = Field(True, strict=True)
    tier: Literal["free", "paid"] = "free"


class KeyOrder(BaseModel):
    model_config = ConfigDict(extra="forbid")
    provider: Literal["gemini", "openai", "anthropic"]
    ids: list[int] = Field(max_length=100)


def ai_keys_router(db):
    router = APIRouter(prefix="/api/ai/keys")

    def describe(row):
        scheduler = scheduler_for(db())
        usage = db().ai_usage(row.id, pacific_day())
        from types import SimpleNamespace
        for model, value in usage.items():
            candidate = Candidate(row.id, SimpleNamespace(model=model, info=SimpleNamespace(key=row.provider)), tier=row.tier)
            value["limit_rpd"] = scheduler.limits(candidate).rpd
            value.pop("tokens", None)
            value.pop("exhausted", None)
        return dict(id=row.id, provider=row.provider, label=row.label, hint=row.hint,
                    priority=row.priority, enabled=row.enabled, tier=row.tier,
                    status=scheduler.status.get(row.id, "unchecked"), usage_today=usage)

    @router.get("")
    def keys(user: CurrentUser = Depends(current_user)):
        return [describe(row) for row in db().list_keys(user.id)]

    @router.post("")
    async def add(body: NewKey, user: CurrentUser = Depends(current_user)):
        secret = body.api_key.strip()
        if len(secret) < 8:
            raise HTTPException(422, "API key is too short")
        try:
            await run_in_threadpool(list_models, user.id, body.provider, secret, True)
        except Exception:
            forget_models(user.id, body.provider)
            # Never echo an SDK exception: URLs and diagnostics may contain the API key.
            raise HTTPException(400, "Key không dùng được. Kiểm tra key và kết nối tới nhà cung cấp.") from None
        row = db().add_key(user.id, body.provider, encrypt(secret), key_hint(secret), body.label, body.tier)
        scheduler_for(db()).status[row.id] = "ok"
        return describe(row)

    @router.put("/order")
    def order(body: KeyOrder, user: CurrentUser = Depends(current_user)):
        try:
            db().order_keys(user.id, body.provider, body.ids)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        return {"ok": True}

    @router.patch("/{key_id:int}")
    def patch(key_id: int, body: KeyPatch, user: CurrentUser = Depends(current_user)):
        if not db().update_key(user.id, key_id, body.model_dump(exclude_unset=True)):
            raise HTTPException(404, "API key not found")
        return describe(next(row for row in db().list_keys(user.id) if row.id == key_id))

    @router.delete("/{key_id:int}")
    def delete(key_id: int, user: CurrentUser = Depends(current_user)):
        row = next((row for row in db().list_keys(user.id) if row.id == key_id), None)
        if row is None or not db().delete_key_id(user.id, key_id):
            raise HTTPException(404, "API key not found")
        forget_models(user.id, row.provider)
        return {"ok": True}

    return router
