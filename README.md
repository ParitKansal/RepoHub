# GitClone

A self-hosted Git hosting platform built with FastAPI, PostgreSQL, and Nginx. GitClone gives you GitHub-like repository management — code browsing, issues, pull requests with conflict detection, and native `git push`/`git clone` over HTTPS — deployed entirely on your own infrastructure.

**Live demo:** https://parit-gitclone.duckdns.org:8443

---

## Features

- **Repository management** — create public/private repos, star repos, delete repos
- **Code browser** — browse files and directories at any branch or commit, syntax-highlighted file viewer
- **Commits & branches** — full commit history, per-file history, branch switching, commit detail view
- **Issues** — open/close issues with threaded comments
- **Pull requests** — open PRs between branches, live conflict detection before merge, merge via fast-forward or merge commit
- **Network graph** — visualise the fork/contributor network of a repository
- **User accounts** — registration, login, profile pages, JWT-cookie auth
- **Native Git over HTTPS** — `git clone`, `git push`, `git pull` work against the server via HTTP Basic auth (`git-http-backend` under the hood)
- **Markdown rendering** — README.md files are rendered in the repository view
- **Rate limiting** — per-IP rate limiting via SlowAPI
- **CSRF protection** — custom CSRF middleware on all state-changing POST routes
- **Structured JSON logging** — every request logged with method, path, status, and latency
- **Sentry integration** — optional error tracking via `SENTRY_DSN`
- **Health endpoint** — `GET /health` returns DB status for uptime monitoring

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.11+, FastAPI, SQLAlchemy 2, Alembic |
| Templating | Jinja2 |
| Database | PostgreSQL 15 |
| Auth | JWT (python-jose), bcrypt (passlib) |
| Git | Bare repositories via `git-http-backend` subprocess |
| Reverse proxy | Nginx (TLS termination, static files, upstream proxy) |
| Containerisation | Docker, Docker Compose |
| Monitoring | Sentry SDK, SlowAPI rate limiting |

---

## Project Structure

```
GitClone/
├── backend/
│   ├── app/
│   │   ├── main.py          # FastAPI app factory, middleware, router registration
│   │   ├── models.py        # SQLAlchemy ORM models
│   │   ├── auth.py          # JWT creation & cookie extraction
│   │   ├── config.py        # Pydantic settings (env-based)
│   │   ├── csrf.py          # CSRF middleware
│   │   ├── database.py      # SQLAlchemy engine & session factory
│   │   ├── deps.py          # Shared FastAPI dependencies (DB session, templates, rate limiter)
│   │   ├── git/
│   │   │   ├── interface.py        # Abstract git interface
│   │   │   └── subprocess_impl.py  # Git operations via subprocess
│   │   └── routers/
│   │       ├── auth_routes.py  # /register, /login, /logout
│   │       ├── repos.py        # Repo CRUD, star, settings
│   │       ├── code.py         # File browser, commit history, file view
│   │       ├── issues.py       # Issue list, detail, comments
│   │       ├── pulls.py        # Pull request list, detail, merge, conflict API
│   │       ├── network.py      # Repository network graph
│   │       ├── users.py        # User profiles, dashboard, search
│   │       └── git_http.py     # git-http-backend proxy (clone/push/pull)
│   ├── alembic/             # Database migrations
│   ├── Dockerfile
│   └── requirements.txt
├── frontend/
│   ├── templates/           # Jinja2 HTML templates
│   │   ├── base.html
│   │   ├── repo_detail.html
│   │   ├── commits.html
│   │   ├── pulls.html
│   │   ├── issues.html
│   │   └── ...
│   └── static/              # CSS, images (served directly by Nginx)
├── nginx/
│   ├── nginx.conf           # HTTP→HTTPS redirect + upstream proxy config
│   └── certs/               # TLS certificate & key
├── docker-compose.yml
└── scripts/
    └── backup.sh
```

---

## Data Models

| Model | Key Fields |
|---|---|
| `User` | `username`, `email`, `hashed_password` |
| `Repository` | `name`, `description`, `is_private`, `owner_id` |
| `Issue` | `title`, `description`, `status` (Open/Closed), `repo_id`, `author_id` |
| `Comment` | `content`, `created_at`, `issue_id`, `author_id` |
| `PullRequest` | `title`, `status` (Open/Merged/Closed), `source_branch`, `target_branch`, `repo_id` |
| `Star` | `user_id`, `repo_id`, `created_at` |

