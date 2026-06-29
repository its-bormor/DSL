import sqlite3
import json

DB_PATH = r"C:\Users\beamg\.local\share\mimocode\mimocode.db"
conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row
cur = conn.cursor()

# Get all user messages from work sessions (not checkpoint-writer sessions)
work_sessions = [
    "ses_143f25f78ffeEWWco9M3y6u6UT",
    "ses_0ec703077ffeH8bNlCPj33LWiz"
]

for sid in work_sessions:
    print(f"\n=== USER MESSAGES IN {sid} ===")
    cur.execute("""
        SELECT m.id, m.time_created, json_extract(m.data, '$.content') as content
        FROM message m
        WHERE m.session_id = ?
          AND json_extract(m.data, '$.role') = 'user'
        ORDER BY m.time_created
    """, (sid,))
    for row in cur.fetchall():
        content = row['content'] if row['content'] else ''
        print(f"  [{row['time_created']}] {content[:500]}")

# Also check what the DSL-main project is about
print("\n=== DSL-main project files ===")
import os
project_dir = r"C:\Users\beamg\.gemini\antigravity\scratch\DSL-main"
if os.path.exists(project_dir):
    for item in os.listdir(project_dir):
        full = os.path.join(project_dir, item)
        if os.path.isfile(full):
            print(f"  {item} ({os.path.getsize(full)} bytes)")
        else:
            print(f"  {item}/")

# Check for user messages with Thai keywords
print("\n=== USER MESSAGES WITH THAI KEYWORDS ===")
thai_keywords = ["แก้", "เปลี่ยน", "ลบ", "เพิ่ม", "ระบบ", "รัน", "ต่อเนื่อง", "log", "ปัญหา", "เว็บ", "ดีไซน์", "รูปแบบ", "外观"]
for kw in thai_keywords:
    cur.execute("""
        SELECT m.session_id, m.time_created, json_extract(m.data, '$.content') as content
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
            content = r['content'][:300] if r['content'] else ''
            print(f"    session={r['session_id']} | {content}")

conn.close()
