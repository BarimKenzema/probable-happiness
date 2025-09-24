import os
import requests
import subprocess
import time
import platform

# --- CONFIGURATION ---
# These are correctly set for your repositories. No changes needed.
COLLECTOR_REPO_USER = "BarimKenzema"
COLLECTOR_REPO_NAME = "Haj-Karim" 
REFINER_REPO_PATH = "." # This means the script is inside the V2ray-Sub folder

# The URL to the raw pre-filtered list from your collector repo
SOURCE_URL = f"https://raw.githubusercontent.com/{COLLECTOR_REPO_USER}/{COLLECTOR_REPO_NAME}/main/filtered-for-refiner.txt"
LOCAL_SOURCE_FILE = "filtered-for-refiner.txt"

def run_command(command):
    """Runs a command in the shell and prints its output."""
    try:
        print(f"--- Running command: {' '.join(command)} ---")
        # Use shell=True for git commands to work easily on Windows
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
    
    # 1. Sync with GitHub to get the latest version of your showroom
    print("\n--- Step 1: Syncing with GitHub remote ---")
    if not run_command(["git", "pull"]):
        print("!!! Git pull failed. Please resolve conflicts manually before running again.")
        return

    # 2. Download the box of parts from the factory (Repo A)
    print(f"\n--- Step 2: Downloading configs from {SOURCE_URL} ---")
    try:
        response = requests.get(SOURCE_URL, timeout=30)
        response.raise_for_status()
        with open(LOCAL_SOURCE_FILE, 'w', encoding='utf-8') as f:
            f.write(response.text)
        print(f"Successfully downloaded and saved to {LOCAL_SOURCE_FILE}")
    except requests.RequestException as e:
        print(f"!!! FATAL: Could not download configs from Repo A. Error: {e}")
        return

    # 3. Start the workshop: Run the main testing script
    print("\n--- Step 3: Starting the local refining process (main.py) ---")
    if not run_command(["python", "main.py"]):
        print("!!! The main.py script failed to execute properly.")
        return
        
    # 4. Put the finished products in the showroom: Save and upload to GitHub
    print("\n--- Step 4: Pushing verified configs to GitHub ---")
    run_command(["git", "add", "."])
    
    commit_message = f"✅ Verified configs from Iran @ {time.strftime('%Y-%m-%d %H:%M:%S')}"
    
    # Use 'git commit' with quotes around the message
    if run_command(["git", "commit", "-m", commit_message]):
        run_command(["git", "push"])
    else:
        print("--- No changes to commit or commit failed. This is normal if no new working configs were found. ---")

    end_time = time.time()
    print(f"\n--- Local runner finished in {end_time - start_time:.2f} seconds. ---")


if __name__ == "__main__":
    main()