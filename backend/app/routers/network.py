import os
from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy.orm import Session
from .. import models, auth
from ..deps import templates, get_db
from ..git import subprocess_impl as git_utils
from ..config import settings

router = APIRouter()


@router.get("/{username}/{repo_name}/network", response_class=HTMLResponse)
async def repo_network(request: Request, username: str, repo_name: str, branch: str = "__all__", db: Session = Depends(get_db)):
    owner = db.query(models.User).filter(models.User.username == username).first()
    if not owner:
        return templates.TemplateResponse(request=request, name="error.html", context={"error": "User not found", "user": auth.get_current_user_from_cookie(request, db)})

    repo = db.query(models.Repository).filter(
        models.Repository.owner_id == owner.id,
        models.Repository.name == repo_name
    ).first()

    current_user = auth.get_current_user_from_cookie(request, db)

    if not repo or (repo.is_private and (not current_user or current_user.id != owner.id)):
        return templates.TemplateResponse(request=request, name="error.html", context={"error": "Repository not found", "user": current_user})

    repo_path = os.path.join(settings.repos_dir, owner.username, f"{repo.name}.git")
    branches = []
    if not git_utils.is_repo_empty(repo_path):
        branches = git_utils.get_branches(repo_path)

    return templates.TemplateResponse(request=request, name="network.html", context={
        "user": current_user,
        "repo": repo,
        "owner": owner,
        "branches": branches,
        "current_branch": branch
    })


@router.get("/{username}/{repo_name}/graph-data")
async def repo_graph_data(request: Request, username: str, repo_name: str, branch: str = "__all__", db: Session = Depends(get_db)):
    owner = db.query(models.User).filter(models.User.username == username).first()
    if not owner:
        return JSONResponse({"error": "User not found"}, status_code=404)

    repo = db.query(models.Repository).filter(
        models.Repository.owner_id == owner.id,
        models.Repository.name == repo_name
    ).first()

    current_user = auth.get_current_user_from_cookie(request, db)

    if not repo or (repo.is_private and (not current_user or current_user.id != owner.id)):
        return JSONResponse({"error": "Repository not found"}, status_code=404)

    repo_path = os.path.join(settings.repos_dir, owner.username, f"{repo.name}.git")
    if git_utils.is_repo_empty(repo_path):
        return JSONResponse({"commits": [], "branch_tips": {}})

    commits = git_utils.get_commit_graph(repo_path, branch, limit=80)
    branch_tips = git_utils.get_branch_tips(repo_path)
    return JSONResponse({"commits": commits, "branch_tips": branch_tips})
