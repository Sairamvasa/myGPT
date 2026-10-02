import sqlite3
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DB_NAME = str(BASE_DIR / "mygpt.db")


def get_connection():
    conn = sqlite3.connect(
        DB_NAME,
        check_same_thread=False,
        timeout=30.0,
    )
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 30000")
    return conn


# ==============================
# USERS TABLE
# ==============================

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

# Add project_id to conversations (nullable — NULL means non-project chat)
try:
    cursor.execute(
        "ALTER TABLE conversations ADD COLUMN project_id INTEGER DEFAULT NULL"
    )
except sqlite3.OperationalError:
    pass

# NOTE: conversations with NULL user_id are NOT reassigned to any user.
# They are inaccessible via get_conversations() (which filters by user_id)
# and will not appear in any user's conversation list.
# Do NOT auto-assign orphaned records to a real user — that is a data
# isolation violation.


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

# ==============================
# PROJECTS TABLE
# ==============================

cursor.execute("""
CREATE TABLE IF NOT EXISTS projects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    description TEXT DEFAULT '',
    user_id INTEGER NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS project_files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    filename TEXT NOT NULL,
    file_path TEXT NOT NULL,
    file_type TEXT NOT NULL,
    file_size INTEGER NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
""")

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


def get_conversation_project_id(chat_id):
    """Return the project_id linked to a conversation, or None."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        "SELECT project_id FROM conversations WHERE id = ?",
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


# ==============================
# PROJECTS TABLE
# ==============================

def create_project(user_id, title, description=""):
    """Create a new project owned by *user_id*. Returns the new project id."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        INSERT INTO projects (title, description, user_id)
        VALUES (?, ?, ?)
        """,
        (title, description, user_id)
    )

    project_id = cursor.lastrowid
    conn.commit()
    conn.close()

    return project_id


def get_projects(user_id):
    """Return all projects owned by *user_id*, newest first."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, title, description, user_id, created_at, updated_at
        FROM projects
        WHERE user_id = ?
        ORDER BY id DESC
    """, (user_id,))

    rows = cursor.fetchall()
    conn.close()

    return [
        {
            "id": row[0],
            "title": row[1],
            "description": row[2] or "",
            "user_id": row[3],
            "created_at": row[4],
            "updated_at": row[5],
        }
        for row in rows
    ]


def get_project(project_id, user_id):
    """Return a single project if it belongs to *user_id*, else None."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, title, description, user_id, created_at, updated_at
        FROM projects
        WHERE id = ? AND user_id = ?
    """, (project_id, user_id))

    row = cursor.fetchone()
    conn.close()

    if row is None:
        return None

    return {
        "id": row[0],
        "title": row[1],
        "description": row[2] or "",
        "user_id": row[3],
        "created_at": row[4],
        "updated_at": row[5],
    }


def update_project(project_id, user_id, title, description=""):
    """Update a project's title/description. Returns True if updated."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        "UPDATE projects SET title = ?, description = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ? AND user_id = ?",
        (title, description, project_id, user_id)
    )

    conn.commit()
    updated = cursor.rowcount > 0
    conn.close()

    return updated


def get_project_owner(project_id):
    """Return the user_id that owns the project, or None."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        "SELECT user_id FROM projects WHERE id = ?",
        (project_id,)
    )

    row = cursor.fetchone()
    conn.close()

    return row[0] if row else None


def delete_project(project_id, user_id):
    """Delete a project and all associated data (conversations, files)."""
    conn = get_connection()
    cursor = conn.cursor()

    # Verify ownership
    cursor.execute(
        "SELECT id FROM projects WHERE id = ? AND user_id = ?",
        (project_id, user_id)
    )

    if cursor.fetchone() is None:
        conn.close()
        return False

    # Get all conversation ids for this project
    cursor.execute(
        "SELECT id FROM conversations WHERE project_id = ?",
        (project_id,)
    )
    chat_ids = [row[0] for row in cursor.fetchall()]

    # Delete chats for all project conversations
    for chat_id in chat_ids:
        cursor.execute("DELETE FROM chats WHERE chat_id = ?", (chat_id,))

    # Delete project conversations
    cursor.execute("DELETE FROM conversations WHERE project_id = ?", (project_id,))

    # Delete project files
    cursor.execute("DELETE FROM project_files WHERE project_id = ?", (project_id,))

    # Delete project itself
    cursor.execute("DELETE FROM projects WHERE id = ?", (project_id,))

    conn.commit()
    conn.close()

    return True


def get_project_conversations(project_id, user_id):
    """Return all conversations within a project (ownership verified)."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT c.id, c.title
        FROM conversations c
        JOIN projects p ON c.project_id = p.id
        WHERE c.project_id = ? AND p.user_id = ?
        ORDER BY c.id DESC
    """, (project_id, user_id))

    rows = cursor.fetchall()
    conn.close()

    return [
        {"chat_id": row[0], "title": row[1]}
        for row in rows
    ]


def create_project_conversation(project_id, user_id, title="New Chat"):
    """Create a conversation linked to a project. Verifies ownership."""
    conn = get_connection()
    cursor = conn.cursor()

    # Verify project ownership
    cursor.execute(
        "SELECT id FROM projects WHERE id = ? AND user_id = ?",
        (project_id, user_id)
    )

    if cursor.fetchone() is None:
        conn.close()
        raise ValueError("Project not found or not owned by user")

    cursor.execute(
        """
        INSERT INTO conversations (user_id, title, project_id)
        VALUES (?, ?, ?)
        """,
        (user_id, title, project_id)
    )

    chat_id = cursor.lastrowid
    conn.commit()
    conn.close()

    return chat_id


def save_project_file(project_id, user_id, filename, file_path, file_type, file_size):
    """Record a file associated with a project. Returns the file record id."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        INSERT INTO project_files (project_id, user_id, filename, file_path, file_type, file_size)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (project_id, user_id, filename, file_path, file_type, file_size)
    )

    file_id = cursor.lastrowid
    conn.commit()
    conn.close()

    return file_id


def get_project_files(project_id, user_id):
    """Return all files for a project (ownership verified via user_id)."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, project_id, user_id, filename, file_path, file_type, file_size, created_at
        FROM project_files
        WHERE project_id = ? AND user_id = ?
        ORDER BY id DESC
    """, (project_id, user_id))

    rows = cursor.fetchall()
    conn.close()

    return [
        {
            "id": row[0],
            "project_id": row[1],
            "user_id": row[2],
            "filename": row[3],
            "file_path": row[4],
            "file_type": row[5],
            "file_size": row[6],
            "created_at": row[7],
        }
        for row in rows
    ]


def get_project_file(file_id, user_id):
    """Return a single file record if owned by *user_id*, else None."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, project_id, user_id, filename, file_path, file_type, file_size, created_at
        FROM project_files
        WHERE id = ? AND user_id = ?
    """, (file_id, user_id))

    row = cursor.fetchone()
    conn.close()

    if row is None:
        return None

    return {
        "id": row[0],
        "project_id": row[1],
        "user_id": row[2],
        "filename": row[3],
        "file_path": row[4],
        "file_type": row[5],
        "file_size": row[6],
        "created_at": row[7],
    }


def delete_project_file(file_id, user_id):
    """Delete a project file. Returns True if deleted."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        "DELETE FROM project_files WHERE id = ? AND user_id = ?",
        (file_id, user_id)
    )

    conn.commit()
    deleted = cursor.rowcount > 0
    conn.close()

    return deleted
