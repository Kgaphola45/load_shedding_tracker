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
        
    conn.commit()

init_db()

# --- Helper Functions ---
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
        update_frame = ttk.Frame(self)
        update_frame.grid(row=3, column=0, pady=15)

        ttk.Label(update_frame, text="Update Area:").pack(side="left", padx=5)
        self.new_area_entry = ttk.Entry(update_frame)
        self.new_area_entry.pack(side="left", padx=5)
        ttk.Button(update_frame, text="Update", command=self.update_area).pack(side="left", padx=5)

        ttk.Button(self, text="Logout", command=lambda: controller.show_frame(LoginScreen)).grid(row=4, column=0, pady=10)

    def on_show(self):
        user = self.controller.current_user
        if not user:
            return # Should not happen

        # Unpack user including role (now 5 columns)
        # Handle cases where existing DB usage might vary, but we standardized on 5 columns in schema update
        try:
            self.user_id, username, _, area, role = user
        except ValueError:
            # Fallback for old sessions or inconsistent state if 4 items
            if len(user) == 4:
                self.user_id, username, _, area = user
                role = 'user'
            else:
                self.user_id, username, _, area, role = user[0], user[1], user[2], user[3], user[4]

        self.welcome_label.config(text=f"Welcome, {username} ({role})")
        self.area_label.config(text=f"Area: {area}")
        self.new_area_entry.delete(0, tk.END)
        self.new_area_entry.insert(0, area)
        
        self.load_schedule(area)
        self.setup_admin_controls(role)

    def load_schedule(self, area):
        self.schedule_list.delete(0, tk.END)
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
            
            ttk.Button(self.admin_frame, text="Upload Schedule CSV", command=self.upload_csv).pack(side="left", padx=5)
            # Placeholder for Edit Stages - for now Upload CSV covers schedule updates
            # ttk.Button(self.admin_frame, text="Edit Stages", state="disabled").pack(side="left", padx=5)

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
                self.load_schedule(self.new_area_entry.get()) # Reload current view
                messagebox.showinfo("Success", "Schedule updated successfully!")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to upload CSV: {e}")

    def update_area(self):
        new_area = self.new_area_entry.get()
        if not new_area:
            messagebox.showerror("Error", "Area cannot be empty")
            return

        cursor.execute(
            "UPDATE users SET area=? WHERE id=?",
            (new_area, self.user_id)
        )
        conn.commit()
        
        # Update current user session data
        # We need to preserve the role. unpacking again to be safe.
        # current_user tuple: (id, username, password, area, role)
        # We only updated area (index 3)
        c_user = list(self.controller.current_user)
        # Ensure it has 5 elements; if 4, append 'user'
        if len(c_user) == 4:
            c_user.append('user')
            
        c_user[3] = new_area
        self.controller.current_user = tuple(c_user)
        
        messagebox.showinfo("Success", "Area updated.")
        self.on_show() # Refresh dashboard


if __name__ == "__main__":
    app = LoadSheddingApp()
    app.mainloop()
