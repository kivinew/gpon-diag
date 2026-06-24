import os, sys, pathlib
VENV_SITE = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '.venv', 'Lib', 'site-packages'))
print('site', VENV_SITE)
sys.path.append(VENV_SITE)
try:
    import dotenv
    print('import ok')
except Exception as e:
    print('import error', e)
