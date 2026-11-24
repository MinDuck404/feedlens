"""FastAPI entry point, error responses and local frontend assets."""
from fastapi import APIRouter, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.exceptions import RequestValidationError
from fastapi.encoders import jsonable_encoder
from starlette.exceptions import HTTPException as StarletteHTTPException
from fastapi.staticfiles import StaticFiles
from feedlens.core import config
from feedlens.core.config import BACKEND_DIR
from feedlens.core.config import settings
from feedlens.db.repository import Database
from feedlens.core.messages import error_code
from feedlens.routes.dependencies import db
from feedlens.routes import auth, preferences, platforms, ai_keys, runs, agent
from feedlens.routes.profile import profile_router
from feedlens.routes.topics import topics_router
from feedlens.routes.trends import trends_router
from feedlens.routes.search import search_router

app = FastAPI(title="FeedLens API", version="0.4.0")
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins,
                   allow_methods=["*"], allow_headers=["*"])
app.state.db = Database(settings.database_url)
app.state.db.fail_interrupted()

@app.exception_handler(StarletteHTTPException)
async def http_error(_request: Request, exc: StarletteHTTPException):
    return JSONResponse({"detail": exc.detail, "code": error_code(str(exc.detail), exc.status_code)},
                        status_code=exc.status_code, headers=exc.headers)


@app.exception_handler(RequestValidationError)
async def validation_error(_request: Request, exc: RequestValidationError):
    return JSONResponse({"detail": jsonable_encoder(exc.errors()), "code": "error.validation"}, status_code=422)

public = APIRouter(prefix="/api")
private = APIRouter(prefix="/api")
public.include_router(auth.public)
for domain in (auth, preferences, platforms, ai_keys, runs, agent):
    private.include_router(domain.private)
app.include_router(ai_keys.ai_keys_router(db))
app.include_router(public)
app.include_router(private)
app.include_router(profile_router(db, lambda: config.settings.is_cloud))
app.include_router(topics_router(db))
app.include_router(trends_router(db))
app.include_router(search_router(db))

DIST = BACKEND_DIR.parent / "frontend" / "dist"
if DIST.exists() and not settings.is_cloud:
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        f = DIST / path
        if path and f.is_file():
            return FileResponse(f)
        # index.html luôn lấy bản mới, để sau khi cập nhật trình duyệt không giữ giao diện cũ
        return FileResponse(DIST / "index.html", headers={"Cache-Control": "no-cache"})
