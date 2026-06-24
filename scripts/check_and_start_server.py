"""Check if Flask server is running; if not, diagnose and start it with file locking.
This script is intended to be invoked repeatedly (e.g., via /loop)."""
import os, subprocess, time, re
import sys, os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "hermes-lockutils")))
from file_lock import lock_file, unlock_file

def is_server_running():
    """Check if the server process started via run_server.py is already running.
    This avoids detecting the Flask dev server which may spawn multiple processes.
    """
    try:
        out = subprocess.check_output([
            "tasklist",
            "/FI",
            "IMAGENAME eq python.exe",
            "/FI",
            "WINDOWTITLE eq run_server*",
        ], text=True)
        return "run_server.py" in out
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
    """Start the production server via Waitress.
    Ensures any leftover Flask dev server processes are terminated before launch.
    """
    # Terminate any lingering Flask dev server processes (identified by window title)
    try:
        subprocess.run([
            "taskkill",
            "/FI",
            "IMAGENAME eq python.exe",
            "/FI",
            "WINDOWTITLE eq Flask*",
            "/F",
        ], capture_output=True, text=True)
    except Exception:
        pass

    lock_path = os.path.join(os.getenv("TEMP", "."), "gpon_server.lock")
    lock_file(lock_path)
    try:
        subprocess.Popen(
            ["E:/DOWNLOADS/CREATIVE/PYTHON/GitHub/gpon-diag/.venv/Scripts/python.exe", "scripts/run_server.py"],
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
