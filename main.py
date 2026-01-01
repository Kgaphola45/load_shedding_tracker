import sqlite3
import tkinter as tk
from tkinter import messagebox
from hashlib import sha256
import csv


#DATABASE
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



# loading the CSV
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
        messagebox.showerror("Error", "load_shedding_schedule.csv not found!")
    return schedule

mock_schedule = load_schedule_from_csv()



#helper
def hash_password(password):
    return sha256(password.encode()).hexdigest()

current_user = None

# g
root = tk.Tk()
root.title("Load Shedding Tracker")
root.geometry("400x380")
root.resizable(False, False)

def clear_screen():
    for widget in root.winfo_children():
        widget.destroy()

        

# register
def register_screen():
    clear_screen()

    tk.Label(root, text="Register", font=("Arial", 18)).pack(pady=10)

    tk.Label(root, text="Username").pack()
    username_entry = tk.Entry(root)
    username_entry.pack()

    tk.Label(root, text="Password").pack()
    password_entry = tk.Entry(root, show="*")
    password_entry.pack()

    tk.Label(root, text="Area / Suburb").pack()
    area_entry = tk.Entry(root)
    area_entry.pack()

    def register_user():
        username = username_entry.get()
        password = password_entry.get()
        area = area_entry.get()

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
            login_screen()
        except sqlite3.IntegrityError:
            messagebox.showerror("Error", "Username already exists")

    tk.Button(root, text="Register", command=register_user).pack(pady=10)
    tk.Button(root, text="Back to Login", command=login_screen).pack()


#login feature
def login_screen():
    clear_screen()

    tk.Label(root, text="Login", font=("Arial", 18)).pack(pady=10)

    tk.Label(root, text="Username").pack()
    username_entry = tk.Entry(root)
    username_entry.pack()

    tk.Label(root, text="Password").pack()
    password_entry = tk.Entry(root, show="*")
    password_entry.pack()

    def login_user():
        global current_user
        cursor.execute(
            "SELECT * FROM users WHERE username=? AND password=?",
            (username_entry.get(), hash_password(password_entry.get()))
        )
        user = cursor.fetchone()

        if user:
            current_user = user
            dashboard()
        else:
            messagebox.showerror("Error", "Invalid username or password")

    tk.Button(root, text="Login", command=login_user).pack(pady=10)
    tk.Button(root, text="Register", command=register_screen).pack()