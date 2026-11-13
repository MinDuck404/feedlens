"""feedlens serve | login | run | push | agent | cookies push | demo"""
from __future__ import annotations

import argparse
import os
import sys
import webbrowser


def _request_from_args(a):
    from .models import RunRequest

    return RunRequest(platform=a.platform, source_type=a.source_type, sources=a.sources, count=a.count,
                      job_mode=a.jobs, keywords=a.keywords, profile=a.profile, only_new=a.only_new,
                      headless=a.headless, ai_provider=a.ai, ai_model=a.model)


def _push(a) -> None:
    import httpx

    from .pipeline import scrape

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

    from .agent import load_config
    from .browser import open_context, profile_dir
    from .cookies import DOMAIN

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

    a = ap.parse_args(argv)
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")

    if a.cmd == "serve":
        import uvicorn
        if a.open:
            webbrowser.open(f"http://127.0.0.1:{a.port}")
        uvicorn.run("feedlens.api:app", host="127.0.0.1", port=a.port)
    elif a.cmd == "login":
        from .browser import interactive_login
        print("Đăng nhập trong cửa sổ Chrome vừa mở. FeedLens chỉ lưu cookie phiên, không lưu mật khẩu.")
        print("✅ Đã đăng nhập" if interactive_login(a.platform) else "❌ Chưa phát hiện phiên đăng nhập")
    elif a.cmd == "push":
        if not a.server or not a.token:
            from .agent import load_config
            cfg = load_config()
            a.server, a.token = a.server or cfg.get("server", ""), a.token or cfg.get("token", "")
        _push(a)
    elif a.cmd == "agent":
        from .agent import Agent, load_config, save_config

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
    elif a.cmd == "demo":
        from . import pipeline
        from .config import settings
        from .db import Database
        from .demo import DEMO_POSTS
        from .models import RunRequest

        db = Database(settings.database_url)
        req = RunRequest(platform="facebook", source_type="group", sources=[DEMO_POSTS[0].source],
                         count=len(DEMO_POSTS), job_mode=True, keywords=["python", "remote"], ai_provider="offline")
        pipeline.scrape = lambda *_: list(DEMO_POSTS)
        uid = db.local_user_id()
        run_id = db.create_run(req, uid)
        pipeline.execute_run(db, run_id, req, uid)
        print(f"Đã tạo lượt mẫu #{run_id}. Chạy `feedlens serve` để xem.")
    elif a.cmd == "run":
        from .config import settings
        from .db import Database
        from .export import to_markdown
        from .models import RunRequest
        from .pipeline import execute_run

        db = Database(settings.database_url)
        req = _request_from_args(a)
        uid = db.local_user_id()
        run_id = db.create_run(req, uid)
        execute_run(db, run_id, req, uid)
        run = db.get_run(run_id)
        if run["status"] == "error":
            print("Lỗi:", run["error"]); sys.exit(1)
        print(to_markdown(run, db.get_posts(run_id)))


if __name__ == "__main__":
    main()
