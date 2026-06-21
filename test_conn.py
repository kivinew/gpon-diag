#!/usr/bin/env python3
"""Quick telnet connection test to OLT."""

import os
import sys
from dotenv import load_dotenv

load_dotenv()
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.olt import OltConnection

HOST = os.getenv("GPON_OLT_TEST_HOST", "172.16.40.111")
USER = os.getenv("GPON_OLT_40_111_USERNAME", "")
PASS = os.getenv("GPON_OLT_40_111_PASSWORD", "")

if not USER or not PASS:
    print("Set GPON_OLT_40_111_USERNAME / GPON_OLT_40_111_PASSWORD in .env")
    sys.exit(1)

olt = OltConnection(HOST, 23, USER, PASS)
try:
    olt.connect()
    print(f"Connected to {HOST}!")
    out = olt.send_command("display version", max_more=0)
    print(f"Version:\n{out[:300]}")
except Exception as e:
    print(f"Failed: {e}")
finally:
    olt.disconnect()
