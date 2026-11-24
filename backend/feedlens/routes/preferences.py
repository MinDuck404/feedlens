"""Preferences routes."""
from __future__ import annotations


import json

import fastapi as fastapi
import feedlens.routes.dependencies as dependencies

from fastapi import APIRouter, Depends, Request
from feedlens.core.auth import CurrentUser as User
from feedlens.core.auth import current_user

private = APIRouter()


PREFS_MAX_BYTES = 64_000


@private.get("/preferences")
def get_preferences(user: User = Depends(current_user)):
    return dependencies.db().get_preferences(user.id)


@private.put("/preferences")
async def put_preferences(request: Request, user: User = Depends(current_user)):
    """Lưu cài đặt của form "Lướt mới" và danh sách group. Frontend quyết định cấu trúc; server chỉ giới hạn kích thước."""
    raw = await request.body()
    if len(raw) > PREFS_MAX_BYTES:
        raise fastapi.HTTPException(413, "Cài đặt quá lớn.")
    try:
        prefs = json.loads(raw or b"{}")
    except ValueError:
        raise fastapi.HTTPException(400, "JSON không hợp lệ.")
    if not isinstance(prefs, dict):
        raise fastapi.HTTPException(400, "Cài đặt phải là một object JSON.")
    dependencies.db().set_preferences(user.id, prefs)
    return {"ok": True}
