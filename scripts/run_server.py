import os, sys

# Add project root and virtual‑env site‑packages to PYTHONPATH
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.append(PROJECT_ROOT)

VENV_SITE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".venv", "Lib", "site-packages"))
sys.path.append(VENV_SITE)

# Optional dotenv loading – ignore if not installed
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

if __name__ == "__main__":
    # Clean up any stale OLT connections on startup
    try:
        from core.olt import close_all
        close_all()
    except Exception:
        pass

    # Import Flask app
    try:
        from web.app import app as flask_app
        app = flask_app
    except Exception:
        import traceback, sys
        traceback.print_exc()
        sys.exit(1)
    # Production settings
    app.debug = False
    # Start server with Waitress if available
    try:
        from waitress import serve
        serve(app, host="0.0.0.0", port=5000)
    except Exception:
        import traceback, sys
        traceback.print_exc()
        sys.exit(1)
