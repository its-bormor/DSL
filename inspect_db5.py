import sqlite3
import json

DB_PATH = r"C:\Users\beamg\.local\share\mimocode\mimocode.db"
conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row
cur = conn.cursor()

# Check task table schema
cur.execute("PRAGMA table_info(task)")
print("=== TASK TABLE SCHEMA ===")
for row in cur.fetchall():
    print(f"  {row}")

cur.execute("PRAGMA table_info(task_event)")
print("\n=== TASK_EVENT TABLE SCHEMA ===")
for row in cur.fetchall():
    print(f"  {row}")

# Check tasks
print("\n=== TASKS ===")
try:
    cur.execute("SELECT * FROM task")
    for row in cur.fetchall():
        print(f"  {dict(row)}")
except Exception as e:
    print(f"  Error: {e}")

print("\n=== TASK EVENTS ===")
try:
    cur.execute("SELECT * FROM task_event ORDER BY time_created DESC LIMIT 20")
    for row in cur.fetchall():
        print(f"  {dict(row)}")
except Exception as e:
    print(f"  Error: {e}")

# Check actor registry
print("\n=== ACTOR REGISTRY ===")
try:
    cur.execute("SELECT * FROM actor_registry")
    for row in cur.fetchall():
        print(f"  {dict(row)}")
except Exception as e:
    print(f"  Error: {e}")

# Check what session the current session maps to in the DB
print("\n=== CURRENT SESSION CHECK ===")
cur.execute("SELECT * FROM session WHERE id = 'ses_0ec702f98ffehLsPplVRDAEPyw'")
row = cur.fetchone()
if row:
    print(f"  {dict(row)}")

# Search for user messages with keywords across all sessions
print("\n=== USER MESSAGES WITH KEY PATTERNS ===")
keywords = ["rule", "always", "never", "remember", "decision", "decided", "workflow", "repeat", "again"]
for kw in keywords:
    cur.execute("""
        SELECT m.session_id, m.time_created, substr(json_extract(m.data, '$.content'), 1, 200) as content
        FROM message m
        WHERE json_extract(m.data, '$.role') = 'user'
          AND json_extract(m.data, '$.content') LIKE ?
        ORDER BY m.time_created DESC
        LIMIT 3
    """, (f'%{kw}%',))
    rows = cur.fetchall()
    if rows:
        print(f"\n  Keyword: '{kw}'")
        for r in rows:
            print(f"    session={r['session_id']} | {r['content']}")

conn.close()
