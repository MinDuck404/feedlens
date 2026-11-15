from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse

from .ai import user_keys
from .ai.registry import preferred_provider
from .analyzer import get_analyzer
from .auth import CurrentUser, current_user
from .job_profile import MAX_CV_BYTES, JobProfile, ProfileError, analyze_cv, extract_cv_pdf, load_profile, store_profile


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
