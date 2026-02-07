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
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS friends (
            friend_id_1 TEXT NOT NULL,
            friend_id_2 TEXT NOT NULL,
            PRIMARY KEY (friend_id_1, friend_id_2)
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

def add_friend(user_id, friend_email):
    """Adds a friend row (Friend Request). Returns status string."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    try:
        # Find friend's UUID
        cursor.execute("SELECT id FROM users WHERE email = ?", (friend_email,))
        row = cursor.fetchone()
        if not row:
            return "User not found"
        friend_id = row[0]

        if user_id == friend_id:
            return "Cannot add yourself"

        # Check if relationship already exists
        cursor.execute("SELECT 1 FROM friends WHERE friend_id_1 = ? AND friend_id_2 = ?", (user_id, friend_id))
        if cursor.fetchone():
            return "Request already sent"

        cursor.execute("INSERT INTO friends (friend_id_1, friend_id_2) VALUES (?, ?)", (user_id, friend_id))
        conn.commit()
        return "Success"
    except Exception as e:
        return str(e)
    finally:
        conn.close()

def remove_friend(user_id, friend_id):
    """Removes any relationship between user_id and friend_id."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    try:
        cursor.execute("""
            DELETE FROM friends 
            WHERE (friend_id_1 = ? AND friend_id_2 = ?)
               OR (friend_id_1 = ? AND friend_id_2 = ?)
        """, (user_id, friend_id, friend_id, user_id))
        conn.commit()
        return "Success"
    except Exception as e:
        return str(e)
    finally:
        conn.close()

def _get_users_from_query(query, params):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()
    
    return [
        {"id": r[0], "email": r[1], "username": r[2], "first_name": r[3], "last_name": r[4]}
        for r in rows
    ]

def get_friends(user_id):
    """Returns users where both have added each other."""
    query = """
        SELECT u.id, u.email, u.username, u.first_name, u.last_name
        FROM users u
        JOIN friends f1 ON u.id = f1.friend_id_2
        JOIN friends f2 ON u.id = f2.friend_id_1
        WHERE f1.friend_id_1 = ? AND f2.friend_id_2 = ?
    """
    return _get_users_from_query(query, (user_id, user_id))

def get_incoming_requests(user_id):
    """Returns users who added user_id, but user_id hasn't added them back."""
    query = """
        SELECT u.id, u.email, u.username, u.first_name, u.last_name
        FROM users u
        JOIN friends incoming ON u.id = incoming.friend_id_1
        WHERE incoming.friend_id_2 = ?
        AND u.id NOT IN (
            SELECT friend_id_2 FROM friends WHERE friend_id_1 = ?
        )
    """
    return _get_users_from_query(query, (user_id, user_id))

def get_pending_requests(user_id):
    """Returns users whom user_id added, but they haven't added user_id back."""
    query = """
        SELECT u.id, u.email, u.username, u.first_name, u.last_name
        FROM users u
        JOIN friends outgoing ON u.id = outgoing.friend_id_2
        WHERE outgoing.friend_id_1 = ?
        AND u.id NOT IN (
            SELECT friend_id_1 FROM friends WHERE friend_id_2 = ?
        )
    """
    return _get_users_from_query(query, (user_id, user_id))