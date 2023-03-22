import subprocess
import os
import asyncio
import shutil


def _run(*args, **kwargs):
    kwargs.setdefault('timeout', 30)
    return subprocess.run(*args, **kwargs)


def _write_hook(hook_path: str, content: str):
    with open(hook_path, "w") as f:
        f.write(content)
    os.chmod(hook_path, 0o755)


async def create_bare_repo(repos_dir: str, username: str, repo_name: str) -> bool:
    # 1. Disk Quota Check (require at least 1GB free space)
    try:
        total, used, free = shutil.disk_usage(repos_dir)
        if free < 1024 * 1024 * 1024:  # 1 GB in bytes
            print(f"Error: Insufficient disk space on {repos_dir} (Free: {free / (1024**3):.2f} GB)")
            return False
    except Exception as e:
        print(f"Warning: Could not check disk space: {e}")

    user_dir = os.path.join(repos_dir, username)
    os.makedirs(user_dir, exist_ok=True)
    repo_path = os.path.join(user_dir, f"{repo_name}.git")
    try:
        await asyncio.to_thread(
            _run,
            ["git", "init", "--bare", repo_path],
            check=True,
            capture_output=True,
            text=True
        )

        # 2. Setup pre-receive hook to enforce a 100MB repository size limit
        hooks_dir = os.path.join(repo_path, "hooks")
        os.makedirs(hooks_dir, exist_ok=True)
        hook_path = os.path.join(hooks_dir, "pre-receive")
        
        hook_content = """#!/bin/bash
# Enforce repository size limit of 100MB
MAX_SIZE_KB=102400
CURRENT_SIZE_KB=$(du -sk . | cut -f1)

if [ "$CURRENT_SIZE_KB" -gt "$MAX_SIZE_KB" ]; then
    echo "======================================================="
    echo "ERROR: Push rejected!"
    echo "Repository size limit of 100MB exceeded."
    echo "Current size: $((CURRENT_SIZE_KB / 1024))MB."
    echo "======================================================="
    exit 1
fi
"""
        await asyncio.to_thread(_write_hook, hook_path, hook_content)
        return True
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
        print(f"Error creating git repo: {e}")
        return False
    except Exception as e:
        print(f"Error setting up git hooks: {e}")
        return False


async def is_repo_empty(repo_path: str) -> bool:
    try:
        result = await asyncio.to_thread(
            _run,
            ["git", "rev-list", "-n", "1", "--all"],
            cwd=repo_path,
            check=True,
            capture_output=True,
            text=True
        )
        return len(result.stdout.strip()) == 0
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return True


async def get_branches(repo_path: str) -> list:
    if await is_repo_empty(repo_path):
        return []
    try:
        result = await asyncio.to_thread(
            _run,
            ["git", "branch", "--format=%(refname:short)"],
            cwd=repo_path,
            check=True,
            capture_output=True,
            text=True
        )
        branches = [b.strip() for b in result.stdout.strip().split('\n') if b.strip()]
        priority = {'main': 0, 'master': 1}
        branches.sort(key=lambda b: (priority.get(b, 2), b))
        return branches
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return []


async def get_repo_commits(repo_path: str, limit: int = 20, branch: str = "main", skip: int = 0) -> list:
    if await is_repo_empty(repo_path):
        return []
    try:
        result = await asyncio.to_thread(
            _run,
            ["git", "log", branch, f"--skip={skip}", "-n", str(limit), "--pretty=format:%H|%an|%ar|%s"],
            cwd=repo_path,
            check=True,
            capture_output=True,
            text=True
        )
        commits = []
        for line in result.stdout.strip().split('\n'):
            if line:
                parts = line.split('|', 3)
                if len(parts) == 4:
                    commits.append({
                        "hash": parts[0],
                        "author": parts[1],
                        "time_ago": parts[2],
                        "message": parts[3]
                    })
        return commits
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return []


def parse_diff(diff_text: str) -> list:
    if not diff_text:
        return []
    files = []
    current_file = None
    for line in diff_text.split('\n'):
        if line.startswith('diff --git'):
            if current_file:
                files.append(current_file)
            parts = line.split(' ')
            filename = parts[-1][2:] if len(parts) >= 4 else "unknown"
            current_file = {"name": filename, "lines": []}
        elif current_file is not None:
            current_file["lines"].append(line)
    if current_file:
        files.append(current_file)
    return files


