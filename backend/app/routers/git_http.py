import os
import base64
import subprocess
from fastapi import APIRouter, Depends, Request, Response, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from .. import models, auth
from ..deps import get_db
from ..config import settings

router = APIRouter()

def parse_basic_auth(auth_header: str):
    if not auth_header or not auth_header.startswith("Basic "):
        return None, None
    try:
        decoded = base64.b64decode(auth_header[6:]).decode("utf-8")
        username, password = decoded.split(":", 1)
        return username, password
    except Exception:
        return None, None

def authenticate_git(request: Request, db: Session):
    auth_header = request.headers.get("Authorization")
    username, password = parse_basic_auth(auth_header)
    if not username or not password:
        return None
    
    user = db.query(models.User).filter(models.User.username == username).first()
    if user and auth.verify_password(password, user.hashed_password):
        return user
    return None

async def run_git_http_backend(request: Request, username: str, repo_name: str, path_info: str):
    # Determine the absolute path of the repository on disk
    repo_dir = os.path.join(settings.repos_dir, username)
    repo_path = os.path.join(repo_dir, f"{repo_name}.git")

    if not os.path.exists(repo_path):
        return Response("Repository not found", status_code=status.HTTP_404_NOT_FOUND)

    # Prepare environment variables for git http-backend
    env = {
        "GIT_PROJECT_ROOT": repo_dir,
        "GIT_HTTP_EXPORT_ALL": "1",
        "PATH_INFO": f"/{repo_name}.git/{path_info}",
        "REQUEST_METHOD": request.method,
        "QUERY_STRING": request.url.query,
        "CONTENT_TYPE": request.headers.get("Content-Type", ""),
    }

    # Start the git http-backend process
    proc = subprocess.Popen(
        ["git", "http-backend"],
        env=env,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    # Read the request body
    body = await request.body()

    # Run the process and get output
    stdout, stderr = proc.communicate(input=body)

    if proc.returncode != 0:
        return Response(f"Internal git error: {stderr.decode('utf-8', errors='ignore')}", status_code=500)

    # Parse HTTP headers from git http-backend output
    headers = {}
    response_body = b""
    
    # git http-backend outputs headers followed by a blank line, then the body
    parts = stdout.split(b"\r\n\r\n", 1)
    if len(parts) < 2:
        parts = stdout.split(b"\n\n", 1)

    if len(parts) >= 2:
        header_part, response_body = parts[0], parts[1]
        for line in header_part.splitlines():
            if b":" in line:
                key, val = line.split(b":", 1)
                headers[key.decode("utf-8").strip()] = val.decode("utf-8").strip()
    else:
        response_body = stdout

    # Extract Status header if present
    status_code = 200
    if "Status" in headers:
        try:
            status_code = int(headers.pop("Status").split()[0])
        except Exception:
            pass

    return Response(content=response_body, status_code=status_code, headers=headers)

@router.get("/repos/{username}/{repo_name}.git/info/refs")
async def git_info_refs(
    request: Request,
    username: str,
    repo_name: str,
    db: Session = Depends(get_db)
):
    # Authenticate user
    user = authenticate_git(request, db)
    if not user:
        return Response(
            "Unauthorized",
            status_code=status.HTTP_401_UNAUTHORIZED,
            headers={"WWW-Authenticate": 'Basic realm="GitClone"'}
        )

    # Verify repository ownership or public access
    owner = db.query(models.User).filter(models.User.username == username).first()
    repo = db.query(models.Repository).filter(
        models.Repository.owner_id == owner.id if owner else False,
        models.Repository.name == repo_name
    ).first()

    if not repo:
        return Response("Repository not found", status_code=status.HTTP_404_NOT_FOUND)

    # If repository is private, only owner can access it
    if repo.is_private and user.id != owner.id:
        return Response("Unauthorized", status_code=status.HTTP_401_UNAUTHORIZED)

    return await run_git_http_backend(request, username, repo_name, "info/refs")

@router.post("/repos/{username}/{repo_name}.git/git-upload-pack")
async def git_upload_pack(
    request: Request,
    username: str,
    repo_name: str,
    db: Session = Depends(get_db)
):
    # Authenticate user (Pulling/cloning)
    user = authenticate_git(request, db)
    if not user:
        return Response(
            "Unauthorized",
            status_code=status.HTTP_401_UNAUTHORIZED,
            headers={"WWW-Authenticate": 'Basic realm="GitClone"'}
        )

    owner = db.query(models.User).filter(models.User.username == username).first()
    repo = db.query(models.Repository).filter(
        models.Repository.owner_id == owner.id if owner else False,
        models.Repository.name == repo_name
    ).first()

    if not repo:
        return Response("Repository not found", status_code=status.HTTP_404_NOT_FOUND)

    if repo.is_private and user.id != owner.id:
        return Response("Unauthorized", status_code=status.HTTP_401_UNAUTHORIZED)

    return await run_git_http_backend(request, username, repo_name, "git-upload-pack")

@router.post("/repos/{username}/{repo_name}.git/git-receive-pack")
async def git_receive_pack(
    request: Request,
    username: str,
    repo_name: str,
    db: Session = Depends(get_db)
):
    # Authenticate user (Pushing)
    user = authenticate_git(request, db)
    if not user:
        return Response(
            "Unauthorized",
            status_code=status.HTTP_401_UNAUTHORIZED,
            headers={"WWW-Authenticate": 'Basic realm="GitClone"'}
        )

    owner = db.query(models.User).filter(models.User.username == username).first()
    repo = db.query(models.Repository).filter(
        models.Repository.owner_id == owner.id if owner else False,
        models.Repository.name == repo_name
    ).first()

    if not repo:
        return Response("Repository not found", status_code=status.HTTP_404_NOT_FOUND)

    # Only the owner of the repository can push to it
    if user.id != owner.id:
        return Response("Unauthorized", status_code=status.HTTP_401_UNAUTHORIZED)

    return await run_git_http_backend(request, username, repo_name, "git-receive-pack")
