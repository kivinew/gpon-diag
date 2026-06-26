import sys, threading, time
import urllib.request

sys.path.append(r'E:/DOWNLOADS/CREATIVE/PYTHON/GitHub/gpon-diag')
from web.app import app
from waitress import serve


def run_server():
    serve(app, host='127.0.0.1', port=5000)

thread = threading.Thread(target=run_server, daemon=True)
thread.start()
# give server time to start
time.sleep(3)
try:
    with urllib.request.urlopen('http://127.0.0.1:5000', timeout=5) as resp:
        code = resp.getcode()
        print('HTTP', code)
        sys.exit(0 if code == 200 else 1)
except Exception as e:
    print('Error', e)
    sys.exit(1)
