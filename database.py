import sqlite3
import os
from datetime import datetime, timedelta
import csv
from hashlib import sha256

# --- Database Setup ---
conn = sqlite3.connect("load_shedding.db")
cursor = conn.cursor()

def init_db():
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE,
        password TEXT,
        area TEXT,
        role TEXT DEFAULT 'user',
        province TEXT,
        municipality TEXT
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS schedules (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        area TEXT,
        time_slot TEXT
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS stage_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT,
        stage INTEGER
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS user_locations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        name TEXT,
        province TEXT,
        municipality TEXT,
        area TEXT,
        FOREIGN KEY(user_id) REFERENCES users(id)
    )
    """)
    
    # Migrations
    try:
        cursor.execute("ALTER TABLE users ADD COLUMN role TEXT DEFAULT 'user'")
    except sqlite3.OperationalError:
        pass
        
    try:
        cursor.execute("ALTER TABLE users ADD COLUMN province TEXT")
    except sqlite3.OperationalError:
        pass
        
    try:
        cursor.execute("ALTER TABLE users ADD COLUMN municipality TEXT")
    except sqlite3.OperationalError:
        pass
        
    # Migrate existing single locations to user_locations table
    try:
        # Check if users have locations but no entries in user_locations
        cursor.execute("SELECT id, area, province, municipality FROM users WHERE area IS NOT NULL AND area != ''")
        users = cursor.fetchall()
        for user in users:
            uid, area, prov, muni = user
            # Check if this user already has locations (avoid dups on re-run)
            cursor.execute("SELECT COUNT(*) FROM user_locations WHERE user_id=?", (uid,))
            if cursor.fetchone()[0] == 0:
                # Add default location
                prov = prov if prov else "Unknown"
                muni = muni if muni else "Unknown"
                cursor.execute("INSERT INTO user_locations (user_id, name, province, municipality, area) VALUES (?, ?, ?, ?, ?)", 
                               (uid, "Home", prov, muni, area))
        conn.commit()
    except Exception as e:
        print(f"Migration error: {e}")
    
    # Seed Settings & History
    cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('current_stage', '0')")
    
    # Seed History if empty (Mock Data)
    cursor.execute("SELECT COUNT(*) FROM stage_history")
    if cursor.fetchone()[0] == 0:
        now = datetime.now()
        # 60 days ago: Stage 0
        cursor.execute("INSERT INTO stage_history (timestamp, stage) VALUES (?, ?)", ((now - timedelta(days=60)).strftime("%Y-%m-%d %H:%M:%S"), 0))
        # 45 days ago: Stage 4 (Last Month activity)
        cursor.execute("INSERT INTO stage_history (timestamp, stage) VALUES (?, ?)", ((now - timedelta(days=45)).strftime("%Y-%m-%d %H:%M:%S"), 4))
        # 30 days ago: Stage 0 (End of Last Month activity)
        cursor.execute("INSERT INTO stage_history (timestamp, stage) VALUES (?, ?)", ((now - timedelta(days=30)).strftime("%Y-%m-%d %H:%M:%S"), 0))
        # 10 days ago: Stage 2 (This Month activity)
        cursor.execute("INSERT INTO stage_history (timestamp, stage) VALUES (?, ?)", ((now - timedelta(days=10)).strftime("%Y-%m-%d %H:%M:%S"), 2))
        # Today: Ensure current stage is logged
        cursor.execute("INSERT INTO stage_history (timestamp, stage) VALUES (?, ?)", (now.strftime("%Y-%m-%d %H:%M:%S"), 0)) # Default to 0 match settings

    conn.commit()

init_db()

# --- Helper DB Functions ---

def hash_password(password):
    return sha256(password.encode()).hexdigest()

def get_current_stage():
    cursor.execute("SELECT value FROM settings WHERE key='current_stage'")
    result = cursor.fetchone()
    return int(result[0]) if result else 0

def set_current_stage(stage):
    cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('current_stage', ?)", (str(stage),))
    # Log to history
    cursor.execute("INSERT INTO stage_history (timestamp, stage) VALUES (?, ?)", (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), stage))
    conn.commit()

def load_schedule_from_db(area):
    cursor.execute("SELECT time_slot FROM schedules WHERE area=?", (area,))
    rows = cursor.fetchall()
    if rows:
        return [row[0] for row in rows]
    return ["No schedule available for this area"]

def import_csv_to_db(file_path):
    try:
        conn.execute("BEGIN TRANSACTION")
        cursor.execute("DELETE FROM schedules") # Full replace
        
        with open(file_path, newline="", encoding="utf-8") as file:
            reader = csv.DictReader(file)
            for row in reader:
                cursor.execute("INSERT INTO schedules (area, time_slot) VALUES (?, ?)", (row["area"], row["time_slot"]))
        
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e

def seed_admin():
    try:
        # Check if admin exists
        cursor.execute("SELECT * FROM users WHERE username='admin'")
        if not cursor.fetchone():
            cursor.execute(
                "INSERT INTO users (username, password, area, role, province, municipality) VALUES (?, ?, ?, ?, ?, ?)",
                ("admin", hash_password("admin123"), "Admin Area", "admin", "System", "System")
            )
            conn.commit()
            print("Admin user seeded.")
        else:
            # Ensure existing admin has valid new fields
            cursor.execute(
                "UPDATE users SET role='admin', province='System', municipality='System' WHERE username='admin' AND province IS NULL"
            )
            conn.commit()
            print("Admin user updated.")
    except Exception as e:
        print(f"Error seeding admin: {e}")

def add_user_location(user_id, name, province, municipality, area):
    cursor.execute(
        "INSERT INTO user_locations (user_id, name, province, municipality, area) VALUES (?, ?, ?, ?, ?)",
        (user_id, name, province, municipality, area)
    )
    conn.commit()

def get_user_locations(user_id):
    cursor.execute("SELECT id, name, province, municipality, area FROM user_locations WHERE user_id=?", (user_id,))
    return cursor.fetchall()

def delete_user_location(location_id, user_id):
    cursor.execute("DELETE FROM user_locations WHERE id=? AND user_id=?", (location_id, user_id))
    conn.commit()

def update_user_location(location_id, user_id, name, province, municipality, area):
    cursor.execute(
        "UPDATE user_locations SET name=?, province=?, municipality=?, area=? WHERE id=? AND user_id=?",
        (name, province, municipality, area, location_id, user_id)
    )
    conn.commit()

# Initial Migration from CSV on Startup if DB is empty
def migrate_csv_to_db_if_empty():
    cursor.execute("SELECT COUNT(*) FROM schedules")
    if cursor.fetchone()[0] == 0:
        if os.path.exists("load_shedding_schedule.csv"):
            print("Migrating initial CSV to DB...")
            # We skip validation for the initial bootstrap or assume it's valid/partial
            # Or we can just run the import
            try:
                import_csv_to_db("load_shedding_schedule.csv")
                print("Migration complete.")
            except Exception as e:
                print(f"Migration failed: {e}")

migrate_csv_to_db_if_empty()
seed_admin()
