import sqlite3
import json

DB_PATH = r"C:\Users\beamg\.local\share\mimocode\mimocode.db"
conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row
cur = conn.cursor()

# 1. List tables
cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = [r[0] for r in cur.fetchall()]
print("=== TABLES ===")
for t in tables:
    print(f"  {t}")

# 2. List all sessions
print("\n=== ALL SESSIONS ===")
cur.execute("SELECT id, project_id, directory, title, time_created FROM session ORDER BY time_created DESC")
for row in cur.fetchall():
    print(f"  {row['id']} | project={row['project_id']} | dir={row['directory']} | title={row['title']} | created={row['time_created']}")

# 3. Count messages per session
print("\n=== MESSAGE COUNTS ===")
cur.execute("""
    SELECT s.id, s.title, COUNT(m.id) as msg_count
    FROM session s
    LEFT JOIN message m ON m.session_id = s.id
    GROUP BY s.id
    ORDER BY s.time_created DESC
""")
for row in cur.fetchall():
    print(f"  {row['id']} | msgs={row['msg_count']} | {row['title']}")

conn.close()
