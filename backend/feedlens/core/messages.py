"""Stable UI codes alongside legacy human-readable diagnostics."""
import re


def error_code(message: str, status: int = 500, *, run_error: bool = False, analysis_error: bool = False) -> str:
    if "Invalid or unsafe custom endpoint URL" in message:
        return "error.custom_endpoint"
    if "Custom default model is required" in message:
        return "error.custom_model"
    if "Custom endpoint connection failed" in message:
        return "error.custom_connection"
    if "Selected AI key provider mismatch" in message:
        return "error.ai_key_provider"
    if "Selected AI key is unavailable" in message:
        return "error.ai_key_unavailable"
    if "AI service temporarily unavailable" in message:
        return "error.ai_service_paused"
    if "AI request configuration failed" in message:
        return "error.ai_configuration"
    if "AI request exceeds TPM" in message:
        return "error.ai_request_too_large"
    if "AI returned empty analysis" in message:
        return "error.ai_empty_output"
    if "AI output repeatedly invalid/truncated" in message:
        return "error.ai_output_budget"
    if "analysis stopped by user" in message:
        return "error.analysis_stopped"
    if "AI analysis is not running" in message:
        return "error.analysis_not_running"
    if any(fragment in message.lower() for fragment in (
        "browser not found", "executable doesn't exist", "executable does not exist",
        "chromium distribution", "please run the following command to download new browsers",
    )):
        return "error.browser_missing"
    if analysis_error:
        lowered = message.lower()
        if any(s in lowered for s in ("401", "403", "invalid api", "api key not valid", "api_key_invalid", "authentication", "unauthorized")):
            return "error.ai_auth"
        if any(s in lowered for s in ("429", "quota", "rate_limit", "rate limit", "resource_exhausted", "credit", "billing")):
            return "error.ai_quota"
        if any(s in lowered for s in ("500", "502", "503", "504", "overloaded", "unavailable", "timeout", "timed out", "connection")):
            return "error.ai_unavailable"
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
    default = "analysis_failed" if analysis_error else "run_failed" if run_error else "request_failed"
    return f"error.{ {401: 'session_expired', 403: 'forbidden', 409: 'conflict', 422: 'validation'}.get(status, default)}"


def progress_message(progress: dict | None) -> dict | None:
    if progress is None:
        return None
    phase = progress.get("phase", "preparing")
    if phase not in {"pending", "queued", "scraping", "analyzing", "summarizing", "done", "analysis_failed", "error"}:
        phase = "preparing"
    raw = progress.get("message", "")
    if m := re.search(r"(.+?) đang quá tải \(HTTP (\d+)\), thử lại sau (\d+) giây", raw):
        return {**progress, "message_code": "progress.service_wait",
                "message_vars": {"provider": m[1], "status": int(m[2]), "seconds": int(m[3])}}
    if m := re.search(r"Chuyển sang key (.+?) \(cùng model (.+?)\)", raw):
        return {**progress, "message_code": "progress.key_switch", "message_vars": {"key": m[1], "model": m[2]}}
    # Thông báo của bộ điều phối AI (ai/scheduler.py): mã riêng để giao diện hiện đúng thay vì "Đang phân tích bài".
    if m := re.search(r"chờ hạn mức phút của (.+?) \((.+?)\): (\d+) giây", raw):
        return {**progress, "message_code": "progress.quota_wait",
                "message_vars": {"provider": m[1], "model": m[2], "seconds": int(m[3])}}
    if m := re.search(r"(\S+) không còn dùng được, chuyển sang (.+?)…?$", raw):
        return {**progress, "message_code": "progress.model_switch", "message_vars": {"model": m[1], "next": m[2]}}
    message = raw.lower()
    if "chờ" in message and ("xác minh" in message or "đăng nhập" in message):
        phase = "verification"
    return {**progress, "message_code": f"progress.{phase}"}
