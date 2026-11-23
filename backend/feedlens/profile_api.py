import asyncio
import threading

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse

from .ai import user_keys
from .ai.base import AIError
from .ai.registry import preferred_provider
from .ai.scheduler import AIServiceUnavailable, QuotaExhausted
from .analyzer import get_analyzer
from .auth import CurrentUser, current_user
from .job_profile import MAX_CV_BYTES, JobProfile, ProfileError, analyze_cv, extract_cv_pdf, load_profile, store_profile
from .messages import error_code

# Bound the whole AI conversion so quota waits or slow providers cannot leave the upload spinning.
CV_DEADLINE_SECONDS = 45


def profile_router(db, is_cloud):
    router = APIRouter(prefix="/api/profile")

    @router.get("")
    def get_profile(user: CurrentUser = Depends(current_user)):
        try:
            return load_profile(db(), user.id)
        except ProfileError as exc:
            return JSONResponse({"code": exc.code, "detail": exc.code}, status_code=409)

    @router.put("")
    def put_profile(profile: JobProfile, user: CurrentUser = Depends(current_user)):
        store_profile(db(), user.id, profile, is_cloud())
        return load_profile(db(), user.id)

    @router.delete("")
    def delete_profile(user: CurrentUser = Depends(current_user)):
        db().delete_job_profile(user.id)
        return {"ok": True}

    @router.post("/cv")
    async def convert_cv(file: UploadFile | None = File(None), text: str = Form(""),
                         ai_provider: str = Form("auto"), language: str = Form("vi"),
                         user: CurrentUser = Depends(current_user)):
        try:
            if file:
                try:
                    data = await file.read(MAX_CV_BYTES + 1)
                finally:
                    await file.close()
                text = await run_in_threadpool(extract_cv_pdf, data)
            elif len(text.encode("utf8")) > MAX_CV_BYTES:
                raise ProfileError("error.cv_too_large")
            stop = threading.Event()
            last_wait: dict = {}

            def convert():
                # Key lookup and model listing are blocking; keep them off the event loop.
                analyzer = get_analyzer(preferred_provider(db(), user.id, ai_provider), None, user_keys(db(), user.id), user.id)
                analyzer.stop_event = stop
                if hasattr(analyzer, "on_state"):
                    def record_state(state):
                        if state.get("state") in {"service_wait", "quota_wait"}:
                            last_wait.update(state)
                    analyzer.on_state = record_state
                return analyze_cv(text, analyzer, language if language in ("vi", "en", "zh") else "vi")

            # asyncio.wait (not wait_for) returns at the deadline without waiting for the blocked thread.
            task = asyncio.ensure_future(run_in_threadpool(convert))
            await asyncio.wait({task}, timeout=CV_DEADLINE_SECONDS)
            if not task.done():
                stop.set()  # the worker exits at its next scheduler check or when the HTTP call returns
                task.add_done_callback(lambda t: t.cancelled() or t.exception())
                if last_wait.get("state") == "service_wait":
                    return JSONResponse({"code": "error.cv_analysis_overloaded", "detail": "AI service overloaded"}, status_code=503)
                if last_wait.get("state") == "quota_wait":
                    return JSONResponse({"code": "error.ai_quota", "detail": "AI quota rate-limited"}, status_code=429)
                return JSONResponse({"code": "error.cv_analysis_timeout", "detail": "CV analysis timed out"}, status_code=504)
            return task.result()
        except ProfileError as exc:
            return JSONResponse({"code": exc.code, "detail": exc.code}, status_code=400)
        except AIServiceUnavailable:
            return JSONResponse({"code": "error.cv_analysis_overloaded", "detail": "AI service overloaded"}, status_code=503)
        except QuotaExhausted:
            return JSONResponse({"code": "error.ai_quota", "detail": "AI quota exhausted"}, status_code=429)
        except AIError as exc:
            code = error_code(str(exc), analysis_error=True)
            if code == "error.ai_auth":
                return JSONResponse({"code": code, "detail": code}, status_code=502)
            if code == "error.ai_quota":
                return JSONResponse({"code": code, "detail": code}, status_code=429)
            if code in {"error.ai_unavailable", "error.ai_service_paused"}:
                return JSONResponse({"code": "error.cv_analysis_overloaded", "detail": "AI service overloaded"}, status_code=503)
            return JSONResponse({"code": "error.cv_analysis_failed", "detail": "CV analysis failed"}, status_code=502)
        except Exception:
            return JSONResponse({"code": "error.cv_analysis_failed", "detail": "CV analysis failed"}, status_code=502)

    return router
