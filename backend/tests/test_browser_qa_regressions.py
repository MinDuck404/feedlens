
import feedlens.routes.auth as auth_routes
from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from feedlens import api
from feedlens import browser
from feedlens.runs import server_runner
from tests.test_browser_detection import cloud, fake_playwright, local_state, no_native


def test_headless_shell_only_can_run_server_but_cannot_open_login(monkeypatch, tmp_path):
    import playwright.sync_api as playwright_api
    local_state(monkeypatch, tmp_path)
    no_native(monkeypatch)
    full = tmp_path / "chromium-123/chrome-linux64/chrome"
    shell = tmp_path / "chromium_headless_shell-123/chrome-headless-shell-linux64/chrome-headless-shell"
    shell.parent.mkdir(parents=True)
    shell.touch()
    launched = []
    page = SimpleNamespace(set_default_timeout=lambda *a: None)
    context = SimpleNamespace(add_cookies=lambda *a: None, route=lambda *a: None, new_page=lambda: page)
    engine = SimpleNamespace(new_context=lambda **kw: context, close=lambda: None)
    @contextmanager
    def playwright():
        yield SimpleNamespace(chromium=SimpleNamespace(executable_path=str(full), launch=lambda **kw: launched.append(kw) or engine))
    monkeypatch.setattr(browser, "sync_playwright", playwright)
    monkeypatch.setattr(playwright_api, "sync_playwright", playwright)
    with server_runner.cookie_page([]) as opened:
        assert opened is page
    assert launched[0]["headless"] is True
    assert "executable_path" not in launched[0] or launched[0]["executable_path"] == str(shell)
    assert auth_routes._browser_installed()
    with pytest.raises(browser.BrowserNotFoundError):
        browser.interactive_login("facebook")


def test_platform_poll_shares_discovery_and_caches_it(cloud, monkeypatch, tmp_path):
    client = cloud(mode="local")
    local_state(monkeypatch, tmp_path)
    no_native(monkeypatch)
    fake_playwright(monkeypatch, tmp_path / "missing")
    clock = [0.0]
    monkeypatch.setattr(browser, "time", SimpleNamespace(monotonic=lambda: clock[0]))
    original = browser.sync_playwright
    calls = []
    @contextmanager
    def counted():
        calls.append(True)
        with original() as pw:
            yield pw
    monkeypatch.setattr(browser, "sync_playwright", counted)
    assert len(client.get("/api/platforms").json()) == 4
    assert len(client.get("/api/platforms").json()) == 4
    assert len(calls) == 1
    clock[0] = 16.0
    client.get("/api/platforms")
    assert len(calls) == 2
    client.post("/api/platforms/facebook/check")
    assert len(calls) == 3  # Manual checks bypass the polling cache.


def test_explicit_check_returns_missing_and_finishes_checking(cloud, monkeypatch, tmp_path):
    client = cloud(mode="local")
    local_state(monkeypatch, tmp_path)
    no_native(monkeypatch)
    fake_playwright(monkeypatch, tmp_path / "missing")
    result = client.post("/api/platforms/facebook/check").json()
    assert result["missing"] is True
    assert client.get("/api/platforms").json()[0]["checking"] is False


def test_startup_browser_warning_includes_vietnamese(monkeypatch, capsys):
    no_native(monkeypatch)
    browser.warn_if_no_native_browser()
    assert "Chưa tìm thấy Chrome/Edge" in capsys.readouterr().out
