from fastapi import APIRouter, Request, Depends, Form, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from .. import models, auth
from ..deps import templates, get_db

router = APIRouter()


@router.get("/{username}/{repo_name}/issues", response_class=HTMLResponse)
async def repo_issues(request: Request, username: str, repo_name: str, state: str = "open", db: Session = Depends(get_db)):
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

    open_count = db.query(models.Issue).filter(models.Issue.repo_id == repo.id, models.Issue.status == "Open").count()
    closed_count = db.query(models.Issue).filter(models.Issue.repo_id == repo.id, models.Issue.status == "Closed").count()

    query = db.query(models.Issue).filter(models.Issue.repo_id == repo.id)
    if state.lower() == "closed":
        query = query.filter(models.Issue.status == "Closed")
    else:
        query = query.filter(models.Issue.status == "Open")

    issues = query.all()

    return templates.TemplateResponse(request=request, name="issues.html", context={
        "user": current_user,
        "repo": repo,
        "owner": owner,
        "issues": issues,
        "state": state.lower(),
        "open_count": open_count,
        "closed_count": closed_count
    })


@router.get("/{username}/{repo_name}/issues/new", response_class=HTMLResponse)
async def new_issue_get(request: Request, username: str, repo_name: str, db: Session = Depends(get_db)):
    user = auth.get_current_user_from_cookie(request, db)
    if not user:
        return RedirectResponse(url="/login")

    owner = db.query(models.User).filter(models.User.username == username).first()
    repo = db.query(models.Repository).filter(
        models.Repository.owner_id == owner.id if owner else False,
        models.Repository.name == repo_name
    ).first()

    if not repo:
        return RedirectResponse(url="/dashboard")

    return templates.TemplateResponse(request=request, name="new_issue.html", context={
        "user": user,
        "repo": repo,
        "owner": owner
    })


@router.post("/{username}/{repo_name}/issues/new")
async def new_issue_post(
    request: Request,
    username: str,
    repo_name: str,
    title: str = Form(...),
    description: str = Form(None),
    db: Session = Depends(get_db)
):
    user = auth.get_current_user_from_cookie(request, db)
    if not user:
        return RedirectResponse(url="/login")

    owner = db.query(models.User).filter(models.User.username == username).first()
    repo = db.query(models.Repository).filter(
        models.Repository.owner_id == owner.id if owner else False,
        models.Repository.name == repo_name
    ).first()

    if not repo:
        return RedirectResponse(url="/dashboard")

    new_issue = models.Issue(title=title, description=description, repo_id=repo.id, author_id=user.id)
    db.add(new_issue)
    db.commit()
    db.refresh(new_issue)

    return RedirectResponse(url=f"/{username}/{repo_name}/issues/{new_issue.id}", status_code=status.HTTP_302_FOUND)


@router.get("/{username}/{repo_name}/issues/{issue_id}", response_class=HTMLResponse)
async def issue_detail(request: Request, username: str, repo_name: str, issue_id: int, db: Session = Depends(get_db)):
    owner = db.query(models.User).filter(models.User.username == username).first()
    repo = db.query(models.Repository).filter(
        models.Repository.owner_id == owner.id if owner else False,
        models.Repository.name == repo_name
    ).first()

    if not repo:
        return RedirectResponse(url="/dashboard")

    issue = db.query(models.Issue).filter(models.Issue.id == issue_id, models.Issue.repo_id == repo.id).first()
    if not issue:
        return RedirectResponse(url=f"/{username}/{repo_name}/issues")

    current_user = auth.get_current_user_from_cookie(request, db)

    return templates.TemplateResponse(request=request, name="issue_detail.html", context={
        "user": current_user,
        "repo": repo,
        "owner": owner,
        "issue": issue
    })


@router.post("/{username}/{repo_name}/issues/{issue_id}/comment")
async def add_issue_comment(
    request: Request,
    username: str,
    repo_name: str,
    issue_id: int,
    content: str = Form(...),
    db: Session = Depends(get_db)
):
    current_user = auth.get_current_user_from_cookie(request, db)
    if not current_user:
        return RedirectResponse(url="/login")

    owner = db.query(models.User).filter(models.User.username == username).first()
    repo = db.query(models.Repository).filter(
        models.Repository.owner_id == owner.id,
        models.Repository.name == repo_name
    ).first()

    issue = db.query(models.Issue).filter(models.Issue.id == issue_id, models.Issue.repo_id == repo.id).first()
    if not issue:
        return RedirectResponse(url=f"/{username}/{repo_name}/issues")

    new_comment = models.Comment(content=content, issue_id=issue.id, author_id=current_user.id)
    db.add(new_comment)
    db.commit()

    return RedirectResponse(url=f"/{username}/{repo_name}/issues/{issue_id}", status_code=status.HTTP_302_FOUND)


@router.post("/{username}/{repo_name}/issues/{issue_id}/close")
async def close_issue(
    request: Request,
    username: str,
    repo_name: str,
    issue_id: int,
    db: Session = Depends(get_db)
):
    current_user = auth.get_current_user_from_cookie(request, db)
    if not current_user:
        return RedirectResponse(url="/login")

    owner = db.query(models.User).filter(models.User.username == username).first()
    repo = db.query(models.Repository).filter(
        models.Repository.owner_id == owner.id,
        models.Repository.name == repo_name
    ).first()

    issue = db.query(models.Issue).filter(models.Issue.id == issue_id, models.Issue.repo_id == repo.id).first()
    if not issue:
        return RedirectResponse(url=f"/{username}/{repo_name}/issues")

    if current_user.id != owner.id and current_user.id != issue.author_id:
        return RedirectResponse(url=f"/{username}/{repo_name}/issues/{issue_id}")

    issue.status = "Closed" if issue.status == "Open" else "Open"
    db.commit()

    return RedirectResponse(url=f"/{username}/{repo_name}/issues/{issue_id}", status_code=status.HTTP_302_FOUND)
