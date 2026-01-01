import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from hashlib import sha256
import csv
import shutil
import sqlite3
import os

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
    
    # Seed Settings
    cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('current_stage', '0')")

    conn.commit()

init_db()

# --- Helper Functions ---
def get_current_stage():
    cursor.execute("SELECT value FROM settings WHERE key='current_stage'")
    result = cursor.fetchone()
    return int(result[0]) if result else 0

def set_current_stage(stage):
    cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('current_stage', ?)", (str(stage),))
    conn.commit()

def hash_password(password):
    return sha256(password.encode()).hexdigest()

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


# --- Helper Functions ---
def load_schedule_from_csv(filename="load_shedding_schedule.csv"):
    schedule = {}
    try:
        with open(filename, newline="", encoding="utf-8") as file:
            reader = csv.DictReader(file)
            for row in reader:
                area = row["area"]
                time_slot = row["time_slot"]

                if area not in schedule:
                    schedule[area] = []
                schedule[area].append(time_slot)
    except FileNotFoundError:
        # We will handle the warning in the UI if needed
        pass
    return schedule

mock_schedule = {}

def refresh_schedule():
    global mock_schedule
    mock_schedule = load_schedule_from_csv()

refresh_schedule()

def hash_password(password):
    return sha256(password.encode()).hexdigest()


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
        self.area_label.grid(row=1, column=0, pady=(0, 15))

        # Schedule Container
        schedule_frame = ttk.LabelFrame(self, text="Load Shedding Schedule", padding=10)
        schedule_frame.grid(row=2, column=0, sticky="nsew", padx=10, pady=5)
        schedule_frame.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1) # Allow schedule to expand

        self.schedule_list = tk.Listbox(schedule_frame, font=("Segoe UI", 10), height=8, bd=0, highlightthickness=0)
        self.schedule_list.pack(side="left", fill="both", expand=True)
        
        scrollbar = ttk.Scrollbar(schedule_frame, orient="vertical", command=self.schedule_list.yview)
        scrollbar.pack(side="right", fill="y")
        self.schedule_list.config(yscrollcommand=scrollbar.set)

        # Update Area Section
        self.update_frame = ttk.LabelFrame(self, text="Update Location", padding=10)
        self.update_frame.grid(row=3, column=0, pady=15, sticky="ew", padx=10)
        self.update_frame.columnconfigure(1, weight=1)
        
        # We reuse the cascading logic, but we need to bind to the self.update_frame
        # Since setup_cascading_combos creates attributes like self.province_cb which would overwrite each other if used blindly locally,
        # but since Dashboard and RegisterScreen are different instances, it's fine.
        
        self.setup_cascading_combos(self.update_frame, row_start=0)
        
        ttk.Button(self.update_frame, text="Update Location", command=self.update_area).grid(row=3, column=0, columnspan=2, pady=10)

        ttk.Button(self, text="Logout", command=lambda: controller.show_frame(LoginScreen)).grid(row=4, column=0, pady=10)

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

    def load_schedule(self, area, stage=None):
        if stage is None:
            stage = get_current_stage()

        self.schedule_list.delete(0, tk.END)
        
        if stage == 0:
            self.schedule_list.insert(tk.END, "No Load Shedding currently active.")
            return

        schedule = mock_schedule.get(area, ["No schedule available for this area"])
        for slot in schedule:
            self.schedule_list.insert(tk.END, slot)

    def setup_admin_controls(self, role):
        # Clear previous admin controls if any
        if hasattr(self, 'admin_frame'):
            self.admin_frame.destroy()

        if role == 'admin':
            self.admin_frame = ttk.LabelFrame(self, text="Admin Controls", padding=10)
            self.admin_frame.grid(row=5, column=0, sticky="ew", padx=10, pady=10)
            
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
            try:
                # Validate CSV structure roughly? Or just copy.
                # Simple copy for now.
                target_path = "load_shedding_schedule.csv"
                try:
                    # Backup old
                    shutil.copy(target_path, target_path + ".bak")
                except FileNotFoundError:
                    pass
                
                shutil.copy(file_path, target_path)
                refresh_schedule()
                self.on_show() # Refresh to update view
                messagebox.showinfo("Success", "Schedule updated successfully!")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to upload CSV: {e}")

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


if __name__ == "__main__":
    app = LoadSheddingApp()
    app.mainloop()
