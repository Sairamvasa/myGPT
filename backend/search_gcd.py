import sqlite3
conn = sqlite3.connect('mygpt.db')
cursor = conn.cursor()
cursor.execute("SELECT chat_id, id, role, message FROM chats WHERE message LIKE '%GCD%' OR message LIKE '%gcd%' OR message LIKE '%public class%' ORDER BY id DESC LIMIT 10")
for row in cursor.fetchall():
    print(row)
conn.close()