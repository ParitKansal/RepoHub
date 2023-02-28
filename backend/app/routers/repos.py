import os
import re
import shutil
import markdown
from fastapi import APIRouter, Request, Depends, Form, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from .. import models, auth
from ..deps import templates, get_db
from ..git import subprocess_impl as git_utils
from ..config import settings

router = APIRouter()


@router.get("/repo/new", response_class=HTMLResponse)
async def new_repo_get(request: Request, db: Session = Depends(get_db)):
    user = auth.get_current_user_from_cookie(request, db)
    if not user:
        return RedirectResponse(url="/login")
    return templates.TemplateResponse(request=request, name="new_repo.html", context={"user": user})


@router.post("/repo/new", response_class=HTMLResponse)
async def new_repo_post(
    request: Request,
    repo_name: str = Form(...),
    description: str = Form(None),
    visibility: str = Form("public"),
    db: Session = Depends(get_db)
):
    user = auth.get_current_user_from_cookie(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=303)

    is_private = (visibility == "private")

    if not re.match(r"^[a-zA-Z0-9_-]+$", repo_name):
        return templates.TemplateResponse(request=request, name="new_repo.html", context={"error": "Invalid repository name", "user": user})

    existing_repo = db.query(models.Repository).filter(
        models.Repository.owner_id == user.id,
        models.Repository.name == repo_name
    ).first()

    if existing_repo:
        return templates.TemplateResponse(request=request, name="new_repo.html", context={"error": "Repository already exists", "user": user})

    success = await git_utils.create_bare_repo(settings.repos_dir, user.username, repo_name)
    if not success:
        return templates.TemplateResponse(request=request, name="new_repo.html", context={"error": "Failed to create git repository on disk", "user": user})

    new_repo = models.Repository(name=repo_name, description=description, is_private=is_private, owner_id=user.id)
    db.add(new_repo)
    db.commit()

    return RedirectResponse(url=f"/{user.username}/{repo_name}", status_code=status.HTTP_302_FOUND)


@router.get("/{username}/{repo_name}", response_class=HTMLResponse)
async def repo_detail(request: Request, username: str, repo_name: str, branch: str = "main", db: Session = Depends(get_db)):
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

    is_empty = await git_utils.is_repo_empty(repo_path)
    files = []
    latest_commit = None
    readme_html = None
    branches = []
    contributors = []

    if not is_empty:
        branches = await git_utils.get_branches(repo_path)
        if branch not in branches and branches:
            branch = branches[0]

        files = await git_utils.get_repo_files(repo_path, branch=branch)
        commits = await git_utils.get_repo_commits(repo_path, limit=1, branch=branch)
        if commits:
            latest_commit = commits[0]

        for file in files:
            if file['name'].lower() == 'readme.md' and file['type'] == 'blob':
                try:
                    readme_content = await git_utils.get_file_content(repo_path, file['name'], branch=branch)
                    if readme_content:
                        readme_html = markdown.markdown(readme_content, extensions=['fenced_code', 'tables'])
                except Exception:
                    pass

        contributors = await git_utils.get_contributors(repo_path)

    return templates.TemplateResponse(request=request, name="repo_detail.html", context={
        "user": current_user,
        "repo": repo,
        "owner": owner,
        "is_empty": is_empty,
        "files": files,
        "latest_commit": latest_commit,
        "readme_html": readme_html,
        "branches": branches,
        "current_branch": branch,
        "contributors": contributors
    })


@router.get("/{username}/{repo_name}/settings", response_class=HTMLResponse)
async def repo_settings(request: Request, username: str, repo_name: str, db: Session = Depends(get_db)):
    current_user = auth.get_current_user_from_cookie(request, db)
    if not current_user or current_user.username != username:
        return RedirectResponse(url=f"/{username}/{repo_name}", status_code=303)

    owner = db.query(models.User).filter(models.User.username == username).first()
    repo = db.query(models.Repository).filter(
        models.Repository.owner_id == owner.id,
        models.Repository.name == repo_name
    ).first()

    if not repo:
        return RedirectResponse(url="/", status_code=303)

    return templates.TemplateResponse(request=request, name="settings.html", context={
        "user": current_user,
        "repo": repo,
        "owner": owner
    })


@router.post("/{username}/{repo_name}/delete", response_class=RedirectResponse)
async def delete_repo(request: Request, username: str, repo_name: str, db: Session = Depends(get_db)):
    current_user = auth.get_current_user_from_cookie(request, db)
    if not current_user or current_user.username != username:
        return RedirectResponse(url=f"/{username}/{repo_name}", status_code=303)

    owner = db.query(models.User).filter(models.User.username == username).first()
    repo = db.query(models.Repository).filter(
        models.Repository.owner_id == owner.id,
        models.Repository.name == repo_name
    ).first()

    if repo:
        db.delete(repo)
        db.commit()

        repo_path = os.path.join(settings.repos_dir, owner.username, f"{repo.name}.git")
        if os.path.exists(repo_path):
            shutil.rmtree(repo_path)

    return RedirectResponse(url="/dashboard", status_code=303)


@router.post("/{username}/{repo_name}/star", response_class=RedirectResponse)
async def toggle_star(request: Request, username: str, repo_name: str, db: Session = Depends(get_db)):
    user = auth.get_current_user_from_cookie(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=303)

    owner = db.query(models.User).filter(models.User.username == username).first()
    if not owner:
        return RedirectResponse(url="/", status_code=303)

    repo = db.query(models.Repository).filter(
        models.Repository.owner_id == owner.id,
        models.Repository.name == repo_name
    ).first()

    if not repo:
        return RedirectResponse(url="/", status_code=303)

    existing_star = db.query(models.Star).filter(
        models.Star.user_id == user.id,
        models.Star.repo_id == repo.id
    ).first()

    if existing_star:
        db.delete(existing_star)
    else:
        db.add(models.Star(user_id=user.id, repo_id=repo.id))

    db.commit()

    referer = request.headers.get("referer")
    if referer:
        return RedirectResponse(url=referer, status_code=303)
    return RedirectResponse(url=f"/{username}/{repo_name}", status_code=303)
