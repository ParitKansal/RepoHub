import os
import subprocess
import shutil

# Configuration
REPO_URL = "https://parit-gitclone.duckdns.org:8443/repos/parit/project_1.git"
USERNAME = "parit"
PASSWORD = "Complex@123"
# URL encode the '@' in the password for the git remote URL
ENCODED_PASSWORD = PASSWORD.replace("@", "%40")
AUTH_REPO_URL = f"https://{USERNAME}:{ENCODED_PASSWORD}@parit-gitclone.duckdns.org:8443/repos/parit/project_1.git"

DEMO_DIR = "/Users/xelpmoc/Desktop/Projects/GitClone/scratch/demo_repo"

def run_git(args, cwd=None):
    # Disable SSL verification since we are using a self-signed/duckdns setup that might trigger warnings locally
    cmd = ["git", "-c", "http.sslVerify=false"] + args
    print(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Error: {result.stderr}")
    else:
        print(f"Success: {result.stdout.strip()}")
    return result

def main():
    # Clean up old demo dir if it exists
    if os.path.exists(DEMO_DIR):
        shutil.rmtree(DEMO_DIR)
    os.makedirs(DEMO_DIR, exist_ok=True)

    print("--- 1. Initializing Local Repo ---")
    run_git(["init"], cwd=DEMO_DIR)
    run_git(["config", "user.name", "Parit Kansal"], cwd=DEMO_DIR)
    run_git(["config", "user.email", "paritkansal121@gmail.com"], cwd=DEMO_DIR)

    print("\n--- 2. Creating Initial Commit on 'main' ---")
    readme_path = os.path.join(DEMO_DIR, "README.md")
    with open(readme_path, "w") as f:
        f.write("# Project 1\n\nThis is a demo repository to test our custom Git hosting server.\n")
    
    run_git(["add", "README.md"], cwd=DEMO_DIR)
    run_git(["commit", "-m", "Initial commit: Add README.md"], cwd=DEMO_DIR)
    run_git(["branch", "-M", "main"], cwd=DEMO_DIR)

    print("\n--- 3. Adding Remote and Pushing 'main' ---")
    run_git(["remote", "add", "origin", AUTH_REPO_URL], cwd=DEMO_DIR)
    run_git(["push", "-u", "origin", "main"], cwd=DEMO_DIR)

    print("\n--- 4. Creating 'feature/auth' branch ---")
    run_git(["checkout", "-b", "feature/auth"], cwd=DEMO_DIR)
    auth_path = os.path.join(DEMO_DIR, "auth.py")
    with open(auth_path, "w") as f:
        f.write("def login(username, password):\n    print(f'Logging in user: {username}')\n    return True\n")
    
    run_git(["add", "auth.py"], cwd=DEMO_DIR)
    run_git(["commit", "-m", "Add basic authentication logic"], cwd=DEMO_DIR)
    run_git(["push", "-u", "origin", "feature/auth"], cwd=DEMO_DIR)

    print("\n--- 5. Creating 'bugfix/styles' branch with modifications ---")
    # Go back to main first
    run_git(["checkout", "main"], cwd=DEMO_DIR)
    run_git(["checkout", "-b", "bugfix/styles"], cwd=DEMO_DIR)
    
    # Modify README (Simulate insertions/deletions)
    with open(readme_path, "r") as f:
        content = f.read()
    
    # Replace some text
    new_content = content.replace(
        "This is a demo repository to test our custom Git hosting server.",
        "This repository showcases our premium, custom-built Git server running on Google Cloud.\n\n## Features\n- Ultra-fast git push/pull\n- Automated backups\n- Built-in security hooks"
    )
    with open(readme_path, "w") as f:
        f.write(new_content)

    run_git(["add", "README.md"], cwd=DEMO_DIR)
    run_git(["commit", "-m", "Update README with feature list and description"], cwd=DEMO_DIR)
    run_git(["push", "-u", "origin", "bugfix/styles"], cwd=DEMO_DIR)

    print("\n--- 6. Creating 'feature/database' branch ---")
    run_git(["checkout", "main"], cwd=DEMO_DIR)
    run_git(["checkout", "-b", "feature/database"], cwd=DEMO_DIR)
    db_path = os.path.join(DEMO_DIR, "db.py")
    with open(db_path, "w") as f:
        f.write("def connect_db():\n    print('Connecting to PostgreSQL database...')\n    return None\n")
    
    run_git(["add", "db.py"], cwd=DEMO_DIR)
    run_git(["commit", "-m", "Add database connection module"], cwd=DEMO_DIR)
    run_git(["push", "-u", "origin", "feature/database"], cwd=DEMO_DIR)

    print("\n--- Demo Git Activity Completed! ---")

if __name__ == "__main__":
    main()
