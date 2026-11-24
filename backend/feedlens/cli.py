"""feedlens serve | login | run | push | agent | cookies push | demo"""
from __future__ import annotations

import argparse
import json
import os
import sys
import webbrowser


def _request_from_args(a):
    from feedlens.core.models import RunRequest

    req = RunRequest(platform=a.platform, source_type=a.source_type, sources=a.sources, count=a.count,
                      mode=getattr(a, "mode", None), options=getattr(a, "options", {}),
                      job_mode=a.jobs, keywords=a.keywords, profile=a.profile, only_new=a.only_new,
                      headless=a.headless, ai_provider=a.ai, ai_model=a.model)
    from feedlens.runs.source_modes import normalize
    normalize(req)
    return req


def _push(a) -> None:
    import httpx

    from feedlens.runs.pipeline import scrape

    if not a.server or not a.token:
        sys.exit("Thiếu --server/--token (hoặc biến FEEDLENS_SERVER / FEEDLENS_AGENT_TOKEN).")
    server = a.server.rstrip("/")
    req = _request_from_args(a)
    headers = {"Authorization": f"Bearer {a.token}"}
    # Kiểm tra kết nối + token trước khi tốn công lướt
    r = httpx.get(f"{server}/api/runs", headers=headers, timeout=30)
    if r.status_code != 200:
        sys.exit(f"Không kết nối được server ({r.status_code}): {r.text[:200]}")

    print(f"Đang lướt {req.platform}…")
    posts = scrape(req, set(), lambda n, msg: print(f"\r  {msg}", end="", flush=True))
    print()
    if not posts:
        sys.exit("Không lấy được bài nào — kiểm tra đăng nhập (`feedlens login`) hoặc selector.")
    r = httpx.post(f"{server}/api/ingest", headers=headers, timeout=120,
                   json={"request": req.model_dump(), "posts": [p.model_dump() for p in posts]})
    if r.status_code != 200:
        sys.exit(f"Server từ chối ({r.status_code}): {r.text[:300]}")
    print(f"Đã gửi {len(posts)} bài, lượt #{r.json()['id']}. Server đang phân tích; mở giao diện web để xem.")


