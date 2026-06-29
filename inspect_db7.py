import sqlite3
import json

DB_PATH = r"C:\Users\beamg\.local\share\mimocode\mimocode.db"
conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row
cur = conn.cursor()

# Check actual message data format
print("=== MESSAGE DATA FORMAT SAMPLES ===")
for sid in ["ses_143f25f78ffeEWWco9M3y6u6UT", "ses_0ec703077ffeH8bNlCPj33LWiz"]:
    print(f"\nSession: {sid}")
    cur.execute("""
        SELECT m.id, m.data
        FROM message m
        WHERE m.session_id = ?
          AND json_extract(m.data, '$.role') = 'user'
        LIMIT 3
    """, (sid,))
    for row in cur.fetchall():
        data = json.loads(row['data'])
        print(f"  {json.dumps(data, ensure_ascii=False)[:600]}")

# Check part data for user messages
print("\n=== PART DATA FOR USER MESSAGES ===")
for sid in ["ses_143f25f78ffeEWWco9M3y6u6UT", "ses_0ec703077ffeH8bNlCPj33LWiz"]:
    print(f"\nSession: {sid}")
    cur.execute("""
        SELECT p.data as part_data
        FROM part p
        JOIN message m ON p.message_id = m.id
        WHERE m.session_id = ?
          AND json_extract(m.data, '$.role') = 'user'
        LIMIT 5
    """, (sid,))
    for row in cur.fetchall():
        if row['part_data']:
            pdata = json.loads(row['part_data'])
            print(f"  type={pdata.get('type')} text={pdata.get('text', '')[:400]}")

# Check DSL-main project files
print("\n=== DSL-main bot.py first 50 lines ===")
bot_path = r"C:\Users\beamg\.gemini\antigravity\scratch\DSL-main\bot.py"
with open(bot_path, 'r', encoding='utf-8') as f:
    lines = f.readlines()[:50]
    for i, line in enumerate(lines, 1):
        print(f"  {i}: {line.rstrip()}")

conn.close()
