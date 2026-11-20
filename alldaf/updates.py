"""Update check, connection test and what's-new."""
import tkinter as tk
import urllib.request
from tkinter import ttk
from .config import CHANGELOG, CREAM, GOLD, HEADERS, INK, LOG_FILE, PANEL, VERSION
from .net import check_for_update, download_update, make_ctx


class UpdateMixin:
    # ---------- connection test and changelog ----------
    def test_connection(self, skip_ssl):
        lines = []
        for label, url in (("alldaf.org", "https://alldaf.org/"),
                           ("GitHub (for updates)", "https://api.github.com/")):
            try:
                with urllib.request.urlopen(urllib.request.Request(url, headers=HEADERS), timeout=10,
                                            context=make_ctx(skip_ssl)) as r:
                    lines.append(f"{label}: connected (HTTP {r.status})")
            except Exception as e:
                text = str(e)
                lines.append(f"{label}: FAILED - {text}")
                if any(word in text.upper() for word in ("CERTIFICATE", "SSL", "EOF")):
                    lines.append("   This looks like a secure-connection problem. A proxy or security program "
                                 "may be interfering. Try turning on 'Skip SSL check (proxy)'.")
        lines.append(f"Activity log: {LOG_FILE}")
        self.q.put(("info", "Connection test", "\n".join(lines)))

    def show_changelog(self):
        win = tk.Toplevel(self.root)
        win.title("What's new")
        win.configure(bg=CREAM)
        win.geometry("480x520")
        win.transient(self.root)
        ttk.Button(win, text="Close", command=win.destroy).pack(side="bottom", pady=(0, 12))
        txt = tk.Text(win, wrap="word", relief="flat", bg=PANEL, fg=INK, font=("Segoe UI", 10),
                      padx=14, pady=12, highlightthickness=1, highlightbackground=GOLD)
        txt.pack(fill="both", expand=True, padx=12, pady=(12, 8))
        for ver, items in CHANGELOG:
            here = "  (this version)" if ver == VERSION else ""
            txt.insert("end", f"Version {ver}{here}\n")
            for item in items:
                txt.insert("end", f"  \u2022  {item}\n")
            txt.insert("end", "\n")
        txt.config(state="disabled")

    # ---------- updates ----------
    def update_check(self, manual=False, skip_ssl=True):
        try:
            found = check_for_update(skip_ssl)
        except Exception as e:
            if manual:
                self.q.put(("notice", f"Couldn't check for updates: {e}"))
            return
        if found:
            self.q.put(("update", found["tag"], found["page"], found["exe_url"], found["sha_url"]))
        elif manual:
            self.q.put(("notice", f"You have the latest version ({VERSION})."))

    def apply_update(self, tag, exe_url, sha_url):
        try:
            self.q.put(("progress", 0, f"Downloading update {tag}...", ""))
            self.retry(lambda: download_update(exe_url, sha_url), "downloading the update")
            self.q.put(("restart", tag))
        except Exception as e:
            self.q.put(("notice", f"Update failed: {e}\n\nYou can download it from the release page instead."))
