
import threading

import feedlens.routes.auth as auth_routes
import feedlens.routes.dependencies as dependencies
import feedlens.routes.platforms as platform_routes
from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from feedlens import api, browser
from tests.test_cloud import cloud, _signup, _agent


class ImmediateThread:
    def __init__(self, target, **kwargs):
        self.target = target

    def start(self):
        self.target()


def fake_playwright(monkeypatch, executable, error=None):
    launched = []
    context = SimpleNamespace(close=lambda: None)

    def launch(**kwargs):
        launched.append(kwargs)
        if error:
            raise error
        return context

    @contextmanager
    def playwright():
        yield SimpleNamespace(chromium=SimpleNamespace(executable_path=str(executable), launch_persistent_context=launch))

    monkeypatch.setattr(browser, "sync_playwright", playwright)
    return launched


def no_native(monkeypatch):
    monkeypatch.setattr(browser, "find_chrome", lambda: None)
    monkeypatch.setattr(browser, "find_edge", lambda: None, raising=False)


def local_state(monkeypatch, tmp_path):
    monkeypatch.setattr(browser, "settings", SimpleNamespace(profiles_dir=tmp_path, browser_channel="chrome"))
    for name in ("_login_state", "_session_cache", "_session_checks", "_login_errors", "_login_finish"):
        monkeypatch.setattr(platform_routes, name, {}, raising=False)
    monkeypatch.setattr(platform_routes, "_session_started", True)


def test_login_api_missing_browser_returns_error_without_ghost_profile(cloud, monkeypatch, tmp_path):
    client = cloud(mode="local")
    local_state(monkeypatch, tmp_path)
    no_native(monkeypatch)
    fake_playwright(monkeypatch, tmp_path / "missing", RuntimeError("Executable doesn't exist"))
    monkeypatch.setattr(threading, "Thread", ImmediateThread)
    response = client.post("/api/platforms/facebook/login")
    assert response.status_code == 503
    assert response.json()["code"] == "error.browser_missing"
    state = client.get("/api/platforms").json()[0]
    assert state["login_state"] == "idle" and state["has_profile"] is False
    assert not (tmp_path / "facebook").exists()


def test_login_worker_runtime_error_is_reported_not_swallowed(cloud, monkeypatch, tmp_path):
    client = cloud(mode="local")
    local_state(monkeypatch, tmp_path)
    monkeypatch.setattr(browser, "find_chrome", lambda: "chrome")
    monkeypatch.setattr(browser, "detect_browser", lambda *a, **k: browser.BrowserInfo("chrome", "chrome"))
    monkeypatch.setattr(threading, "Thread", ImmediateThread)
    monkeypatch.setattr(browser, "interactive_login", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("profile locked")))
    assert client.post("/api/platforms/facebook/login").status_code == 200
    state = client.get("/api/platforms").json()[0]
    assert state["login_state"] == "idle"
    assert state["login_error"] == "profile locked"
    assert state["login_error_code"] == "error.browser_failed"
    client.post("/api/platforms/facebook/logout")
    assert client.get("/api/platforms").json()[0]["login_error"] is None


def test_open_context_missing_browser_raises_structured_error_and_leaves_no_profile_dir(monkeypatch, tmp_path):
    local_state(monkeypatch, tmp_path)
    no_native(monkeypatch)
    fake_playwright(monkeypatch, tmp_path / "missing")
    with pytest.raises(browser.BrowserNotFoundError):
        with browser.open_context("facebook"):
            pytest.fail("Missing browser launched")
    assert not (tmp_path / "facebook").exists()


