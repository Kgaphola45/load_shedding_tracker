import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from hashlib import sha256
import csv
import shutil
import sqlite3
import os
from datetime import datetime, timedelta

# --- Data Sources ---
LOCATIONS = {
    "Gauteng": {
        "City of Johannesburg": ["Sandton", "Soweto", "Johannesburg", "Midrand", "Roodepoort", "Randburg"],
        "City of Tshwane": ["Pretoria", "Centurion"],
        "Ekurhuleni": ["Benoni", "Boksburg", "Kempton Park", "Germiston", "Alberton", "Springs", "Brakpan"],
        "Mogale City": ["Krugersdorp"],
        "Emfuleni": ["Vereeniging"]
    },
    "Limpopo": {
        "Polokwane": ["Polokwane"]
    }
}

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

# --- Helper Functions ---
import re

def get_current_stage():
    cursor.execute("SELECT value FROM settings WHERE key='current_stage'")
    result = cursor.fetchone()
    return int(result[0]) if result else 0

def set_current_stage(stage):
    cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('current_stage', ?)", (str(stage),))
    # Log to history
    cursor.execute("INSERT INTO stage_history (timestamp, stage) VALUES (?, ?)", (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), stage))
    conn.commit()

def calculate_daily_outage_hours(area):
    """Calcs total hours per day for a given area based on schedule slots."""
    schedule = load_schedule_from_db(area)
    total_hours = 0.0
    for slot in schedule:
        try:
            start_str, end_str = slot.split(" - ")
            start_dt = datetime.strptime(start_str, "%H:%M")
            end_dt = datetime.strptime(end_str, "%H:%M")
            
            diff = (end_dt - start_dt).seconds / 3600
            if diff < 0: diff += 24 # Handle wrap around if needed, though usually dealt with in delta
            total_hours += diff
        except ValueError:
            pass
    return total_hours

def get_analytics(area):
    now = datetime.now()
    
    # Time Ranges
    start_this_week = now - timedelta(days=now.weekday()) # Monday
    start_this_week = start_this_week.replace(hour=0, minute=0, second=0, microsecond=0)
    
    start_this_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    
    last_month_end = start_this_month - timedelta(seconds=1)
    start_last_month = last_month_end.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    
    daily_hours = calculate_daily_outage_hours(area)
    
    def calculate_hours_in_range(start_date, end_date):
        total = 0
        current = start_date
        while current <= end_date:
            # Find stage active on 'current' day
            # Get last stage change before end of 'current' day
            day_end_str = current.replace(hour=23, minute=59, second=59).strftime("%Y-%m-%d %H:%M:%S")
            cursor.execute("SELECT stage FROM stage_history WHERE timestamp <= ? ORDER BY timestamp DESC LIMIT 1", (day_end_str,))
            res = cursor.fetchone()
            stage = res[0] if res else 0
            
            if stage > 0:
                total += daily_hours
            
            current += timedelta(days=1)
        return total

    return {
        "this_week": calculate_hours_in_range(start_this_week, now),
        "this_month": calculate_hours_in_range(start_this_month, now),
        "last_month": calculate_hours_in_range(start_last_month, last_month_end)
    }

def hash_password(password):
    return sha256(password.encode()).hexdigest()

def get_valid_areas():
    areas = set()
    for prov in LOCATIONS:
        for muni in LOCATIONS[prov]:
            for area in LOCATIONS[prov][muni]:
                areas.add(area)
    return areas

def validate_csv(file_path):
    time_pattern = re.compile(r"^([0-1]?[0-9]|2[0-3]):[0-5][0-9]\s*-\s*([0-1]?[0-9]|2[0-3]):[0-5][0-9]$")
    valid_areas = get_valid_areas()
    
    try:
        with open(file_path, newline="", encoding="utf-8") as file:
            reader = csv.DictReader(file)
            if "area" not in reader.fieldnames or "time_slot" not in reader.fieldnames:
                return False, "CSV missing 'area' or 'time_slot' columns"
            
            for line_num, row in enumerate(reader, start=2): # Start 2 to account for header
                area = row.get("area", "").strip()
                time_slot = row.get("time_slot", "").strip()
                
                if area not in valid_areas:
                    # In a real app we might relax this or allow adding new areas dynamically. 
                    # For now, strict validation as requested.
                    return False, f"Row {line_num}: Unknown area '{area}'"
                
                if not time_pattern.match(time_slot):
                    return False, f"Row {line_num}: Invalid time format '{time_slot}'. Expected HH:MM - HH:MM"
                    
    except Exception as e:
        return False, f"Error reading CSV: {e}"

    return True, None

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

