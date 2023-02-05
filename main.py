import os
import re
import markdown
from fastapi import FastAPI, Request, Depends, Form, Cookie, status, Response
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

@app.get("/search", response_class=HTMLResponse)
async def search_repositories(request: Request, q: str = "", db: Session = Depends(get_db)):
    current_user = auth.get_current_user_from_cookie(request, db)
    
    # Search by name, description, or owner username for public repos OR user's own repos
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

@app.post("/{username}/{repo_name}/star", response_class=RedirectResponse)
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
        new_star = models.Star(user_id=user.id, repo_id=repo.id)
        db.add(new_star)
        
    db.commit()
    
    # Redirect back to where they came from
    referer = request.headers.get("referer")
    if referer:
        return RedirectResponse(url=referer, status_code=303)
    return RedirectResponse(url=f"/{username}/{repo_name}", status_code=303)

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request, db: Session = Depends(get_db)):
    user = auth.get_current_user_from_cookie(request, db)
    if not user:
        return RedirectResponse(url="/login")
    
    repositories = db.query(models.Repository).filter(models.Repository.owner_id == user.id).all()
    return templates.TemplateResponse(request=request, name="dashboard.html", context={"user": user, "repositories": repositories})

@app.get("/{username}", response_class=HTMLResponse)
async def user_profile(request: Request, username: str, db: Session = Depends(get_db)):
    # Find the user being viewed
    profile_user = db.query(models.User).filter(models.User.username == username).first()
    if not profile_user:
        return RedirectResponse(url="/")
        
    # Get their repositories (filter out private ones unless viewing own profile)
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

@app.get("/repo/new", response_class=HTMLResponse)
async def new_repo_get(request: Request, db: Session = Depends(get_db)):
    user = auth.get_current_user_from_cookie(request, db)
    if not user:
        return RedirectResponse(url="/login")
    return templates.TemplateResponse(request=request, name="new_repo.html", context={"user": user})

@app.post("/repo/new", response_class=HTMLResponse)
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
    new_repo = models.Repository(name=repo_name, description=description, is_private=is_private, owner_id=user.id)
    db.add(new_repo)
    db.commit()
    
    return RedirectResponse(url=f"/{user.username}/{repo_name}", status_code=status.HTTP_302_FOUND)

@app.get("/{username}/{repo_name}", response_class=HTMLResponse)
async def repo_detail(request: Request, username: str, repo_name: str, branch: str = "main", db: Session = Depends(get_db)):
    # Look up the owner
    owner = db.query(models.User).filter(models.User.username == username).first()
    if not owner:
        return templates.TemplateResponse(request=request, name="repo_detail.html", context={"error": "User not found", "user": auth.get_current_user_from_cookie(request, db)})
        
    # Look up the repo
    repo = db.query(models.Repository).filter(
        models.Repository.owner_id == owner.id, 
        models.Repository.name == repo_name
    ).first()
    
    current_user = auth.get_current_user_from_cookie(request, db)
    
    if not repo or (repo.is_private and (not current_user or current_user.id != owner.id)):
        return templates.TemplateResponse(request=request, name="repo_detail.html", context={"error": "Repository not found", "user": current_user})
        
    repo_path = os.path.join(REPOS_DIR, owner.username, f"{repo.name}.git")
    
    is_empty = git_utils.is_repo_empty(repo_path)
    files = []
    latest_commit = None
    readme_html = None
    
    if not is_empty:
        branches = git_utils.get_branches(repo_path)
        if branch not in branches and branches:
            branch = branches[0]
            
        files = git_utils.get_repo_files(repo_path, branch=branch)
        commits = git_utils.get_repo_commits(repo_path, limit=1, branch=branch)
        if commits:
            latest_commit = commits[0]
            
        # Look for README.md
        for file in files:
            if file['name'].lower() == 'readme.md' and file['type'] == 'blob':
                try:
                    readme_content = git_utils.get_file_content(repo_path, file['name'], branch=branch)
                    if readme_content:
                        readme_html = markdown.markdown(readme_content, extensions=['fenced_code', 'tables'])
                except Exception:
                    pass

    return templates.TemplateResponse(request=request, name="repo_detail.html", context={
        "user": current_user, 
        "repo": repo, 
        "owner": owner,
        "is_empty": is_empty,
        "files": files,
        "latest_commit": latest_commit,
        "readme_html": readme_html,
        "branches": git_utils.get_branches(repo_path) if not is_empty else [],
        "current_branch": branch
    })