def test_open_context_and_login_both_honor_feedlens_chrome_path(monkeypatch, tmp_path):
    local_state(monkeypatch, tmp_path)
    executable = tmp_path / "portable" / "chrome.exe"
    executable.parent.mkdir()
    executable.touch()
    monkeypatch.setenv("FEEDLENS_CHROME_PATH", str(executable))
    launched = fake_playwright(monkeypatch, tmp_path / "missing")
    plain = []
    monkeypatch.setattr(browser.subprocess, "Popen", lambda args: plain.append(args) or SimpleNamespace(wait=lambda **k: 0))
    monkeypatch.setattr(browser, "check_session", lambda p: True)
    assert browser.interactive_login("facebook")
    with browser.open_context("facebook"):
        pass
    assert plain[0][0] == str(executable)
    assert launched[0]["executable_path"] == str(executable)
    assert "channel" not in launched[0]


def test_windows_edge_fallback_uses_plain_window_login(monkeypatch, tmp_path):
    local_state(monkeypatch, tmp_path)
    monkeypatch.delenv("FEEDLENS_CHROME_PATH", raising=False)
    monkeypatch.setattr(browser.sys, "platform", "win32")
    for env in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA"):
        monkeypatch.setenv(env, str(tmp_path if env == "PROGRAMFILES(X86)" else tmp_path / "absent"))
    executable = tmp_path / "Microsoft/Edge/Application/msedge.exe"
    executable.parent.mkdir(parents=True)
    executable.touch()
    launched = fake_playwright(monkeypatch, tmp_path / "missing")
    plain = []
    monkeypatch.setattr(browser.subprocess, "Popen", lambda args: plain.append(args) or SimpleNamespace(wait=lambda **k: 0))
    monkeypatch.setattr(browser, "check_session", lambda p: True)
    monkeypatch.setattr(browser, "_playwright_login", lambda *a: pytest.fail("Edge must use a plain window"))
    assert browser.interactive_login("linkedin")
    assert plain[0][0] == str(executable)
    assert not any("automation" in arg or "remote-debugging" in arg for arg in plain[0])
    assert browser.browser_status("linkedin") == {"browser": "msedge", "oauth_limited": False, "missing": False}
    with browser.open_context("linkedin"):
        pass
    assert launched[0]["executable_path"] == str(executable)


def test_playwright_chromium_fallback_marks_oauth_limited(monkeypatch, tmp_path):
    local_state(monkeypatch, tmp_path)
    no_native(monkeypatch)
    executable = tmp_path / "playwright-chromium"
    executable.touch()
    launched = fake_playwright(monkeypatch, executable)
    assert browser.browser_status() == {"browser": "chromium", "oauth_limited": True, "missing": False}
    monkeypatch.setattr(browser, "_playwright_login", lambda *args: "automated")
    assert browser.interactive_login("reddit") == "automated"
    with browser.open_context("reddit"):
        pass
    assert launched[0]["executable_path"] == str(executable)
    assert "channel" not in launched[0]
    assert (tmp_path / "reddit/.browser").read_text() == "chromium"


@pytest.mark.parametrize("system,command", [("darwin", None), ("linux", "google-chrome-stable"), ("linux", "chromium"), ("linux", None)])
def test_macos_user_apps_and_linux_browser_detection(monkeypatch, tmp_path, system, command):
    monkeypatch.delenv("FEEDLENS_CHROME_PATH", raising=False)
    monkeypatch.setattr(browser.sys, "platform", system)
    monkeypatch.setattr(browser.Path, "home", lambda: tmp_path)
    executable = tmp_path / ("Applications/Google Chrome.app/Contents/MacOS/Google Chrome" if system == "darwin" else "browser")
    executable.parent.mkdir(parents=True, exist_ok=True)
    executable.touch()
    monkeypatch.setattr(browser.shutil, "which", lambda name: str(executable) if name == command else None)
    monkeypatch.setattr(browser.Path, "is_file", lambda path: path == executable)
    assert browser.find_chrome() == (str(executable) if system == "darwin" or command else None)


