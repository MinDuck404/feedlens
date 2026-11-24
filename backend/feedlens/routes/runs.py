"""Runs routes."""
from __future__ import annotations


import feedlens.ai.registry as ai_registry
import feedlens.analysis.heuristic as heuristic_analysis
import feedlens.analysis.prompts as analysis_prompts
import feedlens.config as config
import fastapi as fastapi
import fastapi.responses as fastapi_responses
import feedlens.jobs.profile as job_profile
import feedlens.messages as messages
import feedlens.models as models
import feedlens.routes.agent as agent_routes
import feedlens.routes.dependencies as dependencies
import feedlens.runs.export as run_exports
import feedlens.runs.pipeline as run_pipeline

from typing import Literal
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from ..auth import CurrentUser as User, current_user
from ..models import RunRequest

private = APIRouter()


def _check_ai(req: RunRequest, user_id: int):
    try:
        return ai_registry.resolve_provider_key(ai_registry.preferred_provider(dependencies.db(), user_id, req.ai_provider), ai_registry.user_keys(dependencies.db(), user_id))
    except ValueError as e:
        raise fastapi.HTTPException(400, str(e))


def _own_run(run_id: int, user: User) -> dict:
    r = dependencies.db().get_run(run_id, user.id)
    if not r:
        raise fastapi.HTTPException(404, "Không tìm thấy lượt này.")
    return r


@private.post("/runs")
def create_run(req: RunRequest, user: User = Depends(current_user)):
    from feedlens.runs.source_modes import normalize
    try:
        normalize(req)
    except ValueError as exc:
        raise fastapi.HTTPException(422, f"Invalid source mode/options: {exc}") from exc
    req = req.model_copy(update={"count": min(req.count, run_pipeline.run_cap(req))})
    _check_ai(req, user.id)
    if config.settings.is_cloud and req.runner == "server":
        if not config.settings.server_scrape:
            raise fastapi.HTTPException(403, "Server này đã tắt chế độ lướt bằng cookie. Hãy chạy bằng agent.")
        s = dependencies.db().get_session(user.id, req.platform)
        if not s:
            raise fastapi.HTTPException(400, f"Chưa có cookie {req.platform}. Thêm trong Cài đặt → Lướt trên server.")
        if s.status == "invalid":
            raise fastapi.HTTPException(400, f"Cookie {req.platform} đã hết hiệu lực: {s.status_message} Hãy gửi cookie mới.")
        req = req.model_copy(update={"headless": True})
        run_id = run_pipeline.start_server_run(dependencies.db(), req, user.id)
        return {"id": run_id}
    if config.settings.is_cloud:
        run_id = dependencies.db().create_run(req, user.id, status="pending")
        from feedlens.runs.pipeline import total_target
        run_pipeline.PROGRESS[run_id] = {"phase": "pending", "done": 0, "target": total_target(req), "message": "Đang chờ agent nhận việc…"}
        return {"id": run_id, "agent": agent_routes._agent_info(user.id)}
    return {"id": run_pipeline.start_run(dependencies.db(), req, user.id)}


@private.get("/runs")
def runs(user: User = Depends(current_user)):
    return [{**r, "progress": messages.progress_message(run_pipeline.PROGRESS.get(r["id"])), "error_code": messages.error_code(r["error"], run_error=True, analysis_error=r["status"] == "analysis_failed") if r.get("error") else None} for r in dependencies.db().list_runs(user.id)]


@private.get("/runs/{run_id}")
def run_detail(run_id: int, user: User = Depends(current_user), posts: bool = True):
    r = _own_run(run_id, user)
    counts = dependencies.db().analysis_counts(run_id)
    active = r["status"] in {"pending", "queued", "scraping", "analyzing"}
    can_continue = not active and dependencies.db().can_continue_analysis(run_id)
    analysis_used_ai = r["request"].get("analysis_used_ai", r.get("ai_label") not in {"", heuristic_analysis.HeuristicAnalyzer.label})
    can_reprocess_ai = (not active and analysis_used_ai and r["status"] in {"done", "analysis_failed"}
                        and counts["total"] > 0)
    topic_count = len(dependencies.db().list_topics(user.id, enabled_only=True)) if not active else 0
    has_cv = job_profile.load_profile(dependencies.db(), user.id) is not None if not active else bool(r["request"].get("job_mode"))
    result = {**r, "progress": messages.progress_message(run_pipeline.PROGRESS.get(run_id)),
              "posts_version": counts["offline"] + 2 * counts["ai"],
              "analysis_counts": counts,
              "can_continue_analysis": can_continue,
              "can_reanalyze_ai": (not can_continue and not analysis_used_ai and r["status"] == "done"
                                   and counts["total"] > 0),
              "can_reprocess_ai": can_reprocess_ai,
              "reanalyze_requests_estimate": analysis_prompts.estimate_classification_requests_for_count(
                  counts["total"], r["request"].get("job_mode", False), r["request"].get("keywords", []),
                  r["request"].get("profile", ""), topic_count, has_cv=has_cv),
              "reanalysis_active": bool(r["request"].get("reanalysis_active")),
              "error_code": messages.error_code(r["error"], run_error=True, analysis_error=r["status"] == "analysis_failed") if r.get("error") else None}
    if posts:
        result["posts"] = [p.model_dump() for p in dependencies.db().get_posts(run_id, include_raw=True)]
    return result