@app.get("/{username}/{repo_name}/commits", response_class=HTMLResponse)
async def repo_commits(request: Request, username: str, repo_name: str, branch: str = "main", db: Session = Depends(get_db)):
    owner = db.query(models.User).filter(models.User.username == username).first()
    if not owner:
        return templates.TemplateResponse(request=request, name="commits.html", context={"error": "User not found", "user": auth.get_current_user_from_cookie(request, db)})
        
    repo = db.query(models.Repository).filter(
        models.Repository.owner_id == owner.id, 
        models.Repository.name == repo_name
    ).first()
    
    current_user = auth.get_current_user_from_cookie(request, db)
    
    if not repo or (repo.is_private and (not current_user or current_user.id != owner.id)):
        return templates.TemplateResponse(request=request, name="commits.html", context={"error": "Repository not found", "user": current_user})
        
    repo_path = os.path.join(REPOS_DIR, owner.username, f"{repo.name}.git")
    
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

@app.get("/{username}/{repo_name}/branches", response_class=HTMLResponse)
async def repo_branches(request: Request, username: str, repo_name: str, db: Session = Depends(get_db)):
    owner = db.query(models.User).filter(models.User.username == username).first()
    if not owner:
        return templates.TemplateResponse(request=request, name="branches.html", context={"error": "User not found", "user": auth.get_current_user_from_cookie(request, db)})
        
    repo = db.query(models.Repository).filter(
        models.Repository.owner_id == owner.id, 
        models.Repository.name == repo_name
    ).first()
    
    current_user = auth.get_current_user_from_cookie(request, db)
    
    if not repo or (repo.is_private and (not current_user or current_user.id != owner.id)):
        return templates.TemplateResponse(request=request, name="branches.html", context={"error": "Repository not found", "user": current_user})
        
    repo_path = os.path.join(REPOS_DIR, owner.username, f"{repo.name}.git")
    branches = []
    if not git_utils.is_repo_empty(repo_path):
        branches = git_utils.get_branches(repo_path)
        
    return templates.TemplateResponse(request=request, name="branches.html", context={
        "user": current_user, 
        "repo": repo, 
        "owner": owner,
        "branches": branches
    })

@app.get("/{username}/{repo_name}/settings", response_class=HTMLResponse)
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

@app.post("/{username}/{repo_name}/delete", response_class=RedirectResponse)
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
        # Delete from db
        db.delete(repo)
        db.commit()
        
        # Delete from disk
        import shutil
        repo_path = os.path.join(REPOS_DIR, owner.username, f"{repo.name}.git")
        if os.path.exists(repo_path):
            shutil.rmtree(repo_path)
            
    return RedirectResponse(url="/dashboard", status_code=303)

@app.get("/{username}/{repo_name}/blob/{filepath:path}", response_class=HTMLResponse)
async def repo_blob(request: Request, username: str, repo_name: str, filepath: str, branch: str = "main", db: Session = Depends(get_db)):
    owner = db.query(models.User).filter(models.User.username == username).first()
    if not owner:
        return templates.TemplateResponse(request=request, name="file_view.html", context={"error": "User not found", "user": auth.get_current_user_from_cookie(request, db)})
        
    repo = db.query(models.Repository).filter(
        models.Repository.owner_id == owner.id, 
        models.Repository.name == repo_name
    ).first()
    
    current_user = auth.get_current_user_from_cookie(request, db)
    
    if not repo or (repo.is_private and (not current_user or current_user.id != owner.id)):
        return templates.TemplateResponse(request=request, name="file_view.html", context={"error": "Repository not found", "user": current_user})
        
    repo_path = os.path.join(REPOS_DIR, owner.username, f"{repo.name}.git")
    
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