def test_profile_browser_affinity_avoids_cross_browser_switch(monkeypatch, tmp_path):
    local_state(monkeypatch, tmp_path)
    monkeypatch.setattr(browser, "find_chrome", lambda: "new-chrome")
    monkeypatch.setattr(browser, "find_edge", lambda: "existing-edge")
    pdir = tmp_path / "facebook"
    pdir.mkdir()
    (pdir / ".browser").write_text("msedge")
    launched = fake_playwright(monkeypatch, tmp_path / "missing")
    with browser.open_context("facebook"):
        pass
    assert launched[0]["executable_path"] == "existing-edge"
    monkeypatch.setattr(browser, "find_edge", lambda: None)
    with pytest.raises(browser.BrowserNotFoundError):
        with browser.open_context("facebook"):
            pass
    assert len(launched) == 1


def test_legacy_profile_stays_chrome_and_launch_failure_does_not_fall_back(monkeypatch, tmp_path):
    local_state(monkeypatch, tmp_path)
    monkeypatch.setattr(browser, "find_chrome", lambda: "chrome")
    monkeypatch.setattr(browser, "find_edge", lambda: "edge")
    pdir = tmp_path / "facebook"
    pdir.mkdir()
    (pdir / "Cookies").write_bytes(b"keep")
    launched = fake_playwright(monkeypatch, tmp_path / "missing", RuntimeError("profile locked"))
    with pytest.raises(RuntimeError, match="profile locked"):
        with browser.open_context("facebook"):
            pass
    assert len(launched) == 1 and launched[0]["executable_path"] == "chrome"
    assert (pdir / "Cookies").read_bytes() == b"keep"


@pytest.mark.parametrize("diagnostic", ["Browser not found: Chrome", "Executable doesn't exist at /custom/path"])
def test_local_run_missing_browser_maps_to_browser_missing_code(cloud, monkeypatch, diagnostic):
    from feedlens.runs import pipeline
    from feedlens.analysis.heuristic import HeuristicAnalyzer
    from feedlens.models import RunRequest

    client = cloud(mode="local")
    req = RunRequest(platform="facebook", ai_provider="offline")
    rid = dependencies.db().create_run(req, dependencies.db().local_user_id())
    monkeypatch.setattr(pipeline, "get_analyzer", lambda *args: HeuristicAnalyzer())
    monkeypatch.setattr(pipeline, "scrape", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError(diagnostic)))
    pipeline.execute_run(dependencies.db(), rid, req)
    detail = client.get(f"/api/runs/{rid}").json()
    assert detail["status"] == "error" and detail["error_code"] == "error.browser_missing"


def test_cloud_agent_fail_missing_browser_maps_to_browser_missing_code(cloud):
    from feedlens.models import RunRequest

    client = cloud()
    headers = _signup(client)
    agent = _agent(client, headers)
    uid = dependencies.db().get_user_by_email("a@x.io").id
    rid = dependencies.db().create_run(RunRequest(platform="facebook"), uid)
    assert client.post(f"/api/agent/runs/{rid}/fail", headers=agent, json={"error": "Executable doesn't exist"}).status_code == 200
    assert client.get(f"/api/runs/{rid}", headers=headers).json()["error_code"] == "error.browser_missing"


@pytest.mark.parametrize("name", ["chrome", "msedge", "chromium", None])
def test_browser_status_and_cloud_isolation(cloud, monkeypatch, tmp_path, name):
    client = cloud(mode="local")
    local_state(monkeypatch, tmp_path)
    monkeypatch.setattr(browser, "find_chrome", lambda: "chrome" if name == "chrome" else None)
    monkeypatch.setattr(browser, "find_edge", lambda: "edge" if name == "msedge" else None)
    executable = tmp_path / "outside-default-cache" / "chromium"
    executable.parent.mkdir()
    if name == "chromium":
        executable.touch()
    fake_playwright(monkeypatch, executable)
    state = client.get("/api/platforms").json()[0]
    assert state["browser"] == name
    assert state["missing"] is (name is None)
    assert state["oauth_limited"] is (name == "chromium")
    assert auth_routes._browser_installed() is (name is not None)
    client = cloud()
    headers = _signup(client)
    response = client.post("/api/platforms/facebook/login", headers=headers)
    assert response.status_code == 409 and response.json()["code"] == "error.local_only"