async def get_commit_details(repo_path: str, commit_hash: str) -> dict:
    if not os.path.exists(repo_path):
        return None
    try:
        meta_result = await asyncio.to_thread(
            _run,
            ["git", "show", commit_hash, "-s", "--format=%an|%ad|%s"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            check=True
        )
        parts = meta_result.stdout.strip().split("|", 2)
        if len(parts) != 3:
            return None
        author, date, message = parts

        diff_result = await asyncio.to_thread(
            _run,
            ["git", "show", commit_hash, "--pretty=format:", "--patch"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            check=True
        )
        diff_files = parse_diff(diff_result.stdout.strip())

        return {
            "hash": commit_hash,
            "author": author,
            "date": date,
            "message": message,
            "diff_files": diff_files
        }
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return None


async def get_repo_files(repo_path: str, branch: str = "main") -> list:
    if await is_repo_empty(repo_path):
        return []
    try:
        result_hash = await asyncio.to_thread(
            _run,
            ["git", "rev-parse", branch],
            cwd=repo_path,
            check=True,
            capture_output=True,
            text=True
        )
        latest_hash = result_hash.stdout.strip()

        result = await asyncio.to_thread(
            _run,
            ["git", "ls-tree", latest_hash],
            cwd=repo_path,
            check=True,
            capture_output=True,
            text=True
        )
        files = []
        for line in result.stdout.strip().split('\n'):
            if line:
                parts = line.split(maxsplit=3)
                if len(parts) == 4:
                    files.append({
                        "mode": parts[0],
                        "type": parts[1],
                        "hash": parts[2],
                        "name": parts[3]
                    })
        files.sort(key=lambda x: (x["type"] != "tree", x["name"]))
        return files
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return []


async def get_file_content(repo_path: str, filepath: str, branch: str = "main") -> str:
    try:
        result_hash = await asyncio.to_thread(
            _run,
            ["git", "rev-parse", branch],
            cwd=repo_path,
            check=True,
            capture_output=True,
            text=True
        )
        latest_hash = result_hash.stdout.strip()

        result = await asyncio.to_thread(
            _run,
            ["git", "show", f"{latest_hash}:{filepath}"],
            cwd=repo_path,
            check=True,
            capture_output=True,
            text=True
        )
        return result.stdout
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return None


async def get_contributors(repo_path: str) -> list:
    if await is_repo_empty(repo_path):
        return []
    try:
        result = await asyncio.to_thread(
            _run,
            ["git", "shortlog", "-sn", "--all"],
            cwd=repo_path,
            check=True,
            capture_output=True,
            text=True
        )
        contributors = []
        for line in result.stdout.strip().split('\n'):
            if line:
                parts = line.strip().split('\t', 1)
                if len(parts) == 2:
                    contributors.append({
                        "commits": int(parts[0]),
                        "name": parts[1]
                    })
        return contributors
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return []


async def get_branch_diff(repo_path: str, target_branch: str, source_branch: str) -> list:
    try:
        result = await asyncio.to_thread(
            _run,
            ["git", "diff", f"{target_branch}...{source_branch}", "--patch"],
            cwd=repo_path,
            check=True,
            capture_output=True,
            text=True
        )
        return parse_diff(result.stdout)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return []


async def get_commit_graph(repo_path: str, branch: str = "__all__", limit: int = 80) -> list:
    if await is_repo_empty(repo_path):
        return []
    try:
        if branch == "__all__":
            all_branches = await get_branches(repo_path)
            if "main" in all_branches:
                ordered = ["main"] + [b for b in all_branches if b != "main"]
            elif "master" in all_branches:
                ordered = ["master"] + [b for b in all_branches if b != "master"]
            else:
                ordered = all_branches
            log_args = ["git", "log"] + ordered + ["-n", str(limit), "--pretty=format:%H|%P|%an|%ar|%s", "--topo-order"]
        else:
            log_args = ["git", "log", branch, "-n", str(limit), "--pretty=format:%H|%P|%an|%ar|%s", "--topo-order"]

        result = await asyncio.to_thread(_run, log_args, cwd=repo_path, check=True, capture_output=True, text=True)
        commits = []
        for line in result.stdout.strip().split('\n'):
            if not line:
                continue
            parts = line.split('|', 4)
            if len(parts) < 5:
                continue
            full_hash, parents_raw, author, time_ago, message = parts
            parents = [p for p in parents_raw.split(' ') if p]
            commits.append({
                "hash": full_hash,
                "short_hash": full_hash[:7],
                "parents": parents,
                "author": author,
                "time_ago": time_ago,
                "message": message
            })
        return commits
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return []


async def get_branch_tips(repo_path: str) -> dict:
    if await is_repo_empty(repo_path):
        return {}
    try:
        result = await asyncio.to_thread(
            _run,
            ["git", "show-ref", "--heads"],
            cwd=repo_path, check=True, capture_output=True, text=True
        )
        tips = {}
        for line in result.stdout.strip().split('\n'):
            if ' ' in line:
                commit_hash, ref = line.split(' ', 1)
                name = ref.strip().replace('refs/heads/', '')
                tips[name] = commit_hash.strip()
        return tips
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return {}


async def merge_branches(repo_path: str, target_branch: str, source_branch: str, author_name: str, author_email: str) -> bool:
    import tempfile
    import shutil

    temp_dir = tempfile.mkdtemp()
    abs_repo_path = os.path.abspath(repo_path)
    try:
        clone_res = await asyncio.to_thread(_run, ["git", "clone", abs_repo_path, "."], cwd=temp_dir, capture_output=True, text=True)
        if clone_res.returncode != 0:
            print(f"Merge error (clone failed): {clone_res.stderr}")
            return False

        await asyncio.to_thread(_run, ["git", "config", "user.name", author_name], cwd=temp_dir, check=True)
        await asyncio.to_thread(_run, ["git", "config", "user.email", author_email], cwd=temp_dir, check=True)

        checkout_res = await asyncio.to_thread(_run, ["git", "checkout", target_branch], cwd=temp_dir, capture_output=True, text=True)
        if checkout_res.returncode != 0:
            print(f"Merge error (checkout failed): {checkout_res.stderr}")
            return False

        merge_result = await asyncio.to_thread(
            _run,
            ["git", "merge", f"origin/{source_branch}", "--no-ff", "-m",
             f"Merge branch '{source_branch}' into {target_branch}"],
            cwd=temp_dir,
            capture_output=True,
            text=True
        )
        if merge_result.returncode != 0:
            print(f"Merge error (merge failed): {merge_result.stderr}\nStdout: {merge_result.stdout}")
            return False

        push_res = await asyncio.to_thread(_run, ["git", "push", "origin", target_branch], cwd=temp_dir, capture_output=True, text=True)
        if push_res.returncode != 0:
            print(f"Merge error (push failed): {push_res.stderr}")
            return False

        return True
    except Exception as e:
        print(f"Merge error (exception): {e}")
        return False
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
