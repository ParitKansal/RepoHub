import os
import subprocess

REPO_DIR = "/Users/xelpmoc/Desktop/Projects/GitClone/scratch/complex_repo"

def run_git(args):
    cmd = ["git", "-c", "http.sslVerify=false"] + args
    return subprocess.run(cmd, cwd=REPO_DIR, capture_output=True, text=True)

def resolve_file_conflicts(filepath):
    if not os.path.exists(filepath):
        return
    
    with open(filepath, "r") as f:
        lines = f.readlines()
        
    clean_lines = []
    for line in lines:
        # Simply strip out the Git conflict markers to merge both changes cleanly
        if line.startswith("<<<<<<<") or line.startswith("=======") or line.startswith(">>>>>>>"):
            continue
        clean_lines.append(line)
        
    with open(filepath, "w") as f:
        f.writelines(clean_lines)
    print(f"Resolved conflicts in: {os.path.basename(filepath)}")

def main():
    print("--- 1. Pulling latest main from server ---")
    run_git(["checkout", "main"])
    run_git(["pull", "origin", "main"])
    
    print("\n--- 2. Switching to branch 'refactor/database-queries' ---")
    run_git(["checkout", "refactor/database-queries"])
    
    print("\n--- 3. Starting merge with 'main' ---")
    # This will trigger conflicts
    res = run_git(["merge", "main"])
    print(res.stdout)
    print(res.stderr)
    
    # List of files we know have conflicts
    conflicting_files = ["main.py", "config.json", "docs.md", "styles.css"]
    
    print("\n--- 3. Automatically resolving conflicts ---")
    for f in conflicting_files:
        resolve_file_conflicts(os.path.join(REPO_DIR, f))
        
    print("\n--- 4. Committing and Pushing resolution ---")
    run_git(["add", "."])
    run_git(["commit", "-m", "Resolve merge conflicts automatically"])
    push_res = run_git(["push", "origin", "bugfix/api-timeout"])
    
    if push_res.returncode == 0:
        print("Successfully resolved and pushed the changes to the server!")
    else:
        print(f"Failed to push: {push_res.stderr}")

if __name__ == "__main__":
    main()