def load_schedule_from_db(area):
    cursor.execute("SELECT time_slot FROM schedules WHERE area=?", (area,))
    rows = cursor.fetchall()
    if rows:
        return [row[0] for row in rows]
    return ["No schedule available for this area"]

# --- Datetime Logic ---
from datetime import datetime, timedelta

def calculate_next_outage(schedule_slots):
    """
    Returns (state, hours, minutes, seconds_diff, next_start_dt)
    state: "ACTIVE", "FUTURE", "NONE"
    """
    if not schedule_slots or schedule_slots == ["No schedule available for this area"]:
        return "NONE", 0, 0, 0, None
        
    now = datetime.now()
    today_str = now.strftime("%Y-%m-%d")
    tomorrow = now + timedelta(days=1)
    tomorrow_str = tomorrow.strftime("%Y-%m-%d")
    
    upcoming_diffs = []
    current_active = None

    for slot in schedule_slots:
        try:
            start_str, end_str = slot.split(" - ")
            
            # Create datetime objects for today
            start_dt = datetime.strptime(f"{today_str} {start_str}", "%Y-%m-%d %H:%M")
            end_dt = datetime.strptime(f"{today_str} {end_str}", "%Y-%m-%d %H:%M")
            
            # Handle "Current" outage wrap-around (e.g. 22:00 - 00:30)
            if end_dt < start_dt:
                end_dt += timedelta(days=1)
                
            if start_dt <= now < end_dt:
                time_left = end_dt - now
                hours, remainder = divmod(time_left.seconds, 3600)
                minutes = remainder // 60
                return "ACTIVE", hours, minutes, time_left.total_seconds(), start_dt

            # Handle "Future" outage (Today)
            if start_dt > now:
                upcoming_diffs.append((start_dt - now, start_dt))
            
            # Handle "Tomorrow" (Recurrence)
            start_dt_tom = datetime.strptime(f"{tomorrow_str} {start_str}", "%Y-%m-%d %H:%M")
            upcoming_diffs.append((start_dt_tom - now, start_dt_tom))
            
        except ValueError:
            continue
            
    if not upcoming_diffs:
        return "NONE", 0, 0, 0, None
        
    # Find smallest positive diff
    upcoming_diffs.sort()
    diff, next_dt = upcoming_diffs[0]
    
    hours, remainder = divmod(diff.seconds, 3600)
    minutes = remainder // 60
    hours += diff.days * 24
    
    return "FUTURE", hours, minutes, diff.total_seconds(), next_dt

def get_next_outage_countdown(schedule_slots):
    state, hours, minutes, _, _ = calculate_next_outage(schedule_slots)
    
    if state == "ACTIVE":
        return f"CURRENTLY ACTIVE (Ends in {hours}h {minutes}m)"
    elif state == "FUTURE":
        return f"Next outage in {hours}h {minutes}m"
    else:
        return "No upcoming outages"

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

mock_schedule = {} # Deprecated

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

seed_admin()


# --- Main Application Class ---
class LoadSheddingApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Load Shedding Tracker")
        self.geometry("500x500")
        self.resizable(False, False)
        
        # Configure Styles
        self.style = ttk.Style(self)
        self.style.theme_use('clam') # 'clam' usually looks cleaner than default on Windows if 'vista'/'winnative' isn't great
        
        self.style.configure("TLabel", font=("Segoe UI", 11))
        self.style.configure("Title.TLabel", font=("Segoe UI", 20, "bold"), foreground="#333")
        self.style.configure("Header.TLabel", font=("Segoe UI", 12, "bold"))
        self.style.configure("TButton", font=("Segoe UI", 10), padding=6)
        self.style.configure("TEntry", padding=5)

        self.container = ttk.Frame(self)
        self.container.pack(side="top", fill="both", expand=True)
        self.container.grid_rowconfigure(0, weight=1)
        self.container.grid_columnconfigure(0, weight=1)

        self.frames = {}
        self.current_user = None

        for F in (LoginScreen, RegisterScreen, Dashboard):
            frame = F(self.container, self)
            self.frames[F] = frame
            frame.grid(row=0, column=0, sticky="nsew")

        self.show_frame(LoginScreen)

    def show_frame(self, cont):
        frame = self.frames[cont]
        if hasattr(frame, "on_show"):
            frame.on_show()
        frame.tkraise()
    
    def set_user(self, user):
        self.current_user = user


