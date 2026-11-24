"""Multiple encrypted keys; responses contain metadata and hints only."""
from __future__ import annotations


import feedlens.ai.registry as ai_registry
import feedlens.core.crypto as crypto
import fastapi as fastapi
import fastapi.concurrency as fastapi_concurrency
import feedlens.routes.dependencies as dependencies
from typing import Literal

from fastapi import APIRouter
from fastapi import Depends
from fastapi import HTTPException
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import Field

from feedlens.ai.registry import forget_models
from feedlens.ai.registry import list_models
from feedlens.ai.scheduler import Candidate
from feedlens.ai.scheduler import pacific_day
from feedlens.ai.scheduler import scheduler_for
from feedlens.core.auth import CurrentUser
from feedlens.core.auth import current_user
from feedlens.core.crypto import encrypt
from feedlens.core.crypto import key_hint


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


"""Ai keys routes."""

from fastapi import APIRouter
from fastapi import Depends
from pydantic import BaseModel
from pydantic import Field
from feedlens.core.auth import CurrentUser as User
from feedlens.core.auth import current_user

private = APIRouter()


@private.get("/ai/providers")
def ai_providers(user: User = Depends(current_user)):
    return ai_registry.provider_status(dependencies.db(), user.id)


class DefaultAIBody(BaseModel):
    provider: str = Field(max_length=40)


@private.put("/ai/default")
def set_default_ai(body: DefaultAIBody, user: User = Depends(current_user)):
    _provider_or_404(body.provider)
    try:
        ai_registry.resolve_provider_key(body.provider, ai_registry.user_keys(dependencies.db(), user.id))
    except ValueError as e:
        raise fastapi.HTTPException(400, str(e))
    dependencies.db().set_default_ai(user.id, body.provider)
    return {"ok": True}


class KeyBody(BaseModel):
    api_key: str = Field(min_length=8, max_length=500)


def _provider_or_404(p: str):
    if p not in ai_registry.PROVIDERS:
        raise fastapi.HTTPException(404, "Nhà cung cấp AI không hỗ trợ")


@private.put("/ai/keys/{p}")
async def save_key(p: str, body: KeyBody, user: User = Depends(current_user)):
    """Kiểm tra key bằng cách lấy danh sách model, đúng thì mã hóa và lưu."""
    _provider_or_404(p)
    key = body.api_key.strip()
    try:
        models = await fastapi_concurrency.run_in_threadpool(ai_registry.list_models, user.id, p, key, True)
    except Exception as e:  # noqa: BLE001 — lỗi xác thực của nhà cung cấp
        ai_registry.forget_models(user.id, p)
        raise fastapi.HTTPException(400, f"Key không dùng được với {ai_registry.PROVIDERS[p].info.name}: {str(e)[:200]}")
    dependencies.db().upsert_key(user.id, p, crypto.encrypt(key), crypto.key_hint(key))
    return {"ok": True, "models": models}


@private.delete("/ai/keys/{p}")
def delete_key(p: str, user: User = Depends(current_user)):
    _provider_or_404(p)
    dependencies.db().delete_key(user.id, p)
    if dependencies.db().get_default_ai(user.id) == p:
        dependencies.db().set_default_ai(user.id, None)
    ai_registry.forget_models(user.id, p)
    return {"ok": True}


@private.get("/ai/models/{p}")
async def models(p: str, refresh: bool = False, user: User = Depends(current_user)):
    _provider_or_404(p)
    keys = ai_registry.user_keys(dependencies.db(), user.id)
    if p not in keys:
        raise fastapi.HTTPException(400, f"Chưa có API key cho {ai_registry.PROVIDERS[p].info.name}.")
    try:
        items = await fastapi_concurrency.run_in_threadpool(ai_registry.list_models, user.id, p, keys[p][0], refresh)
    except Exception as e:  # noqa: BLE001
        raise fastapi.HTTPException(502, f"Không lấy được danh sách model: {str(e)[:200]}")
    return {"models": items, "default": ai_registry.pick_default(p, items)}
