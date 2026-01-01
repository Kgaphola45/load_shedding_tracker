import sqlite3
import tkinter as tk
from tkinter import ttk, messagebox
from hashlib import sha256
import csv

# --- Database Setup ---
conn = sqlite3.connect("load_shedding.db")
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE,
    password TEXT,
    area TEXT
)
""")
conn.commit()


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

mock_schedule = load_schedule_from_csv()

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
            entry.delete(0, tk.END)


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

        ttk.Label(self, text="Area / Suburb").grid(row=3, column=0, sticky="e", padx=5, pady=5)
        self.area_entry = ttk.Entry(self)
        self.area_entry.grid(row=3, column=1, sticky="w", padx=5, pady=5)

        btn_frame = ttk.Frame(self)
        btn_frame.grid(row=4, column=0, columnspan=2, pady=20)

        ttk.Button(btn_frame, text="Sign Up", command=self.register_user).pack(side="left", padx=5)
        ttk.Button(btn_frame, text="Back to Login", command=lambda: controller.show_frame(LoginScreen)).pack(side="left", padx=5)

    def on_show(self):
        self.clear_entries([self.username_entry, self.password_entry, self.area_entry])

    def register_user(self):
        username = self.username_entry.get()
        password = self.password_entry.get()
        area = self.area_entry.get()

        if not username or not password or not area:
            messagebox.showerror("Error", "All fields are required")
            return

        try:
            cursor.execute(
                "INSERT INTO users (username, password, area) VALUES (?, ?, ?)",
                (username, hash_password(password), area)
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

        self.user_id, username, _, area = user
        self.welcome_label.config(text=f"Welcome, {username}")
        self.area_label.config(text=f"Area: {area}")
        self.new_area_entry.delete(0, tk.END)
        self.new_area_entry.insert(0, area)
        
        self.load_schedule(area)

    def load_schedule(self, area):
        self.schedule_list.delete(0, tk.END)
        schedule = mock_schedule.get(area, ["No schedule available for this area"])
        for slot in schedule:
            self.schedule_list.insert(tk.END, slot)

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
        self.controller.current_user = (self.user_id, self.controller.current_user[1], self.controller.current_user[2], new_area)
        
        messagebox.showinfo("Success", "Area updated.")
        self.on_show() # Refresh dashboard


if __name__ == "__main__":
    app = LoadSheddingApp()
    app.mainloop()
