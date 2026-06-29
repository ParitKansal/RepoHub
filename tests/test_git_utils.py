import os
import subprocess
import tempfile
import shutil

import pytest

import git_utils


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def temp_dir():
    """Provide a temporary directory that is cleaned up after the test."""
    d = tempfile.mkdtemp()
    yield d
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture()
def bare_repo(temp_dir):
    """Create a bare git repo on disk and return its path."""
    repo_path = os.path.join(temp_dir, "user", "repo.git")
    git_utils.create_bare_repo(temp_dir, "user", "repo")
    return repo_path


@pytest.fixture()
def populated_repo(bare_repo, temp_dir):
    """Clone the bare repo, add a commit, push, and return the bare repo path."""
    clone_dir = os.path.join(temp_dir, "clone")
    subprocess.run(["git", "clone", bare_repo, clone_dir], check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=clone_dir, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=clone_dir, check=True, capture_output=True)

    # Create a file and commit
    with open(os.path.join(clone_dir, "README.md"), "w") as f:
        f.write("# Hello\n")
    subprocess.run(["git", "add", "."], cwd=clone_dir, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=clone_dir, check=True, capture_output=True)

    # Rename default branch to main and push
    subprocess.run(["git", "branch", "-M", "main"], cwd=clone_dir, check=True, capture_output=True)
    subprocess.run(["git", "push", "-u", "origin", "main"], cwd=clone_dir, check=True, capture_output=True)

    return bare_repo, clone_dir


# ---------------------------------------------------------------------------
# Tests for create_bare_repo
# ---------------------------------------------------------------------------

class TestCreateBareRepo:
    def test_creates_directory(self, temp_dir):
        result = git_utils.create_bare_repo(temp_dir, "alice", "my-project")
        assert result is True
        repo_path = os.path.join(temp_dir, "alice", "my-project.git")
        assert os.path.isdir(repo_path)

    def test_is_bare_repository(self, temp_dir):
        git_utils.create_bare_repo(temp_dir, "alice", "my-project")
        repo_path = os.path.join(temp_dir, "alice", "my-project.git")
        r = subprocess.run(
            ["git", "rev-parse", "--is-bare-repository"],
            cwd=repo_path, capture_output=True, text=True,
        )
        assert r.stdout.strip() == "true"

    def test_creates_user_dir_if_missing(self, temp_dir):
        git_utils.create_bare_repo(temp_dir, "newuser", "repo")
        assert os.path.isdir(os.path.join(temp_dir, "newuser"))


# ---------------------------------------------------------------------------
# Tests for is_repo_empty
# ---------------------------------------------------------------------------

class TestIsRepoEmpty:
    def test_empty_bare_repo(self, bare_repo):
        assert git_utils.is_repo_empty(bare_repo) is True

    def test_non_empty_repo(self, populated_repo):
        bare_path, _ = populated_repo
        assert git_utils.is_repo_empty(bare_path) is False

    def test_nonexistent_path(self, temp_dir):
        # subprocess.run raises FileNotFoundError when cwd doesn't exist
        with pytest.raises(FileNotFoundError):
            git_utils.is_repo_empty(os.path.join(temp_dir, "nope"))


# ---------------------------------------------------------------------------
# Tests for get_branches
# ---------------------------------------------------------------------------

class TestGetBranches:
    def test_empty_repo_returns_empty(self, bare_repo):
        assert git_utils.get_branches(bare_repo) == []

    def test_returns_main_branch(self, populated_repo):
        bare_path, _ = populated_repo
        branches = git_utils.get_branches(bare_path)
        assert "main" in branches

    def test_multiple_branches(self, populated_repo):
        bare_path, clone_dir = populated_repo
        subprocess.run(["git", "checkout", "-b", "feature"], cwd=clone_dir, check=True, capture_output=True)
        subprocess.run(["git", "push", "origin", "feature"], cwd=clone_dir, check=True, capture_output=True)
        branches = git_utils.get_branches(bare_path)
        assert "main" in branches
        assert "feature" in branches


# ---------------------------------------------------------------------------
# Tests for get_repo_commits
# ---------------------------------------------------------------------------

