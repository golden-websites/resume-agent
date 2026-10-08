import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash

# security: salted password hashes (werkzeug ships with Flask)
def hash_password(password):
    return generate_password_hash(password)

def check_password(password, password_hash):
    return check_password_hash(password_hash, password)

def get_connection():
    connection = sqlite3.connect(
        "/app/database/resume.db"
    )

    connection.execute(
        "PRAGMA foreign_keys = ON"
    )

    return connection

def create_table():
    connection = get_connection()
    cursor = connection.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            email TEXT NOT NULL UNIQUE,
            password TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS resumes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            data TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS conversations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            resume_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (resume_id) REFERENCES resumes(id)
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id INTEGER NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY (conversation_id) REFERENCES conversations(id)
        )
    """)
    connection.commit()
    connection.close()

def create_user(username, email, password):
    connection = get_connection()
    cursor = connection.cursor()
    password_hash = hash_password(password)
    cursor.execute("""
        INSERT INTO users (username, email, password)
        VALUES (?, ?, ?)
    """, (username, email, password_hash))
    connection.commit()
    connection.close()

def get_user_by_email(email):
    connection = get_connection()
    cursor = connection.cursor()
    cursor.execute(
        "SELECT id, username, email, password FROM users WHERE email = ?",
        (email,)
    )
    user = cursor.fetchone()
    connection.close()
    return user

def get_user_by_id(user_id):
    connection = get_connection()
    cursor = connection.cursor()
    cursor.execute(
        """
        SELECT id, username, email
        FROM users
        WHERE id = ?
        """,
        (user_id,)
    )
    user = cursor.fetchone()
    connection.close()
    return user

def create_resume(user_id, data):
    connection = get_connection()
    cursor = connection.cursor()
    cursor.execute("""
        INSERT INTO resumes (user_id, data)
        VALUES (?, ?)
    """, (user_id, data))
    connection.commit()
    resume_id = cursor.lastrowid
    connection.close()
    return resume_id

def get_resumes_by_user(user_id):
    connection = get_connection()
    cursor = connection.cursor()
    cursor.execute("""
        SELECT id, data, created_at, updated_at
        FROM resumes
        WHERE user_id = ?
        ORDER BY updated_at DESC
    """, (user_id,))
    resumes = cursor.fetchall()
    connection.close()
    return resumes

def get_resume_by_id(resume_id, user_id):
    connection = get_connection()
    cursor = connection.cursor()
    cursor.execute("""
        SELECT id, user_id, data, created_at, updated_at
        FROM resumes
        WHERE id = ? AND user_id = ?
    """, (resume_id, user_id))
    resume = cursor.fetchone()
    connection.close()
    return resume

def update_resume(resume_id, user_id, data):
    connection = get_connection()
    cursor = connection.cursor()
    cursor.execute("""
        UPDATE resumes
        SET data = ?, updated_at = CURRENT_TIMESTAMP
        WHERE id = ? AND user_id = ?
    """, (data, resume_id, user_id))
    connection.commit()
    connection.close()

def create_conversation(user_id, resume_id, title):
    connection = get_connection()
    cursor = connection.cursor()
    cursor.execute("""
        INSERT INTO conversations (
            user_id,
            resume_id,
            title
        )
        VALUES (?, ?, ?)
    """, (user_id, resume_id, title))
    connection.commit()
    conversation_id = cursor.lastrowid
    connection.close()
    return conversation_id

def get_conversations_by_user(user_id):
    connection = get_connection()
    cursor = connection.cursor()
    cursor.execute("""
        SELECT id, resume_id, title, created_at, updated_at
        FROM conversations
        WHERE user_id = ?
        ORDER BY updated_at DESC
    """, (user_id,))
    conversations = cursor.fetchall()
    connection.close()
    return conversations

def get_conversation_by_id(conversation_id, user_id):
    connection = get_connection()
    cursor = connection.cursor()
    cursor.execute("""
        SELECT id, user_id, resume_id, title, created_at, updated_at
        FROM conversations
        WHERE id = ? AND user_id = ?
    """, (conversation_id, user_id))
    conversation = cursor.fetchone()
    connection.close()
    return conversation

def update_conversation_time(conversation_id, user_id):
    connection = get_connection()
    cursor = connection.cursor()
    cursor.execute("""
        UPDATE conversations
        SET updated_at = CURRENT_TIMESTAMP
        WHERE id = ? AND user_id = ?
    """, (conversation_id, user_id))
    connection.commit()
    connection.close()

def save_message(conversation_id, role, content):
    connection = get_connection()
    cursor = connection.cursor()
    cursor.execute("""
        INSERT INTO messages (
            conversation_id,
            role,
            content
        )
        VALUES (?, ?, ?)
    """, (conversation_id, role, content))
    connection.commit()
    message_id = cursor.lastrowid
    connection.close()
    return message_id

def get_messages(conversation_id):
    connection = get_connection()
    cursor = connection.cursor()
    cursor.execute("""
        SELECT id, role, content, created_at
        FROM messages
        WHERE conversation_id = ?
        ORDER BY id ASC
    """, (conversation_id,))
    messages = cursor.fetchall()
    connection.close()
    return messages


# ---------------------------------------------------------------------------
# CHANGED: new functions (conversation reuse + deletes)
# ---------------------------------------------------------------------------

def get_latest_conversation_by_resume(resume_id, user_id):
    connection = get_connection()
    cursor = connection.cursor()
    cursor.execute("""
        SELECT id, user_id, resume_id, title, created_at, updated_at
        FROM conversations
        WHERE resume_id = ? AND user_id = ?
        ORDER BY updated_at DESC, id DESC
        LIMIT 1
    """, (resume_id, user_id))
    conversation = cursor.fetchone()
    connection.close()
    return conversation

def get_conversations_by_resume(resume_id, user_id):
    connection = get_connection()
    cursor = connection.cursor()
    cursor.execute("""
        SELECT id, resume_id, title, created_at, updated_at
        FROM conversations
        WHERE resume_id = ? AND user_id = ?
        ORDER BY updated_at DESC, id DESC
    """, (resume_id, user_id))
    conversations = cursor.fetchall()
    connection.close()
    return conversations

def delete_conversation(conversation_id, user_id):
    """Deletes a conversation and its messages. Returns False if the
    conversation does not exist or belongs to someone else."""
    connection = get_connection()
    try:
        cursor = connection.cursor()
        cursor.execute(
            "SELECT id FROM conversations WHERE id = ? AND user_id = ?",
            (conversation_id, user_id)
        )
        if cursor.fetchone() is None:
            return False
        cursor.execute(
            "DELETE FROM messages WHERE conversation_id = ?",
            (conversation_id,)
        )
        cursor.execute(
            "DELETE FROM conversations WHERE id = ? AND user_id = ?",
            (conversation_id, user_id)
        )
        connection.commit()
        return True
    finally:
        connection.close()

def delete_resume(resume_id, user_id):
    """Deletes a resume, its conversations and their messages.
    Returns False if the resume does not exist or belongs to someone else."""
    connection = get_connection()
    try:
        cursor = connection.cursor()
        cursor.execute(
            "SELECT id FROM resumes WHERE id = ? AND user_id = ?",
            (resume_id, user_id)
        )
        if cursor.fetchone() is None:
            return False
        cursor.execute("""
            DELETE FROM messages
            WHERE conversation_id IN (
                SELECT id FROM conversations
                WHERE resume_id = ? AND user_id = ?
            )
        """, (resume_id, user_id))
        cursor.execute(
            "DELETE FROM conversations WHERE resume_id = ? AND user_id = ?",
            (resume_id, user_id)
        )
        cursor.execute(
            "DELETE FROM resumes WHERE id = ? AND user_id = ?",
            (resume_id, user_id)
        )
        connection.commit()
        return True
    finally:
        connection.close()
