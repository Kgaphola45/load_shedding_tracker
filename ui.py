import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import sqlite3
import random
from database import cursor, conn, hash_password, get_current_stage, set_current_stage, load_schedule_from_db, import_csv_to_db, add_user_location, get_user_locations, delete_user_location, update_user_location, get_setting, set_setting
from utils import LOCATIONS, validate_csv, calculate_next_outage, get_analytics
import sys 
import os
import winshell
from win32com.client import Dispatch
from datetime import datetime

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
        
        # Settings Button (Top Right)
        ttk.Button(self, text="⚙️", width=3, command=self.open_settings).place(relx=1.0, rely=0.0, anchor="ne", x=-10, y=10)

        # Location Selector Frame
        loc_frame = ttk.Frame(self)
        loc_frame.grid(row=1, column=0, pady=(0, 5))
        
        ttk.Label(loc_frame, text="Location:").pack(side="left", padx=5)
        self.location_var = tk.StringVar()
        self.location_selector = ttk.Combobox(loc_frame, textvariable=self.location_var, state="readonly", width=30)
        self.location_selector.pack(side="left", padx=5)
        self.location_selector.bind("<<ComboboxSelected>>", self.on_location_change)
        
        ttk.Button(loc_frame, text="+", width=3, command=self.open_add_location).pack(side="left", padx=2)
        ttk.Button(loc_frame, text="-", width=3, command=self.delete_current_location).pack(side="left", padx=2)
        
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

        # Update Area Section (Now Edit Current Location)
        self.update_frame = ttk.LabelFrame(self, text="Edit Selected Location", padding=10)
        self.update_frame.grid(row=4, column=0, pady=15, sticky="ew", padx=10)
        self.update_frame.columnconfigure(1, weight=1)
        
        self.setup_cascading_combos(self.update_frame, row_start=0)
        
        ttk.Button(self.update_frame, text="Save Changes", command=self.save_location_changes).grid(row=3, column=0, columnspan=2, pady=10)
        
        # Analytics Button
        ttk.Button(self, text="View History & Analytics", command=self.show_analytics).grid(row=5, column=0, pady=(10, 5))
        
        # Calendar Button
        ttk.Button(self, text="View Calendar", command=self.show_calendar).grid(row=6, column=0, pady=5)

        ttk.Button(self, text="Logout", command=lambda: controller.show_frame(LoginScreen)).grid(row=7, column=0, pady=10)

    def open_add_location(self):
        AddLocationWindow(self)

    def open_settings(self):
        SettingsWindow(self)

    def delete_current_location(self):
        if not self.current_location_data:
            return
            
        if messagebox.askyesno("Confirm", f"Delete location '{self.current_location_data['name']}'?"):
            delete_user_location(self.current_location_data['id'], self.user_id)
            self.on_show() # Refresh

    def on_location_change(self, event):
        selection = self.location_selector.get()
        # Find data
        target = next((loc for loc in self.locations if f"{loc[1]} - {loc[4]}" == selection or loc[1] == selection), None)
        if target:
            # target: id, name, province, municipality, area
            self.current_location_data = {
                'id': target[0],
                'name': target[1],
                'province': target[2],
                'municipality': target[3],
                'area': target[4]
            }
            # Update UI
            self.refresh_for_location()
    
    def refresh_for_location(self):
        data = self.current_location_data
        
        # Pre-fill update combos
        self.province_cb.set(data['province'] if data['province'] in LOCATIONS else '')
        self.municipality_cb.set(data['municipality']) 
        
        # Trigger updates
        if data['province'] in LOCATIONS:
            self.on_province_change(None)
            self.municipality_cb.set(data['municipality'])
            if data['municipality'] in LOCATIONS[data['province']]:
                 self.on_municipality_change(None)
                 self.area_cb.set(data['area'])

        current_stage = get_current_stage()
        self.load_schedule(data['area'], current_stage)
        self.update_timer()

    def show_calendar(self):
        if not self.current_location_data:
             return
        user_area = self.current_location_data['area']
        CalendarWindow(self, user_area)

    def show_analytics(self):
        if not self.current_location_data:
             return
        user_area = self.current_location_data['area']
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

        # Unpack user
        try:
            # Fetch fresh from DB
            cursor.execute("SELECT * FROM users WHERE id=?", (user[0],))
            user = cursor.fetchone()
            self.controller.current_user = user 
            
            # Helper to safely unpack (id, username, password, area, role, province, municipality)
            self.user_id = user[0]
            username = user[1]
            role = user[4] if len(user) > 4 else "user"
                
        except Exception:
            self.user_id = user[0]
            username = "User"
            role = "user"

        self.welcome_label.config(text=f"Welcome, {username} ({role})")
        
        # Load User Locations
        self.locations = get_user_locations(self.user_id)
        if not self.locations:
            # Should not happen due to migration, but safety check
            self.locations = []
            
        # Update Selector
        # Format: "Name - Area"
        loc_values = [f"{loc[1]} - {loc[4]}" for loc in self.locations]
        self.location_selector['values'] = loc_values
        
        if self.locations:
            self.location_selector.current(0)
            self.on_location_change(None)
        else:
            self.current_location_data = None
            self.location_selector.set('')
            
        self.setup_admin_controls(role)
        
    def update_timer(self):
        # Cancel existing timer if any to avoid duplicates
        if hasattr(self, 'timer_id') and self.timer_id:
            self.after_cancel(self.timer_id)
            
        stage = get_current_stage()
        if stage == 0 or not self.current_location_data:
            self.countdown_label.config(text="")
        else:
            area = self.current_location_data['area']
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
            
            # Update Tray Icon Status
            is_power_on = (state != "ACTIVE")
            self.controller.tray.update_status(is_power_on)
        
        # Schedule next update in 60s
        self.timer_id = self.after(60000, self.update_timer)

    def check_alerts(self, seconds_diff, next_start_dt):
        if not next_start_dt:
            return
            
        alerts_enabled = get_setting('alerts_enabled', 'True') == 'True'
        if not alerts_enabled:
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
            
            # Simulator
            ttk.Button(self.admin_frame, text="⚡ Simulator", command=self.open_simulator).pack(side="left", padx=15)

    def open_simulator(self):
        SimulatorWindow(self)

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

    def save_location_changes(self):
        if not self.current_location_data:
            return

        province = self.province_cb.get()
        municipality = self.municipality_cb.get()
        area = self.area_cb.get()
        
        if not area or not province or not municipality:
            messagebox.showerror("Error", "Please select all location fields")
            return

        update_user_location(self.current_location_data['id'], self.user_id, self.current_location_data['name'], province, municipality, area)
        
        messagebox.showinfo("Success", "Location updated.")
        self.on_show() # Refresh dashboard


