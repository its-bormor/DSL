import sqlite3
import json

DB_PATH = r"C:\Users\beamg\.local\share\mimocode\mimocode.db"
conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row
cur = conn.cursor()

SESSION_ID = "ses_143f25f78ffeEWWco9M3y6u6UT"

# Get all assistant messages with their parts
cur.execute("""
    SELECT m.id, m.time_created, m.data as msg_data,
           p.id as part_id, p.time_created as part_time, p.data as part_data
    FROM message m
    LEFT JOIN part p ON p.message_id = m.id
    WHERE m.session_id = ?
      AND json_extract(m.data, '$.role') = 'assistant'
    ORDER BY m.time_created, p.time_created
""", (SESSION_ID,))

rows = cur.fetchall()
print(f"=== ASSISTANT MESSAGES FOR {SESSION_ID} ===")
print(f"Total rows: {len(rows)}\n")

for row in rows:
    msg_data = json.loads(row['msg_data'])
    part_data = json.loads(row['part_data']) if row['part_data'] else None
    
    if part_data:
        ptype = part_data.get('type', 'unknown')
        if ptype == 'tool':
            tool = part_data.get('tool', '?')
            state = part_data.get('state', {})
            inp = state.get('input', {})
            out = state.get('output', '')
            
            # Summarize tool call
            if tool == 'bash':
                cmd = inp.get('command', '')[:200]
                out_preview = str(out)[:200] if out else ''
                print(f"[msg {row['id']}] bash: {cmd}")
                if out_preview:
                    print(f"  output: {out_preview}")
            elif tool == 'write':
                fp = inp.get('filePath', '')
                content_len = len(inp.get('content', ''))
                print(f"[msg {row['id']}] write: {fp} ({content_len} chars)")
            elif tool == 'edit':
                fp = inp.get('filePath', '')
                old_len = len(inp.get('oldString', ''))
                new_len = len(inp.get('newString', ''))
                print(f"[msg {row['id']}] edit: {fp} (old={old_len}c, new={new_len}c)")
            elif tool == 'read':
                fp = inp.get('filePath', '')
                print(f"[msg {row['id']}] read: {fp}")
            elif tool == 'grep':
                pattern = inp.get('pattern', '')
                path = inp.get('path', '')
                print(f"[msg {row['id']}] grep: pattern={pattern} path={path}")
            elif tool == 'glob':
                pattern = inp.get('pattern', '')
                print(f"[msg {row['id']}] glob: {pattern}")
            else:
                print(f"[msg {row['id']}] {tool}: {json.dumps(inp)[:200]}")
        elif ptype == 'text':
            text = part_data.get('text', '')[:300]
            if text.strip():
                print(f"[msg {row['id']}] TEXT: {text}")
        elif ptype in ('step-start', 'step-finish'):
            tokens = part_data.get('tokens', '')
            print(f"[msg {row['id']}] {ptype} tokens={tokens}")
    
conn.close()
