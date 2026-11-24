from __future__ import annotations

import os
import secrets
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parents[2]
load_dotenv(BACKEND_DIR / ".env")


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    database_url: str
    browser_channel: str
    max_posts: int
    default_ai: str  # anthropic | openai | gemini | offline
    cors_origins: list[str]
    mode: str              # local | cloud
    secret: str            # khóa ký token phiên + mã hóa API key của user
    allow_signup: bool     # cloud: cho phép đăng ký tài khoản mới
    server_scrape: bool    # cloud: cho phép chế độ 'Server' (lướt trên server bằng cookie user lưu)

    @property
    def is_cloud(self) -> bool:
        return self.mode == "cloud"

    @property
    def auth_enabled(self) -> bool:
        return self.is_cloud

    @property
    def profiles_dir(self) -> Path:
        return self.data_dir / "profiles"


def _normalize_db_url(url: str) -> str:
    # Railway/Heroku cấp "postgres://" hoặc "postgresql://"; SQLAlchemy + psycopg3 cần "postgresql+psycopg://"
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix):]
    return url


def _local_secret(data_dir: Path) -> str:
    """Chế độ local không bắt buộc đặt FEEDLENS_SECRET: tự sinh một lần và lưu trong data/."""
    f = data_dir / "secret.key"
    if not f.exists():
        f.write_text(secrets.token_urlsafe(48))
    return f.read_text().strip()


def load_settings() -> Settings:
    data_dir = Path(os.getenv("FEEDLENS_DATA_DIR") or BACKEND_DIR / "data").resolve()
    (data_dir / "profiles").mkdir(parents=True, exist_ok=True)
    mode = os.getenv("FEEDLENS_MODE", "local").lower()
    return Settings(
        data_dir=data_dir,
        database_url=_normalize_db_url(os.getenv("DATABASE_URL") or "")
        or f"sqlite:///{(data_dir / 'feedlens.db').as_posix()}",
        browser_channel=os.getenv("FEEDLENS_BROWSER_CHANNEL", "chrome"),
        max_posts=int(os.getenv("FEEDLENS_MAX_POSTS", "500")),
        default_ai=os.getenv("FEEDLENS_AI_PROVIDER", "auto"),
        cors_origins=[o.strip() for o in os.getenv(
            "FEEDLENS_CORS", "http://localhost:5173,http://127.0.0.1:5173").split(",") if o.strip()],
        mode=mode,
        secret=os.getenv("FEEDLENS_SECRET") or ("" if mode == "cloud" else _local_secret(data_dir)),
        allow_signup=os.getenv("FEEDLENS_ALLOW_SIGNUP", "true").lower() in ("1", "true", "yes"),
        server_scrape=os.getenv("FEEDLENS_SERVER_SCRAPE", "true").lower() in ("1", "true", "yes"),
    )


settings = load_settings()
