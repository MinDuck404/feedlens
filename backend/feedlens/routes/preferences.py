"""Preferences routes."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from ..auth import CurrentUser as User, current_user
from .. import api

private = APIRouter()


@private.get("/preferences")
def get_preferences(user: User = Depends(current_user)):
    return api.db().get_preferences(user.id)


@private.put("/preferences")
async def put_preferences(request: Request, user: User = Depends(current_user)):
    """Lưu cài đặt của form "Lướt mới" và danh sách group. Frontend quyết định cấu trúc; server chỉ giới hạn kích thước."""
    raw = await request.body()
    if len(raw) > api.PREFS_MAX_BYTES:
        raise api.HTTPException(413, "Cài đặt quá lớn.")
    try:
        prefs = api.json.loads(raw or b"{}")
    except ValueError:
        raise api.HTTPException(400, "JSON không hợp lệ.")
    if not isinstance(prefs, dict):
        raise api.HTTPException(400, "Cài đặt phải là một object JSON.")
    api.db().set_preferences(user.id, prefs)
    return {"ok": True}
