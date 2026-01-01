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