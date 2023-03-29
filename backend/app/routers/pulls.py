import os
import asyncio
import subprocess
from fastapi import APIRouter, Request, Depends, Form, status, Query
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from sqlalchemy.orm import Session
from .. import models, auth
from ..deps import templates, get_db
from ..git import subprocess_impl as git_utils
from ..config import settings

router = APIRouter()


@router.get("/{username}/{repo_name}/api/check-conflicts")
async def check_conflicts(
    request: Request,
    username: str,
    repo_name: str,
    base: str = Query(...),
    compare: str = Query(...),
    db: Session = Depends(get_db)
):
    owner = db.query(models.User).filter(models.User.username == username).first()
    repo = db.query(models.Repository).filter(
        models.Repository.owner_id == owner.id,
        models.Repository.name == repo_name
    ).first() if owner else None

    current_user = auth.get_current_user_from_cookie(request, db)
    if not repo or (repo.is_private and (not current_user or current_user.id != owner.id)):
        return JSONResponse({"error": "Not found"}, status_code=404)

    if base == compare:
        return JSONResponse({"has_conflicts": False, "conflicting_files": []})

    repo_path = os.path.join(settings.repos_dir, owner.username, f"{repo.name}.git")

    if await git_utils.is_repo_empty(repo_path):
        return JSONResponse({"has_conflicts": False, "conflicting_files": []})

    try:
        mt = await asyncio.to_thread(
            subprocess.run,
            ["git", "merge-tree", "--write-tree", base, compare],
            cwd=repo_path, capture_output=True, text=True, timeout=30
        )
        has_conflicts = (mt.returncode != 0)
        conflicting_files = []
        if has_conflicts and mt.stdout:
            for line in mt.stdout.splitlines():
                if not line.strip():
                    break
                parts = line.split("\t")
                if len(parts) == 2:
                    filename = parts[1].strip()
                    if filename not in conflicting_files:
                        conflicting_files.append(filename)
        return JSONResponse({"has_conflicts": has_conflicts, "conflicting_files": conflicting_files})
    except Exception:
        return JSONResponse({"has_conflicts": False, "conflicting_files": []})


@router.get("/{username}/{repo_name}/pulls", response_class=HTMLResponse)
async def repo_pulls(request: Request, username: str, repo_name: str, db: Session = Depends(get_db)):
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

    pulls = db.query(models.PullRequest).filter(
        models.PullRequest.repo_id == repo.id
    ).order_by(models.PullRequest.created_at.desc()).all()

    return templates.TemplateResponse(request=request, name="pulls.html", context={
        "user": current_user,
        "repo": repo,
        "owner": owner,
        "pulls": pulls
    })


@router.get("/{username}/{repo_name}/pull/new", response_class=HTMLResponse)
async def new_pull_get(request: Request, username: str, repo_name: str, base: str = "main", compare: str = "", db: Session = Depends(get_db)):
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
    diff_files = []

    if not await git_utils.is_repo_empty(repo_path):
        branches = await git_utils.get_branches(repo_path)
        if not compare and len(branches) > 1:
            compare = branches[1] if branches[1] != base else branches[0]
        elif not compare:
            compare = base

        if base in branches and compare in branches and base != compare:
            diff_files = await git_utils.get_branch_diff(repo_path, base, compare)

    return templates.TemplateResponse(request=request, name="new_pull.html", context={
        "user": current_user,
        "repo": repo,
        "owner": owner,
        "branches": branches,
        "base": base,
        "compare": compare,
        "diff_files": diff_files
    })


