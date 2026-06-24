import os, sys

# Add project root and virtual‑env site‑packages to PYTHONPATH
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.append(PROJECT_ROOT)

VENV_SITE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".venv", "Lib", "site-packages"))
sys.path.append(VENV_SITE)

if __name__ == "__main__":
    # Load environment variables (config.yaml may rely on .env)
    from dotenv import load_dotenv
    load_dotenv(os.path.join(PROJECT_ROOT, ".env"))
    try:
        from web import app  # import Flask app
    except Exception as exc:
        import traceback, sys
        traceback.print_exc()
        sys.exit(1)
    # Ensure production settings – disable Flask debug/reloader
    app.debug = False
    # Waitress will serve the Flask app without the development server warnings
    from waitress import serve
    serve(app, host="0.0.0.0", port=5000)
