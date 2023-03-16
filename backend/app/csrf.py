import secrets
from starlette.requests import Request
from starlette.responses import HTMLResponse

CSRF_COOKIE = "csrftoken"
CSRF_FIELD = "csrf_token"
EXEMPT_PATHS = {"/health", "/login", "/register"}  # Exempt login/register if needed, or keep them protected but make sure they work. Let's keep them protected since they have the csrf_token field.


class CSRFMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope, receive)
        
        # We only validate POST requests that are not exempt
        if request.method == "POST" and request.url.path not in EXEMPT_PATHS:
            # Read the body and create a replayed receive channel so downstream handlers can read it again
            body = await request.body()
            
            async def receive_with_body():
                return {"type": "http.request", "body": body, "more_body": False}

            # Re-evaluate the request with the replayed body
            replayed_request = Request(scope, receive_with_body)
            
            cookie_token = replayed_request.cookies.get(CSRF_COOKIE, "")
            try:
                form = await replayed_request.form()
                form_token = form.get(CSRF_FIELD, "")
            except Exception:
                form_token = ""

            if not cookie_token or not secrets.compare_digest(cookie_token, form_token):
                response = HTMLResponse("CSRF validation failed", status_code=403)
                await response(scope, receive, send)
                return

            # Pass the replayed receive channel to the rest of the application
            await self.app(scope, receive_with_body, send)
            return

        # For other requests (like GET), we inject the CSRF cookie if it's not already there
        async def send_with_cookie(message):
            if message["type"] == "http.response.start":
                headers = message.setdefault("headers", [])
                # Check if the user already has the CSRF cookie
                has_cookie = False
                cookie_header = next((val for name, val in scope.get("headers", []) if name == b"cookie"), b"")
                if f"{CSRF_COOKIE}=".encode() in cookie_header:
                    has_cookie = True

                if not has_cookie:
                    token = secrets.token_urlsafe(32)
                    # Set cookie (non-httpOnly so JavaScript/templates can access it if needed)
                    headers.append((
                        b"set-cookie",
                        f"{CSRF_COOKIE}={token}; Path=/; SameSite=Lax; Secure".encode()
                    ))
            await send(message)

        await self.app(scope, receive, send_with_cookie)