class BaseFrame(ttk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent, padding="20 20 20 20")
        self.controller = controller

    def clear_entries(self, entries):
        for entry in entries:
            if isinstance(entry, ttk.Combobox):
                entry.set('')
            else:
                entry.delete(0, tk.END)

    def setup_cascading_combos(self, parent_frame, row_start):
        # Province
        ttk.Label(parent_frame, text="Province").grid(row=row_start, column=0, sticky="e", padx=5, pady=5)
        self.province_cb = ttk.Combobox(parent_frame, state="readonly", values=list(LOCATIONS.keys()))
        self.province_cb.grid(row=row_start, column=1, sticky="w", padx=5, pady=5)
        self.province_cb.bind("<<ComboboxSelected>>", self.on_province_change)

        # Municipality
        ttk.Label(parent_frame, text="Municipality").grid(row=row_start+1, column=0, sticky="e", padx=5, pady=5)
        self.municipality_cb = ttk.Combobox(parent_frame, state="readonly")
        self.municipality_cb.grid(row=row_start+1, column=1, sticky="w", padx=5, pady=5)
        self.municipality_cb.bind("<<ComboboxSelected>>", self.on_municipality_change)

        # Area
        ttk.Label(parent_frame, text="Area / Suburb").grid(row=row_start+2, column=0, sticky="e", padx=5, pady=5)
        self.area_cb = ttk.Combobox(parent_frame, state="readonly")
        self.area_cb.grid(row=row_start+2, column=1, sticky="w", padx=5, pady=5)

    def on_province_change(self, event):
        province = self.province_cb.get()
        if province in LOCATIONS:
            municipalities = list(LOCATIONS[province].keys())
            self.municipality_cb['values'] = municipalities
            self.municipality_cb.set('')
            self.area_cb['values'] = []
            self.area_cb.set('')

    def on_municipality_change(self, event):
        province = self.province_cb.get()
        municipality = self.municipality_cb.get()
        if province in LOCATIONS and municipality in LOCATIONS[province]:
            areas = LOCATIONS[province][municipality]
            self.area_cb['values'] = areas
            self.area_cb.set('')


class LoginScreen(BaseFrame):
    def __init__(self, parent, controller):
        super().__init__(parent, controller)
        
        # Center content
        self.columnconfigure(0, weight=1)
        self.columnconfigure(1, weight=1)

        ttk.Label(self, text="Login", style="Title.TLabel").grid(row=0, column=0, columnspan=2, pady=(0, 20))

        ttk.Label(self, text="Username").grid(row=1, column=0, sticky="e", padx=5, pady=5)
        self.username_entry = ttk.Entry(self)
        self.username_entry.grid(row=1, column=1, sticky="w", padx=5, pady=5)

        ttk.Label(self, text="Password").grid(row=2, column=0, sticky="e", padx=5, pady=5)
        self.password_entry = ttk.Entry(self, show="*")
        self.password_entry.grid(row=2, column=1, sticky="w", padx=5, pady=5)
        self.password_entry.bind("<Return>", lambda event: self.login_user())

        btn_frame = ttk.Frame(self)
        btn_frame.grid(row=3, column=0, columnspan=2, pady=20)
        
        ttk.Button(btn_frame, text="Login", command=self.login_user).pack(side="left", padx=5)
        ttk.Button(btn_frame, text="Register", command=lambda: controller.show_frame(RegisterScreen)).pack(side="left", padx=5)

    def on_show(self):
        self.clear_entries([self.username_entry, self.password_entry])

    def login_user(self):
        username = self.username_entry.get()
        password = self.password_entry.get()

        cursor.execute(
            "SELECT * FROM users WHERE username=? AND password=?",
            (username, hash_password(password))
        )
        user = cursor.fetchone()

        if user:
            self.controller.set_user(user)
            self.controller.show_frame(Dashboard)
        else:
            messagebox.showerror("Error", "Invalid username or password")


