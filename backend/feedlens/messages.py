"""Stable UI codes alongside legacy human-readable diagnostics."""


def error_code(message: str, status: int = 500, *, run_error: bool = False) -> str:
    for fragment, code in (
        ("Sai email", "invalid_credentials"),
        ("FEEDLENS_SECRET", "config"),
        ("Thử quá nhiều", "rate_limited"),
        ("đóng đăng ký", "signup_closed"),
        ("Email không hợp lệ", "invalid_email"),
        ("Mật khẩu cần", "password_short"),
        ("đã có tài khoản", "email_taken"),
        ("cloud không có trình duyệt", "local_only"),
        ("Nền tảng không hỗ trợ", "unsupported_platform"),
        ("Nhà cung cấp AI không hỗ trợ", "unsupported_provider"),
        ("Cài đặt quá lớn", "invalid_preferences"),
        ("Cài đặt phải", "invalid_preferences"),
        ("JSON không hợp lệ", "validation"),
        ("Không tìm thấy lượt", "run_missing"),
        ("Nhập ít nhất", "sources_missing"),
        ("tắt chế độ lướt", "server_scrape_disabled"),
        ("Chế độ lướt trên server", "server_scrape_disabled"),
        ("Chưa có cookie", "cookie_missing"),
        ("Key không dùng được", "key_invalid"),
        ("Chưa có API key", "key_missing"),
        ("Không lấy được danh sách model", "models_failed"),
        ("Server không mở được trình duyệt", "browser_failed"),
        ("cookie", "cookie_invalid"),
        ("Cookie", "cookie_invalid"),
    ):
        if fragment in message:
            return f"error.{code}"
    default = "run_failed" if run_error else "request_failed"
    return f"error.{ {401: 'session_expired', 403: 'forbidden', 409: 'conflict', 422: 'validation'}.get(status, default)}"


def progress_message(progress: dict | None) -> dict | None:
    if progress is None:
        return None
    phase = progress.get("phase", "preparing")
    if phase not in {"pending", "queued", "scraping", "analyzing", "summarizing", "done"}:
        phase = "preparing"
    message = progress.get("message", "").lower()
    if "chờ" in message and ("xác minh" in message or "đăng nhập" in message):
        phase = "verification"
    return {**progress, "message_code": f"progress.{phase}"}