def _push_cookies(a) -> None:
    import json

    import httpx

    from feedlens.runs.agent import load_config
    from feedlens.browser.profiles import open_context
    from feedlens.browser.profiles import profile_dir
    from feedlens.browser.cookies import DOMAIN

    cfg = load_config()
    server = (a.server or cfg.get("server") or os.getenv("FEEDLENS_SERVER", "")).rstrip("/")
    token = a.token or cfg.get("token") or os.getenv("FEEDLENS_AGENT_TOKEN", "")
    if not server or not token:
        sys.exit("Chưa có server/token. Chạy `feedlens agent --server ... --token ...` một lần, hoặc truyền --server --token.")
    if not profile_dir(a.platform).exists():
        sys.exit(f"Chưa đăng nhập {a.platform} trên máy này. Chạy `feedlens login {a.platform}` trước.")
    with open_context(a.platform, headless=True) as ctx:
        cookies = [c for c in ctx.cookies() if DOMAIN[a.platform] in c["domain"]]
    print(f"Đọc được {len(cookies)} cookie {DOMAIN[a.platform]} từ profile FeedLens. Đang gửi (mã hóa trên server)…")
    r = httpx.put(f"{server}/api/sessions/{a.platform}", timeout=60,
                  headers={"Authorization": f"Bearer {token}"}, json={"cookies": json.dumps(cookies)})
    if r.status_code != 200:
        sys.exit(f"Server từ chối ({r.status_code}): {r.json().get('detail', r.text)[:300]}")
    print(f"Đã lưu cookie {a.platform} ({r.json()['hint']}). Trên web chọn 'Chạy bằng: Server' để lướt không cần agent.")


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="feedlens")
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("serve", help="Chạy API (và giao diện đã build nếu có frontend/dist)")
    s.add_argument("--port", type=int, default=8765)
    s.add_argument("--open", action="store_true", help="Mở trình duyệt")

    lg = sub.add_parser("login", help="Mở Chrome để đăng nhập một nền tảng")
    lg.add_argument("platform", choices=["facebook", "linkedin", "x", "reddit"])

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("platform", choices=["facebook", "linkedin", "x", "reddit"])
    common.add_argument("--type", dest="source_type", default="feed", choices=["feed", "group", "search"])
    common.add_argument("--mode", help="Platform mode (jobs, page, subreddit, account, list…)")
    common.add_argument("--options", type=json.loads, default={}, help='Mode options JSON, e.g. {"keywords":"Python"}')
    common.add_argument("--source", dest="sources", action="append", default=[])
    common.add_argument("-n", "--count", type=int, default=30)
    common.add_argument("--jobs", action="store_true", help="Chế độ tìm việc")
    common.add_argument("-k", "--keyword", dest="keywords", action="append", default=[])
    common.add_argument("--profile", default="", help="Vài dòng về bạn, để chấm độ phù hợp việc làm")
    common.add_argument("--only-new", action="store_true", help="Bỏ qua bài đã thấy ở lượt trước")
    common.add_argument("--headless", action="store_true", help="Chạy ẩn (một số nền tảng sẽ chặn)")
    common.add_argument("--ai", default="auto", choices=["auto", "anthropic", "openai", "gemini", "offline"])
    common.add_argument("--model", default="", help="Ghi đè model của nhà cung cấp AI")

    sub.add_parser("run", parents=[common], help="Lướt + tóm tắt ngay trên máy này")
    p = sub.add_parser("push", parents=[common], help="Lướt một lần trên máy này rồi gửi bài lên server cloud")
    p.add_argument("--server", default=os.getenv("FEEDLENS_SERVER", ""), help="URL backend cloud (hoặc FEEDLENS_SERVER)")
    p.add_argument("--token", default=os.getenv("FEEDLENS_AGENT_TOKEN", ""), help="Token agent (hoặc FEEDLENS_AGENT_TOKEN)")

    ag = sub.add_parser("agent", help="Chạy nền: nhận việc từ web FeedLens cloud, lướt trên máy này")
    ag.add_argument("--server", default="", help="URL backend cloud (lưu lại cho lần sau)")
    ag.add_argument("--token", default="", help="Token agent tạo trong phần Cài đặt (lưu lại cho lần sau)")

    ck = sub.add_parser("cookies", help="Gửi cookie đăng nhập (từ profile FeedLens trên máy) lên server để lướt bằng server")
    ck.add_argument("action", choices=["push"])
    ck.add_argument("platform", choices=["facebook", "linkedin", "x", "reddit"])
    ck.add_argument("--server", default="", help="URL backend cloud (mặc định lấy từ cấu hình agent)")
    ck.add_argument("--token", default="", help="Token agent (mặc định lấy từ cấu hình agent)")

    sub.add_parser("demo", help="Tạo một lượt mẫu (dữ liệu giả) để xem giao diện")
    sub.add_parser("clean-cache", help="Dọn cache Chrome trong các profile (giữ nguyên phiên đăng nhập)")

    a = ap.parse_args(argv)
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")

    if a.cmd == "serve":
        import uvicorn
        if a.open:
            import threading
            import urllib.request

            def open_when_ready():
                url = f"http://127.0.0.1:{a.port}"
                for _ in range(60):  # đợi server sẵn sàng rồi mới mở trình duyệt
                    try:
                        urllib.request.urlopen(f"{url}/api/health", timeout=1)
                        break
                    except Exception:  # noqa: BLE001
                        threading.Event().wait(0.5)
                webbrowser.open(url)

            threading.Thread(target=open_when_ready, daemon=True).start()
        uvicorn.run("feedlens.api:app", host="127.0.0.1", port=a.port)
        # Web server đã tắt. Không chờ các lô AI đang thử lại (ThreadPoolExecutor bị Python join lúc thoát,
        # có thể treo terminal hàng phút). Lô xong đã lưu; lần chạy sau fail_interrupted() mở "Phân tích tiếp".
        sys.stdout.flush()
        sys.stderr.flush()
        os._exit(0)
    elif a.cmd == "login":
        from feedlens.browser.profiles import interactive_login
        print("Đăng nhập trong cửa sổ Chrome vừa mở. FeedLens chỉ lưu cookie phiên, không lưu mật khẩu.")
        print("✅ Đã đăng nhập" if interactive_login(a.platform) else "❌ Chưa phát hiện phiên đăng nhập")
    elif a.cmd == "push":
        if not a.server or not a.token:
            from feedlens.runs.agent import load_config
            cfg = load_config()
            a.server, a.token = a.server or cfg.get("server", ""), a.token or cfg.get("token", "")
        _push(a)
    elif a.cmd == "agent":
        from feedlens.runs.agent import Agent
        from feedlens.runs.agent import load_config
        from feedlens.runs.agent import save_config

        cfg = load_config()
        server = a.server or cfg.get("server") or os.getenv("FEEDLENS_SERVER", "")
        token = a.token or cfg.get("token") or os.getenv("FEEDLENS_AGENT_TOKEN", "")
        if not server or not token:
            sys.exit("Lần đầu chạy: feedlens agent --server <URL backend> --token <token tạo trên web>")
        if a.server or a.token:
            save_config(server, token)
        try:
            Agent(server, token).run_forever()
        except KeyboardInterrupt:
            print("\nĐã dừng agent.")
    elif a.cmd == "cookies":
        _push_cookies(a)
    elif a.cmd == "clean-cache":
        from feedlens.browser.profiles import clean_all_caches

        results = clean_all_caches()
        if not results:
            print("Chưa có profile nào để dọn.")
        for platform, before, after in results:
            print(f"{platform}: {before / 1048576:.0f}MB -> {after / 1048576:.0f}MB")
    elif a.cmd == "demo":
        from feedlens.runs import pipeline
        from feedlens.core.config import settings
        from feedlens.db.repository import Database
        from .demo import DEMO_POSTS
        from feedlens.core.models import RunRequest

        db = Database(settings.database_url)
        req = RunRequest(platform="facebook", source_type="group", sources=["https://www.facebook.com/groups/demo"],
                         count=len(DEMO_POSTS), job_mode=True, keywords=["python", "remote"], ai_provider="offline")
        pipeline.scrape = lambda *_: list(DEMO_POSTS)
        uid = db.local_user_id()
        run_id = db.create_run(req, uid)
        pipeline.execute_run(db, run_id, req, uid)
        print(f"Đã tạo lượt mẫu #{run_id}. Chạy `feedlens serve` để xem.")
    elif a.cmd == "run":
        from feedlens.core.config import settings
        from feedlens.db.repository import Database
        from feedlens.runs.export import to_markdown
        from feedlens.core.models import RunRequest
        from feedlens.runs.pipeline import execute_run

        db = Database(settings.database_url)
        req = _request_from_args(a)
        uid = db.local_user_id()
        run_id = db.create_run(req, uid)
        execute_run(db, run_id, req, uid)
        run = db.get_run(run_id)
        if run["status"] == "error":
            print("Lỗi:", run["error"]); sys.exit(1)
        print(to_markdown(run, [p for p in db.get_posts(run_id) if p.analyzed]))


if __name__ == "__main__":
    main()
