"""Check if Flask server is running; if not, diagnose and start it with file locking.
This script is intended to be invoked repeatedly (e.g., via /loop)."""
import os, subprocess, time, re
import sys, os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "hermes-lockutils")))
from file_lock import lock_file, unlock_file

def is_server_running():
    """Determine if a single Waitress server is listening on port 5000.
    Returns True only if exactly one process is listening on that port.
    """
    try:
        out = subprocess.check_output(["netstat", "-ano"], text=True)
        pids = []
        for line in out.splitlines():
            if ("0.0.0.0:5000" in line or "[::]:5000" in line) and "LISTENING" in line:
                parts = line.split()
                pids.append(parts[-1])
        # If exactly one PID is listening, assume it's the correct server
        return len(pids) == 1
    except Exception:
        return False

def check_logs():
    log_path = os.path.join("data", "logs", "server.log")
    if not os.path.exists(log_path):
        return "Log file not found"
    with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
        lines = f.readlines()[-20:]
    errors = [l for l in lines if "ERROR" in l or "Traceback" in l]
    return "\n".join(errors) if errors else "No recent errors"

def kill_port_processes():
    """Kill any processes listening on port 5000 (excluding the current check script)."""
    try:
        out = subprocess.check_output(["netstat", "-ano"], text=True)
        for line in out.splitlines():
            if ("0.0.0.0:5000" in line or "[::]:5000" in line) and "LISTENING" in line:
                parts = line.split()
                pid = parts[-1]
                # Avoid killing this script itself
                if pid != str(os.getpid()):
                    subprocess.run(["taskkill", "/PID", pid, "/F"], capture_output=True)
    except Exception:
        pass

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
    # Additionally kill any processes still listening on port 5000
    kill_port_processes()

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

    # Add project root and virtual‑env site‑packages to PYTHONPATH so Flask, dotenv, waitress and local modules are found
    venv_site = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", ".venv", "Lib", "site-packages")
    )
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    env = os.environ.copy()
    env["PYTHONPATH"] = project_root + os.pathsep + venv_site + os.pathsep + env.get("PYTHONPATH", "")

    lock_path = os.path.join(os.getenv("TEMP", "."), "gpon_server.lock")
    lock_file(lock_path)
    try:
        print('PYTHONPATH:', env.get('PYTHONPATH',''))
        subprocess.Popen(
            [
                "E:/DOWNLOADS/CREATIVE/PYTHON/GitHub/gpon-diag/.venv/Scripts/python.exe",
                "-u", "-m", "scripts.run_server"
            ],
            creationflags=0x08000000,
            env=env,
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
