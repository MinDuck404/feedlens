"""Đọc cookie người dùng dán vào (hoặc agent gửi lên) và chuẩn hóa về định dạng Playwright.

Hỗ trợ:
- JSON mảng từ extension Cookie-Editor / EditThisCookie, hoặc JSON xuất bởi Playwright (`context.cookies()`)
- Netscape `cookies.txt`
- Chuỗi header kiểu `c_user=123; xs=abc; datr=...`
"""
from __future__ import annotations

import json
import time

# Cookie chứng tỏ đã đăng nhập, và tên miền gốc của từng nền tảng
SESSION_COOKIE = {"facebook": "c_user", "linkedin": "li_at", "x": "auth_token", "reddit": "reddit_session"}
DOMAIN = {"facebook": "facebook.com", "linkedin": "linkedin.com", "x": "x.com", "reddit": "reddit.com"}
# Cookie cần thêm để phiên thật sự dùng được (thiếu thì báo người dùng)
REQUIRED = {"facebook": {"c_user", "xs"}, "linkedin": {"li_at"}, "x": {"auth_token", "ct0"}, "reddit": {"reddit_session"}}

_SAMESITE = {"no_restriction": "None", "none": "None", "lax": "Lax", "strict": "Strict", "unspecified": "Lax"}


class CookieError(ValueError):
    pass


def _norm(c: dict, platform: str) -> dict | None:
    name, value = c.get("name"), c.get("value")
    if not name or value is None:
        return None
    domain = (c.get("domain") or f".{DOMAIN[platform]}").strip()
    if DOMAIN[platform] not in domain:
        return None
    if not domain.startswith("."):
        domain = "." + domain.lstrip(".")
    expires = c.get("expires", c.get("expirationDate"))
    try:
        expires = float(expires) if expires not in (None, "", -1) else -1
    except (TypeError, ValueError):
        expires = -1
    if 0 < expires < time.time():
        return None  # đã hết hạn
    same = _SAMESITE.get(str(c.get("sameSite", "lax")).lower(), "Lax")
    secure = bool(c.get("secure", True)) or same == "None"
    return {"name": str(name), "value": str(value), "domain": domain, "path": c.get("path") or "/",
            "expires": expires, "httpOnly": bool(c.get("httpOnly", False)), "secure": secure, "sameSite": same}


def parse_cookies(text: str, platform: str) -> list[dict]:
    if platform not in DOMAIN:
        raise CookieError(f"Nền tảng không hỗ trợ: {platform}")
    text = (text or "").strip()
    if not text:
        raise CookieError("Chưa dán cookie nào.")
    raw: list[dict] = []
    if text[0] in "[{":
        try:
            data = json.loads(text)
        except ValueError as e:
            raise CookieError(f"JSON không hợp lệ: {e}") from e
        if isinstance(data, dict):
            data = data.get("cookies", [data])
        raw = [c for c in data if isinstance(c, dict)]
    elif "\t" in text:  # Netscape cookies.txt
        for line in text.splitlines():
            if line.startswith("#HttpOnly_"):
                line, http_only = line[len("#HttpOnly_"):], True
            elif line.startswith("#") or not line.strip():
                continue
            else:
                http_only = False
            parts = line.split("\t")
            if len(parts) >= 7:
                raw.append({"domain": parts[0], "path": parts[2], "secure": parts[3].upper() == "TRUE",
                            "expirationDate": parts[4], "name": parts[5], "value": parts[6].strip(),
                            "httpOnly": http_only})
    else:  # c_user=1; xs=2
        for pair in text.replace("\n", ";").split(";"):
            if "=" in pair:
                k, v = pair.split("=", 1)
                raw.append({"name": k.strip(), "value": v.strip(), "secure": True, "httpOnly": True})
    cookies = [n for c in raw if (n := _norm(c, platform))]
    names = {c["name"] for c in cookies}
    missing = REQUIRED[platform] - names
    if missing:
        raise CookieError(f"Thiếu cookie {', '.join(sorted(missing))} của {DOMAIN[platform]}. "
                          "Hãy xuất cookie khi đang đăng nhập (đã qua xác minh 2 bước).")
    return cookies


def cookie_hint(cookies: list[dict], platform: str) -> str:
    """Gợi ý nhận dạng tài khoản mà không lộ giá trị nhạy cảm (vd 4 số cuối c_user)."""
    sid = next((c["value"] for c in cookies if c["name"] == SESSION_COOKIE[platform]), "")
    return f"…{sid[-4:]}" if platform == "facebook" and sid.isdigit() else f"{len(cookies)} cookie"
