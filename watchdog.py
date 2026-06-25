import subprocess, time, socket, os

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '.'))
VENV_PY = os.path.join(PROJECT_ROOT, '.venv', 'Scripts', 'python.exe')

def is_port_open(port=5000):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('127.0.0.1', port)) == 0

def start_server():
    env = os.environ.copy()
    proj_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    venv_site = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '.venv', 'Lib', 'site-packages'))
    env['PYTHONPATH'] = proj_root + os.pathsep + venv_site + os.pathsep + env.get('PYTHONPATH','')
    subprocess.Popen([VENV_PY, '-u', '-m', 'scripts.run_server'], creationflags=0x08000000, env=env, stdout=open(os.path.join('data','logs','server.log'),'a',encoding='utf-8'), stderr=subprocess.STDOUT)

while True:
    if not is_port_open():
        start_server()
    time.sleep(30)