class AddLocationWindow(tk.Toplevel):
    def __init__(self, parent_dashboard):
        super().__init__(parent_dashboard)
        self.title("Add New Location")
        self.geometry("400x350")
        self.parent = parent_dashboard
        
        ttk.Label(self, text="Add New Location", font=("Segoe UI", 14, "bold")).pack(pady=10)
        
        frm = ttk.Frame(self, padding=20)
        frm.pack(fill="both", expand=True)

        # Name
        ttk.Label(frm, text="Location Name (e.g. Work)").grid(row=0, column=0, sticky="w", pady=5)
        self.name_entry = ttk.Entry(frm, width=30)
        self.name_entry.grid(row=1, column=0, sticky="w", pady=(0, 10))
        
        # Cascading
        self.setup_cascading_combos(frm, 2)
        
        ttk.Button(frm, text="Save Location", command=self.save).grid(row=5, column=0, pady=20)

    def setup_cascading_combos(self, parent_frame, row_start):
        # Local impl to reuse existing logic but customized layout if needed, 
        # but easier to just copy logic or instantiate a helper if we were strict.
        # Function hijacking from BaseFrame since we can't easily inherit because we are Toplevel + Base logic mixed.
        # Actually, let's just duplicate the setup for simplicity or use a helper class.
        # We can call the helper method if we make this class inherit helper or just manual.
        
        # Province
        ttk.Label(parent_frame, text="Province").grid(row=row_start, column=0, sticky="w", pady=5)
        self.province_cb = ttk.Combobox(parent_frame, state="readonly", values=list(LOCATIONS.keys()), width=30)
        self.province_cb.grid(row=row_start+1, column=0, sticky="w", pady=(0, 10))
        self.province_cb.bind("<<ComboboxSelected>>", self.on_province_change)

        # Municipality
        ttk.Label(parent_frame, text="Municipality").grid(row=row_start+2, column=0, sticky="w", pady=5)
        self.municipality_cb = ttk.Combobox(parent_frame, state="readonly", width=30)
        self.municipality_cb.grid(row=row_start+3, column=0, sticky="w", pady=(0, 10))
        self.municipality_cb.bind("<<ComboboxSelected>>", self.on_municipality_change)

        # Area
        ttk.Label(parent_frame, text="Area").grid(row=row_start+4, column=0, sticky="w", pady=5)
        self.area_cb = ttk.Combobox(parent_frame, state="readonly", width=30)
        self.area_cb.grid(row=row_start+5, column=0, sticky="w", pady=(0, 10))
        
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
            
    def save(self):
        name = self.name_entry.get()
        province = self.province_cb.get()
        municipality = self.municipality_cb.get()
        area = self.area_cb.get()
        
        if not name or not province or not municipality or not area:
            messagebox.showerror("Error", "All fields are required")
            return
            
        add_user_location(self.parent.user_id, name, province, municipality, area)
        self.parent.on_show() # Refresh parent
        self.destroy()


