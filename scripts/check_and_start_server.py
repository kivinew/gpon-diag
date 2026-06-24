"""Check if Flask server is running; if not, diagnose and start it with file locking.
This script is intended to be invoked repeatedly (e.g., via /loop)."""
import os, subprocess, time, re
import sys, os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "hermes-lockutils")))
from file_lock import lock_file, unlock_file

def is_server_running():
    # Look for python processes with flask app title
    try:
        out = subprocess.check_output(["tasklist", "/FI", "IMAGENAME eq python.exe", "/FI", "WINDOWTITLE eq Flask*"], text=True)
        return "python.exe" in out
    except subprocess.CalledProcessError:
        return False

def check_logs():
    log_path = os.path.join("data", "logs", "server.log")
    if not os.path.exists(log_path):
        return "Log file not found"
    with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
        lines = f.readlines()[-20:]
    errors = [l for l in lines if "ERROR" in l or "Traceback" in l]
    return "\n".join(errors) if errors else "No recent errors"

def start_server():
    lock_path = os.path.join(os.getenv("TEMP", "."), "gpon_server.lock")
    lock_file(lock_path)
    try:
        subprocess.Popen(
            ["E:/DOWNLOADS/CREATIVE/PYTHON/GitHub/gpon-diag/.venv/Scripts/python.exe", "-m", "web.app", "--no-reload"],
            creationflags=0x08000000,
            stdout=open(os.path.join("data", "logs", "server.log"), "a", encoding="utf-8"),
            stderr=subprocess.STDOUT,
        )
        time.sleep(2)
    finally:
        unlock_file(lock_path)

if __name__ == "__main__":
    if is_server_running():
        print("Server already running")
    else:
        print("Server not running. Checking logs for cause:")
        print(check_logs())
        print("Attempting to start server...")
        start_server()
        print("Start command issued")
