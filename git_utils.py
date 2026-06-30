import subprocess
import os

def create_bare_repo(repos_dir: str, username: str, repo_name: str) -> bool:
    """
    Creates a bare git repository at repos_dir/username/repo_name.git
    """
    user_dir = os.path.join(repos_dir, username)
    os.makedirs(user_dir, exist_ok=True)
    
    repo_path = os.path.join(user_dir, f"{repo_name}.git")
    
    try:
        # Run git init --bare
        result = subprocess.run(
            ["git", "init", "--bare", repo_path],
            check=True,
            capture_output=True,
            text=True
        )
        return True
    except subprocess.CalledProcessError as e:
        print(f"Error creating git repo: {e.stderr}")
        return False

def get_branches(repo_path: str) -> list:
    if is_repo_empty(repo_path):
        return []
    try:
        result = subprocess.run(
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
    except subprocess.CalledProcessError:
        return []

def is_repo_empty(repo_path: str) -> bool:
    try:
        result = subprocess.run(
            ["git", "rev-list", "-n", "1", "--all"],
            cwd=repo_path,
            check=True,
            capture_output=True,
            text=True
        )
        return len(result.stdout.strip()) == 0
    except subprocess.CalledProcessError:
        return True

def get_repo_commits(repo_path: str, limit: int = 20, branch: str = "main") -> list:
    if is_repo_empty(repo_path):
        return []
        
    try:
        result = subprocess.run(
            ["git", "log", branch, "-n", str(limit), "--pretty=format:%H|%an|%ar|%s"],
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
    except subprocess.CalledProcessError:
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

def get_commit_details(repo_path: str, commit_hash: str) -> dict:
    """
    Retrieves the metadata and the raw diff for a specific commit.
    """
    if not os.path.exists(repo_path):
        return None
        
    try:
        # Get metadata
        meta_result = subprocess.run(
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
        
        # Get diff patch
        diff_result = subprocess.run(
            ["git", "show", commit_hash, "--pretty=format:", "--patch"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            check=True
        )
        diff_text = diff_result.stdout.strip()
        diff_files = parse_diff(diff_text)
        
        return {
            "hash": commit_hash,
            "author": author,
            "date": date,
            "message": message,
            "diff_files": diff_files
        }
    except subprocess.CalledProcessError:
        return None

def get_repo_files(repo_path: str, branch: str = "main") -> list:
    if is_repo_empty(repo_path):
        return []
        
    try:
        # Get the latest commit hash from the specific branch
        result_hash = subprocess.run(
            ["git", "rev-parse", branch],
            cwd=repo_path,
            check=True,
            capture_output=True,
            text=True
        )
        latest_hash = result_hash.stdout.strip()
        
        result = subprocess.run(
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
        # Sort files: directories (trees) first, then blobs
        files.sort(key=lambda x: (x["type"] != "tree", x["name"]))
        return files
    except subprocess.CalledProcessError:
        return []

def get_file_content(repo_path: str, filepath: str, branch: str = "main") -> str:
    try:
        # Get the latest commit hash from the specific branch
        result_hash = subprocess.run(
            ["git", "rev-parse", branch],
            cwd=repo_path,
            check=True,
            capture_output=True,
            text=True
        )
        latest_hash = result_hash.stdout.strip()

        result = subprocess.run(
            ["git", "show", f"{latest_hash}:{filepath}"],
            cwd=repo_path,
            check=True,
            capture_output=True,
            text=True
        )
        return result.stdout
    except subprocess.CalledProcessError:
        return None

def get_contributors(repo_path: str) -> list:
    if is_repo_empty(repo_path):
        return []
    try:
        result = subprocess.run(
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
    except subprocess.CalledProcessError:
        return []

def get_branch_diff(repo_path: str, target_branch: str, source_branch: str) -> list:
    """
    Returns the diff files between target_branch and source_branch
    """
    try:
        result = subprocess.run(
            ["git", "diff", f"{target_branch}...{source_branch}", "--patch"],
            cwd=repo_path,
            check=True,
            capture_output=True,
            text=True
        )
        return parse_diff(result.stdout)
    except subprocess.CalledProcessError:
        return []

def get_commit_graph(repo_path: str, branch: str = "__all__", limit: int = 80) -> list:
    if is_repo_empty(repo_path):
        return []
    try:
        if branch == "__all__":
            # List main/master first so it always occupies lane 0 in topo-order.
            # Fall back to --all if neither exists.
            all_branches = get_branches(repo_path)
            if "main" in all_branches:
                ordered = ["main"] + [b for b in all_branches if b != "main"]
            elif "master" in all_branches:
                ordered = ["master"] + [b for b in all_branches if b != "master"]
            else:
                ordered = all_branches
            log_args = ["git", "log"] + ordered + ["-n", str(limit), "--pretty=format:%H|%P|%an|%ar|%s", "--topo-order"]
        else:
            log_args = ["git", "log", branch, "-n", str(limit), "--pretty=format:%H|%P|%an|%ar|%s", "--topo-order"]
        result = subprocess.run(log_args, cwd=repo_path, check=True, capture_output=True, text=True)
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
    except subprocess.CalledProcessError:
        return []

def get_branch_tips(repo_path: str) -> dict:
    if is_repo_empty(repo_path):
        return {}
    try:
        # git show-ref --heads always outputs full 40-char hashes
        result = subprocess.run(
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
    except subprocess.CalledProcessError:
        return {}

def merge_branches(repo_path: str, target_branch: str, source_branch: str, author_name: str, author_email: str) -> bool:
    """
    Attempts to merge source_branch into target_branch.
    Returns True if successful, False if there are conflicts.
    """
    import tempfile
    import shutil
    
    temp_dir = tempfile.mkdtemp()
    abs_repo_path = os.path.abspath(repo_path)
    try:
        # Clone the bare repo to a temp directory
        subprocess.run(["git", "clone", abs_repo_path, "."], cwd=temp_dir, check=True, capture_output=True)
        
        # Configure local git user for the merge commit
        subprocess.run(["git", "config", "user.name", author_name], cwd=temp_dir, check=True)
        subprocess.run(["git", "config", "user.email", author_email], cwd=temp_dir, check=True)
        
        # Checkout target branch
        subprocess.run(["git", "checkout", target_branch], cwd=temp_dir, check=True, capture_output=True)
        
        # Attempt to merge source branch
        merge_result = subprocess.run(
            ["git", "merge", f"origin/{source_branch}", "--no-ff", "-m", f"Merge branch '{source_branch}' into {target_branch}"],
            cwd=temp_dir,
            capture_output=True,
            text=True
        )
        
        if merge_result.returncode != 0:
            # Merge conflict occurred
            return False
            
        # Push the merged branch back to the bare repo
        subprocess.run(["git", "push", "origin", target_branch], cwd=temp_dir, check=True, capture_output=True)
        return True
    except Exception as e:
        print(f"Merge error: {e}")
        return False
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
