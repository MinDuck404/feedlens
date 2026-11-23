import asyncio
import threading

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse

from .ai import user_keys
from .ai.registry import preferred_provider
from .analyzer import get_analyzer
from .auth import CurrentUser, current_user
from .job_profile import MAX_CV_BYTES, JobProfile, ProfileError, analyze_cv, extract_cv_pdf, load_profile, store_profile

# Bound the whole AI conversion so quota waits or slow providers cannot leave the upload spinning.
CV_DEADLINE_SECONDS = 120


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

            def convert():
                # Key lookup and model listing are blocking; keep them off the event loop.
                analyzer = get_analyzer(preferred_provider(db(), user.id, ai_provider), None, user_keys(db(), user.id), user.id)
                analyzer.stop_event = stop
                return analyze_cv(text, analyzer, language if language in ("vi", "en", "zh") else "vi")

            try:
                return await asyncio.wait_for(run_in_threadpool(convert), CV_DEADLINE_SECONDS)
            except asyncio.TimeoutError:
                return JSONResponse({"code": "error.cv_analysis_timeout", "detail": "CV analysis timed out"}, status_code=504)
            finally:
                stop.set()
        except ProfileError as exc:
            return JSONResponse({"code": exc.code, "detail": exc.code}, status_code=400)
        except Exception:
            return JSONResponse({"code": "error.cv_analysis_failed", "detail": "CV analysis failed"}, status_code=502)

    return router
