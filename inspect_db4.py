import sqlite3
import json

DB_PATH = r"C:\Users\beamg\.local\share\mimocode\mimocode.db"
conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row
cur = conn.cursor()

# Check the Thai inquiry session
SESSION_ID = "ses_143fdd47fffeFo2feM6GuuJvgU"

print(f"=== SESSION: {SESSION_ID} ===\n")

cur.execute("SELECT * FROM session WHERE id = ?", (SESSION_ID,))
s = cur.fetchone()
print(f"Title: {s['title']}")
print(f"Directory: {s['directory']}")

cur.execute("""
    SELECT m.id, m.agent_id, m.time_created, m.data as msg_data,
           p.id as part_id, p.time_created as part_time, p.data as part_data
    FROM message m
    LEFT JOIN part p ON p.message_id = m.id
    WHERE m.session_id = ?
    ORDER BY m.time_created, p.time_created
""", (SESSION_ID,))

rows = cur.fetchall()
for row in rows:
    msg_data = json.loads(row['msg_data'])
    role = msg_data.get('role', '?')
    
    if row['part_data']:
        part_data = json.loads(row['part_data'])
        ptype = part_data.get('type', 'unknown')
        
        if ptype == 'text':
            text = part_data.get('text', '')[:500]
            if text.strip():
                print(f"[{role}] TEXT: {text}")

# Also check tasks and task_events
print("\n=== TASKS ===")
cur.execute("SELECT * FROM task")
for row in cur.fetchall():
    data = json.loads(row['data']) if row['data'] else {}
    print(f"  Task {row['id']}: {data.get('summary', 'no summary')} | status={data.get('status', '?')}")

print("\n=== TASK EVENTS ===")
cur.execute("SELECT * FROM task_event ORDER BY time_created DESC LIMIT 20")
for row in cur.fetchall():
    data = json.loads(row['data']) if row['data'] else {}
    print(f"  Task {row['task_id']}: {data.get('event_summary', '?')} | session={row['session_id']}")

# Check actor registry
print("\n=== ACTOR REGISTRY ===")
cur.execute("SELECT * FROM actor_registry")
for row in cur.fetchall():
    data = json.loads(row['data']) if row['data'] else {}
    print(f"  {row['id']}: {json.dumps(data)[:200]}")

conn.close()
