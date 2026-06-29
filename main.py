import os
from fastapi import FastAPI, Depends, Request, Form, Response, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
import models
import database
import auth
import git_utils
import re

REPOS_DIR = "./repos"
os.makedirs(REPOS_DIR, exist_ok=True)

# Create database tables
models.Base.metadata.create_all(bind=database.engine)

app = FastAPI(title="GitClone College Project")

# Setup templates
templates = Jinja2Templates(directory="templates")

# Dependency
def get_db():
    db = database.SessionLocal()
    try:
        yield db
    finally:
        db.close()

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request, db: Session = Depends(get_db)):
    user = auth.get_current_user_from_cookie(request, db)
    if user:
        return RedirectResponse(url="/dashboard")
    return templates.TemplateResponse(request=request, name="index.html", context={"user": None})

@app.get("/login", response_class=HTMLResponse)
async def login_get(request: Request):
    return templates.TemplateResponse(request=request, name="login.html", context={"user": None})

@app.post("/login")
async def login_post(
    request: Request, 
    response: Response,
    username: str = Form(...), 
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    user = db.query(models.User).filter(models.User.username == username).first()
    if not user or not auth.verify_password(password, user.hashed_password):
        return templates.TemplateResponse(request=request, name="login.html", context={"error": "Invalid username or password", "user": None})
    
    access_token = auth.create_access_token(data={"sub": user.username})
    
    # Create redirect response
    redirect = RedirectResponse(url="/dashboard", status_code=status.HTTP_302_FOUND)
    # Set cookie
    redirect.set_cookie(key="access_token", value=f"Bearer {access_token}", httponly=True)
    return redirect

@app.get("/register", response_class=HTMLResponse)
async def register_get(request: Request):
    return templates.TemplateResponse(request=request, name="register.html", context={"user": None})

@app.post("/register")
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

    # Check if user exists
    existing_user = db.query(models.User).filter((models.User.username == username) | (models.User.email == email)).first()
    if existing_user:
        return templates.TemplateResponse(request=request, name="register.html", context={"error": "Username or Email already registered", "user": None})
    
    hashed_password = auth.get_password_hash(password)
    new_user = models.User(username=username, email=email, hashed_password=hashed_password)
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    
    return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)

@app.get("/logout")
async def logout():
    response = RedirectResponse(url="/")
    response.delete_cookie("access_token")
    return response

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request, db: Session = Depends(get_db)):
    user = auth.get_current_user_from_cookie(request, db)
    if not user:
        return RedirectResponse(url="/login")
    
    repositories = db.query(models.Repository).filter(models.Repository.owner_id == user.id).all()
    return templates.TemplateResponse(request=request, name="dashboard.html", context={"user": user, "repositories": repositories})

@app.get("/repo/new", response_class=HTMLResponse)
async def new_repo_get(request: Request, db: Session = Depends(get_db)):
    user = auth.get_current_user_from_cookie(request, db)
    if not user:
        return RedirectResponse(url="/login")
    return templates.TemplateResponse(request=request, name="new_repo.html", context={"user": user})

@app.post("/repo/new")
async def new_repo_post(
    request: Request,
    repo_name: str = Form(...),
    description: str = Form(None),
    db: Session = Depends(get_db)
):
    user = auth.get_current_user_from_cookie(request, db)
    if not user:
        return RedirectResponse(url="/login")
        
    # Basic validation for repository name (alphanumeric and dashes)
    if not re.match(r"^[a-zA-Z0-9_-]+$", repo_name):
        return templates.TemplateResponse(request=request, name="new_repo.html", context={"error": "Invalid repository name", "user": user})

    # Check if repo already exists for this user
    existing_repo = db.query(models.Repository).filter(
        models.Repository.owner_id == user.id, 
        models.Repository.name == repo_name
    ).first()
    
    if existing_repo:
        return templates.TemplateResponse(request=request, name="new_repo.html", context={"error": "Repository already exists", "user": user})

    # Create physically on disk
    success = git_utils.create_bare_repo(REPOS_DIR, user.username, repo_name)
    if not success:
        return templates.TemplateResponse(request=request, name="new_repo.html", context={"error": "Failed to create git repository on disk", "user": user})

    # Save to database
    new_repo = models.Repository(name=repo_name, description=description, owner_id=user.id)
    db.add(new_repo)
    db.commit()
    
    return RedirectResponse(url=f"/{user.username}/{repo_name}", status_code=status.HTTP_302_FOUND)

