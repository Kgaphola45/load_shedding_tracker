import tkinter as tk
from tkinter import ttk
from ui import LoginScreen, RegisterScreen, Dashboard
from tray import TrayIcon
from database import get_setting

# --- Main Application Class ---
class LoadSheddingApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Load Shedding Tracker")
        self.geometry("600x750")
        self.resizable(True, True)
        
        # System Tray Logic
        self.protocol("WM_DELETE_WINDOW", self.minimize_to_tray)
        self.tray = TrayIcon(self)
        self.tray.run()
        
        # Configure Styles
        self.style = ttk.Style(self)
        self.style.theme_use('clam') 
        
        # Apply Theme
        self.apply_theme()

    def apply_theme(self):
        theme = get_setting('theme', 'Light')
        
        if theme == 'Dark':
            bg_color = "#2b2b2b"
            fg_color = "#ffffff"
            entry_bg = "#404040"
            entry_fg = "#ffffff"
            active_bg = "#505050"
        else:
            bg_color = "#f0f0f0"
            fg_color = "#000000"
            entry_bg = "#ffffff"
            entry_fg = "#000000"
            active_bg = "#e0e0e0"

        # General
        self.configure(bg=bg_color)
        self.style.configure(".", background=bg_color, foreground=fg_color)
        self.style.configure("TFrame", background=bg_color)
        self.style.configure("TLabel", background=bg_color, foreground=fg_color, font=("Segoe UI", 11))
        self.style.configure("Title.TLabel", font=("Segoe UI", 20, "bold"), foreground=fg_color, background=bg_color)
        self.style.configure("Header.TLabel", font=("Segoe UI", 12, "bold"), foreground=fg_color, background=bg_color)
        self.style.configure("TLabelframe", background=bg_color, foreground=fg_color)
        self.style.configure("TLabelframe.Label", background=bg_color, foreground=fg_color)
        
        self.style.configure("TButton", font=("Segoe UI", 10), padding=6, background=active_bg, foreground=fg_color)
        self.style.map("TButton", background=[('active', active_bg)])
        
        self.style.configure("TEntry", fieldbackground=entry_bg, foreground=entry_fg, padding=5)
        self.style.map("TEntry", fieldbackground=[('readonly', entry_bg)])
        
        # Combobox
        self.style.configure("TCombobox", fieldbackground=entry_bg, background=active_bg, foreground=entry_fg)
        self.style.map("TCombobox", fieldbackground=[('readonly', entry_bg)], selectbackground=[('readonly', active_bg)])
        
        # Checkbutton
        self.style.configure("TCheckbutton", background=bg_color, foreground=fg_color)

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

    def minimize_to_tray(self):
        self.withdraw()
        
    def quit_app(self):
        if hasattr(self.tray, 'stop'):
            self.tray.stop()
        self.destroy()

if __name__ == "__main__":
    app = LoadSheddingApp()
    app.mainloop()
