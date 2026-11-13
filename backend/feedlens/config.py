from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent
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
    password: str          # mật khẩu đăng nhập app (bắt buộc ở chế độ cloud)
    secret: str            # khóa ký token phiên
    api_token: str         # token cho bot ở máy đẩy bài lên (feedlens push)

    @property
    def is_cloud(self) -> bool:
        return self.mode == "cloud"

    @property
    def auth_enabled(self) -> bool:
        return self.is_cloud or bool(self.password)

    @property
    def profiles_dir(self) -> Path:
        return self.data_dir / "profiles"


def _normalize_db_url(url: str) -> str:
    # Railway/Heroku cấp "postgres://" hoặc "postgresql://"; SQLAlchemy + psycopg3 cần "postgresql+psycopg://"
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix):]
    return url


def load_settings() -> Settings:
    data_dir = Path(os.getenv("FEEDLENS_DATA_DIR") or BACKEND_DIR / "data").resolve()
    (data_dir / "profiles").mkdir(parents=True, exist_ok=True)
    return Settings(
        data_dir=data_dir,
        database_url=_normalize_db_url(os.getenv("DATABASE_URL") or "")
        or f"sqlite:///{(data_dir / 'feedlens.db').as_posix()}",
        browser_channel=os.getenv("FEEDLENS_BROWSER_CHANNEL", "chrome"),
        max_posts=int(os.getenv("FEEDLENS_MAX_POSTS", "300")),
        default_ai=os.getenv("FEEDLENS_AI_PROVIDER", "auto"),
        cors_origins=[o.strip() for o in os.getenv(
            "FEEDLENS_CORS", "http://localhost:5173,http://127.0.0.1:5173").split(",") if o.strip()],
        mode=os.getenv("FEEDLENS_MODE", "local").lower(),
        password=os.getenv("FEEDLENS_PASSWORD", ""),
        secret=os.getenv("FEEDLENS_SECRET", ""),
        api_token=os.getenv("FEEDLENS_API_TOKEN", ""),
    )


settings = load_settings()