@app.get("/{username}/{repo_name}/commit/{commit_hash}", response_class=HTMLResponse)
async def commit_detail(request: Request, username: str, repo_name: str, commit_hash: str, db: Session = Depends(get_db)):
    owner = db.query(models.User).filter(models.User.username == username).first()
    
    repo = db.query(models.Repository).filter(
        models.Repository.owner_id == owner.id if owner else False, 
        models.Repository.name == repo_name
    ).first()
    
    user = auth.get_current_user_from_cookie(request, db)
    
    if not repo or (repo.is_private and (not user or user.id != owner.id)):
        return RedirectResponse(url="/", status_code=303)
        
    repo_path = os.path.join(REPOS_DIR, username, repo_name + ".git")
    commit_data = git_utils.get_commit_details(repo_path, commit_hash)
    
    if not commit_data:
        return RedirectResponse(url=f"/{username}/{repo_name}/commits")
        
    
    return templates.TemplateResponse(request=request, name="commit_detail.html", context={
        "user": current_user, 
        "repo": repo, 
        "owner": owner,
        "commit": commit_data
    })

@app.get("/{username}/{repo_name}/issues", response_class=HTMLResponse)
async def repo_issues(request: Request, username: str, repo_name: str, state: str = "open", db: Session = Depends(get_db)):
    owner = db.query(models.User).filter(models.User.username == username).first()
    if not owner:
        return templates.TemplateResponse(request=request, name="issues.html", context={"error": "User not found", "user": auth.get_current_user_from_cookie(request, db)})
        
    repo = db.query(models.Repository).filter(
        models.Repository.owner_id == owner.id, 
        models.Repository.name == repo_name
    ).first()
    
    current_user = auth.get_current_user_from_cookie(request, db)
    
    if not repo or (repo.is_private and (not current_user or current_user.id != owner.id)):
        return templates.TemplateResponse(request=request, name="issues.html", context={"error": "Repository not found", "user": current_user})
        
    open_count = db.query(models.Issue).filter(models.Issue.repo_id == repo.id, models.Issue.status == "Open").count()
    closed_count = db.query(models.Issue).filter(models.Issue.repo_id == repo.id, models.Issue.status == "Closed").count()
    
    query = db.query(models.Issue).filter(models.Issue.repo_id == repo.id)
    if state.lower() == "closed":
        query = query.filter(models.Issue.status == "Closed")
    else:
        query = query.filter(models.Issue.status == "Open")
        
    issues = query.all()
    current_user = auth.get_current_user_from_cookie(request, db)
    
    return templates.TemplateResponse(request=request, name="issues.html", context={
        "user": current_user, 
        "repo": repo, 
        "owner": owner,
        "issues": issues,
        "state": state.lower(),
        "open_count": open_count,
        "closed_count": closed_count
    })

@app.get("/{username}/{repo_name}/issues/new", response_class=HTMLResponse)
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

@app.post("/{username}/{repo_name}/issues/new")
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
        
    new_issue = models.Issue(
        title=title, 
        description=description, 
        repo_id=repo.id, 
        author_id=user.id
    )
    db.add(new_issue)
    db.commit()
    db.refresh(new_issue)
    
    return RedirectResponse(url=f"/{username}/{repo_name}/issues/{new_issue.id}", status_code=status.HTTP_302_FOUND)

@app.get("/{username}/{repo_name}/issues/{issue_id}", response_class=HTMLResponse)
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

@app.post("/{username}/{repo_name}/issues/{issue_id}/comment")
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
        
    new_comment = models.Comment(
        content=content,
        issue_id=issue.id,
        author_id=current_user.id
    )
    db.add(new_comment)
    db.commit()
    
    return RedirectResponse(url=f"/{username}/{repo_name}/issues/{issue_id}", status_code=status.HTTP_302_FOUND)

@app.post("/{username}/{repo_name}/issues/{issue_id}/close")
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
        
    # Only repo owner or issue author can close it
    if current_user.id != owner.id and current_user.id != issue.author_id:
        return RedirectResponse(url=f"/{username}/{repo_name}/issues/{issue_id}")
        
    if issue.status == "Open":
        issue.status = "Closed"
    else:
        issue.status = "Open"
        
    db.commit()
    return RedirectResponse(url=f"/{username}/{repo_name}/issues/{issue_id}", status_code=status.HTTP_302_FOUND)
