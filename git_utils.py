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
