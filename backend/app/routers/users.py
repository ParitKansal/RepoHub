from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from .. import models, auth
from ..deps import templates, get_db

router = APIRouter()


@router.get("/search", response_class=HTMLResponse)
async def search_repositories(request: Request, q: str = "", db: Session = Depends(get_db)):
    current_user = auth.get_current_user_from_cookie(request, db)

    query = db.query(models.Repository).join(models.User, models.Repository.owner_id == models.User.id)

    if current_user:
        query = query.filter(
            (models.Repository.is_private == False) |
            (models.Repository.owner_id == current_user.id)
        )
    else:
        query = query.filter(models.Repository.is_private == False)

    if q:
        search_term = f"%{q}%"
        query = query.filter(
            (models.Repository.name.ilike(search_term)) |
            (models.Repository.description.ilike(search_term)) |
            (models.User.username.ilike(search_term))
        )

    results = query.all()

    return templates.TemplateResponse(request=request, name="search_results.html", context={
        "user": current_user,
        "query": q,
        "results": results
    })


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request, db: Session = Depends(get_db)):
    user = auth.get_current_user_from_cookie(request, db)
    if not user:
        return RedirectResponse(url="/login")

    repositories = db.query(models.Repository).filter(models.Repository.owner_id == user.id).all()
    return templates.TemplateResponse(request=request, name="dashboard.html", context={"user": user, "repositories": repositories})


@router.get("/{username}", response_class=HTMLResponse)
async def user_profile(request: Request, username: str, db: Session = Depends(get_db)):
    profile_user = db.query(models.User).filter(models.User.username == username).first()
    if not profile_user:
        return RedirectResponse(url="/")

    current_user = auth.get_current_user_from_cookie(request, db)

    query = db.query(models.Repository).filter(models.Repository.owner_id == profile_user.id)
    if not current_user or current_user.id != profile_user.id:
        query = query.filter(models.Repository.is_private == False)

    repositories = query.all()

    return templates.TemplateResponse(request=request, name="user_profile.html", context={
        "user": current_user,
        "profile_user": profile_user,
        "repositories": repositories
    })