Bare git repositories live on disk at `$REPOS_DIR/<username>/<repo_name>.git`.

---

## Getting Started

### Prerequisites

- Docker & Docker Compose
- `git` (for pushing/cloning repos)

### 1. Clone the repo

```bash
git clone https://github.com/ParitKansal/GitClone.git
cd GitClone
```

### 2. Configure environment

```bash
cp backend/.env.example backend/.env
```

Edit `backend/.env`:

```env
# Required — generate with: python -c "import secrets; print(secrets.token_hex(32))"
SECRET_KEY=your-secret-key-here

# PostgreSQL (used automatically by docker-compose)
DATABASE_URL=postgresql://gitclone:gitclone@postgres:5432/gitclone

# Where bare git repos are stored inside the container
REPOS_DIR=/repos

# Jinja2 template directory inside the container
TEMPLATES_DIR=/app/frontend/templates

# Optional: Sentry error tracking
SENTRY_DSN=
```

### 3. TLS certificates

For local development, generate a self-signed certificate:

```bash
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout nginx/certs/nginx.key \
  -out nginx/certs/nginx.crt \
  -subj "/CN=localhost"
```

For production, replace these files with real certificates (e.g. from Let's Encrypt).

### 4. Start the stack

```bash
docker compose up --build -d
```

Services:
- **PostgreSQL** on an internal Docker network
- **FastAPI** (`uvicorn`, 4 workers) on port 8000 (internal)
- **Nginx** on `0.0.0.0:8080` (HTTP → HTTPS redirect) and `0.0.0.0:8443` (HTTPS)

Open https://localhost:8443 in your browser.

### 5. Use Git over HTTPS

After registering an account and creating a repository:

```bash
# Clone
git clone https://localhost:8443/<username>/<repo_name>.git

# Or add as a remote
git remote add origin https://localhost:8443/<username>/<repo_name>.git
git push -u origin main
```

Git will prompt for your GitClone username and password.

---

## Configuration Reference

All configuration is read from environment variables (or a `.env` file in `backend/`).

| Variable | Default | Description |
|---|---|---|
| `SECRET_KEY` | *(required)* | JWT signing key |
| `DATABASE_URL` | `sqlite:///./gitclone.db` | SQLAlchemy database URL |
| `REPOS_DIR` | `repos` | Path to bare git repositories on disk |
| `TEMPLATES_DIR` | `frontend/templates` | Path to Jinja2 templates |
| `ALGORITHM` | `HS256` | JWT signing algorithm |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `1440` | JWT lifetime (24 h) |
| `CORS_ORIGINS` | `[]` | Allowed CORS origins |
| `SENTRY_DSN` | `""` | Sentry DSN (leave empty to disable) |

---

## API Routes

| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | Health check (DB connectivity) |
| `GET/POST` | `/register` | User registration |
| `GET/POST` | `/login` | User login |
| `POST` | `/logout` | User logout |
| `GET` | `/dashboard` | Authenticated user dashboard |
| `GET` | `/<username>` | User profile |
| `GET/POST` | `/repo/new` | Create repository |
| `GET` | `/<user>/<repo>` | Repository file browser |
| `GET` | `/<user>/<repo>/commits/<branch>` | Commit history |
| `GET` | `/<user>/<repo>/commit/<sha>` | Commit detail / diff |
| `GET` | `/<user>/<repo>/blob/<branch>/<path>` | File viewer |
| `GET` | `/<user>/<repo>/branches` | Branch list |
| `GET/POST` | `/<user>/<repo>/issues` | Issue list / create |
| `GET/POST` | `/<user>/<repo>/issues/<id>` | Issue detail / comment |
| `GET/POST` | `/<user>/<repo>/pulls` | Pull request list / create |
| `GET/POST` | `/<user>/<repo>/pulls/<id>` | PR detail / merge |
| `GET` | `/<user>/<repo>/api/check-conflicts` | Live conflict detection (JSON) |
| `GET` | `/<user>/<repo>/network` | Repository network graph |
| `POST` | `/<user>/<repo>/star` | Toggle star |
| `GET/POST` | `/<user>/<repo>/settings` | Repository settings |
| `POST` | `/<user>/<repo>/delete` | Delete repository |
| `*` | `/<user>/<repo>.git/*` | Git smart HTTP (clone/push/pull) |

---

## Development (without Docker)

```bash
# Install dependencies
cd backend
pip install -r requirements.txt

# Set environment variables
export SECRET_KEY=dev-secret
export DATABASE_URL=sqlite:///./gitclone.db
export REPOS_DIR=repos
export TEMPLATES_DIR=../frontend/templates

# Run database migrations (first time only)
alembic upgrade head

# Start the dev server
uvicorn app.main:app --reload --port 8000
```

Open http://localhost:8000.

---

## Deployment (Production)

1. **Provision a server** with Docker & Docker Compose installed.
2. **Set a real `SECRET_KEY`** — never use the default.
3. **Replace self-signed certs** in `nginx/certs/` with real TLS certificates.
4. **Update `nginx/nginx.conf`** — change `server_name localhost` to your domain.
5. **Configure firewall** — expose ports 80 and 443 (or 8080/8443 if behind a router).
6. **Run:**
   ```bash
   docker compose up --build -d
   ```
7. **Set up backups** — `scripts/backup.sh` provides a starting point for backing up the PostgreSQL volume and the `repos-data` volume.

---

## Production Infrastructure

The live instance at **https://parit-gitclone.duckdns.org:8443** runs on Google Cloud Platform.

### Host VM

| Property | Value |
|---|---|
| Provider | Google Cloud Platform |
| Instance | `instance-20260630-063832` |
| Zone | `us-central1-b` |
| vCPUs | 2× AMD EPYC 7B12 |
| RAM | 955 MB (no swap) |
| Boot disk | 8.7 GB (51% used) |
| OS | Ubuntu (latest LTS) |

### Running Containers

| Container | Image | Ports | Memory |
|---|---|---|---|
| `repohub-nginx-1` | `nginx:alpine` | `0.0.0.0:8080→80`, `0.0.0.0:8443→443` | ~4 MB |
| `repohub-web-1` | `repohub-web` (local build) | `8000` (internal) | ~333 MB |
| `repohub-postgres-1` | `postgres:15` | `5432` (internal) | ~33 MB |

All three containers have been running continuously since deployment. Startup order: Postgres (with healthcheck) → web → nginx.

### Docker Volumes

| Volume | Purpose |
|---|---|
| `pgdata` | PostgreSQL data directory (persisted across restarts) |
| `repos-data` | Bare git repositories (`/repos` inside the web container) |

### Nginx Configuration

- Port **8080** (HTTP) — redirects all traffic to HTTPS via `301`
- Port **8443** (HTTPS) — TLS termination with self-signed certificate
- TLS protocols: **TLSv1.2 and TLSv1.3** only
- `/static/` — served directly by Nginx with `Cache-Control: public, 30d`
- All other requests — proxied to `http://web:8000` with forwarded headers (`X-Real-IP`, `X-Forwarded-For`, `X-Forwarded-Proto`)

### Web Service

- **Command:** `uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4`
- **Templates:** mounted from `./frontend` into `/app/frontend` inside the container
- **Repos dir:** Docker volume `repos-data` mounted at `/repos`
- **Logs:** `json-file` driver, max 10 MB × 3 files per service

### Resource Usage (live snapshot)

```
CONTAINER              CPU %    MEM USAGE / LIMIT       MEM %
repohub-web-1          1.28%    332.6 MiB / 955.5 MiB   34.80%
repohub-postgres-1     0.00%    33.5  MiB / 955.5 MiB    3.50%
repohub-nginx-1        0.00%    4.1   MiB / 955.5 MiB    0.43%
```

> **Note:** The VM has no swap configured. If a memory spike occurs (e.g. large `git merge`), the OOM killer may terminate a container. Consider adding swap or upgrading to a larger instance type for production workloads.

### Capacity Limits

- **Disk:** 4.3 GB remaining — adequate for small-to-medium usage; monitor as repositories grow
- **RAM:** ~145 MB available headroom — sufficient for light traffic; spikes during concurrent git operations may cause OOM
- **Network:** Standard GCP egress billing applies

---

## Security Notes

- Passwords are hashed with bcrypt via passlib.
- Sessions use signed JWT cookies (HS256, 24 h expiry).
- CSRF tokens protect all state-changing POST endpoints.
- Per-IP rate limiting is applied globally via SlowAPI.
- Private repositories are invisible to unauthenticated users and other users.
- Git HTTP transport requires Basic auth credentials for push; public repos allow anonymous clone.
