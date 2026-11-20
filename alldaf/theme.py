"""Window theme, icon and taskbar flash."""
import sys
import tkinter as tk
from tkinter import ttk
from .config import BURGUNDY, CREAM, GOLD, INK, MUTED, PANEL
from .util import resource_path


def flash_window(root):
    """Flash the taskbar button until the window is clicked. Windows only; does nothing elsewhere."""
    if not sys.platform.startswith("win"):
        return
    try:
        import ctypes
        from ctypes import wintypes

        class FLASHWINFO(ctypes.Structure):
            _fields_ = [("cbSize", wintypes.UINT), ("hwnd", wintypes.HWND), ("dwFlags", wintypes.DWORD),
                        ("uCount", wintypes.UINT), ("dwTimeout", wintypes.DWORD)]

        hwnd = ctypes.windll.user32.GetParent(root.winfo_id())
        info = FLASHWINFO(ctypes.sizeof(FLASHWINFO), hwnd, 0x0F, 5, 0)  # flash all, until the window is active
        ctypes.windll.user32.FlashWindowEx(ctypes.byref(info))
    except Exception:
        pass


def set_window_icon(root):
    try:
        img = tk.PhotoImage(file=str(resource_path("icon.png")))
        root.iconphoto(True, img)
        root._icon_ref = img  # keep a reference so it isn't garbage-collected
    except Exception:
        pass


def apply_theme(root):
    style = ttk.Style(root)
    style.theme_use("clam")
    root.configure(bg=CREAM)

    # Native ttk combobox popup colors.
    root.option_add("*TCombobox*Listbox.background", PANEL)
    root.option_add("*TCombobox*Listbox.foreground", INK)
    root.option_add("*TCombobox*Listbox.selectBackground", GOLD)
    root.option_add("*TCombobox*Listbox.selectForeground", BURGUNDY)

    style.configure(".", background=CREAM, foreground=INK,
                    font=("Segoe UI", 10))
    style.configure("TFrame", background=CREAM)
    style.configure("Panel.TFrame", background=PANEL)
    style.configure("TLabel", background=CREAM, foreground=INK)
    style.configure("Field.TLabel", background=CREAM, foreground=BURGUNDY,
                    font=("Segoe UI Semibold", 10))
    style.configure("Section.TLabel", background=CREAM, foreground=BURGUNDY,
                    font=("Segoe UI Semibold", 11))
    style.configure("Muted.TLabel", background=CREAM, foreground=MUTED,
                    font=("Segoe UI", 9))
    style.configure("Status.TLabel", background=CREAM, foreground=BURGUNDY,
                    font=("Segoe UI Semibold", 10))
    style.configure("Banner.TFrame", background=BURGUNDY)
    style.configure("Banner.TLabel", background=BURGUNDY, foreground="#f1d77c",
                    font=("Georgia", 19, "bold"))
    style.configure("BannerSub.TLabel", background=BURGUNDY,
                    foreground="#f3e8d0", font=("Segoe UI", 9))
    style.configure("TButton", background="#eee5d3", foreground=BURGUNDY,
                    bordercolor="#d8c9a8", focuscolor=GOLD,
                    padding=(11, 6), font=("Segoe UI", 9))
    style.map("TButton",
              background=[("active", "#e4d7bd"), ("disabled", "#e8e0d2")],
              foreground=[("disabled", "#a99d8c")])
    style.configure("Gold.TButton", background=GOLD, foreground=BURGUNDY,
                    bordercolor=GOLD, focuscolor=GOLD,
                    font=("Segoe UI Semibold", 10), padding=(18, 8))
    style.map("Gold.TButton",
              background=[("active", "#d8b33c"), ("disabled", "#e7dcb9")],
              foreground=[("disabled", "#9a8c70")])
    style.configure("TCheckbutton", background=CREAM, foreground=INK,
                    font=("Segoe UI", 9))
    style.map("TCheckbutton", background=[("active", CREAM)])
    style.configure("TRadiobutton", background=CREAM, foreground=INK,
                    padding=(3, 3))
    style.map("TRadiobutton", background=[("active", CREAM)])
    style.configure("TEntry", fieldbackground=PANEL, foreground=INK,
                    insertcolor=INK, bordercolor="#d8c9a8",
                    lightcolor=GOLD, darkcolor="#d8c9a8", padding=6)
    style.map("TEntry", bordercolor=[("focus", GOLD)])
    style.configure("TCombobox", fieldbackground=PANEL, foreground=INK,
                    background=PANEL, bordercolor="#d8c9a8",
                    arrowcolor=BURGUNDY, lightcolor=GOLD,
                    darkcolor="#d8c9a8", padding=5)
    style.map("TCombobox",
              fieldbackground=[("readonly", PANEL)],
              foreground=[("readonly", INK)],
              selectbackground=[("readonly", PANEL)],
              selectforeground=[("readonly", INK)],
              bordercolor=[("focus", GOLD)])
    style.configure("Gold.Horizontal.TProgressbar",
                    troughcolor="#e9dfc7", background=GOLD,
                    bordercolor="#e9dfc7", lightcolor=GOLD, darkcolor=GOLD,
                    thickness=10)
    style.configure("Vertical.TScrollbar", background="#e4d5b4",
                    troughcolor=CREAM, bordercolor=CREAM,
                    arrowcolor=BURGUNDY, lightcolor="#e4d5b4",
                    darkcolor="#e4d5b4", arrowsize=12)
    style.map("Vertical.TScrollbar",
              background=[("active", GOLD), ("pressed", GOLD)])