class RegisterScreen(BaseFrame):
    def __init__(self, parent, controller):
        super().__init__(parent, controller)
        
        self.columnconfigure(0, weight=1)
        self.columnconfigure(1, weight=1)

        ttk.Label(self, text="Register", style="Title.TLabel").grid(row=0, column=0, columnspan=2, pady=(0, 20))

        ttk.Label(self, text="Username").grid(row=1, column=0, sticky="e", padx=5, pady=5)
        self.username_entry = ttk.Entry(self)
        self.username_entry.grid(row=1, column=1, sticky="w", padx=5, pady=5)

        ttk.Label(self, text="Password").grid(row=2, column=0, sticky="e", padx=5, pady=5)
        self.password_entry = ttk.Entry(self, show="*")
        self.password_entry.grid(row=2, column=1, sticky="w", padx=5, pady=5)

        # Cascading Locators
        self.setup_cascading_combos(self, row_start=3)
        # Note: setup_cascading_combos uses row 3, 4, 5

        btn_frame = ttk.Frame(self)
        btn_frame.grid(row=6, column=0, columnspan=2, pady=20)

        ttk.Button(btn_frame, text="Sign Up", command=self.register_user).pack(side="left", padx=5)
        ttk.Button(btn_frame, text="Back to Login", command=lambda: controller.show_frame(LoginScreen)).pack(side="left", padx=5)

    def on_show(self):
        self.clear_entries([self.username_entry, self.password_entry])
        # Reset combos
        self.province_cb.set('')
        self.municipality_cb.set('')
        self.municipality_cb['values'] = []
        self.area_cb.set('')
        self.area_cb['values'] = []

    def register_user(self):
        username = self.username_entry.get()
        password = self.password_entry.get()
        province = self.province_cb.get()
        municipality = self.municipality_cb.get()
        area = self.area_cb.get()

        if not username or not password or not area or not province or not municipality:
            messagebox.showerror("Error", "All fields are required")
            return

        try:
            cursor.execute(
                "INSERT INTO users (username, password, area, role, province, municipality) VALUES (?, ?, ?, ?, ?, ?)",
                (username, hash_password(password), area, 'user', province, municipality)
            )
            conn.commit()
            messagebox.showinfo("Success", "Registration successful!")
            self.controller.show_frame(LoginScreen)
        except sqlite3.IntegrityError:
            messagebox.showerror("Error", "Username already exists")