class AnalysisBody(BaseModel):
    ai_provider: str = Field("auto", max_length=40)
    ai_model: str = Field("", max_length=200)
    mode: Literal["continue", "reanalyze_all"] = "continue"


@private.post("/runs/{run_id}/analysis/stop", status_code=202)
def stop_analysis(run_id: int, body: AnalysisBody | None = None, user: User = Depends(current_user)):
    run = _own_run(run_id, user)
    if run["status"] != "analyzing":
        raise fastapi.HTTPException(409, "AI analysis is not running.")
    replacement = None
    if body is not None:
        if body.mode != "continue":
            raise fastapi.HTTPException(422, "Model changes must continue saved analysis.")
        replacement = models.RunRequest(**{**run["request"], "ai_provider": body.ai_provider, "ai_model": body.ai_model})
        _check_ai(replacement, user.id)
    if not run_pipeline.request_stop(run_id, replacement):
        raise fastapi.HTTPException(409, "AI analysis is not running or is already stopping.")
    return {"ok": True, "stopping": True, "will_continue": replacement is not None}


@private.post("/runs/{run_id}/analysis")
def retry_analysis(run_id: int, body: AnalysisBody, user: User = Depends(current_user)):
    r = _own_run(run_id, user)
    raw = dependencies.db().get_analysis_posts(run_id)
    reanalyze_all = body.mode == "reanalyze_all"
    if reanalyze_all and (r["status"] not in {"done", "analysis_failed"} or not raw):
        raise fastapi.HTTPException(409, "Lượt này chưa có bài đã lưu để phân tích lại bằng AI.")
    if not dependencies.db().can_continue_analysis(run_id, reanalyze_all=reanalyze_all):
        raise fastapi.HTTPException(409, "Lượt này không có bài chờ phân tích lại.")
    req = models.RunRequest(**{**r["request"], "ai_provider": body.ai_provider, "ai_model": body.ai_model})
    resolved_provider = _check_ai(req, user.id)
    if reanalyze_all and resolved_provider == "offline":
        raise fastapi.HTTPException(400, "Chưa có API key AI. Thêm key trong phần Cài đặt để phân tích bằng AI.")
    if not dependencies.db().claim_analysis(run_id, req):
        raise fastapi.HTTPException(409, "Lượt này đang được phân tích.")
    if reanalyze_all:
        request = {**req.model_dump(), "analysis_used_ai": True, "reanalysis_active": True}
        if "scrape_report" in r["request"]:
            request["scrape_report"] = r["request"]["scrape_report"]
        dependencies.db().save_raw_posts(run_id, raw)  # Seed legacy runs before only_new filtering in start_analysis.
        dependencies.db().mark_posts_pending(run_id)
        dependencies.db().update_run(run_id, request=request)
        run_pipeline.start_analysis(dependencies.db(), run_id, req, raw, user.id, reanalyze_all=True)
    else:
        metadata = {key: r["request"][key] for key in ("scrape_report", "analysis_used_ai", "reanalysis_active")
                    if key in r["request"]}
        dependencies.db().update_run(run_id, request={**req.model_dump(), **metadata})
        dependencies.db().save_raw_posts(run_id, raw)  # Seed legacy runs before only_new filtering in start_analysis.
        run_pipeline.start_analysis(dependencies.db(), run_id, req, raw, user.id)
    return {"ok": True}


@private.delete("/runs/{run_id}")
def delete_run(run_id: int, user: User = Depends(current_user)):
    if not dependencies.db().delete_run(run_id, user.id):
        raise fastapi.HTTPException(404, "Không tìm thấy lượt này.")
    run_pipeline.PROGRESS.pop(run_id, None)
    return {"ok": True}


@private.get("/runs/{run_id}/export")
def export(run_id: int, fmt: str = "md", user: User = Depends(current_user)):
    r = _own_run(run_id, user)
    posts = dependencies.db().get_posts(run_id, include_raw=True)
    body, mime, ext = {
        "csv": (lambda: run_exports.to_csv(posts, r), "text/csv; charset=utf-8", "csv"),
        "json": (lambda: run_exports.to_json(r, posts), "application/json", "json"),
    }.get(fmt, (lambda: run_exports.to_markdown(r, posts), "text/markdown; charset=utf-8", "md"))
    return fastapi_responses.PlainTextResponse(body(), media_type=mime,
                             headers={"Content-Disposition": f'attachment; filename="feedlens-{run_id}.{ext}"'})
