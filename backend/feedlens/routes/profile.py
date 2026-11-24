from __future__ import annotations


from fastapi import APIRouter
from fastapi import Depends
from fastapi import File
from fastapi import Form
from fastapi import UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse

from feedlens.ai.registry import user_keys
from feedlens.ai.registry import preferred_provider
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
            analyzer = get_analyzer(preferred_provider(db(), user.id, ai_provider), None, user_keys(db(), user.id), user.id)
            return await run_in_threadpool(analyze_cv, text, analyzer, language if language in ("vi", "en", "zh") else "vi")
        except ProfileError as exc:
            return JSONResponse({"code": exc.code, "detail": exc.code}, status_code=400)
        except Exception:
            return JSONResponse({"code": "error.cv_analysis_failed", "detail": "CV analysis failed"}, status_code=502)

    return router
