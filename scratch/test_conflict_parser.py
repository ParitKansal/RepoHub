import subprocess
import os

repo_path = "/Users/xelpmoc/Desktop/Projects/GitClone/scratch/complex_repo"
target_branch = "feature/dark-mode"
source_branch = "docs/api-guide"

def main():
    conflicting_files = []
    
    # 1. Run git merge-tree --write-tree
    mt = subprocess.run(
        ["git", "merge-tree", "--write-tree", target_branch, source_branch],
        cwd=repo_path, capture_output=True, text=True, timeout=30
    )
    can_merge = (mt.returncode == 0)
    print(f"Can merge: {can_merge}")
    print(f"Stdout length: {len(mt.stdout) if mt.stdout else 0}")
    
    if not can_merge and mt.stdout:
        for line in mt.stdout.splitlines():
            if not line.strip():
                print("Encountered blank line, stopping...")
                break
            parts = line.split("\t")
            if len(parts) == 2:
                filename = parts[1].strip()
                if filename not in conflicting_files:
                    conflicting_files.append(filename)
                    
    print(f"Conflicting files parsed: {conflicting_files}")

if __name__ == "__main__":
    main()
