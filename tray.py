import threading
import pystray
from PIL import Image, ImageDraw

class TrayIcon:
    def __init__(self, app):
        self.app = app
        self.icon = None
        self.running = False
        self.last_color = None

    def create_image(self, color):
        width = 64
        height = 64
        image = Image.new('RGB', (width, height), (255, 255, 255))
        dc = ImageDraw.Draw(image)
        # Draw white background
        dc.rectangle((0, 0, width, height), fill=(255, 255, 255))
        # Draw status circle
        fill_color = "#00FF00" if color == "green" else "#FF0000"
        dc.ellipse((10, 10, 54, 54), fill=fill_color, outline=fill_color)
        return image

    def run(self):
        self.running = True
        image = self.create_image("green")
        menu = pystray.Menu(
            pystray.MenuItem("Show", self.show_app),
            pystray.MenuItem("Exit", self.exit_app)
        )
        self.icon = pystray.Icon("LoadSheddingTracker", image, "Load Shedding Tracker", menu)
        # Run in a thread so it doesn't block tkinter
        threading.Thread(target=self.icon.run, daemon=True).start()

    def stop(self):
        if self.icon:
            self.icon.stop()

    def update_status(self, is_power_on):
        if not self.icon: return
        color = "green" if is_power_on else "red"
        
        if self.last_color != color:
            self.last_color = color
            self.icon.icon = self.create_image(color)

    def show_app(self, icon, item):
        self.app.after(0, self.app.deiconify)

    def exit_app(self, icon, item):
        self.icon.stop()
        self.app.after(0, self.app.quit_app)
