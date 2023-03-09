# Production Readiness TODO

Work through these one by one before deploying to real users.
Ordered by priority — fix the top ones first.

---

## 🔴 Critical (fix before any real traffic)

- [x] **Blocking subprocess in async routes**
  All git calls use synchronous `subprocess.run()` inside `async def` route handlers.
  Under load, one slow git operation freezes the entire server.
  Fix: wrap all calls in `asyncio.to_thread()` inside `backend/app/git/subprocess_impl.py`.

- [x] **No database migrations (Alembic)**
  `create_all()` in `main.py` cannot alter existing tables.
  Adding/renaming any column in `models.py` will leave production data stuck.
  Fix: install Alembic, run `alembic init`, generate migrations for every schema change.

- [x] **No git operation timeouts**
  A large repo or hung `git merge` hangs the process indefinitely.
  Fix: add `timeout=30` (or appropriate value) to every `subprocess.run()` call in
  `backend/app/git/subprocess_impl.py`.

- [x] **`docker-compose.yml` uses `--reload` flag**
  `--reload` is a dev-only flag that watches the filesystem. Remove it for production.
  Use `CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]`
  in the Dockerfile instead.

- [x] **No rate limiting on login**
  `POST /login` can be brute-forced with no throttle.
  Fix: add `slowapi` library with a per-IP limiter on `auth_routes.py`.

---

## 🟠 Security (fix before going public)

- [x] **`SECRET_KEY` has an insecure default**
  `config.py` defaults to `"dev-secret-change-me"`. If the env var is not set, JWTs
  can be forged.
  Fix: remove the default, make it a required field — app should refuse to start without it.

- [x] **Cookie missing `Secure` and `SameSite` flags**
  `auth_routes.py:37` sets the cookie without `secure=True` and `samesite="lax"`.
  Fix: `redirect.set_cookie(..., httponly=True, secure=True, samesite="lax")`

- [x] **No CSRF protection**
  All POST forms can be submitted cross-site.
  Fix: add a CSRF token to forms (use `itsdangerous` or a FastAPI middleware).

- [x] **No CORS headers**
  Required if/when you add a separate JS frontend.
  Fix: add `fastapi.middleware.cors.CORSMiddleware` in `main.py` with an allowlist.

- [x] **`bcrypt==3.2.0` is pinned to an outdated version**
  Has known vulnerabilities. Pin removed it from auto-updates.
  Fix: upgrade to latest `bcrypt` and remove the hard pin in `requirements.txt`.

- [x] **`datetime.utcnow()` is deprecated**
  `auth.py:22` — will raise a warning and eventually break on Python 3.12+.
  Fix: replace with `datetime.now(timezone.utc)`.

---

## 🟡 Reliability & Operations

- [x] **No structured logging**
  No way to debug production issues — errors just print to stdout with no context.
  Fix: configure Python `logging` with JSON formatter; log every request + errors.

- [x] **No health check endpoint**
  Load balancers and container orchestrators (k8s, ECS) need `GET /health`.
  Fix: add a route in `main.py` that checks DB connectivity and returns `{"status": "ok"}`.

- [x] **No pagination on list endpoints**
  `/issues` returns all issues, `/commits` returns 50 but with no cursor.
  A repo with 10,000 issues would return everything in one query.
  Fix: add `limit` + `offset` (or cursor-based) pagination to issues, pulls, search.

- [ ] **Repos stored on local disk only**
  Not horizontally scalable — a second server instance won't see the repos.
  No backup strategy either.
  Fix (long term): store bare repos on a network volume (NFS, EFS) or use object storage
  with a git-over-HTTP layer.

- [ ] **No nginx / reverse proxy in front of uvicorn**
  Uvicorn is an ASGI server, not designed to face the internet directly.
  Fix: add an nginx container in `docker-compose.yml` to handle TLS, compression, and
  static files.

- [ ] **No TLS / HTTPS**
  All cookies and tokens travel in plaintext.
  Fix: terminate TLS at nginx using Let's Encrypt (certbot) or a cloud load balancer.

- [x] **Uvicorn runs single-process in Docker**
  Fix: use `--workers 4` (or `gunicorn` with uvicorn workers) in the Dockerfile CMD.

---

## 🟢 Nice to Have (polish)

- [/] **Tailwind CSS loaded from CDN**
  *Switched from dynamic JS compiler to a standard CSS CDN link, but still loaded from the internet.*
  Fix: bundle Tailwind with `npx tailwindcss` build step into `frontend/static/`.

- [x] **No error monitoring**
  No way to know when exceptions happen in production.
  Fix: integrate Sentry (`sentry-sdk[fastapi]`) with DSN from env var.

- [x] **No environment separation**
  Same config file used for dev and prod.
  Fix: support `.env.dev`, `.env.prod`, and load based on `APP_ENV` variable.

- [x] **No `__pycache__` / `.pyc` ignore in Dockerfile**
  Build context includes compiled bytecache.
  Fix: add `**/__pycache__` and `**/*.pyc` to `.dockerignore`.

- [x] **`repos/` directory has no size limits**
  A user could push a multi-GB repo and fill the disk.
  Fix: add disk quota checks before `create_bare_repo`; set git push size limits via
  git hooks (`pre-receive`).

---

## Future: C++ Git Layer

When ready to replace Python subprocess git calls with C++:
1. Implement all functions from `backend/app/git/interface.py` (`GitAdapter` Protocol)
   in a new file (e.g. `backend/app/git/cpp_impl.py` or a separate C++ HTTP service).
2. Change the import in `backend/app/routers/*.py` from `subprocess_impl` to the new impl.
3. No other files need to change — the Protocol is the contract.
