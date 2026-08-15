import sqlite3
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DB_NAME = str(BASE_DIR / "mygpt.db")


def get_connection():
    conn = sqlite3.connect(
        DB_NAME,
        check_same_thread=False
    )
    return conn


# ==============================
# USERS TABLE
# ==============================

# ==============================
# USERS TABLE
# ==============================

conn = get_connection()
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
""")


conn.commit()
conn.close()

# Create tables
conn = get_connection()
cursor = conn.cursor()

# existing conversations table...

cursor.execute("""
CREATE TABLE IF NOT EXISTS conversations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
""")

# Add user_id to existing conversations table
try:
    cursor.execute(
        "ALTER TABLE conversations ADD COLUMN user_id INTEGER"
    )
except sqlite3.OperationalError:
    pass

# Assign existing conversations to user 1
cursor.execute("""
    UPDATE conversations
    SET user_id = 1
    WHERE user_id IS NULL
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS chats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id INTEGER,
    role TEXT,
    message TEXT
)
""")


 
cursor.execute("""
CREATE TABLE IF NOT EXISTS memory (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    memory_key TEXT UNIQUE,
    memory_value TEXT
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS memories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fact TEXT NOT NULL,
    importance INTEGER DEFAULT 3,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
""")

# Add user_id to memories table
try:
    cursor.execute("ALTER TABLE memories ADD COLUMN user_id INTEGER")
except sqlite3.OperationalError:
    pass

# Add user_id to memory table
try:
    cursor.execute("ALTER TABLE memory ADD COLUMN user_id INTEGER")
except sqlite3.OperationalError:
    pass

conn.commit()
conn.close()


def create_conversation(user_id, title="New Chat"):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        INSERT INTO conversations(user_id, title)
        VALUES (?, ?)
        """,
        (user_id, title)
    )

    chat_id = cursor.lastrowid

    conn.commit()
    conn.close()

    return chat_id


def update_conversation_title(chat_id, title):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        "UPDATE conversations SET title = ? WHERE id = ?",
        (title, chat_id)
    )

    conn.commit()
    conn.close()


def get_conversations(user_id):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, title
        FROM conversations
        WHERE user_id = ?
        ORDER BY id DESC
    """, (user_id,))

    rows = cursor.fetchall()

    conn.close()

    return rows


def get_conversation_owner(chat_id):
    """Return the user_id that owns the conversation, or None if it doesn't exist."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        "SELECT user_id FROM conversations WHERE id = ?",
        (chat_id,)
    )

    row = cursor.fetchone()

    conn.close()

    return row[0] if row else None


def get_chat_messages(chat_id):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT role, message
        FROM chats
        WHERE chat_id = ?
        ORDER BY id ASC
    """, (chat_id,))

    rows = cursor.fetchall()

    conn.close()

    return rows


def delete_conversation(chat_id):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        "DELETE FROM chats WHERE chat_id = ?",
        (chat_id,)
    )

    cursor.execute(
        "DELETE FROM conversations WHERE id = ?",
        (chat_id,)
    )

    conn.commit()
    conn.close()
def is_first_message(chat_id):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT COUNT(*)
        FROM chats
        WHERE chat_id = ? AND role = 'user'
        """,
        (chat_id,)
    )

    count = cursor.fetchone()[0]

    conn.close()

    return count == 0



def save_message(chat_id, role, message):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        INSERT INTO chats(chat_id, role, message)
        VALUES (?, ?, ?)
        """,
        (chat_id, role, message)
    )

    conn.commit()
    conn.close()


def get_history(chat_id):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT role, message
        FROM chats
        WHERE chat_id = ?
        ORDER BY id
        """,
        (chat_id,)
    )

    rows = cursor.fetchall()

    conn.close()

    return rows

def remember_memory(key, value, user_id):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT OR REPLACE INTO memory(memory_key, memory_value, user_id)
        VALUES (?, ?, ?)
    """, (key, value, user_id))

    conn.commit()
    conn.close()


def recall_memory(key, user_id):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT memory_value
        FROM memory
        WHERE memory_key = ? AND user_id = ?
    """, (key, user_id))

    row = cursor.fetchone()

    conn.close()

    if row:
        return row[0]

    return None

def save_memory(fact, user_id, importance=3):

    conn = get_connection()
    cursor = conn.cursor()

    # Check if the same memory already exists for this user
    cursor.execute(
        "SELECT id FROM memories WHERE fact = ? AND user_id = ?",
        (fact, user_id)
    )

    if cursor.fetchone() is None:

        cursor.execute(
            """
            INSERT INTO memories(fact, importance, user_id)
            VALUES (?, ?, ?)
            """,
            (fact, importance, user_id)
        )

        conn.commit()

    conn.close()
    
def get_all_memories(user_id):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT fact
        FROM memories
        WHERE user_id = ?
        ORDER BY importance DESC, id DESC
    """, (user_id,))

    rows = cursor.fetchall()

    conn.close()

    return [row[0] for row in rows]