@app.get("/{username}/{repo_name}", response_class=HTMLResponse)
async def repo_detail(request: Request, username: str, repo_name: str, db: Session = Depends(get_db)):
    # Look up the owner
    owner = db.query(models.User).filter(models.User.username == username).first()
    if not owner:
        return templates.TemplateResponse(request=request, name="repo_detail.html", context={"error": "User not found", "user": auth.get_current_user_from_cookie(request, db)})
        
    # Look up the repo
    repo = db.query(models.Repository).filter(
        models.Repository.owner_id == owner.id, 
        models.Repository.name == repo_name
    ).first()
    
    if not repo:
        return templates.TemplateResponse(request=request, name="repo_detail.html", context={"error": "Repository not found", "user": auth.get_current_user_from_cookie(request, db)})
        
    current_user = auth.get_current_user_from_cookie(request, db)
    repo_path = os.path.join(REPOS_DIR, owner.username, f"{repo.name}.git")
    
    is_empty = git_utils.is_repo_empty(repo_path)
    files = []
    latest_commit = None
    
    if not is_empty:
        files = git_utils.get_repo_files(repo_path)
        commits = git_utils.get_repo_commits(repo_path, limit=1)
        if commits:
            latest_commit = commits[0]

    return templates.TemplateResponse(request=request, name="repo_detail.html", context={
        "user": current_user, 
        "repo": repo, 
        "owner": owner,
        "is_empty": is_empty,
        "files": files,
        "latest_commit": latest_commit
    })

@app.get("/{username}/{repo_name}/commits", response_class=HTMLResponse)
async def repo_commits(request: Request, username: str, repo_name: str, db: Session = Depends(get_db)):
    owner = db.query(models.User).filter(models.User.username == username).first()
    if not owner:
        return templates.TemplateResponse(request=request, name="commits.html", context={"error": "User not found", "user": auth.get_current_user_from_cookie(request, db)})
        
    repo = db.query(models.Repository).filter(
        models.Repository.owner_id == owner.id, 
        models.Repository.name == repo_name
    ).first()
    
    if not repo:
        return templates.TemplateResponse(request=request, name="commits.html", context={"error": "Repository not found", "user": auth.get_current_user_from_cookie(request, db)})
        
    current_user = auth.get_current_user_from_cookie(request, db)
    repo_path = os.path.join(REPOS_DIR, owner.username, f"{repo.name}.git")
    commits = git_utils.get_repo_commits(repo_path, limit=50)
    
    return templates.TemplateResponse(request=request, name="commits.html", context={
        "user": current_user, 
        "repo": repo, 
        "owner": owner,
        "commits": commits
    })

@app.get("/{username}/{repo_name}/blob/{filepath:path}", response_class=HTMLResponse)
async def repo_blob(request: Request, username: str, repo_name: str, filepath: str, db: Session = Depends(get_db)):
    owner = db.query(models.User).filter(models.User.username == username).first()
    if not owner:
        return templates.TemplateResponse(request=request, name="file_view.html", context={"error": "User not found", "user": auth.get_current_user_from_cookie(request, db)})
        
    repo = db.query(models.Repository).filter(
        models.Repository.owner_id == owner.id, 
        models.Repository.name == repo_name
    ).first()
    
    if not repo:
        return templates.TemplateResponse(request=request, name="file_view.html", context={"error": "Repository not found", "user": auth.get_current_user_from_cookie(request, db)})
        
    current_user = auth.get_current_user_from_cookie(request, db)
    repo_path = os.path.join(REPOS_DIR, owner.username, f"{repo.name}.git")
    
    content = git_utils.get_file_content(repo_path, filepath)
    
    return templates.TemplateResponse(request=request, name="file_view.html", context={
        "user": current_user, 
        "repo": repo, 
        "owner": owner,
        "filepath": filepath,
        "content": content
    })
