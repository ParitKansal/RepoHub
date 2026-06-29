import os
import sys
import shutil
import subprocess
import tempfile
from unittest.mock import patch, MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import models
import auth
import database

# ---------------------------------------------------------------------------
# Test database & app setup
# ---------------------------------------------------------------------------

engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


# We need to import main *after* patching sys.path; main.py creates tables at
# import time, so we create the tables in the in-memory DB first.
models.Base.metadata.create_all(bind=engine)

from main import app, get_db

app.dependency_overrides[get_db] = override_get_db

client = TestClient(app)

# Temporary repos directory used for git operations in tests
TEMP_REPOS_DIR = tempfile.mkdtemp()


@pytest.fixture(autouse=True)
def _reset_db():
    """Drop and recreate tables between tests for isolation."""
    models.Base.metadata.drop_all(bind=engine)
    models.Base.metadata.create_all(bind=engine)
    yield
    # Cleanup temp repos
    for item in os.listdir(TEMP_REPOS_DIR):
        path = os.path.join(TEMP_REPOS_DIR, item)
        if os.path.isdir(path):
            shutil.rmtree(path, ignore_errors=True)


def _register_user(username="testuser", email="test@example.com", password="password123"):
    """Helper to register a user via the API."""
    return client.post(
        "/register",
        data={
            "username": username,
            "email": email,
            "password": password,
            "confirm_password": password,
        },
        follow_redirects=False,
    )


def _login_user(username="testuser", password="password123"):
    """Helper to login and return cookies."""
    response = client.post(
        "/login",
        data={"username": username, "password": password},
        follow_redirects=False,
    )
    return response.cookies


# ---------------------------------------------------------------------------
# Root & static pages
# ---------------------------------------------------------------------------


class TestRootAndStaticPages:
    def test_root_page_unauthenticated(self):
        response = client.get("/")
        assert response.status_code == 200

    def test_root_redirects_when_authenticated(self):
        _register_user()
        cookies = _login_user()
        response = client.get("/", cookies=cookies, follow_redirects=False)
        assert response.status_code in (302, 307)
        assert "/dashboard" in response.headers["location"]

    def test_login_page(self):
        response = client.get("/login")
        assert response.status_code == 200

    def test_register_page(self):
        response = client.get("/register")
        assert response.status_code == 200


# ---------------------------------------------------------------------------
# Authentication endpoints
# ---------------------------------------------------------------------------