@router.post("/{username}/{repo_name}/pull/new", response_class=RedirectResponse)
async def new_pull_post(
    request: Request,
    username: str,
    repo_name: str,
    title: str = Form(...),
    description: str = Form(None),
    base: str = Form(...),
    compare: str = Form(...),
    db: Session = Depends(get_db)
):
    current_user = auth.get_current_user_from_cookie(request, db)
    if not current_user:
        return RedirectResponse(url="/login", status_code=303)

    owner = db.query(models.User).filter(models.User.username == username).first()
    repo = db.query(models.Repository).filter(
        models.Repository.owner_id == owner.id,
        models.Repository.name == repo_name
    ).first()

    if not repo:
        return RedirectResponse(url="/", status_code=303)

    new_pr = models.PullRequest(
        title=title,
        description=description,
        source_branch=compare,
        target_branch=base,
        repo_id=repo.id,
        author_id=current_user.id
    )
    db.add(new_pr)
    db.commit()

    return RedirectResponse(url=f"/{username}/{repo_name}/pull/{new_pr.id}", status_code=303)


@router.get("/{username}/{repo_name}/pull/{pr_id}", response_class=HTMLResponse)
async def pull_detail(request: Request, username: str, repo_name: str, pr_id: int, db: Session = Depends(get_db)):
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

    pr = db.query(models.PullRequest).filter(
        models.PullRequest.id == pr_id,
        models.PullRequest.repo_id == repo.id
    ).first()
    if not pr:
        return templates.TemplateResponse(request=request, name="error.html", context={"error": "Pull Request not found", "user": current_user})

    repo_path = os.path.join(settings.repos_dir, owner.username, f"{repo.name}.git")
    diff_files = []
    can_merge = False
    conflicting_files = []

    if not await git_utils.is_repo_empty(repo_path):
        diff_files = await git_utils.get_branch_diff(repo_path, pr.target_branch, pr.source_branch)
        if pr.status == "Open":
            try:
                # Modern git merge-tree check: returns 0 if clean, 1 if there are conflicts.
                mt = await asyncio.to_thread(
                    subprocess.run,
                    ["git", "merge-tree", "--write-tree", pr.target_branch, pr.source_branch],
                    cwd=repo_path, capture_output=True, text=True, timeout=30
                )
                can_merge = (mt.returncode == 0)

                if not can_merge and mt.stdout:
                    for line in mt.stdout.splitlines():
                        if not line.strip():
                            break
                        parts = line.split("\t")
                        if len(parts) == 2:
                            filename = parts[1].strip()
                            if filename not in conflicting_files:
                                conflicting_files.append(filename)
            except Exception:
                can_merge = True

    print(f"DEBUG: pr_id={pr_id}, can_merge={can_merge}, conflicting_files={conflicting_files}")
    return templates.TemplateResponse(request=request, name="pull_detail.html", context={
        "user": current_user,
        "repo": repo,
        "owner": owner,
        "pr": pr,
        "diff_files": diff_files,
        "can_merge": can_merge,
        "conflicting_files": conflicting_files
    })


@router.post("/{username}/{repo_name}/pull/{pr_id}/merge", response_class=RedirectResponse)
async def pull_merge(request: Request, username: str, repo_name: str, pr_id: int, db: Session = Depends(get_db)):
    current_user = auth.get_current_user_from_cookie(request, db)
    if not current_user:
        return RedirectResponse(url="/login", status_code=303)

    owner = db.query(models.User).filter(models.User.username == username).first()
    repo = db.query(models.Repository).filter(
        models.Repository.owner_id == owner.id,
        models.Repository.name == repo_name
    ).first()

    if not repo:
        return RedirectResponse(url="/", status_code=303)

    pr = db.query(models.PullRequest).filter(
        models.PullRequest.id == pr_id,
        models.PullRequest.repo_id == repo.id
    ).first()
    if not pr or pr.status != "Open":
        return RedirectResponse(url=f"/{username}/{repo_name}/pulls", status_code=303)

    repo_path = os.path.join(settings.repos_dir, owner.username, f"{repo.name}.git")

    success = await git_utils.merge_branches(
        repo_path,
        pr.target_branch,
        pr.source_branch,
        current_user.username,
        current_user.email or f"{current_user.username}@gitclone.local"
    )

    if success:
        pr.status = "Merged"
        db.commit()

    return RedirectResponse(url=f"/{username}/{repo_name}/pull/{pr_id}", status_code=303)
