import os
from typing import Optional
from dataclasses import dataclass
from fastapi import Request
from sqlalchemy.orm import Session
import models
import auth
import git_utils

REPOS_DIR = "./repos"


@dataclass
class RepoContext:
    owner: models.User
    repo: models.Repository
    current_user: Optional[models.User]
    repo_path: str


def get_repo_path(owner_username: str, repo_name: str) -> str:
    return os.path.join(REPOS_DIR, owner_username, f"{repo_name}.git")


def require_login(request: Request, db: Session) -> Optional[models.User]:
    """Returns the current user or None if not logged in.
    Callers should redirect to /login when None is returned."""
    return auth.get_current_user_from_cookie(request, db)


def lookup_repo_context(
    request: Request, db: Session, username: str, repo_name: str
) -> tuple[Optional[RepoContext], Optional[str]]:
    """Look up owner, repo, current user, and verify access.

    Returns (RepoContext, None) on success or (None, error_message) on failure.
    """
    owner = db.query(models.User).filter(models.User.username == username).first()
    if not owner:
        return None, "User not found"

    repo = db.query(models.Repository).filter(
        models.Repository.owner_id == owner.id,
        models.Repository.name == repo_name
    ).first()

    current_user = auth.get_current_user_from_cookie(request, db)

    if not repo or (repo.is_private and (not current_user or current_user.id != owner.id)):
        return None, "Repository not found"

    repo_path = get_repo_path(owner.username, repo.name)

    return RepoContext(
        owner=owner, repo=repo, current_user=current_user, repo_path=repo_path
    ), None


def validate_branch(repo_path: str, branch: str) -> tuple[str, list]:
    """Validate that the branch exists; fall back to the first available branch.

    Returns (resolved_branch, branches_list).
    """
    branches = git_utils.get_branches(repo_path)
    if branch not in branches and branches:
        branch = branches[0]
    return branch, branches