class TestAuthentication:
    def test_register_success(self):
        response = _register_user()
        assert response.status_code == 302
        assert "/login" in response.headers["location"]

    def test_register_password_mismatch(self):
        response = client.post(
            "/register",
            data={
                "username": "user1",
                "email": "u1@example.com",
                "password": "pass1",
                "confirm_password": "pass2",
            },
        )
        assert response.status_code == 200
        assert "Passwords do not match" in response.text

    def test_register_duplicate_username(self):
        _register_user(username="dup", email="dup1@example.com")
        response = client.post(
            "/register",
            data={
                "username": "dup",
                "email": "dup2@example.com",
                "password": "pass",
                "confirm_password": "pass",
            },
        )
        assert response.status_code == 200
        assert "already registered" in response.text

    def test_login_success(self):
        _register_user()
        response = client.post(
            "/login",
            data={"username": "testuser", "password": "password123"},
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert "access_token" in response.cookies

    def test_login_wrong_password(self):
        _register_user()
        response = client.post(
            "/login",
            data={"username": "testuser", "password": "wrong"},
        )
        assert response.status_code == 200
        assert "Invalid" in response.text

    def test_login_nonexistent_user(self):
        response = client.post(
            "/login",
            data={"username": "nouser", "password": "pass"},
        )
        assert response.status_code == 200
        assert "Invalid" in response.text

    def test_logout(self):
        _register_user()
        cookies = _login_user()
        response = client.get("/logout", cookies=cookies, follow_redirects=False)
        assert response.status_code in (302, 307)


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------


class TestDashboard:
    def test_dashboard_unauthenticated_redirects(self):
        response = client.get("/dashboard", follow_redirects=False)
        assert response.status_code in (302, 307)

    def test_dashboard_authenticated(self):
        _register_user()
        cookies = _login_user()
        response = client.get("/dashboard", cookies=cookies)
        assert response.status_code == 200


# ---------------------------------------------------------------------------
# Repository creation
# ---------------------------------------------------------------------------


class TestRepositoryCreation:
    def test_new_repo_page_unauthenticated(self):
        response = client.get("/repo/new", follow_redirects=False)
        assert response.status_code in (302, 307)

    def test_new_repo_page_authenticated(self):
        _register_user()
        cookies = _login_user()
        response = client.get("/repo/new", cookies=cookies)
        assert response.status_code == 200

    @patch("main.REPOS_DIR", TEMP_REPOS_DIR)
    def test_create_repo_success(self):
        _register_user()
        cookies = _login_user()
        response = client.post(
            "/repo/new",
            data={"repo_name": "my-repo", "description": "test", "visibility": "public"},
            cookies=cookies,
            follow_redirects=False,
        )
        assert response.status_code == 302

    @patch("main.REPOS_DIR", TEMP_REPOS_DIR)
    def test_create_repo_invalid_name(self):
        _register_user()
        cookies = _login_user()
        response = client.post(
            "/repo/new",
            data={"repo_name": "bad name!", "description": "", "visibility": "public"},
            cookies=cookies,
        )
        # Re-renders the new repo form (template doesn't show error text)
        assert response.status_code == 200

    @patch("main.REPOS_DIR", TEMP_REPOS_DIR)
    def test_create_duplicate_repo(self):
        _register_user()
        cookies = _login_user()
        client.post(
            "/repo/new",
            data={"repo_name": "dup-repo", "description": "", "visibility": "public"},
            cookies=cookies,
            follow_redirects=False,
        )
        response = client.post(
            "/repo/new",
            data={"repo_name": "dup-repo", "description": "", "visibility": "public"},
            cookies=cookies,
        )
        # Re-renders the new repo form (template doesn't show error text)
        assert response.status_code == 200

    def test_create_repo_unauthenticated(self):
        response = client.post(
            "/repo/new",
            data={"repo_name": "repo", "description": "", "visibility": "public"},
            follow_redirects=False,
        )
        assert response.status_code in (302, 303)


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------


class TestSearch:
    @patch("main.REPOS_DIR", TEMP_REPOS_DIR)
    def test_search_no_query(self):
        response = client.get("/search")
        assert response.status_code == 200

    @patch("main.REPOS_DIR", TEMP_REPOS_DIR)
    def test_search_with_query(self):
        _register_user()
        cookies = _login_user()
        client.post(
            "/repo/new",
            data={"repo_name": "searchable", "description": "findme", "visibility": "public"},
            cookies=cookies,
            follow_redirects=False,
        )
        response = client.get("/search?q=searchable")
        assert response.status_code == 200


# ---------------------------------------------------------------------------
# User profile
# ---------------------------------------------------------------------------


class TestUserProfile:
    def test_existing_user_profile(self):
        _register_user()
        response = client.get("/testuser")
        assert response.status_code == 200

    def test_nonexistent_user_redirects(self):
        response = client.get("/nobody", follow_redirects=False)
        assert response.status_code in (302, 307)


# ---------------------------------------------------------------------------
# Star toggle
# ---------------------------------------------------------------------------


class TestStarToggle:
    @patch("main.REPOS_DIR", TEMP_REPOS_DIR)
    def test_star_unauthenticated(self):
        _register_user()
        cookies = _login_user()
        client.post(
            "/repo/new",
            data={"repo_name": "star-repo", "description": "", "visibility": "public"},
            cookies=cookies,
            follow_redirects=False,
        )
        response = client.post("/testuser/star-repo/star", follow_redirects=False)
        assert response.status_code == 303

    @patch("main.REPOS_DIR", TEMP_REPOS_DIR)
    def test_star_and_unstar(self):
        _register_user()
        cookies = _login_user()
        client.post(
            "/repo/new",
            data={"repo_name": "star-repo", "description": "", "visibility": "public"},
            cookies=cookies,
            follow_redirects=False,
        )
        # Star
        response = client.post("/testuser/star-repo/star", cookies=cookies, follow_redirects=False)
        assert response.status_code == 303
        # Unstar
        response = client.post("/testuser/star-repo/star", cookies=cookies, follow_redirects=False)
        assert response.status_code == 303

    def test_star_nonexistent_owner(self):
        _register_user()
        cookies = _login_user()
        response = client.post("/nobody/repo/star", cookies=cookies, follow_redirects=False)
        assert response.status_code == 303

    @patch("main.REPOS_DIR", TEMP_REPOS_DIR)
    def test_star_nonexistent_repo(self):
        _register_user()
        cookies = _login_user()
        response = client.post("/testuser/nonexistent/star", cookies=cookies, follow_redirects=False)
        assert response.status_code == 303


# ---------------------------------------------------------------------------
# Issues
# ---------------------------------------------------------------------------


class TestIssues:
    @patch("main.REPOS_DIR", TEMP_REPOS_DIR)
    def _setup_repo(self):
        _register_user()
        cookies = _login_user()
        client.post(
            "/repo/new",
            data={"repo_name": "issue-repo", "description": "", "visibility": "public"},
            cookies=cookies,
            follow_redirects=False,
        )
        return cookies

    @patch("main.REPOS_DIR", TEMP_REPOS_DIR)
    def test_issues_page(self):
        cookies = self._setup_repo()
        response = client.get("/testuser/issue-repo/issues", cookies=cookies)
        assert response.status_code == 200

    @patch("main.REPOS_DIR", TEMP_REPOS_DIR)
    def test_create_issue(self):
        cookies = self._setup_repo()
        response = client.post(
            "/testuser/issue-repo/issues/new",
            data={"title": "Bug", "description": "broken"},
            cookies=cookies,
            follow_redirects=False,
        )
        assert response.status_code == 302

    @patch("main.REPOS_DIR", TEMP_REPOS_DIR)
    def test_new_issue_page(self):
        cookies = self._setup_repo()
        response = client.get("/testuser/issue-repo/issues/new", cookies=cookies)
        assert response.status_code == 200

    def test_new_issue_unauthenticated(self):
        response = client.get("/testuser/issue-repo/issues/new", follow_redirects=False)
        assert response.status_code in (302, 307)

    @patch("main.REPOS_DIR", TEMP_REPOS_DIR)
    def test_issue_detail(self):
        cookies = self._setup_repo()
        client.post(
            "/testuser/issue-repo/issues/new",
            data={"title": "Detail Bug", "description": "details"},
            cookies=cookies,
            follow_redirects=False,
        )
        # Issue id should be 1
        response = client.get("/testuser/issue-repo/issues/1", cookies=cookies)
        assert response.status_code == 200

    @patch("main.REPOS_DIR", TEMP_REPOS_DIR)
    def test_add_comment(self):
        cookies = self._setup_repo()
        client.post(
            "/testuser/issue-repo/issues/new",
            data={"title": "Comment Bug", "description": ""},
            cookies=cookies,
            follow_redirects=False,
        )
        response = client.post(
            "/testuser/issue-repo/issues/1/comment",
            data={"content": "A comment"},
            cookies=cookies,
            follow_redirects=False,
        )
        assert response.status_code == 302

    @patch("main.REPOS_DIR", TEMP_REPOS_DIR)
    def test_close_issue(self):
        cookies = self._setup_repo()
        client.post(
            "/testuser/issue-repo/issues/new",
            data={"title": "Close Me", "description": ""},
            cookies=cookies,
            follow_redirects=False,
        )
        response = client.post(
            "/testuser/issue-repo/issues/1/close",
            cookies=cookies,
            follow_redirects=False,
        )
        assert response.status_code == 302

    @patch("main.REPOS_DIR", TEMP_REPOS_DIR)
    def test_view_closed_issues(self):
        cookies = self._setup_repo()
        client.post(
            "/testuser/issue-repo/issues/new",
            data={"title": "To Close", "description": ""},
            cookies=cookies,
            follow_redirects=False,
        )
        client.post(
            "/testuser/issue-repo/issues/1/close",
            cookies=cookies,
            follow_redirects=False,
        )
        response = client.get("/testuser/issue-repo/issues?state=closed", cookies=cookies)
        assert response.status_code == 200


# ---------------------------------------------------------------------------
# Repository detail / branches / commits / settings / delete
# ---------------------------------------------------------------------------


class TestRepoPages:
    @patch("main.REPOS_DIR", TEMP_REPOS_DIR)
    def _setup_repo(self):
        _register_user()
        cookies = _login_user()
        client.post(
            "/repo/new",
            data={"repo_name": "detail-repo", "description": "d", "visibility": "public"},
            cookies=cookies,
            follow_redirects=False,
        )
        return cookies

    @patch("main.REPOS_DIR", TEMP_REPOS_DIR)
    def test_repo_detail(self):
        cookies = self._setup_repo()
        response = client.get("/testuser/detail-repo", cookies=cookies)
        assert response.status_code == 200

    @patch("main.REPOS_DIR", TEMP_REPOS_DIR)
    def test_repo_branches(self):
        cookies = self._setup_repo()
        response = client.get("/testuser/detail-repo/branches", cookies=cookies)
        assert response.status_code == 200

    @patch("main.REPOS_DIR", TEMP_REPOS_DIR)
    def test_repo_commits(self):
        cookies = self._setup_repo()
        response = client.get("/testuser/detail-repo/commits", cookies=cookies)
        assert response.status_code == 200

    @patch("main.REPOS_DIR", TEMP_REPOS_DIR)
    def test_repo_settings_owner(self):
        cookies = self._setup_repo()
        response = client.get("/testuser/detail-repo/settings", cookies=cookies)
        assert response.status_code == 200

    @patch("main.REPOS_DIR", TEMP_REPOS_DIR)
    def test_repo_settings_non_owner(self):
        self._setup_repo()
        _register_user(username="other", email="other@example.com")
        other_cookies = _login_user(username="other")
        response = client.get("/testuser/detail-repo/settings", cookies=other_cookies, follow_redirects=False)
        assert response.status_code == 303

    @patch("main.REPOS_DIR", TEMP_REPOS_DIR)
    def test_delete_repo(self):
        cookies = self._setup_repo()
        response = client.post("/testuser/detail-repo/delete", cookies=cookies, follow_redirects=False)
        assert response.status_code == 303
        assert "/dashboard" in response.headers["location"]

    def test_repo_detail_nonexistent_user(self):
        response = client.get("/nobody/norepo")
        assert response.status_code == 200  # renders error template

    @patch("main.REPOS_DIR", TEMP_REPOS_DIR)
    def test_private_repo_hidden_from_others(self):
        _register_user()
        cookies = _login_user()
        client.post(
            "/repo/new",
            data={"repo_name": "private-repo", "description": "", "visibility": "private"},
            cookies=cookies,
            follow_redirects=False,
        )
        # Clear session cookies so next request is unauthenticated
        client.cookies.clear()
        response = client.get("/testuser/private-repo")
        assert response.status_code == 200
        assert "Repository not found" in response.text