class SimulatorWindow(tk.Toplevel):
    def __init__(self, parent_app):
        super().__init__(parent_app)
        self.title("Eskom Stage Simulator")
        self.geometry("300x200")
        self.parent_app = parent_app
        self.running = False
        self.timer_id = None
        
        ttk.Label(self, text="⚡ Stage Simulator", font=("Segoe UI", 12, "bold")).pack(pady=10)
        
        self.status_var = tk.StringVar(value="Status: Idle")
        ttk.Label(self, textvariable=self.status_var).pack(pady=5)
        
        btn_frame = ttk.Frame(self)
        btn_frame.pack(pady=10)
        
        ttk.Button(btn_frame, text="Random Mode (5s)", command=lambda: self.start_simulation(5000)).pack(fill="x", pady=2)
        ttk.Button(btn_frame, text="Stress Test (0.5s)", command=lambda: self.start_simulation(500)).pack(fill="x", pady=2)
        ttk.Button(btn_frame, text="Stop", command=self.stop_simulation).pack(fill="x", pady=2)
        
    def start_simulation(self, interval_ms):
        if self.running:
            self.stop_simulation()
            
        self.running = True
        self.status_var.set(f"Running (Interval: {interval_ms}ms)")
        self.run_cycle(interval_ms)
        
    def stop_simulation(self):
        self.running = False
        if self.timer_id:
            self.after_cancel(self.timer_id)
            self.timer_id = None
        self.status_var.set("Status: Stopped")
        
    def run_cycle(self, interval_ms):
        if not self.running:
            return
            
        # Pick random stage 0-8
        new_stage = random.randint(0, 8)
        set_current_stage(new_stage)
        
        # access Dashboard instance via parent_app.frames
        dashboard = self.parent_app.frames[Dashboard]
        dashboard.on_show()
        
        # Schedule next
        self.timer_id = self.after(interval_ms, lambda: self.run_cycle(interval_ms))

class SettingsWindow(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title("Settings")
        self.geometry("400x300")
        
        ttk.Label(self, text="Settings", font=("Segoe UI", 14, "bold")).pack(pady=10)
        
        self.frm = ttk.Frame(self, padding=20)
        self.frm.pack(fill="both", expand=True)
        
        # Alerts
        self.alerts_var = tk.BooleanVar(value=get_setting('alerts_enabled', 'True') == 'True')
        ttk.Checkbutton(self.frm, text="Enable 30-min Alerts", variable=self.alerts_var).grid(row=0, column=0, sticky="w", pady=10)
        
        # Startup
        self.startup_var = tk.BooleanVar(value=get_setting('run_on_startup', 'False') == 'True')
        ttk.Checkbutton(self.frm, text="Run on Windows Startup", variable=self.startup_var).grid(row=1, column=0, sticky="w", pady=10)
        
        # Theme
        ttk.Label(self.frm, text="Theme (Requires Restart)").grid(row=2, column=0, sticky="w", pady=(10, 5))
        self.theme_var = tk.StringVar(value=get_setting('theme', 'Light'))
        self.theme_cb = ttk.Combobox(self.frm, textvariable=self.theme_var, values=["Light", "Dark"], state="readonly")
        self.theme_cb.grid(row=3, column=0, sticky="w", pady=5)
        
        # Save
        ttk.Button(self.frm, text="Save Settings", command=self.save_settings).grid(row=4, column=0, pady=20)
        
    def save_settings(self):
        set_setting('alerts_enabled', str(self.alerts_var.get()))
        set_setting('theme', self.theme_var.get())
        
        # Handle Startup Logic
        current_startup = get_setting('run_on_startup', 'False') == 'True'
        new_startup = self.startup_var.get()
        
        if new_startup != current_startup:
            set_setting('run_on_startup', str(new_startup))
            self.toggle_startup(new_startup)
            
        messagebox.showinfo("Success", "Settings saved.")
        self.destroy()
        
    def toggle_startup(self, enable):
        try:
            startup_folder = os.path.join(os.getenv("APPDATA"), r"Microsoft\Windows\Start Menu\Programs\Startup")
            shortcut_path = os.path.join(startup_folder, "LoadSheddingTracker.lnk")
            
            if enable:
                target = sys.executable
                # Assuming main.py is in the current working directory or same dir as this file
                # Better to get absolute path of main.py
                script_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "main.py")
                
                # Create shortcut
                shell = Dispatch('WScript.Shell')
                shortcut = shell.CreateShortCut(shortcut_path)
                shortcut.Targetpath = target
                shortcut.Arguments = f'"{script_path}"'
                shortcut.WorkingDirectory = os.path.dirname(script_path)
                shortcut.IconLocation = target
                shortcut.save()
            else:
                if os.path.exists(shortcut_path):
                    os.remove(shortcut_path)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to modify startup settings: {e}")

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