def test_empty_ghost_profile_can_use_edge_and_launch_failure_leaves_no_new_folder(monkeypatch, tmp_path):
    local_state(monkeypatch, tmp_path)
    monkeypatch.setattr(browser, "find_chrome", lambda: None)
    monkeypatch.setattr(browser, "find_edge", lambda: "edge")
    (tmp_path / "facebook").mkdir()
    assert browser.detect_browser("facebook").name == "msedge"
    selected = browser.BrowserInfo("msedge", "edge")
    monkeypatch.setattr(browser, "detect_browser", lambda *a, **k: selected)
    monkeypatch.setattr(browser.subprocess, "Popen", lambda *a, **k: (_ for _ in ()).throw(OSError("Cannot start")))
    with pytest.raises(OSError):
        browser.interactive_login("linkedin")
    assert not (tmp_path / "linkedin").exists()


def test_partial_playwright_launch_failure_is_cleaned_without_touching_old_profiles(monkeypatch, tmp_path):
    local_state(monkeypatch, tmp_path)
    monkeypatch.setattr(browser, "find_chrome", lambda: "chrome")
    @contextmanager
    def playwright():
        def launch(**kwargs):
            from pathlib import Path
            pdir = Path(kwargs["user_data_dir"])
            assert not pdir.exists()
            pdir.mkdir()
            (pdir / "generated-lock").touch()
            raise RuntimeError("launch failed")
        yield SimpleNamespace(chromium=SimpleNamespace(launch_persistent_context=launch))
    monkeypatch.setattr(browser, "sync_playwright", playwright)
    with pytest.raises(RuntimeError, match="launch failed"):
        with browser.open_context("facebook"):
            pass
    assert not (tmp_path / "facebook").exists()


def test_agent_check_warns_without_blocking_or_installing_a_browser(monkeypatch, tmp_path, capsys):
    import httpx
    from feedlens.runs.agent import Agent

    no_native(monkeypatch)
    agent = Agent("https://example.test", "fake-token")
    agent.http.close()
    agent.http = httpx.Client(base_url="https://example.test", transport=httpx.MockTransport(
        lambda request: httpx.Response(200, json={"email": "user@example.test"})))
    try:
        agent.check()
    finally:
        agent.http.close()
    output = capsys.readouterr().out
    assert "Chrome/Edge not found" in output and "user@example.test" in output
    assert "https://www.google.com/chrome/" in output


def test_native_browser_does_not_print_a_startup_warning(monkeypatch, capsys):
    monkeypatch.setattr(browser, "find_chrome", lambda: "chrome")
    browser.warn_if_no_native_browser()
    assert capsys.readouterr().out == ""


def test_server_scrape_missing_browser_maps_to_browser_missing_code(cloud, monkeypatch, tmp_path):
    import playwright.sync_api
    from feedlens.runs import pipeline
    from feedlens.analysis.heuristic import HeuristicAnalyzer
    from feedlens.models import RunRequest

    client = cloud()
    headers = _signup(client)
    uid = dependencies.db().get_user_by_email("a@x.io").id
    assert client.put("/api/sessions/facebook", headers=headers, json={"cookies": "c_user=123; xs=synthetic"}).status_code == 200
    req = RunRequest(platform="facebook", ai_provider="offline", runner="server")
    rid = dependencies.db().create_run(req, uid)
    no_native(monkeypatch)
    fake_playwright(monkeypatch, tmp_path / "missing")
    monkeypatch.setattr(playwright.sync_api, "sync_playwright", browser.sync_playwright)
    monkeypatch.setattr(pipeline, "get_analyzer", lambda *args: HeuristicAnalyzer())
    pipeline.execute_server_run(dependencies.db(), rid, req, uid)
    detail = client.get(f"/api/runs/{rid}", headers=headers).json()
    assert detail["status"] == "error" and detail["error_code"] == "error.browser_missing"
