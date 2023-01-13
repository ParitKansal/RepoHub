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

def get_repo_commits(repo_path: str, limit: int = 20) -> list:
    if is_repo_empty(repo_path):
        return []
        
    try:
        result = subprocess.run(
            ["git", "log", "--all", f"-n {limit}", "--pretty=format:%H|%an|%ar|%s"],
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

def get_repo_files(repo_path: str) -> list:
    if is_repo_empty(repo_path):
        return []
        
    try:
        # Get the latest commit hash from any branch
        result_hash = subprocess.run(
            ["git", "rev-list", "-n", "1", "--all"],
            cwd=repo_path,
            check=True,
            capture_output=True,
            text=True
        )
        latest_hash = result_hash.stdout.strip()
        
        result = subprocess.run(
            ["git", "ls-tree", latest_hash, "--name-only"],
            cwd=repo_path,
            check=True,
            capture_output=True,
            text=True
        )
        files = [f for f in result.stdout.strip().split('\n') if f]
        return files
    except subprocess.CalledProcessError:
        return []

def get_file_content(repo_path: str, filepath: str) -> str:
    try:
        # Get the latest commit hash from any branch
        result_hash = subprocess.run(
            ["git", "rev-list", "-n", "1", "--all"],
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
