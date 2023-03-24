import os
import logging
import json
import time
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text as sql_text
from . import models, database
from .config import settings
from .csrf import CSRFMiddleware
from .deps import limiter, templates
from starlette.exceptions import HTTPException as StarletteHTTPException
from fastapi.responses import HTMLResponse
from .routers import auth_routes, users, repos, code, issues, pulls, network, git_http


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return json.dumps({
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "path": getattr(record, "path", None),
            "status": getattr(record, "status", None),
            "duration_ms": getattr(record, "duration_ms", None),
        })


_handler = logging.StreamHandler()
_handler.setFormatter(_JsonFormatter())
logging.basicConfig(handlers=[_handler], level=logging.INFO, force=True)

logger = logging.getLogger(__name__)

if settings.sentry_dsn:
    import sentry_sdk
    from sentry_sdk.integrations.fastapi import FastApiIntegration
    from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration
    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        integrations=[FastApiIntegration(), SqlalchemyIntegration()],
        traces_sample_rate=0.2,
    )

os.makedirs(settings.repos_dir, exist_ok=True)
models.Base.metadata.create_all(bind=database.engine)

app = FastAPI(title="GitClone")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    # Try to get current user from cookie to show in header
    from . import auth
    from .database import SessionLocal
    db = SessionLocal()
    current_user = None
    try:
        current_user = auth.get_current_user_from_cookie(request, db)
    except Exception:
        pass
    finally:
        db.close()

    error_msg = "Page Not Found" if exc.status_code == 404 else exc.detail
    return templates.TemplateResponse(
        request=request,
        name="error.html",
        context={"error": f"{exc.status_code}: {error_msg}", "user": current_user},
        status_code=exc.status_code
    )

app.add_middleware(CSRFMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.monotonic()
    response = await call_next(request)
    duration_ms = round((time.monotonic() - start) * 1000, 1)
    logger.info(
        "%s %s %s",
        request.method,
        request.url.path,
        response.status_code,
        extra={"path": request.url.path, "status": response.status_code, "duration_ms": duration_ms},
    )
    return response


@app.get("/health")
async def health():
    try:
        db = database.SessionLocal()
        db.execute(sql_text("SELECT 1"))
        db.close()
        db_ok = True
    except Exception:
        db_ok = False
    status = "ok" if db_ok else "degraded"
    return JSONResponse({"status": status, "db": db_ok}, status_code=200 if db_ok else 503)


app.mount("/static", StaticFiles(directory="/app/frontend/static"), name="static")

app.include_router(auth_routes.router)
app.include_router(repos.router)
app.include_router(code.router)
app.include_router(issues.router)
app.include_router(pulls.router)
app.include_router(network.router)
app.include_router(users.router)
app.include_router(git_http.router)
