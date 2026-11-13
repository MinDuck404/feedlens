"""Trình duyệt dùng profile riêng cho từng nền tảng.

Người dùng tự đăng nhập trong cửa sổ Chrome thật; cookie phiên được lưu trong
`data/profiles/<platform>`. FeedLens không bao giờ nhận hay lưu mật khẩu.
"""
from __future__ import annotations

import shutil
import time
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Iterator

from playwright.sync_api import BrowserContext, sync_playwright

from .config import settings


@dataclass(frozen=True)
class PlatformInfo:
    key: str
    name: str
    login_url: str
    home_url: str
    session_cookie: str  # cookie chứng tỏ đã đăng nhập
    cookie_domain: str


PLATFORMS: dict[str, PlatformInfo] = {
    "facebook": PlatformInfo("facebook", "Facebook", "https://www.facebook.com/login",
                             "https://www.facebook.com/", "c_user", "facebook.com"),
    "linkedin": PlatformInfo("linkedin", "LinkedIn", "https://www.linkedin.com/login",
                             "https://www.linkedin.com/feed/", "li_at", "linkedin.com"),
    "x": PlatformInfo("x", "X (Twitter)", "https://x.com/i/flow/login",
                      "https://x.com/home", "auth_token", "x.com"),
    "reddit": PlatformInfo("reddit", "Reddit", "https://www.reddit.com/login/",
                           "https://www.reddit.com/", "reddit_session", "reddit.com"),
}

def profile_dir(platform: str):
    return settings.profiles_dir / platform


@contextmanager
def open_context(platform: str, headless: bool = True) -> Iterator[BrowserContext]:
    pdir = profile_dir(platform)
    pdir.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as pw:
        kwargs = dict(
            user_data_dir=str(pdir),
            headless=headless,
            viewport=None if not headless else {"width": 1280, "height": 900},
            locale="vi-VN",
        )
        channel = settings.browser_channel
        try:
            ctx = pw.chromium.launch_persistent_context(
                channel=None if channel == "chromium" else channel, **kwargs)
        except Exception:
            # Fallback sang Chromium của Playwright (cần `playwright install chromium`)
            ctx = pw.chromium.launch_persistent_context(**kwargs)
        try:
            yield ctx
        finally:
            ctx.close()


def _has_session(ctx: BrowserContext, info: PlatformInfo) -> bool:
    return any(c["name"] == info.session_cookie and info.cookie_domain in c["domain"]
               for c in ctx.cookies())


def interactive_login(platform: str, timeout_s: int = 300) -> bool:
    """Mở cửa sổ Chrome để người dùng tự đăng nhập. Trả về True nếu phát hiện phiên."""
    info = PLATFORMS[platform]
    with open_context(platform, headless=False) as ctx:
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        if not _has_session(ctx, info):
            page.goto(info.login_url)
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            if _has_session(ctx, info):
                time.sleep(2)  # cho trang ghi nốt cookie
                return True
            if not ctx.pages:  # người dùng đóng cửa sổ
                break
            time.sleep(1)
        return _has_session(ctx, info)


def check_session(platform: str) -> bool:
    info = PLATFORMS[platform]
    if not profile_dir(platform).exists():
        return False
    try:
        with open_context(platform, headless=True) as ctx:
            return _has_session(ctx, info)
    except Exception:
        return False


def logout(platform: str) -> None:
    shutil.rmtree(profile_dir(platform), ignore_errors=True)