class Dashboard(BaseFrame):
    def __init__(self, parent, controller):
        super().__init__(parent, controller)
        self.columnconfigure(0, weight=1)

        self.welcome_label = ttk.Label(self, text="", style="Title.TLabel")
        self.welcome_label.grid(row=0, column=0, pady=(0, 5))

        self.area_label = ttk.Label(self, text="", style="Header.TLabel")
        self.area_label.grid(row=1, column=0, pady=(0, 5))
        
        # Countdown Label
        self.countdown_label = ttk.Label(self, text="", font=("Segoe UI", 12, "bold"), foreground="red")
        self.countdown_label.grid(row=2, column=0, pady=(0, 15))

        # Schedule Container
        schedule_frame = ttk.LabelFrame(self, text="Load Shedding Schedule", padding=10)
        schedule_frame.grid(row=3, column=0, sticky="nsew", padx=10, pady=5)
        schedule_frame.columnconfigure(0, weight=1)
        self.rowconfigure(3, weight=1) # Allow schedule to expand

        self.schedule_list = tk.Listbox(schedule_frame, font=("Segoe UI", 10), height=8, bd=0, highlightthickness=0)
        self.schedule_list.pack(side="left", fill="both", expand=True)
        
        scrollbar = ttk.Scrollbar(schedule_frame, orient="vertical", command=self.schedule_list.yview)
        scrollbar.pack(side="right", fill="y")
        self.schedule_list.config(yscrollcommand=scrollbar.set)

        # Update Area Section
        self.update_frame = ttk.LabelFrame(self, text="Update Location", padding=10)
        self.update_frame.grid(row=4, column=0, pady=15, sticky="ew", padx=10)
        self.update_frame.columnconfigure(1, weight=1)
        
        # We reuse the cascading logic, but we need to bind to the self.update_frame
        # Since setup_cascading_combos creates attributes like self.province_cb which would overwrite each other if used blindly locally,
        # but since Dashboard and RegisterScreen are different instances, it's fine.
        
        self.setup_cascading_combos(self.update_frame, row_start=0)
        
        ttk.Button(self.update_frame, text="Update Location", command=self.update_area).grid(row=3, column=0, columnspan=2, pady=10)
        
        # Analytics Button
        ttk.Button(self, text="View History & Analytics", command=self.show_analytics).grid(row=5, column=0, pady=(10, 5))
        
        # Calendar Button
        ttk.Button(self, text="View Calendar", command=self.show_calendar).grid(row=6, column=0, pady=5)

        ttk.Button(self, text="Logout", command=lambda: controller.show_frame(LoginScreen)).grid(row=7, column=0, pady=10)

    def show_calendar(self):
        user_area = self.area_cb.get()
        if not user_area or user_area == "Unknown":
            messagebox.showinfo("Calendar", "Please set your location first.")
            return
            
        CalendarWindow(self, user_area)

    def show_analytics(self):
        user_area = self.area_cb.get()
        if not user_area or user_area == "Unknown":
            messagebox.showinfo("Analytics", "Please set your location first.")
            return
            
        stats = get_analytics(user_area)
        
        # Create Toplevel Window
        top = tk.Toplevel(self)
        top.title("Outage History & Analytics")
        top.geometry("400x400")
        
        ttk.Label(top, text="Outage Statistics", font=("Segoe UI", 16, "bold")).pack(pady=20)
        
        # This Week
        f1 = ttk.LabelFrame(top, text="This Week (Since Mon)", padding=10)
        f1.pack(fill="x", padx=20, pady=5)
        ttk.Label(f1, text=f"{stats['this_week']:.1f} Hours", font=("Segoe UI", 14, "bold"), foreground="Orange").pack()
        
        # Month Comparison
        f2 = ttk.LabelFrame(top, text="Monthly Comparison", padding=10)
        f2.pack(fill="x", padx=20, pady=5)
        
        # Grid layout for month compare
        ttk.Label(f2, text="This Month:").grid(row=0, column=0, sticky="e", padx=5)
        ttk.Label(f2, text=f"{stats['this_month']:.1f} Hours", font=("Segoe UI", 12, "bold")).grid(row=0, column=1, sticky="w")
        
        ttk.Label(f2, text="Last Month:").grid(row=1, column=0, sticky="e", padx=5)
        ttk.Label(f2, text=f"{stats['last_month']:.1f} Hours", font=("Segoe UI", 12, "bold")).grid(row=1, column=1, sticky="w")
        
        # Comparison logic
        diff = stats['this_month'] - stats['last_month']
        color = "red" if diff > 0 else "green"
        indicator = "▲" if diff > 0 else "▼" if diff < 0 else "="
        
        ttk.Label(f2, text=f"Diff: {diff:+.1f}h {indicator}", foreground=color).grid(row=2, column=0, columnspan=2, pady=5)

    def on_show(self):
        user = self.controller.current_user
        if not user:
            return 

        # Unpack user. Format depends on DB, but standardized to 7 cols now:
        # id, username, password, area, role, province, municipality
        try:
            # Fetch fresh from DB to ensure we get all cols if schema changed
            cursor.execute("SELECT * FROM users WHERE id=?", (user[0],))
            user = cursor.fetchone()
            self.controller.current_user = user # Update session
            
            # Helper to safely unpack
            if len(user) == 7:
                 self.user_id, username, _, area, role, province, municipality = user
            elif len(user) == 5: # Older schema
                 self.user_id, username, _, area, role = user
                 province, municipality = "Unknown", "Unknown"
            else: # Fallback or 4 items
                self.user_id = user[0]
                username = user[1]
                area = user[3]
                role = 'user'
                province, municipality = "Unknown", "Unknown"
                
        except Exception:
            self.user_id = user[0]
            username = "User"
            area = "Unknown"
            role = "user"
            province, municipality = "Unknown", "Unknown"

        self.welcome_label.config(text=f"Welcome, {username} ({role})")
        
        # Current Stage Display
        current_stage = get_current_stage()
        stage_color = "green" if current_stage == 0 else "orange" if current_stage < 5 else "red"
        stage_text = f"Current Status: Stage {current_stage}" if current_stage > 0 else "Current Status: Suspended (Stage 0)"
        
        self.area_label.config(text=f"{province} > {municipality} > {area}\n{stage_text}", foreground=stage_color)
        
        # Pre-fill update combos if possible
        self.province_cb.set(province if province in LOCATIONS else '')
        self.municipality_cb.set(municipality) 
        self.area_cb.set(area)
        
        # Trigger updates to populate lists
        if province in LOCATIONS:
            self.on_province_change(None)
            self.municipality_cb.set(municipality)
            if municipality in LOCATIONS[province]:
                 self.on_municipality_change(None)
                 self.area_cb.set(area)

        self.load_schedule(area, current_stage)
        self.setup_admin_controls(role)
        
        # Start Countdown Timer
        self.update_timer()

    def update_timer(self):
        # Cancel existing timer if any to avoid duplicates
        if hasattr(self, 'timer_id') and self.timer_id:
            self.after_cancel(self.timer_id)
            
        stage = get_current_stage()
        if stage == 0:
            self.countdown_label.config(text="")
        else:
            area = self.area_cb.get()
            schedule = load_schedule_from_db(area)
            
            # Refactored usage
            state, hours, minutes, seconds_diff, next_start = calculate_next_outage(schedule)
            
            if state == "ACTIVE":
                countdown_text = f"CURRENTLY ACTIVE (Ends in {hours}h {minutes}m)"
            elif state == "FUTURE":
                countdown_text = f"Next outage in {hours}h {minutes}m"
                # Check for alerts
                self.check_alerts(seconds_diff, next_start)
            else:
                countdown_text = "No upcoming outages"
            
            self.countdown_label.config(text=countdown_text)
        
        # Schedule next update in 60s
        self.timer_id = self.after(60000, self.update_timer)

    def check_alerts(self, seconds_diff, next_start_dt):
        if not next_start_dt:
            return
            
        # Alert between 29 and 30 minutes (inclusive of 30, exclusive of 29 for strict window)
        # 30 mins = 1800 seconds. 
        # Range: 1740 < seconds <= 1800 (Capture the minute window)
        if 1740 < seconds_diff <= 1800:
            # Dedup using class attribute
            if hasattr(self, 'last_alert_time') and self.last_alert_time == next_start_dt:
                return # Already alerted for this specific slot
            
            self.last_alert_time = next_start_dt
            self.trigger_alert()

    def trigger_alert(self):
        print(f"ALERT: Load Shedding starts in 30 minutes! ({datetime.now().strftime('%H:%M:%S')})")
        messagebox.showwarning("Load Shedding Alert", "⚠️ Power will go off in 30 minutes! Prepare now!")

    def load_schedule(self, area, stage=None):
        if stage is None:
            stage = get_current_stage()

        self.schedule_list.delete(0, tk.END)
        
        if stage == 0:
            self.schedule_list.insert(tk.END, "No Load Shedding currently active.")
            return

        schedule = load_schedule_from_db(area)
        for slot in schedule:
            self.schedule_list.insert(tk.END, slot)

    def setup_admin_controls(self, role):
        # Clear previous admin controls if any
        if hasattr(self, 'admin_frame'):
            self.admin_frame.destroy()

        if role == 'admin':
            self.admin_frame = ttk.LabelFrame(self, text="Admin Controls", padding=10)
            self.admin_frame.grid(row=7, column=0, sticky="ew", padx=10, pady=10)
            
            # CSV Upload
            ttk.Button(self.admin_frame, text="Upload Schedule CSV", command=self.upload_csv).pack(side="left", padx=5)
            
            # Stage Selector
            ttk.Label(self.admin_frame, text="Stage:").pack(side="left", padx=(15, 5))
            self.stage_var = tk.StringVar(value=str(get_current_stage()))
            self.stage_cb = ttk.Combobox(self.admin_frame, textvariable=self.stage_var, values=[str(i) for i in range(9)], width=3, state="readonly")
            self.stage_cb.pack(side="left", padx=5)
            ttk.Button(self.admin_frame, text="Set", command=self.update_stage).pack(side="left", padx=5)

    def update_stage(self):
        try:
            new_stage = int(self.stage_cb.get())
            set_current_stage(new_stage)
            messagebox.showinfo("Success", f"Stage updated to {new_stage}")
            self.on_show() # Refresh entire dashboard to update colors/schedule
        except ValueError:
             messagebox.showerror("Error", "Invalid stage")

    def upload_csv(self):
        file_path = filedialog.askopenfilename(filetypes=[("CSV Files", "*.csv")])
        if file_path:
            # 1. Validate
            is_valid, error_msg = validate_csv(file_path)
            if not is_valid:
                messagebox.showerror("Validation Error", f"CSV Validation Failed:\n{error_msg}")
                return

            # 2. Import
            try:
                import_csv_to_db(file_path)
                messagebox.showinfo("Success", "Schedule updated and imported to database successfully!")
                self.on_show() # Refresh current view
            except Exception as e:
                messagebox.showerror("Error", f"Failed to import to DB: {e}")

    def update_area(self):
        province = self.province_cb.get()
        municipality = self.municipality_cb.get()
        area = self.area_cb.get()
        
        if not area or not province or not municipality:
            messagebox.showerror("Error", "Please select all location fields")
            return

        cursor.execute(
            "UPDATE users SET area=?, province=?, municipality=? WHERE id=?",
            (area, province, municipality, self.user_id)
        )
        conn.commit()
        
        messagebox.showinfo("Success", "Location updated.")
        self.on_show() # Refresh dashboard


