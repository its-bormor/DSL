import sqlite3
import json

DB_PATH = r"C:\Users\beamg\.local\share\mimocode\mimocode.db"
conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row
cur = conn.cursor()

# Check the other work session
SESSION_ID = "ses_0ec703077ffeH8bNlCPj33LWiz"

print(f"=== SESSION: {SESSION_ID} ===\n")

# Get session metadata
cur.execute("SELECT * FROM session WHERE id = ?", (SESSION_ID,))
s = cur.fetchone()
print(f"Title: {s['title']}")
print(f"Directory: {s['directory']}")
print(f"Created: {s['time_created']}\n")

# Get all messages and parts
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
    agent = row['agent_id'] or 'main'
    
    if row['part_data']:
        part_data = json.loads(row['part_data'])
        ptype = part_data.get('type', 'unknown')
        
        if ptype == 'text':
            text = part_data.get('text', '')[:500]
            if text.strip():
                print(f"[{role}] TEXT: {text}")
        elif ptype == 'tool':
            tool = part_data.get('tool', '?')
            state = part_data.get('state', {})
            inp = state.get('input', {})
            out = state.get('output', '')
            
            if tool == 'bash':
                cmd = inp.get('command', '')[:300]
                out_preview = str(out)[:300] if out else ''
                print(f"[{role}] bash: {cmd}")
                if out_preview:
                    print(f"  output: {out_preview}")
            elif tool == 'read':
                fp = inp.get('filePath', '')
                print(f"[{role}] read: {fp}")
            elif tool == 'edit':
                fp = inp.get('filePath', '')
                print(f"[{role}] edit: {fp}")
            elif tool == 'write':
                fp = inp.get('filePath', '')
                print(f"[{role}] write: {fp}")
            elif tool == 'grep':
                pattern = inp.get('pattern', '')
                print(f"[{role}] grep: {pattern}")
            else:
                print(f"[{role}] {tool}: {json.dumps(inp)[:200]}")
        elif ptype in ('step-start', 'step-finish'):
            tokens = part_data.get('tokens', '')
            if ptype == 'step-finish':
                print(f"[{role}] step-finish tokens={tokens}")

conn.close()
