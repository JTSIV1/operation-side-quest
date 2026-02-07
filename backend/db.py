import sqlite3
import uuid
from datetime import datetime

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
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS routes (
            route_id TEXT PRIMARY KEY,
            owner_id TEXT NOT NULL,
            num_stops INTEGER,
            completed INTEGER DEFAULT 0,
            time_completed TEXT,
            route_data TEXT,
            FOREIGN KEY(owner_id) REFERENCES users(id)
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS route_participants (
            route_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            PRIMARY KEY (route_id, user_id),
            FOREIGN KEY(route_id) REFERENCES routes(route_id),
            FOREIGN KEY(user_id) REFERENCES users(id)
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

def create_route(owner_id, route_data_json, num_stops):
    """Creates a new route entry."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    route_id = str(uuid.uuid4())
    try:
        cursor.execute("""
            INSERT INTO routes (route_id, owner_id, num_stops, completed, time_completed, route_data)
            VALUES (?, ?, ?, 0, NULL, ?)
        """, (route_id, owner_id, num_stops, route_data_json))
        conn.commit()
        return route_id
    except Exception as e:
        return None
    finally:
        conn.close()

def get_user_routes(user_id):
    """Retrieves all routes for a given user."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT DISTINCT r.route_id, r.num_stops, r.completed, r.time_completed, r.route_data, r.owner_id, u.first_name, u.last_name
        FROM routes r
        JOIN users u ON r.owner_id = u.id
        LEFT JOIN route_participants rp ON r.route_id = rp.route_id
        WHERE r.owner_id = ? OR rp.user_id = ?
        ORDER BY r.rowid DESC
    """, (user_id, user_id))
    rows = cursor.fetchall()
    conn.close()
    
    routes = []
    for r in rows:
        routes.append({
            "route_id": r[0],
            "num_stops": r[1],
            "completed": bool(r[2]),
            "time_completed": r[3],
            "route_data": r[4],
            "is_owner": (r[5] == user_id),
            "owner_name": f"{r[6]} {r[7]}"
        })
    return routes

def delete_route(route_id, user_id):
    """Deletes a route if owner, or removes self if participant."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    try:
        # Check ownership
        cursor.execute("SELECT owner_id FROM routes WHERE route_id = ?", (route_id,))
        row = cursor.fetchone()
        if not row:
            return "Route not found"
        
        owner_id = row[0]
        if owner_id == user_id:
            # Delete everything
            cursor.execute("DELETE FROM route_participants WHERE route_id = ?", (route_id,))
            cursor.execute("DELETE FROM routes WHERE route_id = ?", (route_id,))
        else:
            # Just remove participant
            cursor.execute("DELETE FROM route_participants WHERE route_id = ? AND user_id = ?", (route_id, user_id))
        
        conn.commit()
        return "Success"
    except Exception as e:
        return str(e)
    finally:
        conn.close()

def toggle_route_completion(route_id, completed):
    """Updates the completion status of a route."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    time_str = datetime.now().isoformat() if completed else None
    cursor.execute("UPDATE routes SET completed = ?, time_completed = ? WHERE route_id = ?", (1 if completed else 0, time_str, route_id))
    conn.commit()
    conn.close()

def add_route_participant(route_id, friend_email):
    """Adds a user to a route by email."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM users WHERE email = ?", (friend_email,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return "User not found"
    
    friend_id = row[0]
    try:
        cursor.execute("INSERT INTO route_participants (route_id, user_id) VALUES (?, ?)", (route_id, friend_id))
        conn.commit()
        return "Success"
    except sqlite3.IntegrityError:
        return "User already added"
    finally:
        conn.close()

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

def get_route_participants(route_id):
    """Returns a list of users participating in a route."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    query = """
        SELECT u.id, u.email, u.username, u.first_name, u.last_name
        FROM users u
        JOIN route_participants rp ON u.id = rp.user_id
        WHERE rp.route_id = ?
    """
    cursor.execute(query, (route_id,))
    rows = cursor.fetchall()
    conn.close()
    return [
        {"id": r[0], "email": r[1], "username": r[2], "first_name": r[3], "last_name": r[4]}
        for r in rows
    ]

def remove_route_participant(route_id, user_id):
    """Removes a specific user from a route."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM route_participants WHERE route_id = ? AND user_id = ?", (route_id, user_id))
        conn.commit()
        return "Success"
    except Exception as e:
        return str(e)
    finally:
        conn.close()