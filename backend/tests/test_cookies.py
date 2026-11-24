"""Chế độ 'Server': đọc cookie, lưu mã hóa, định tuyến lượt, xử lý cookie hết hiệu lực."""
import json
import time

import pytest

from feedlens.browser.cookies import CookieError
from feedlens.browser.cookies import cookie_hint
from feedlens.browser.cookies import parse_cookies

FB_JSON = json.dumps([
    {"domain": ".facebook.com", "name": "c_user", "value": "100012345678", "path": "/", "secure": True,
     "httpOnly": False, "sameSite": "no_restriction", "expirationDate": time.time() + 86400},
    {"domain": ".facebook.com", "name": "xs", "value": "secret-xs", "path": "/", "secure": True, "httpOnly": True},
    {"domain": ".facebook.com", "name": "old", "value": "x", "expirationDate": 1000},     # hết hạn -> bỏ
    {"domain": ".google.com", "name": "SID", "value": "nope"},                            # khác domain -> bỏ
])


def test_parse_cookie_editor_json():
    cs = parse_cookies(FB_JSON, "facebook")
    assert {c["name"] for c in cs} == {"c_user", "xs"}
    c_user = next(c for c in cs if c["name"] == "c_user")
    assert c_user["sameSite"] == "None" and c_user["secure"] and c_user["domain"] == ".facebook.com"
    assert cookie_hint(cs, "facebook") == "…5678"


def test_parse_header_string_and_netscape():
    assert {c["name"] for c in parse_cookies("c_user=123; xs=abc; datr=zz", "facebook")} == {"c_user", "xs", "datr"}
    txt = ("# Netscape HTTP Cookie File\n"
           ".facebook.com\tTRUE\t/\tTRUE\t0\tc_user\t42\n"
           "#HttpOnly_.facebook.com\tTRUE\t/\tTRUE\t0\txs\tsecret\n")
    cs = parse_cookies(txt, "facebook")
    assert {c["name"]: c["httpOnly"] for c in cs} == {"c_user": False, "xs": True}


def test_parse_rejects_incomplete_or_garbage():
    with pytest.raises(CookieError, match="xs"):
        parse_cookies("c_user=123", "facebook")
    with pytest.raises(CookieError, match="JSON"):
        parse_cookies("[not json", "facebook")
    with pytest.raises(CookieError):
        parse_cookies("", "facebook")


# ---------------------------------------------------------------- API (dùng fixture cloud của test_cloud)
from tests.test_cloud import POSTS, _signup, _wait, cloud  # noqa: E402,F401


def test_cookie_sessions_api_encrypted_and_isolated(cloud):
    from feedlens import api
    c = cloud()
    a, b = _signup(c, "a@x.io"), _signup(c, "b@x.io")
    assert c.get("/api/meta").json()["server_scrape"] is True
    assert c.put("/api/sessions/facebook", headers=a, json={"cookies": "c_user=1; datr=2"}).status_code == 400
    r = c.put("/api/sessions/facebook", headers=a, json={"cookies": FB_JSON})
    assert r.status_code == 200 and r.json()["hint"] == "…5678" and r.json()["status"] == "unchecked"
    listing = c.get("/api/sessions", headers=a)
    assert [s["platform"] for s in listing.json()] == ["facebook"]
    assert "secret-xs" not in listing.text and "100012345678" not in listing.text   # không lộ cookie
    row = api.app.state.db.get_session(1, "facebook")
    assert "secret-xs" not in row.ciphertext                                          # mã hóa khi lưu
    assert c.get("/api/sessions", headers=b).json() == []
    assert c.delete("/api/sessions/facebook", headers=a).status_code == 200
    assert c.get("/api/sessions", headers=a).json() == []


def test_server_run_uses_cookies_and_marks_invalid(cloud, monkeypatch):
    from feedlens.runs import server_runner
    from feedlens.core.models import RawPost
    c = cloud()
    a = _signup(c)
    req = {"platform": "facebook", "source_type": "group", "sources": ["g1", "g2"], "count": 5,
           "ai_provider": "offline", "runner": "server"}
    assert c.post("/api/runs", headers=a, json=req).status_code == 400            # chưa có cookie
    c.put("/api/sessions/facebook", headers=a, json={"cookies": FB_JSON})

    seen_cookies = {}

    def fake_scrape(rq, cookies, seen, progress, report=None):
        seen_cookies["names"] = {x["name"] for x in cookies}
        assert rq.headless and rq.sources == ["g1", "g2"]
        progress(2, "g1: 2/5")
        return [RawPost(**p) for p in POSTS]

    monkeypatch.setattr(server_runner, "scrape_with_cookies", fake_scrape)
    run_id = c.post("/api/runs", headers=a, json=req).json()["id"]
    r = _wait(c, a, run_id)
    assert r["status"] == "done", r["error"]
    assert seen_cookies["names"] == {"c_user", "xs"}                               # đã giải mã đúng
    assert c.get("/api/sessions", headers=a).json()[0]["status"] == "ok"

    def blocked(*args):
        raise server_runner.CookieInvalid("facebook yêu cầu đăng nhập/xác minh")

    monkeypatch.setattr(server_runner, "scrape_with_cookies", blocked)
    run_id = c.post("/api/runs", headers=a, json=req).json()["id"]
    r = _wait(c, a, run_id)
    assert r["status"] == "error" and "xác minh" in r["error"]
    assert c.get("/api/sessions", headers=a).json()[0]["status"] == "invalid"
    again = c.post("/api/runs", headers=a, json=req)
    assert again.status_code == 400 and "hết hiệu lực" in again.json()["detail"]   # chặn tới khi gửi cookie mới
    c.put("/api/sessions/facebook", headers=a, json={"cookies": FB_JSON})
    assert c.get("/api/sessions", headers=a).json()[0]["status"] == "unchecked"


def test_server_mode_can_be_disabled(cloud):
    c = cloud(server_scrape=False)
    a = _signup(c)
    assert c.get("/api/meta").json()["server_scrape"] is False
    assert c.put("/api/sessions/facebook", headers=a, json={"cookies": FB_JSON}).status_code == 409
    assert c.post("/api/runs", headers=a, json={"platform": "facebook", "runner": "server",
                                                 "ai_provider": "offline"}).status_code == 403
