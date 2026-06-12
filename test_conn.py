#!/usr/bin/env python3
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.chdir(os.path.dirname(os.path.abspath(__file__)))

from core.olt import OltConnection

def test_connection():
    olt = OltConnection("172.16.40.111", 23, "kudryavcev.iv", "kudryavcev.iv")
    try:
        olt.connect()
        print("Connected successfully!")
        # Test a simple command
        out = olt.send_command("display version", max_more=0)
        print("Version output:", out[:200])
    except Exception as e:
        print(f"Connection failed: {e}")
    finally:
        olt.disconnect()

if __name__ == "__main__":
    test_connection()