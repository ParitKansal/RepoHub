import os
import subprocess
import shutil
import random
import httpx

# Configuration
BASE_URL = "https://parit-gitclone.duckdns.org:8443"
REPO_NAME = "project_1"
USERNAME = "parit"
PASSWORD = "Complex@123"

ENCODED_PASSWORD = PASSWORD.replace("@", "%40")
AUTH_REPO_URL = f"{BASE_URL.replace('https://', f'https://{USERNAME}:{ENCODED_PASSWORD}@')}/repos/{USERNAME}/{REPO_NAME}.git"
DEMO_DIR = "/Users/xelpmoc/Desktop/Projects/GitClone/scratch/complex_repo"

def create_repo_on_server():
    print("--- 1. Creating 'complex_project' on the server via Web API ---")
    client = httpx.Client(verify=False)  # Ignore self-signed SSL warning
    
    # Get CSRF token first by visiting login page
    r = client.get(f"{BASE_URL}/login")
    csrf_token = client.cookies.get("csrftoken", "")
    
    # Log in
    login_data = {
        "username": USERNAME,
        "password": PASSWORD,
        "csrf_token": csrf_token
    }
    r = client.post(f"{BASE_URL}/login", data=login_data)
    if r.status_code != 200 and "dashboard" not in r.text:
        print("Failed to log in to server")
        return False
    
    # Create new repository
    csrf_token = client.cookies.get("csrftoken", "")
    repo_data = {
        "repo_name": REPO_NAME,
        "description": "A highly complex project with 100+ commits and multiple branches to showcase the Git network graph.",
        "visibility": "public",
        "csrf_token": csrf_token
    }
    r = client.post(f"{BASE_URL}/repo/new", data=repo_data, follow_redirects=True)
    if REPO_NAME in r.text or r.status_code == 200:
        print(f"Successfully created repository '{REPO_NAME}' on the server!")
        return True
    else:
        print("Failed to create repository on server")
        return False

def run_git(args, cwd=None):
    cmd = ["git", "-c", "http.sslVerify=false"] + args
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    return result

def main():
    # Create the repository on the server first
    if not create_repo_on_server():
        # If it already exists, we can still proceed
        print("Repository might already exist, proceeding to push...")

    # Clean up local directory
    if os.path.exists(DEMO_DIR):
        shutil.rmtree(DEMO_DIR)
    os.makedirs(DEMO_DIR, exist_ok=True)

    # Initialize local repo
    run_git(["init"], cwd=DEMO_DIR)
    run_git(["config", "user.name", "Parit Kansal"], cwd=DEMO_DIR)
    run_git(["config", "user.email", "paritkansal121@gmail.com"], cwd=DEMO_DIR)
    run_git(["remote", "add", "origin", AUTH_REPO_URL], cwd=DEMO_DIR)

    print("\n--- 2. Generating 100+ Commits across 8 Branches ---")
    
    # List of files we will modify
    files = ["main.py", "utils.js", "styles.css", "index.html", "config.json", "docs.md"]
    for f in files:
        with open(os.path.join(DEMO_DIR, f), "w") as file_obj:
            file_obj.write(f"# Initial {f}\n")
    
    run_git(["add", "."], cwd=DEMO_DIR)
    run_git(["commit", "-m", "Initial commit: Set up project structure"], cwd=DEMO_DIR)
    run_git(["branch", "-M", "main"], cwd=DEMO_DIR)

    # We will maintain active branches
    branches = ["main"]
    active_branch = "main"

    # Define some feature branches we will create
    feature_branches = [
        "feature/login-page",
        "feature/payment-gateway",
        "feature/user-profile",
        "bugfix/api-timeout",
        "refactor/database-queries",
        "feature/dark-mode",
        "security/jwt-auth",
        "docs/api-guide"
    ]

    total_commits = 100
    commit_messages = [
        "Update function logic", "Fix minor typo", "Optimize loops", "Add error handling",
        "Refactor variable names", "Update styling for buttons", "Add unit tests",
        "Improve database connection pool", "Implement caching layer", "Update configuration parameters",
        "Fix null pointer exception", "Clean up unused imports", "Add API documentation",
        "Implement rate limiting", "Update CSS variables", "Improve loading speed",
        "Add helper utility function", "Fix token validation bug", "Update index layout",
        "Add logger warnings", "Optimize database indexing", "Sanitize user input"
    ]

    for i in range(1, total_commits + 1):
        # Deciding whether to create a new branch, switch branch, or merge
        action = random.choice(["commit", "commit", "commit", "switch", "create_branch", "merge"])
        
        if action == "create_branch" and feature_branches:
            new_branch = feature_branches.pop(0)
            run_git(["checkout", "-b", new_branch], cwd=DEMO_DIR)
            branches.append(new_branch)
            active_branch = new_branch
            print(f"Commit {i:03d}: Created and switched to branch '{new_branch}'")
            
        elif action == "switch" and len(branches) > 1:
            active_branch = random.choice(branches)
            run_git(["checkout", active_branch], cwd=DEMO_DIR)
            print(f"Commit {i:03d}: Switched to branch '{active_branch}'")
            
        elif action == "merge" and len(branches) > 1:
            # Merge some branch into another
            target = random.choice(branches)
            source = random.choice([b for b in branches if b != target])
            run_git(["checkout", target], cwd=DEMO_DIR)
            active_branch = target
            res = run_git(["merge", source, "-m", f"Merge branch '{source}' into '{target}'"], cwd=DEMO_DIR)
            if res.returncode == 0:
                print(f"Commit {i:03d}: Merged '{source}' into '{target}'")
            else:
                # If there's a conflict, abort and just do a regular commit
                run_git(["merge", "--abort"], cwd=DEMO_DIR)
                action = "commit"

        if action == "commit" or i == 1:
            # Modify a random file
            target_file = random.choice(files)
            filepath = os.path.join(DEMO_DIR, target_file)
            with open(filepath, "a") as file_obj:
                file_obj.write(f"\n# Contribution {i} on branch {active_branch}\n")
            
            msg = f"{random.choice(commit_messages)} (#{i})"
            run_git(["add", target_file], cwd=DEMO_DIR)
            run_git(["commit", "-m", msg], cwd=DEMO_DIR)
            print(f"Commit {i:03d}: Committed to '{active_branch}' - '{msg}'")

    print("\n--- 3. Pushing All Branches to the Server ---")
    for b in branches:
        print(f"Pushing branch '{b}'...")
        res = run_git(["push", "-u", "origin", b], cwd=DEMO_DIR)
        if res.returncode == 0:
            print(f"Successfully pushed '{b}'!")
        else:
            print(f"Failed to push '{b}': {res.stderr}")

    print("\n--- Complex Git Activity Generation Complete! ---")

if __name__ == "__main__":
    main()
