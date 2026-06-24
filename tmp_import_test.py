import sys, os
print('exe:', sys.executable)
print('path[0:5]:', sys.path[:5])
try:
    import dotenv
    print('dotenv imported from', dotenv.__file__)
except Exception as e:
    print('Import error:', e)
