#!/usr/bin/env python3
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.chdir(os.path.dirname(os.path.abspath(__file__)))

from core.olt import OltConnection

def test_connection():
    # Try with empty password
    olt = OltConnection("172.16.40.111", 23, "kudryavcev.iv", "")
    try:
        olt.connect()
        print("Connected successfully with empty password!")
        # Test a simple command
        out = olt.send_command("display version", max_more=0)
        print("Version output:", out[:200])
    except Exception as e:
        print(f"Connection failed with empty password: {e}")
    finally:
        if olt._connected:
            olt.disconnect()
    
    # Try with password same as username
    olt2 = OltConnection("172.16.40.111", 23, "kudryavcev.iv", "kudryavcev.iv")
    try:
        olt2.connect()
        print("Connected successfully with password as username!")
        out = olt2.send_command("display version", max_more=0)
        print("Version output:", out[:200])
    except Exception as e:
        print(f"Connection failed with password as username: {e}")
    finally:
        if olt2._connected:
            olt2.disconnect()

if __name__ == "__main__":
    test_connection()