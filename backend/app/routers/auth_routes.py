from fastapi import APIRouter, Request, Depends, Form, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from .. import models, auth
from ..deps import templates, get_db, limiter

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def read_root(request: Request, db: Session = Depends(get_db)):
    user = auth.get_current_user_from_cookie(request, db)
    if user:
        return RedirectResponse(url="/dashboard")
    return templates.TemplateResponse(request=request, name="index.html", context={"user": None})


@router.get("/login", response_class=HTMLResponse)
async def login_get(request: Request):
    return templates.TemplateResponse(request=request, name="login.html", context={"user": None})


@router.post("/login")
@limiter.limit("10/minute")
async def login_post(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    user = db.query(models.User).filter(models.User.username == username).first()
    if not user or not auth.verify_password(password, user.hashed_password):
        return templates.TemplateResponse(request=request, name="login.html", context={"error": "Invalid username or password", "user": None})

    access_token = auth.create_access_token(data={"sub": user.username})
    redirect = RedirectResponse(url="/dashboard", status_code=status.HTTP_302_FOUND)
    redirect.set_cookie(key="access_token", value=f"Bearer {access_token}", httponly=True)
    return redirect


@router.get("/register", response_class=HTMLResponse)
async def register_get(request: Request):
    return templates.TemplateResponse(request=request, name="register.html", context={"user": None})


@router.post("/register")
async def register_post(
    request: Request,
    username: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    confirm_password: str = Form(...),
    db: Session = Depends(get_db)
):
    if password != confirm_password:
        return templates.TemplateResponse(request=request, name="register.html", context={"error": "Passwords do not match", "user": None})

    existing_user = db.query(models.User).filter(
        (models.User.username == username) | (models.User.email == email)
    ).first()
    if existing_user:
        return templates.TemplateResponse(request=request, name="register.html", context={"error": "Username or Email already registered", "user": None})

    hashed_password = auth.get_password_hash(password)
    new_user = models.User(username=username, email=email, hashed_password=hashed_password)
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)


@router.get("/logout")
async def logout():
    response = RedirectResponse(url="/")
    response.delete_cookie("access_token")
    return response
