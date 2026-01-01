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