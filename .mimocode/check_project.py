import sqlite3
import json
conn = sqlite3.connect(r'C:\Users\Administrator\.local\share\mimocode\mimocode.db')
cursor = conn.cursor()
cursor.execute("SELECT * FROM project")
rows = cursor.fetchall()
cursor.execute("PRAGMA table_info(project)")
cols = [r[1] for r in cursor.fetchall()]
print("Columns:", cols)
for row in rows:
    print("\n--- Project ---")
    for i, col in enumerate(cols):
        val = row[i]
        if isinstance(val, str) and len(val) > 200:
            val = val[:200] + "..."
        print(f"  {col}: {val}")
conn.close()