class TestGetRepoCommits:
    def test_empty_repo_returns_empty(self, bare_repo):
        assert git_utils.get_repo_commits(bare_repo) == []

    def test_returns_commits(self, populated_repo):
        bare_path, _ = populated_repo
        commits = git_utils.get_repo_commits(bare_path, branch="main")
        assert len(commits) >= 1
        assert commits[0]["message"] == "Initial commit"
        assert "hash" in commits[0]
        assert "author" in commits[0]

    def test_limit_parameter(self, populated_repo):
        bare_path, clone_dir = populated_repo
        # Add a second commit
        with open(os.path.join(clone_dir, "file2.txt"), "w") as f:
            f.write("content")
        subprocess.run(["git", "add", "."], cwd=clone_dir, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "Second commit"], cwd=clone_dir, check=True, capture_output=True)
        subprocess.run(["git", "push"], cwd=clone_dir, check=True, capture_output=True)

        commits = git_utils.get_repo_commits(bare_path, limit=1, branch="main")
        assert len(commits) == 1


# ---------------------------------------------------------------------------
# Tests for get_repo_files
# ---------------------------------------------------------------------------

class TestGetRepoFiles:
    def test_empty_repo_returns_empty(self, bare_repo):
        assert git_utils.get_repo_files(bare_repo) == []

    def test_returns_files(self, populated_repo):
        bare_path, _ = populated_repo
        files = git_utils.get_repo_files(bare_path, branch="main")
        assert len(files) >= 1
        names = [f["name"] for f in files]
        assert "README.md" in names

    def test_file_has_required_keys(self, populated_repo):
        bare_path, _ = populated_repo
        files = git_utils.get_repo_files(bare_path, branch="main")
        for f in files:
            assert "mode" in f
            assert "type" in f
            assert "hash" in f
            assert "name" in f


# ---------------------------------------------------------------------------
# Tests for get_file_content
# ---------------------------------------------------------------------------

class TestGetFileContent:
    def test_returns_file_content(self, populated_repo):
        bare_path, _ = populated_repo
        content = git_utils.get_file_content(bare_path, "README.md", branch="main")
        assert content is not None
        assert "# Hello" in content

    def test_nonexistent_file_returns_none(self, populated_repo):
        bare_path, _ = populated_repo
        content = git_utils.get_file_content(bare_path, "nope.txt", branch="main")
        assert content is None


# ---------------------------------------------------------------------------
# Tests for get_contributors
# ---------------------------------------------------------------------------

class TestGetContributors:
    def test_empty_repo_returns_empty(self, bare_repo):
        assert git_utils.get_contributors(bare_repo) == []

    def test_returns_contributors(self, populated_repo):
        bare_path, _ = populated_repo
        contributors = git_utils.get_contributors(bare_path)
        assert len(contributors) >= 1
        assert contributors[0]["name"] == "Test"
        assert contributors[0]["commits"] >= 1


# ---------------------------------------------------------------------------
# Tests for parse_diff
# ---------------------------------------------------------------------------

class TestParseDiff:
    def test_empty_string(self):
        assert git_utils.parse_diff("") == []

    def test_none_input(self):
        assert git_utils.parse_diff(None) == []

    def test_single_file_diff(self):
        diff = (
            "diff --git a/file.txt b/file.txt\n"
            "index abc..def 100644\n"
            "--- a/file.txt\n"
            "+++ b/file.txt\n"
            "@@ -1 +1 @@\n"
            "-old line\n"
            "+new line"
        )
        result = git_utils.parse_diff(diff)
        assert len(result) == 1
        assert result[0]["name"] == "file.txt"
        assert len(result[0]["lines"]) > 0

    def test_multiple_files(self):
        diff = (
            "diff --git a/a.txt b/a.txt\n"
            "+line a\n"
            "diff --git a/b.txt b/b.txt\n"
            "+line b"
        )
        result = git_utils.parse_diff(diff)
        assert len(result) == 2
        assert result[0]["name"] == "a.txt"
        assert result[1]["name"] == "b.txt"


# ---------------------------------------------------------------------------
# Tests for get_commit_details
# ---------------------------------------------------------------------------

class TestGetCommitDetails:
    def test_nonexistent_repo(self, temp_dir):
        result = git_utils.get_commit_details(os.path.join(temp_dir, "nope"), "abc123")
        assert result is None

    def test_returns_commit_details(self, populated_repo):
        bare_path, _ = populated_repo
        commits = git_utils.get_repo_commits(bare_path, branch="main")
        commit_hash = commits[0]["hash"]
        details = git_utils.get_commit_details(bare_path, commit_hash)
        assert details is not None
        assert details["hash"] == commit_hash
        assert details["message"] == "Initial commit"
        assert "author" in details
        assert "date" in details
        assert "diff_files" in details

    def test_invalid_hash(self, populated_repo):
        bare_path, _ = populated_repo
        result = git_utils.get_commit_details(bare_path, "0000000000000000000000000000000000000000")
        assert result is None
