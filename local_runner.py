import os
import requests
import subprocess
import time
import platform

# --- CONFIGURATION ---
REFINER_REPO_USER = "BarimKenzema"
REFINER_REPO_NAME = "probable-happiness" # This is Repo B
REFINER_REPO_PATH = "."

# --- NEW URL ---
# We now download the Stage 2 list from Repo B itself.
SOURCE_URL = f"https://raw.githubusercontent.com/{REFINER_REPO_USER}/{REFINER_REPO_NAME}/main/github-refined-list.txt"
LOCAL_SOURCE_FILE = "github-refined-list.txt" # The local filename must match

def run_command(command):
    """Runs a command in the shell and prints its output."""
    try:
        print(f"--- Running command: {' '.join(command)} ---")
        use_shell = platform.system() == "Windows"
        result = subprocess.run(command, check=True, capture_output=True, text=True, shell=use_shell)
        if result.stdout:
            print(result.stdout)
        if result.stderr:
            print("STDERR:", result.stderr)
        return True
    except subprocess.CalledProcessError as e:
        print(f"!!! ERROR executing command: {' '.join(command)} !!!")
        print("STDOUT:", e.stdout)
        print("STDERR:", e.stderr)
        return False

def main():
    start_time = time.time()
    
    os.chdir(REFINER_REPO_PATH)
    
    # 1. Pull latest changes, including the new github-refined-list.txt from the Action
    print("\n--- Step 1: Syncing with GitHub to get Stage 2 list ---")
    if not run_command(["git", "pull"]):
        print("!!! Git pull failed. Please resolve conflicts manually before running again.")
        return

    # 2. The download step is now redundant if git pull works, but we can keep it as a fallback.
    # The `git pull` in Step 1 should have already updated the file.
    print(f"\n--- Step 2: Verifying local Stage 2 list exists ---")
    if not os.path.exists(LOCAL_SOURCE_FILE):
        print(f"!!! Local file '{LOCAL_SOURCE_FILE}' not found after pull. This is unexpected.")
        return

    # 3. Run the main script in Local Mode
    print("\n--- Step 3: Starting the local refining process (Stage 3) ---")
    if not run_command(["python", "main.py"]):
        print("!!! The main.py script failed to execute properly.")
        return
        
    # 4. Commit and push the final, verified results
    print("\n--- Step 4: Pushing verified configs to GitHub ---")
    run_command(["git", "add", "."])
    
    commit_message = f"✅ Stage 3: Verified configs from Iran @ {time.strftime('%Y-%m-%d %H:%M:%S')}"
    
    if run_command(["git", "commit", "-m", commit_message]):
        run_command(["git", "push"])
    else:
        print("--- No changes to commit or commit failed. ---")

    end_time = time.time()
    print(f"\n--- Local runner finished in {end_time - start_time:.2f} seconds. ---")


if __name__ == "__main__":
    main()