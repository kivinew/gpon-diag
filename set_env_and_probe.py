#!/usr/bin/env python3
import os
os.environ['GPON_OLT_OLT_40_111_USERNAME'] = 'kudryavcev.iv'
os.environ['GPON_OLT_OLT_40_111_PASSWORD'] = 'hard5gznm'
os.environ['GPON_OLT_OLT_17_232_USERNAME'] = 'kudryavcev.iv'
os.environ['GPON_OLT_OLT_17_232_PASSWORD'] = 'hard5gznm'

import sys
sys.path.insert(0, '.')

from core.olt import OltConnection

def probe():
    olt = OltConnection("172.16.40.111", 23)
    olt.connect()
    print("Connected to OLT-40.111")
    # Test a simple command
    out = olt.send_command("display version", max_more=0)
    print("Version:", out[:200])
    olt.disconnect()

if __name__ == "__main__":
    probe()