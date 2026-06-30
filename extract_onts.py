#!/usr/bin/env python3
"""
CLI for extracting ONT records with match/mismatch state.

Usage:
  # Extract 20 latest records from diagnoses.db
  python extract_onts.py --from-db --limit 20

  # Extract all online records from DB
  python extract_onts.py --from-db --status online

  # Filter by OLT
  python extract_onts.py --from-db --olt-name 17.232

  # Save to CSV
  python extract_onts.py --from-db --limit 100 -o output/onts.csv

  # Real-time: scan GPON port on OLT
  python extract_onts.py --from-olt OLT-17.232 --port 0/0/4

  # Real-time: scan all ports on OLT
  python extract_onts.py --from-olt OLT-17.232 --all-ports -o all_onts.json

  # Summary statistics only
  python extract_onts.py --from-db --stats
"""

import sys

# Ensure project root is on path
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from core.data_extractor import main_cli

if __name__ == "__main__":
    sys.exit(main_cli())
