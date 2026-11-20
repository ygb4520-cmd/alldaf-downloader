"""AllDaf Shiur Downloader: download every shiur by one speaker on one mesechta.
Files go to <folder>\\<speaker>\\<mesechta>\\. Needs only Python 3. Run:  python alldaf_downloader.py
"""
import tkinter as tk

from alldaf.app import App
from alldaf.net import cleanup_old_exe

if __name__ == "__main__":
    cleanup_old_exe()
    root = tk.Tk()
    App(root)
    root.mainloop()
