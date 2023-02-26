import os
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from . import models, database
from .config import settings
from .routers import auth_routes, users, repos, code, issues, pulls, network

os.makedirs(settings.repos_dir, exist_ok=True)
models.Base.metadata.create_all(bind=database.engine)

app = FastAPI(title="GitClone")

app.mount("/static", StaticFiles(directory="/app/frontend/static"), name="static")

app.include_router(auth_routes.router)
app.include_router(repos.router)
app.include_router(code.router)
app.include_router(issues.router)
app.include_router(pulls.router)
app.include_router(network.router)
app.include_router(users.router)
