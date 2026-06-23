from core.olt import get_olt_connection, close_all
from diagnose import load_config, _load_olt_credentials
from dotenv import load_dotenv
import os

load_dotenv()
config = load_config()
olt_cfg = config['olts'][0]
host = olt_cfg['host']
username, password = _load_olt_credentials(olt_cfg)
print(f"Connecting to {host}...")
olt = get_olt_connection(host, 23, username, password, 30)
olt.connect()
print("Connected")
info = olt.get_olt_info()
print(f"OLT info: {info}")

# Also show raw output for debugging
olt._write("display version\r")
import time
time.sleep(2)
raw = olt._read_to_prompt(8)
print(f"\n--- RAW display version output ---")
print(raw)
print(f"--- END ---")

close_all()
