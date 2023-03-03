import secrets
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from fastapi.responses import HTMLResponse

CSRF_COOKIE = "csrftoken"
CSRF_FIELD = "csrf_token"
EXEMPT_PATHS = {"/health"}


class CSRFMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Only validate state-changing methods
        if request.method == "POST" and request.url.path not in EXEMPT_PATHS:
            cookie_token = request.cookies.get(CSRF_COOKIE, "")
            try:
                form = await request.form()
                form_token = form.get(CSRF_FIELD, "")
            except Exception:
                form_token = ""

            if not cookie_token or not secrets.compare_digest(cookie_token, form_token):
                return HTMLResponse("CSRF validation failed", status_code=403)

        response: Response = await call_next(request)

        # Set CSRF cookie if not present (non-httpOnly so templates can read it)
        if CSRF_COOKIE not in request.cookies:
            response.set_cookie(
                CSRF_COOKIE,
                secrets.token_urlsafe(32),
                samesite="lax",
                secure=True,
                httponly=False,
            )

        return response
