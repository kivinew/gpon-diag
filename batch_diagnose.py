#!/usr/bin/env python3
"""Batch diagnosis for all ONTs on OLT 172.16.17.232.

Executes:
    scroll\r\rdisplay ont info 0 all
parses terminal IDs and runs diagnosis for each with a 1‑second interval.
"""
import time
import logging
from core.olt import get_olt_connection
from diagnose import main as diagnose_main

logging.basicConfig(level=logging.INFO)

HOST = "172.16.17.232"
OLT_NAME = "OLT-17.232"  # arbitrary identifier used by diagnose.py

def get_terminals(conn):
    # Send scroll command to ensure full output
    conn.send_command("scroll", max_more=-1)
    # Retrieve ONT list
    output = conn.send_command("display ont info 0 all", max_more=-1)
    # Each line like "0/0/0/5" etc.
    terminals = []
    for line in output.splitlines():
        line = line.strip()
        if line and "/" in line:
            terminals.append(line)
    return terminals

def main():
    with get_olt_connection(HOST) as conn:
        terminals = get_terminals(conn)
        logging.info("Found %d terminals", len(terminals))
        for term in terminals:
            logging.info("Diagnosing %s", term)
            # Run diagnosis without saving (to avoid DB write conflicts)
            try:
                diagnose_main([term, "--olt", OLT_NAME])
            except Exception as e:
                logging.error("Diagnosis failed for %s: %s", term, e)
            time.sleep(1)

if __name__ == "__main__":
    main()
