import os
from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from .. import models, auth
from ..deps import templates, get_db
from ..git import subprocess_impl as git_utils
from ..config import settings

router = APIRouter()


@router.get("/{username}/{repo_name}/commits", response_class=HTMLResponse)
async def repo_commits(request: Request, username: str, repo_name: str, branch: str = "main", db: Session = Depends(get_db)):
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
    commits = []
    branches = []

    if not git_utils.is_repo_empty(repo_path):
        branches = git_utils.get_branches(repo_path)
        if branch not in branches and branches:
            branch = branches[0]
        commits = git_utils.get_repo_commits(repo_path, limit=50, branch=branch)

    return templates.TemplateResponse(request=request, name="commits.html", context={
        "user": current_user,
        "repo": repo,
        "owner": owner,
        "commits": commits,
        "branches": branches,
        "current_branch": branch
    })


@router.get("/{username}/{repo_name}/branches", response_class=HTMLResponse)
async def repo_branches(request: Request, username: str, repo_name: str, db: Session = Depends(get_db)):
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

    return templates.TemplateResponse(request=request, name="branches.html", context={
        "user": current_user,
        "repo": repo,
        "owner": owner,
        "branches": branches
    })


@router.get("/{username}/{repo_name}/blob/{filepath:path}", response_class=HTMLResponse)
async def repo_blob(request: Request, username: str, repo_name: str, filepath: str, branch: str = "main", db: Session = Depends(get_db)):
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

    branches = git_utils.get_branches(repo_path)
    if branch not in branches and branches:
        branch = branches[0]

    content = git_utils.get_file_content(repo_path, filepath, branch=branch)

    return templates.TemplateResponse(request=request, name="file_view.html", context={
        "user": current_user,
        "repo": repo,
        "owner": owner,
        "filepath": filepath,
        "content": content,
        "current_branch": branch
    })


@router.get("/{username}/{repo_name}/commit/{commit_hash}", response_class=HTMLResponse)
async def commit_detail(request: Request, username: str, repo_name: str, commit_hash: str, db: Session = Depends(get_db)):
    owner = db.query(models.User).filter(models.User.username == username).first()

    repo = db.query(models.Repository).filter(
        models.Repository.owner_id == owner.id if owner else False,
        models.Repository.name == repo_name
    ).first()

    user = auth.get_current_user_from_cookie(request, db)

    if not repo or (repo.is_private and (not user or user.id != owner.id)):
        return RedirectResponse(url="/", status_code=303)

    repo_path = os.path.join(settings.repos_dir, username, repo_name + ".git")
    commit_data = git_utils.get_commit_details(repo_path, commit_hash)

    if not commit_data:
        return RedirectResponse(url=f"/{username}/{repo_name}/commits")

    return templates.TemplateResponse(request=request, name="commit_detail.html", context={
        "user": user,
        "repo": repo,
        "owner": owner,
        "commit": commit_data
    })
