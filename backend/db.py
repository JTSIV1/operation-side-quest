import sqlite3
import uuid

DB_FILE = "users.db"

def init_db():
    """Initialize the database with the users table."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            email TEXT UNIQUE NOT NULL,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            first_name TEXT,
            last_name TEXT
        )
    """)
    conn.commit()
    conn.close()

def create_user(email, username, password, first_name, last_name):
    """Creates a new user and returns their UUID. Returns None if email/username exists."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    user_id = str(uuid.uuid4())
    try:
        cursor.execute("""
            INSERT INTO users (id, email, username, password, first_name, last_name)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (user_id, email, username, password, first_name, last_name))
        conn.commit()
        return user_id
    except sqlite3.IntegrityError:
        return None
    finally:
        conn.close()

def verify_user(email, password):
    """Checks credentials and returns UUID if valid, else None."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM users WHERE email = ? AND password = ?", (email, password))
    row = cursor.fetchone()
    conn.close()
    if row:
        return row[0]
    return None