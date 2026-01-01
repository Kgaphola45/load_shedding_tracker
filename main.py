import tkinter as tk
from tkinter import ttk
from ui import LoginScreen, RegisterScreen, Dashboard
from tray import TrayIcon

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

    def minimize_to_tray(self):
        self.withdraw()
        
    def quit_app(self):
        if hasattr(self.tray, 'stop'):
            self.tray.stop()
        self.destroy()

if __name__ == "__main__":
    app = LoadSheddingApp()
    app.mainloop()