class CalendarWindow(tk.Toplevel):
    def __init__(self, parent, area):
        super().__init__(parent)
        self.title(f"Weekly Schedule - {area}")
        self.geometry("800x600")
        self.area = area
        
        self.canvas = tk.Canvas(self, bg="white")
        self.canvas.pack(fill="both", expand=True, padx=10, pady=10)
        
        # Determine schedule
        stage = get_current_stage()
        if stage == 0:
            self.schedule = []
            ttk.Label(self, text="Stage 0: No Load Shedding", font=("Segoe UI", 14, "bold"), foreground="green").place(x=20, y=20)
        else:
            self.schedule = load_schedule_from_db(area)
            
        self.draw_calendar()
        
    def draw_calendar(self):
        # Config
        width = 750
        height = 550
        margin_left = 60
        margin_top = 40
        col_width = (width - margin_left) / 7
        row_height = (height - margin_top) / 24
        
        days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        
        # 1. Draw Background (Green = Power On)
        self.canvas.create_rectangle(margin_left, margin_top, width, height, fill="#90EE90", outline="")
        
        # 2. Draw Grid & Axes
        # Y-Axis (Hours)
        for h in range(25):
            y = margin_top + (h * row_height)
            self.canvas.create_text(30, y, text=f"{h:02d}:00", font=("Segoe UI", 8))
            self.canvas.create_line(margin_left, y, width, y, fill="#e0e0e0")
            
        # X-Axis (Days)
        for i, day in enumerate(days):
            x = margin_left + (i * col_width)
            self.canvas.create_text(x + col_width/2, 20, text=day, font=("Segoe UI", 10, "bold"))
            self.canvas.create_line(x, margin_top, x, height, fill="#e0e0e0")
            
        # Right border
        self.canvas.create_line(width, margin_top, width, height, fill="#e0e0e0")
            
        # 3. Draw Outages (Red Blocks)
        # Since schedule is daily recurring for now, we draw the same blocks for all 7 days
        for slot in self.schedule:
            try:
                start_str, end_str = slot.split(" - ")
                start_h, start_m = map(int, start_str.split(":"))
                end_h, end_m = map(int, end_str.split(":"))
                
                # Convert to Y pixels
                # Time = H + M/60. Y = margin + Time * row_height
                start_y = margin_top + (start_h + start_m/60) * row_height
                end_y = margin_top + (end_h + end_m/60) * row_height
                
                # Handle Wrap Around (e.g. 22:00 to 00:30)
                # If end_time (00:30) is "sort of" smaller than start_time (22:00) in numeric value on a 24h clock,
                # actually logic: if end < start, it means it crosses midnight.
                
                blocks = []
                if (end_h + end_m/60) < (start_h + start_m/60):
                    # Block 1: Start to 24:00
                    blocks.append((start_y, margin_top + 24 * row_height, f"{start_str} - 24:00"))
                    # Block 2: 00:00 to End
                    blocks.append((margin_top, end_y, f"00:00 - {end_str}"))
                else:
                    blocks.append((start_y, end_y, slot))
                
                # Draw for each day
                for i in range(7):
                    x1 = margin_left + (i * col_width)
                    x2 = x1 + col_width
                    
                    for y1, y2, text in blocks:
                        # Rect
                        self.canvas.create_rectangle(x1, y1, x2, y2, fill="#FF4444", outline="white")
                        # Text (centered)
                        mid_y = (y1 + y2) / 2
                        self.canvas.create_text((x1+x2)/2, mid_y, text=text, font=("Segoe UI", 8), fill="white")
                        
            except ValueError:
                continue

if __name__ == "__main__":
    app = LoadSheddingApp()
    app.mainloop()
