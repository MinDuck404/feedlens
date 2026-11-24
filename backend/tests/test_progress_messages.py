"""Thông báo chờ hạn mức / đổi model phải có mã riêng, để giao diện không đè bằng "Đang phân tích bài"."""
from feedlens.core.messages import progress_message


def test_quota_wait_message_gets_its_own_code_and_vars():
    p = progress_message({"phase": "analyzing", "done": 0, "target": 10,
                          "message": "Đang chờ hạn mức phút của Gemini (gemini-3.5-flash-lite): 18 giây"})
    assert p["message_code"] == "progress.quota_wait"
    assert p["message_vars"] == {"provider": "Gemini", "model": "gemini-3.5-flash-lite", "seconds": 18}


def test_model_switch_message_gets_its_own_code():
    p = progress_message({"phase": "analyzing", "done": 20, "target": 500,
                          "message": "gemini-3.5-flash-lite không còn dùng được, chuyển sang gemini-3.8-flash…"})
    assert p["message_code"] == "progress.model_switch"
    assert p["message_vars"] == {"model": "gemini-3.5-flash-lite", "next": "gemini-3.8-flash"}


def test_ordinary_progress_keeps_phase_code():
    p = progress_message({"phase": "analyzing", "done": 40, "target": 500, "message": "Đã phân loại 40/500"})
    assert p["message_code"] == "progress.analyzing"
    assert "message_vars" not in p
