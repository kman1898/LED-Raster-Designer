"""
LED Raster Designer - Unified Launcher
Companion-style Tkinter window + menu bar icon (rumps on macOS, pystray on Windows).
On macOS, rumps runs on the main thread (required by NSApplication).
Tkinter window runs on a background thread.
"""
import sys
import os
import threading
import webbrowser
import time
import tkinter as tk
from tkinter import ttk

# Resolve paths for PyInstaller bundle
if getattr(sys, 'frozen', False):
    BASE_DIR = sys._MEIPASS
    APP_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    APP_DIR = BASE_DIR

# Ensure BASE_DIR is on sys.path so we can import app, updater, etc.
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from launcher_settings import (
    load_settings, save_settings, get_network_interfaces, set_run_at_login
)

# ---------------------------------------------------------------------------
# Dark theme colors
# ---------------------------------------------------------------------------
BG = '#1a1a1a'
BG_LIGHT = '#2a2a2a'
FG = '#e0e0e0'
FG_DIM = '#888888'
ACCENT = '#FFD700'
RED = '#e74c3c'
GREEN = '#2ecc71'
BTN_BG = '#333333'
BTN_FG = '#e0e0e0'


class LauncherWindow:
    """Companion-style launcher window with dark theme."""

    def __init__(self, root):
        self.root = root
        self.settings = load_settings()
        self.server_thread = None
        self.server_running = False
        self.tray_icon = None
        self._server_stop_event = threading.Event()

        self._build_ui()
        self._start_server()

        # Handle window close button (X) = Hide
        self.root.protocol('WM_DELETE_WINDOW', self._hide_window)

        if self.settings.get('start_minimized', False):
            self.root.withdraw()

    # ------------------------------------------------------------------
    # UI Construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        root = self.root
        root.title('LED Raster Designer')
        root.geometry('380x460')
        root.configure(bg=BG)
        root.resizable(False, False)

        # Try to set the window icon
        try:
            icon_path = os.path.join(BASE_DIR, 'static', 'favicon.ico')
            if os.path.exists(icon_path):
                root.iconbitmap(icon_path)
        except Exception:
            pass

        # -- Header section --
        header = tk.Frame(root, bg=BG)
        header.pack(fill='x', pady=(20, 5))

        tk.Label(header, text='💡', font=('Arial', 36), bg=BG, fg=ACCENT).pack()
        tk.Label(header, text='LED Raster Designer', font=('Arial', 16, 'bold'),
                 bg=BG, fg=FG).pack()

        # Version
        version = self._get_version()
        tk.Label(header, text=f'v{version}', font=('Arial', 11), bg=BG, fg=FG_DIM).pack()

        # -- Status section --
        status_frame = tk.Frame(root, bg=BG)
        status_frame.pack(fill='x', pady=(15, 5))

        self.status_label = tk.Label(status_frame, text='● Running', font=('Arial', 18),
                                     bg=BG, fg=GREEN)
        self.status_label.pack()

        self.url_label = tk.Label(status_frame, text='', font=('Arial', 12),
                                  bg=BG, fg=FG, cursor='hand2')
        self.url_label.pack(pady=(2, 0))
        self.url_label.bind('<Button-1>', lambda e: self._launch_gui())
        self._update_url_display()

        # -- Separator --
        ttk.Separator(root, orient='horizontal').pack(fill='x', padx=30, pady=10)

        # -- Network Interface & Port --
        config_frame = tk.Frame(root, bg=BG)
        config_frame.pack(fill='x', padx=30)

        # Interface row
        iface_frame = tk.Frame(config_frame, bg=BG)
        iface_frame.pack(fill='x', pady=(0, 8))

        tk.Label(iface_frame, text='Network Interface', font=('Arial', 11),
                 bg=BG, fg=FG_DIM).pack(anchor='w')

        self.interfaces = get_network_interfaces()
        iface_labels = [label for _, label in self.interfaces]
        iface_ips = [ip for ip, _ in self.interfaces]

        self.iface_var = tk.StringVar()
        current_iface = self.settings.get('interface', '127.0.0.1')
        if current_iface in iface_ips:
            idx = iface_ips.index(current_iface)
            self.iface_var.set(iface_labels[idx])
        else:
            self.iface_var.set(iface_labels[0])

        self.iface_combo = ttk.Combobox(iface_frame, textvariable=self.iface_var,
                                         values=iface_labels, state='readonly',
                                         width=35)
        self.iface_combo.pack(fill='x', pady=(2, 0))
        self.iface_combo.bind('<<ComboboxSelected>>', self._on_interface_change)

        # Port row
        port_frame = tk.Frame(config_frame, bg=BG)
        port_frame.pack(fill='x', pady=(0, 5))

        tk.Label(port_frame, text='Port', font=('Arial', 11),
                 bg=BG, fg=FG_DIM).pack(anchor='w')

        port_input_frame = tk.Frame(port_frame, bg=BG)
        port_input_frame.pack(fill='x', pady=(2, 0))

        self.port_var = tk.StringVar(value=str(self.settings.get('port', 8050)))
        self.port_entry = tk.Entry(port_input_frame, textvariable=self.port_var,
                                   width=8, font=('Arial', 12),
                                   bg=BG_LIGHT, fg=FG, insertbackground=FG,
                                   relief='flat', bd=2)
        self.port_entry.pack(side='left')

        self.change_btn = tk.Button(port_input_frame, text='Change',
                                    font=('Arial', 10), bg=BTN_BG, fg=BTN_FG,
                                    relief='flat', bd=0, padx=10, pady=2,
                                    activebackground='#444', activeforeground=FG,
                                    command=self._on_port_change)
        self.change_btn.pack(side='left', padx=(8, 0))

        # -- Checkboxes --
        check_frame = tk.Frame(root, bg=BG)
        check_frame.pack(fill='x', padx=30, pady=(10, 5))

        self.start_min_var = tk.BooleanVar(value=self.settings.get('start_minimized', False))
        self.run_login_var = tk.BooleanVar(value=self.settings.get('run_at_login', False))

        cb_style_frame = tk.Frame(check_frame, bg=BG)
        cb_style_frame.pack(fill='x')

        self.start_min_cb = tk.Checkbutton(
            cb_style_frame, text='Start minimized', variable=self.start_min_var,
            bg=BG, fg=FG, selectcolor=BG_LIGHT, activebackground=BG,
            activeforeground=FG, font=('Arial', 11),
            command=self._on_start_minimized_change
        )
        self.start_min_cb.pack(side='left')

        self.run_login_cb = tk.Checkbutton(
            cb_style_frame, text='Run at login', variable=self.run_login_var,
            bg=BG, fg=FG, selectcolor=BG_LIGHT, activebackground=BG,
            activeforeground=FG, font=('Arial', 11),
            command=self._on_run_at_login_change
        )
        self.run_login_cb.pack(side='right')

        # -- Buttons --
        btn_frame = tk.Frame(root, bg=BG)
        btn_frame.pack(fill='x', padx=30, pady=(15, 20))

        self.launch_btn = tk.Button(
            btn_frame, text='Launch GUI', font=('Arial', 12, 'bold'),
            bg='#ffffff', fg='#1a1a1a', relief='flat', bd=0,
            padx=15, pady=8, activebackground='#e0e0e0',
            command=self._launch_gui
        )
        self.launch_btn.pack(side='left', expand=True, fill='x', padx=(0, 5))

        self.hide_btn = tk.Button(
            btn_frame, text='Hide', font=('Arial', 12),
            bg='#444444', fg='#ffffff', relief='solid', bd=1,
            padx=15, pady=8, activebackground='#555', activeforeground='#ffffff',
            highlightbackground='#666666',
            command=self._hide_window
        )
        self.hide_btn.pack(side='left', expand=True, fill='x', padx=(5, 5))

        self.quit_btn = tk.Button(
            btn_frame, text='Quit', font=('Arial', 12),
            bg='#444444', fg='#ffffff', relief='solid', bd=1,
            padx=15, pady=8, activebackground='#555', activeforeground='#ffffff',
            highlightbackground='#666666',
            command=self._quit
        )
        self.quit_btn.pack(side='left', expand=True, fill='x', padx=(5, 0))

    # ------------------------------------------------------------------
    # Server Management
    # ------------------------------------------------------------------

    def _start_server(self):
        """Start Flask server on a daemon thread."""
        self._server_stop_event.clear()
        host = self.settings.get('interface', '127.0.0.1')
        port = int(self.settings.get('port', 8050))

        def run():
            from app import app, socketio, log_event
            log_dir = os.environ.get('_LRD_LOG_DIR', 'unknown')
            log_event('server_start', {
                'port': port,
                'host': host,
                'launcher': 'unified_launcher',
                'log_dir': log_dir
            })
            socketio.run(app, host=host, port=port, debug=False,
                         allow_unsafe_werkzeug=True)

        self.server_thread = threading.Thread(target=run, daemon=True)
        self.server_thread.start()
        self.server_running = True
        self._update_status()

    def _restart_server(self):
        """Stop the server and restart with new settings."""
        self._update_status(restarting=True)

        def do_restart():
            try:
                from app import socketio
                socketio.stop()
            except Exception:
                pass
            time.sleep(0.5)
            self.root.after(0, self._start_server)

        threading.Thread(target=do_restart, daemon=True).start()

    def _update_status(self, restarting=False):
        """Update status label and URL display."""
        if restarting:
            self.status_label.config(text='● Restarting...', fg=ACCENT)
        elif self.server_running:
            self.status_label.config(text='● Running', fg=GREEN)
        else:
            self.status_label.config(text='● Stopped', fg=RED)
        self._update_url_display()

    def _update_url_display(self):
        """Update the URL label."""
        host = self.settings.get('interface', '127.0.0.1')
        port = self.settings.get('port', 8050)
        display_host = host if host != '0.0.0.0' else '127.0.0.1'
        self.url_label.config(text=f'http://{display_host}:{port}')

    def _get_url(self):
        """Get the current server URL."""
        host = self.settings.get('interface', '127.0.0.1')
        port = self.settings.get('port', 8050)
        display_host = host if host != '0.0.0.0' else '127.0.0.1'
        return f'http://{display_host}:{port}'

    # ------------------------------------------------------------------
    # Event Handlers
    # ------------------------------------------------------------------

    def _on_interface_change(self, event=None):
        selected_label = self.iface_var.get()
        for ip, label in self.interfaces:
            if label == selected_label:
                self.settings['interface'] = ip
                break
        save_settings(self.settings)
        self._restart_server()

    def _on_port_change(self):
        try:
            new_port = int(self.port_var.get())
            if new_port < 1024 or new_port > 65535:
                raise ValueError
        except ValueError:
            self.port_var.set(str(self.settings.get('port', 8050)))
            return
        self.settings['port'] = new_port
        save_settings(self.settings)
        self._restart_server()

    def _on_start_minimized_change(self):
        self.settings['start_minimized'] = self.start_min_var.get()
        save_settings(self.settings)

    def _on_run_at_login_change(self):
        enabled = self.run_login_var.get()
        self.settings['run_at_login'] = enabled
        save_settings(self.settings)
        set_run_at_login(enabled)

    def _launch_gui(self):
        webbrowser.open(self._get_url())

    def _hide_window(self):
        self.root.withdraw()

    def _show_window(self, event=None):
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()

    def _quit(self):
        save_settings(self.settings)
        if self.tray_icon:
            try:
                self.tray_icon.stop()
            except Exception:
                pass
        os._exit(0)

    # ------------------------------------------------------------------
    # System Tray (Windows/Linux only)
    # ------------------------------------------------------------------

    def _start_tray(self):
        """Start the system tray icon using pystray (Windows/Linux only)."""
        try:
            import pystray
            from pystray import MenuItem, Menu
        except ImportError:
            return

        icon_image = self._create_tray_icon()

        def show_window(icon, item):
            self.root.after(0, self._show_window)

        def open_browser(icon, item):
            self._launch_gui()

        def quit_app(icon, item):
            self.root.after(0, self._quit)

        host = self.settings.get('interface', '127.0.0.1')
        port = self.settings.get('port', 8050)
        display_host = host if host != '0.0.0.0' else '127.0.0.1'

        self.tray_icon = pystray.Icon(
            name='LED Raster Designer',
            icon=icon_image,
            title='LED Raster Designer',
            menu=Menu(
                MenuItem('Show Window', show_window, default=True),
                MenuItem('Open in Browser', open_browser),
                Menu.SEPARATOR,
                MenuItem(f'Running on {display_host}:{port}', None, enabled=False),
                Menu.SEPARATOR,
                MenuItem('Quit LED Raster Designer', quit_app),
            )
        )
        threading.Thread(target=self.tray_icon.run, daemon=True).start()

    def _create_tray_icon(self):
        from PIL import Image, ImageDraw
        img = Image.new('RGBA', (64, 64), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw.ellipse([16, 4, 48, 36], fill='#FFD700', outline='#FFA500', width=2)
        draw.rectangle([22, 34, 42, 44], fill='#808080', outline='#606060', width=1)
        draw.rectangle([24, 44, 40, 48], fill='#707070', outline='#606060', width=1)
        draw.polygon([(28, 48), (36, 48), (32, 56)], fill='#606060')
        draw.line([32, 0, 32, 4], fill='#FFD700', width=2)
        draw.line([8, 20, 14, 20], fill='#FFD700', width=2)
        draw.line([50, 20, 56, 20], fill='#FFD700', width=2)
        draw.line([14, 8, 18, 12], fill='#FFD700', width=2)
        draw.line([50, 8, 46, 12], fill='#FFD700', width=2)
        return img

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _get_version(self):
        try:
            from updater import get_current_version
            return get_current_version()
        except Exception:
            pass
        try:
            vpath = os.path.join(BASE_DIR, 'VERSION.txt')
            with open(vpath, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line.startswith('v'):
                        return line.split()[0].lstrip('v')
        except Exception:
            pass
        return '0.0.0'


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    if sys.platform == 'darwin':
        _main_mac()
    else:
        _main_other()


def _main_mac():
    """macOS: rumps menu bar on main thread, Tkinter window on background thread."""
    import rumps

    # Create shared settings / state
    settings = load_settings()

    # -- Build and start the Tkinter window on a background thread --
    root = tk.Tk()
    launcher = LauncherWindow(root)

    tk_thread = threading.Thread(target=root.mainloop, daemon=True)
    tk_thread.start()

    # -- rumps menu bar icon on main thread (required by macOS) --
    class LEDMenuBar(rumps.App):
        def __init__(self):
            super().__init__(
                name='LED Raster Designer',
                title='💡',
                quit_button=None,
            )
            self.menu = [
                rumps.MenuItem('Open in Browser', callback=self._open_browser),
                rumps.MenuItem('Show Launcher', callback=self._show_launcher),
                None,  # separator
                rumps.MenuItem('Quit LED Raster Designer', callback=self._quit_app),
            ]

        def _open_browser(self, _):
            launcher._launch_gui()

        def _show_launcher(self, _):
            launcher.root.after(0, launcher._show_window)

        def _quit_app(self, _):
            rumps.quit_application()
            launcher._quit()

    menu_bar = LEDMenuBar()
    menu_bar.run()


def _main_other():
    """Windows/Linux: Tkinter on main thread, pystray on background thread."""
    root = tk.Tk()
    launcher = LauncherWindow(root)
    launcher._start_tray()
    root.mainloop()


if __name__ == '__main__':
    main()
