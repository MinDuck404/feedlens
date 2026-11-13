"""Agent chạy trên máy người dùng: nhận việc từ server FeedLens cloud, lướt bằng Chrome thật, gửi bài lên.

    feedlens agent --server https://feedlens-api.onrender.com --token fla_...   (lần đầu, lưu cấu hình)
    feedlens agent                                                               (các lần sau)
"""
from __future__ import annotations

import json
import time
import traceback
from pathlib import Path

import httpx

from .models import RunRequest
from .pipeline import scrape

CONFIG = Path.home() / ".feedlens" / "agent.json"
POLL_SECONDS = 2


def load_config() -> dict:
    try:
        return json.loads(CONFIG.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_config(server: str, token: str) -> None:
    CONFIG.parent.mkdir(parents=True, exist_ok=True)
    CONFIG.write_text(json.dumps({"server": server, "token": token}), encoding="utf-8")
    try:
        CONFIG.chmod(0o600)
    except OSError:
        pass


class Agent:
    def __init__(self, server: str, token: str):
        self.http = httpx.Client(base_url=server.rstrip("/"), timeout=60,
                                 headers={"Authorization": f"Bearer {token}"})

    def check(self) -> None:
        r = self.http.get("/api/auth/me")
        if r.status_code == 401:
            raise SystemExit("Token agent không hợp lệ. Tạo token mới trong phần Cài đặt trên web.")
        r.raise_for_status()
        print(f"Đã kết nối {self.http.base_url} với tài khoản {r.json()['email']}.")

    def run_forever(self) -> None:
        self.check()
        print("Agent đang chờ việc. Bấm 'Bắt đầu lướt' trên web; Ctrl+C để dừng.")
        backoff = POLL_SECONDS
        while True:
            try:
                r = self.http.get("/api/agent/next")
                r.raise_for_status()
                job = r.json()["job"]
                backoff = POLL_SECONDS
                if job:
                    self.handle(job["id"], RunRequest(**job["request"]))
                    continue
            except httpx.HTTPError as e:
                # Render free ngủ / mạng chập chờn: thử lại chậm dần
                print(f"Mất kết nối server ({e.__class__.__name__}), thử lại sau {backoff}s")
                backoff = min(backoff * 2, 120)
            time.sleep(backoff)

    def handle(self, run_id: int, req: RunRequest) -> None:
        print(f"\nLượt #{run_id}: lướt {req.platform} ({req.source_type}), {req.count} bài")
        last = 0.0

        def progress(n: int, msg: str) -> None:
            nonlocal last
            print(f"\r  {msg}", end="", flush=True)
            if time.time() - last > 2:
                last = time.time()
                try:
                    self.http.post(f"/api/agent/runs/{run_id}/progress",
                                   json={"done": n, "target": req.count, "message": msg})
                except httpx.HTTPError:
                    pass

        try:
            posts = scrape(req, set(), progress)
            print()
            r = self.http.post(f"/api/agent/runs/{run_id}/posts", timeout=180,
                               json={"posts": [p.model_dump() for p in posts]})
            r.raise_for_status()
            print(f"  Đã gửi {len(posts)} bài. Server đang phân tích.")
        except Exception as e:  # noqa: BLE001 — báo lỗi lên web để người dùng thấy
            traceback.print_exc()
            try:
                self.http.post(f"/api/agent/runs/{run_id}/fail", json={"error": str(e)[:1500]})
            except httpx.HTTPError:
                pass
