#!/usr/bin/env python3
import os
os.environ['GPON_OLT_OLT_40_111_USERNAME'] = 'kudryavcev.iv'
os.environ['GPON_OLT_OLT_40_111_PASSWORD'] = 'hard5gznm'
os.environ['GPON_OLT_OLT_17_232_USERNAME'] = 'kudryavcev.iv'
os.environ['GPON_OLT_OLT_17_232_PASSWORD'] = 'hard5gznm'

import sys
sys.path.insert(0, '.')

# Now run diagnose.py as module
from diagnose import main
sys.argv = ['diagnose.py', '0/0/0/5', '--olt', 'OLT-40.111', '--no-save']
main()