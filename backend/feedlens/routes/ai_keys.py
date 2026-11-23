"""Ai keys routes."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from ..auth import CurrentUser as User, current_user
from .. import api

private = APIRouter()


@private.get("/ai/providers")
def ai_providers(user: User = Depends(current_user)):
    return api.provider_status(api.db(), user.id)


class DefaultAIBody(BaseModel):
    provider: str = Field(max_length=40)


@private.put("/ai/default")
def set_default_ai(body: DefaultAIBody, user: User = Depends(current_user)):
    api._provider_or_404(body.provider)
    try:
        api.resolve_provider_key(body.provider, api.user_keys(api.db(), user.id))
    except ValueError as e:
        raise api.HTTPException(400, str(e))
    api.db().set_default_ai(user.id, body.provider)
    return {"ok": True}


class KeyBody(BaseModel):
    api_key: str = Field(min_length=8, max_length=500)


def _provider_or_404(p: str):
    if p not in api.PROVIDERS:
        raise api.HTTPException(404, "Nhà cung cấp AI không hỗ trợ")


@private.put("/ai/keys/{p}")
async def save_key(p: str, body: KeyBody, user: User = Depends(current_user)):
    """Kiểm tra key bằng cách lấy danh sách model, đúng thì mã hóa và lưu."""
    api._provider_or_404(p)
    key = body.api_key.strip()
    try:
        models = await api.run_in_threadpool(api.list_models, user.id, p, key, True)
    except Exception as e:  # noqa: BLE001 — lỗi xác thực của nhà cung cấp
        api.forget_models(user.id, p)
        raise api.HTTPException(400, f"Key không dùng được với {api.PROVIDERS[p].info.name}: {str(e)[:200]}")
    api.db().upsert_key(user.id, p, api.encrypt(key), api.key_hint(key))
    return {"ok": True, "models": models}


@private.delete("/ai/keys/{p}")
def delete_key(p: str, user: User = Depends(current_user)):
    api._provider_or_404(p)
    api.db().delete_key(user.id, p)
    if api.db().get_default_ai(user.id) == p:
        api.db().set_default_ai(user.id, None)
    api.forget_models(user.id, p)
    return {"ok": True}


@private.get("/ai/models/{p}")
async def models(p: str, refresh: bool = False, user: User = Depends(current_user)):
    api._provider_or_404(p)
    keys = api.user_keys(api.db(), user.id)
    if p not in keys:
        raise api.HTTPException(400, f"Chưa có API key cho {api.PROVIDERS[p].info.name}.")
    try:
        items = await api.run_in_threadpool(api.list_models, user.id, p, keys[p][0], refresh)
    except Exception as e:  # noqa: BLE001
        raise api.HTTPException(502, f"Không lấy được danh sách model: {str(e)[:200]}")
    return {"models": items, "default": api.pick_default(p, items)}
