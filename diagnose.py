#!/usr/bin/env python3
"""GPON Diagnostic Tool — main entry point.

This is a thin wrapper that delegates to core.cli_diagnosis.main()
"""

from core.cli_diagnosis import main

if __name__ == "__main__":
    main()