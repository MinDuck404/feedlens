from __future__ import annotations

import asyncio
import threading

from fastapi import APIRouter
from fastapi import Depends
from fastapi import File
from fastapi import Form
from fastapi import UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse

from feedlens.ai.registry import user_keys
from feedlens.ai.registry import preferred_provider
from feedlens.ai.registry import KeySelectionError
from feedlens.analysis.analyzer import get_analyzer
from feedlens.core.auth import CurrentUser
from feedlens.core.auth import current_user
from feedlens.jobs.profile import MAX_CV_BYTES
from feedlens.jobs.profile import JobProfile
from feedlens.jobs.profile import ProfileError
from feedlens.jobs.profile import analyze_cv
from feedlens.jobs.profile import extract_cv_pdf
from feedlens.jobs.profile import load_profile
from feedlens.jobs.profile import store_profile
from feedlens.jobs.profile import offline_cv

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
                         ai_model: str = Form("", max_length=200), ai_key_id: int | None = Form(None, gt=0),
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
            language = language if language in ("vi", "en", "zh") else "vi"
            fallback = await run_in_threadpool(offline_cv, text, language)
            stop = threading.Event()

            def convert():
                provider = ai_provider if ai_key_id is not None else preferred_provider(db(), user.id, ai_provider)
                selected = {"ai_key_id": ai_key_id} if ai_key_id is not None else {}
                analyzer = get_analyzer(provider, ai_model or None, user_keys(db(), user.id), user.id, **selected)
                analyzer.stop_event = stop
                if stop.is_set():
                    return fallback
                return analyze_cv(text, analyzer, language)

            task = asyncio.create_task(run_in_threadpool(convert))
            task.add_done_callback(lambda done: None if done.cancelled() else done.exception())
            try:
                # Do not wait for a blocked SDK thread when the total conversion deadline expires.
                done, _ = await asyncio.wait({task}, timeout=CV_DEADLINE_SECONDS)
                try:
                    result = task.result() if done else {**fallback, "ai_status": "unavailable", "reason": "timeout"}
                except KeySelectionError:
                    raise
                except Exception:
                    result = {**fallback, "ai_status": "unavailable"}
            finally:
                stop.set()  # Prevent another provider request after an in-flight call returns.
            if result.get("ai_status") != "unavailable":
                return result

            def save_fallback():
                previous = load_profile(db(), user.id)
                profile = (previous or JobProfile(primary_roles=result["suggested_roles"])).model_copy(
                    update={"markdown": result["markdown"]})
                store_profile(db(), user.id, profile, is_cloud())
                return {**result, "suggested_roles": profile.primary_roles,
                        "adjacent_roles": [role.model_dump() for role in profile.adjacent_roles],
                        "code": "error.cv_ai_unavailable", "saved": True}
            return await run_in_threadpool(save_fallback)
        except KeySelectionError as exc:
            return JSONResponse({"code": exc.code, "detail": str(exc)}, status_code=exc.status_code)
        except ProfileError as exc:
            return JSONResponse({"code": exc.code, "detail": exc.code}, status_code=400)
        except Exception:
            return JSONResponse({"code": "error.cv_analysis_failed", "detail": "CV analysis failed"}, status_code=502)

    return router
