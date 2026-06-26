import sys, traceback
sys.path.append(r'E:/DOWNLOADS/CREATIVE/PYTHON/GitHub/gpon-diag')
from web.app import app
from waitress import serve
serve(app, host='0.0.0.0', port=5000)