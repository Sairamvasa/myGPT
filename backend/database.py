import sqlite3

conn = sqlite3.connect(
    "chat.db",
    check_same_thread=False
)

cursor = conn.cursor()


# Chats / conversations table
cursor.execute("""
CREATE TABLE IF NOT EXISTS conversations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
""")


# Messages table
cursor.execute("""
CREATE TABLE IF NOT EXISTS chats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id INTEGER,
    role TEXT,
    message TEXT
)
""")

conn.commit()


def create_conversation(title="New Chat"):
    cursor.execute(
        "INSERT INTO conversations(title) VALUES (?)",
        (title,)
    )

    conn.commit()

    return cursor.lastrowid


def update_conversation_title(chat_id, title):
    cursor.execute(
        "UPDATE conversations SET title = ? WHERE id = ?",
        (title, chat_id)
    )

    conn.commit()


def get_conversations():
    cursor.execute("""
        SELECT id, title
        FROM conversations
        ORDER BY id DESC
    """)

    return cursor.fetchall()


def get_chat_messages(chat_id):
    cursor.execute("""
        SELECT role, message
        FROM chats
        WHERE chat_id = ?
        ORDER BY id ASC
    """, (chat_id,))

    return cursor.fetchall()

def delete_conversation(chat_id):
    # Delete messages belonging to this chat
    cursor.execute(
        "DELETE FROM chats WHERE chat_id = ?",
        (chat_id,)
    )

    # Delete conversation
    cursor.execute(
        "DELETE FROM conversations WHERE id = ?",
        (chat_id,)
    )

    conn.commit()