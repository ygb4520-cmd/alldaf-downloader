"""The main window."""
import json
import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import ttk, filedialog, messagebox
from .config import BURGUNDY, CONFIG, CREAM, DEFAULT_SPEAKERS, GOLD, GOLD_LIGHT, INK, MASECHTOS, MUTED, PANEL, SPEED_MAX, SPEED_MIN, SPEED_STEP, VERSION, WORKERS, shared
from .net import make_ctx
from .theme import apply_theme, flash_window, set_window_icon
from .util import parse_daf_range, recommend_workers, snap_speed, speed_text, write_log
from .speakers import SpeakerMixin
from .updates import UpdateMixin
from .downloads import DownloadMixin
from .speedtest import SpeedTestMixin
from .faster import FasterMixin


class App(SpeakerMixin, UpdateMixin, DownloadMixin, SpeedTestMixin, FasterMixin):
    def __init__(self, root):
        self.root, self.q, self.stop = root, queue.Queue(), threading.Event()
        self.busy, self.last_folder = False, None
        self.cfg = {"speakers": DEFAULT_SPEAKERS,
                    "folder": str(Path.home() / "Downloads" / "Shiurim"),
                    "recent": []}
        try:
            self.cfg.update(json.loads(CONFIG.read_text(encoding="utf-8")))
        except Exception:
            pass

        set_window_icon(root)
        apply_theme(root)
        root.title("AllDaf Shiur Downloader")
        root.geometry("700x740")
        root.minsize(680, 680)

        # Main window grid: the log takes any extra vertical space.
        f = ttk.Frame(root, padding=(16, 14, 16, 14))
        f.pack(fill="both", expand=True)
        f.columnconfigure(0, weight=1)
        f.rowconfigure(2, weight=1)  # the mesechta list takes extra height; the log keeps its size

        # Header
        banner = ttk.Frame(f, style="Banner.TFrame", padding=(18, 13))
        banner.grid(row=0, column=0, sticky="ew", pady=(0, 13))
        ttk.Label(banner, text="AllDaf Shiur Downloader",
                  style="Banner.TLabel").pack(anchor="w")
        ttk.Label(banner,
                  text="Download every shiur by a speaker on a mesechta",
                  style="BannerSub.TLabel").pack(anchor="w", pady=(3, 0))

        # Speaker selection
        speaker_section = ttk.Frame(f, padding=(2, 2, 2, 7))
        speaker_section.grid(row=1, column=0, sticky="ew")
        speaker_section.columnconfigure(1, weight=1)
        ttk.Label(speaker_section, text="Speaker",
                  style="Field.TLabel").grid(row=0, column=0,
                                             sticky="w", padx=(0, 12))
        self.speaker = ttk.Combobox(speaker_section, state="readonly")
        self.speaker.grid(row=0, column=1, sticky="ew", padx=(0, 8))
        speaker_buttons = ttk.Frame(speaker_section)
        speaker_buttons.grid(row=0, column=2, sticky="e")
        ttk.Button(speaker_buttons, text="Add", width=7,
                   command=self.add_speaker).pack(side="left")
        ttk.Button(speaker_buttons, text="Remove", width=8,
                   command=self.remove_speaker).pack(side="left", padx=(6, 0))
        self.refresh_speakers()

        # Mesechta search and grouped list
        mesechta_section = ttk.Frame(f, padding=(0, 4, 0, 7))
        mesechta_section.grid(row=2, column=0, sticky="nsew")
        mesechta_section.columnconfigure(0, weight=1)
        mesechta_section.rowconfigure(1, weight=1)
        ttk.Label(mesechta_section, text="Mesechta",
                  style="Field.TLabel").grid(row=0, column=0,
                                             sticky="w", pady=(0, 5))
        list_panel = ttk.Frame(mesechta_section, style="Panel.TFrame",
                               padding=7)
        list_panel.grid(row=1, column=0, sticky="nsew")
        list_panel.columnconfigure(0, weight=1)
        list_panel.rowconfigure(1, weight=1)

        search_row = ttk.Frame(list_panel, style="Panel.TFrame")
        search_row.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        search_row.columnconfigure(0, weight=1)
        self.search = tk.StringVar()
        self.search.trace_add("write", lambda *_: self.filter_list())
        search_entry = ttk.Entry(search_row, textvariable=self.search)
        search_entry.grid(row=0, column=0, sticky="ew")
        # Hint text shown inside the search box while it's empty. It's a separate label placed over
        # the entry, so the search text itself stays empty and the filter isn't affected.
        hint = tk.Label(search_row, text="type to search", bg=PANEL, fg=MUTED, font=("Segoe UI", 9),
                        bd=0, cursor="xterm")
        hint.place(in_=search_entry, x=7, rely=0.5, anchor="w")
        hint.bind("<Button-1>", lambda e: search_entry.focus_set())
        has_focus = {"on": False}

        def update_hint(*_):
            # hide the hint while the box is focused or has text; show it otherwise
            if self.search.get() or has_focus["on"]:
                hint.place_forget()
            else:
                hint.place(in_=search_entry, x=7, rely=0.5, anchor="w")

        def on_focus_in(_e):
            has_focus["on"] = True
            update_hint()

        def on_focus_out(_e):
            has_focus["on"] = False
            update_hint()

        search_entry.bind("<FocusIn>", on_focus_in)
        search_entry.bind("<FocusOut>", on_focus_out)
        self.search.trace_add("write", update_hint)

        list_frame = ttk.Frame(list_panel, style="Panel.TFrame")
        list_frame.grid(row=1, column=0, sticky="nsew")
        list_frame.columnconfigure(0, weight=1)
        list_frame.rowconfigure(0, weight=1)
        self.lb = tk.Listbox(
            list_frame, height=8, exportselection=False,
            activestyle="none", relief="flat", borderwidth=0,
            bg=PANEL, fg=INK, selectbackground=GOLD,
            selectforeground=BURGUNDY, highlightthickness=1,
            highlightbackground="#e2d5bd", highlightcolor=GOLD,
            font=("Segoe UI", 10), selectborderwidth=0)
        self.lb.grid(row=0, column=0, sticky="nsew")
        sb = ttk.Scrollbar(list_frame, command=self.lb.yview)
        sb.grid(row=0, column=1, sticky="ns")
        self.lb.config(yscrollcommand=sb.set)
        self.lb.bind("<<ListboxSelect>>", self.on_select)
        self.filter_list()

        # Talmud type
        type_row = ttk.Frame(f, padding=(2, 7, 2, 7))
        type_row.grid(row=3, column=0, sticky="ew")
        ttk.Label(type_row, text="Type",
                  style="Field.TLabel").pack(side="left", padx=(0, 23))
        self.mode = tk.StringVar(value="Bavli")
        for m in ("Bavli", "Yerushalmi", "Both"):
            ttk.Radiobutton(type_row, text=m, value=m,
                            variable=self.mode).pack(side="left", padx=(0, 17))
        ttk.Label(type_row, text="Dapim", style="Field.TLabel").pack(side="left", padx=(14, 6))
        self.daf_from, self.daf_to = tk.StringVar(), tk.StringVar()
        ttk.Entry(type_row, textvariable=self.daf_from, width=5, justify="center").pack(side="left")
        ttk.Label(type_row, text=" to ").pack(side="left")
        ttk.Entry(type_row, textvariable=self.daf_to, width=5, justify="center").pack(side="left")
        ttk.Label(type_row, text="blank = all", style="Muted.TLabel").pack(side="left", padx=(8, 0))

        # Destination folder
        folder_row = ttk.Frame(f, padding=(2, 4, 2, 9))
        folder_row.grid(row=4, column=0, sticky="ew")
        folder_row.columnconfigure(1, weight=1)
        ttk.Label(folder_row, text="Save to",
                  style="Field.TLabel").grid(row=0, column=0,
                                             sticky="w", padx=(0, 12))
        self.folder = tk.StringVar(value=self.cfg["folder"])
        ttk.Entry(folder_row, textvariable=self.folder).grid(
            row=0, column=1, sticky="ew", padx=(0, 8))
        ttk.Button(folder_row, text="Browse",
                   command=self.browse).grid(row=0, column=2)

        # Primary and secondary actions
        self.skip_ssl = tk.BooleanVar(value=self.cfg.get("skip_ssl", False))
        self.workers = tk.IntVar(value=max(1, min(5, int(self.cfg.get("workers", WORKERS)))))
        try:
            start_speed = snap_speed(self.cfg.get("speed", 1.0))
        except (TypeError, ValueError):
            start_speed = 1.0
        self.speed = tk.DoubleVar(value=start_speed)
        self.speed_text = tk.StringVar(value=speed_text(start_speed))
        self.worker_count = WORKERS
        self.retry_count = 0  # how many times a request has been retried, used by the speed test
        actions = ttk.Frame(f, padding=(0, 3, 0, 10))
        actions.grid(row=5, column=0, sticky="ew")
        top_row = ttk.Frame(actions)
        top_row.pack(fill="x")
        self.start_btn = ttk.Button(
            top_row, text="Start download", style="Gold.TButton",
            command=self.start)
        self.start_btn.pack(side="left")
        self.stop_btn = ttk.Button(
            top_row, text="Stop", command=self.stop.set, state="disabled")
        self.stop_btn.pack(side="left", padx=(8, 8))
        ttk.Button(top_row, text="Open folder", command=self.open_folder).pack(side="left")
        ttk.Button(
            top_row, text="Check for updates",
            command=lambda: threading.Thread(
                target=self.update_check,
                kwargs={"manual": True, "skip_ssl": self.skip_ssl.get()},
                daemon=True).start()
        ).pack(side="right")

        # second row: connection tools, so the first row always fits the window
        tools_row = ttk.Frame(actions, padding=(0, 6, 0, 0))
        tools_row.pack(fill="x")
        ttk.Button(tools_row, text="Test connection",
                   command=lambda: threading.Thread(
                       target=self.test_connection,
                       kwargs={"skip_ssl": self.skip_ssl.get()}, daemon=True).start()
                   ).pack(side="left")
        self.bench_btn = ttk.Button(tools_row, text="Auto-test speed", command=self.auto_test)
        self.bench_btn.pack(side="left", padx=(13, 0))
        ttk.Checkbutton(tools_row, text="Skip SSL check (proxy)",
                        variable=self.skip_ssl).pack(side="left", padx=(13, 0))

        # Progress and status
        progress_section = ttk.Frame(f, padding=(0, 3, 0, 8))
        progress_section.grid(row=6, column=0, sticky="ew")
        progress_section.columnconfigure(0, weight=1)
        self.bar = ttk.Progressbar(
            progress_section, maximum=100,
            style="Gold.Horizontal.TProgressbar")
        self.bar.grid(row=0, column=0, sticky="ew", pady=(0, 7))
        self.status, self.current = tk.StringVar(value="Ready"), tk.StringVar()
        ttk.Label(progress_section, textvariable=self.status,
                  style="Status.TLabel").grid(row=1, column=0, sticky="w")
        par = ttk.Frame(progress_section)
        par.grid(row=1, column=1, sticky="e")
        ttk.Label(par, text="Parallel downloads", style="Muted.TLabel").pack(side="left", padx=(0, 6))
        ttk.Spinbox(par, from_=1, to=5, width=3, textvariable=self.workers, justify="center").pack(side="left")
        ttk.Label(progress_section, textvariable=self.current,
                  style="Muted.TLabel").grid(row=2, column=0,
                                             sticky="w", pady=(2, 0))
        speed_row = ttk.Frame(progress_section)
        speed_row.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        ttk.Label(speed_row, text="Playback speed", style="Field.TLabel").pack(side="left")
        tk.Scale(speed_row, from_=SPEED_MIN, to=SPEED_MAX, resolution=SPEED_STEP, orient="horizontal",
                 variable=self.speed, showvalue=False, length=300, command=self.on_speed_change,
                 bg=CREAM, fg=INK, troughcolor="#e9dfc7", activebackground=GOLD, highlightthickness=0,
                 bd=0, sliderlength=18, width=12).pack(side="left", padx=10)
        ttk.Label(speed_row, textvariable=self.speed_text, style="Status.TLabel",
                  width=9).pack(side="left")
        ttk.Button(speed_row, text="Make faster copies...",
                   command=self.faster_copies_dialog).pack(side="right")

        # Read-only activity log
        log_header = ttk.Frame(f)
        log_header.grid(row=7, column=0, sticky="ew", pady=(3, 5))
        ttk.Label(log_header, text="Activity log",
                  style="Section.TLabel").pack(side="left")
        ttk.Button(log_header, text="What's new", command=self.show_changelog).pack(side="right", padx=(8, 0))
        ttk.Label(log_header, text="Download messages and errors",
                  style="Muted.TLabel").pack(side="right")
        log_frame = ttk.Frame(f, style="Panel.TFrame", padding=5)
        log_frame.grid(row=8, column=0, sticky="nsew")
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
        self.log = tk.Text(
            log_frame, height=8, state="disabled", wrap="word",
            relief="flat", borderwidth=0, bg=PANEL, fg=INK,
            insertbackground=INK, font=("Consolas", 9),
            padx=8, pady=7, spacing1=2, spacing3=2)
        self.log.grid(row=0, column=0, sticky="nsew")
        log_scroll = ttk.Scrollbar(log_frame, command=self.log.yview)
        log_scroll.grid(row=0, column=1, sticky="ns")
        self.log.config(yscrollcommand=log_scroll.set)

        root.update_idletasks()
        root.minsize(root.winfo_reqwidth(), root.winfo_reqheight())  # never smaller than its content
        root.protocol("WM_DELETE_WINDOW", self.close)
        if self.cfg.get("seen_version") != VERSION:
            self.cfg["seen_version"] = VERSION
            self.save_cfg()
            root.after(600, self.show_changelog)
        self.poll()
        threading.Thread(
            target=self.update_check,
            kwargs={"skip_ssl": self.skip_ssl.get()},
            daemon=True).start()

    # ---------- settings ----------
    def save_cfg(self):
        self.cfg["folder"] = self.folder.get()
        try:
            self.cfg["speed"] = snap_speed(self.speed.get())
        except (tk.TclError, ValueError):
            pass
        try:
            self.cfg["workers"] = max(1, min(5, int(self.workers.get())))
        except (tk.TclError, ValueError):
            pass
        self.cfg["skip_ssl"] = self.skip_ssl.get()
        try:
            tmp = CONFIG.with_name(CONFIG.name + ".tmp")
            tmp.write_text(json.dumps(self.cfg, indent=2), encoding="utf-8")
            os.replace(tmp, CONFIG)
        except Exception:
            pass

    def browse(self):
        d = filedialog.askdirectory(initialdir=self.folder.get() or str(Path.home()))
        if d:
            self.folder.set(d)

    # ---------- mesechta list ----------
    def filter_list(self):
        """Recently used mesechtos on top (tinted), then the rest in Bavli order, with labels between them.
        Typing narrows both groups."""
        t = self.search.get().lower().strip()
        saved = [m for m in self.cfg.get("recent", []) if m in MASECHTOS]
        recent = [m for m in saved if t in m.lower()]
        rest = [m for m in MASECHTOS if m not in saved and t in m.lower()]
        rows = []
        if recent:
            rows.append(("header", "Recently used"))
            rows += [("recent", m) for m in recent]
            if rest:
                rows.append(("header", "All mesechtos"))
        rows += [("item", m) for m in rest]
        self.rows = rows
        self.lb.delete(0, "end")
        for i, (kind, text) in enumerate(rows):
            self.lb.insert("end", text)
            if kind == "header":
                self.lb.itemconfig(i, fg=MUTED, bg=CREAM, selectbackground=CREAM, selectforeground=MUTED)
            elif kind == "recent":
                self.lb.itemconfig(i, bg=GOLD_LIGHT)

    def on_select(self, _event=None):
        """Labels can't be chosen, so clear the selection if one lands on a label."""
        sel = self.lb.curselection()
        if sel and self.rows[sel[0]][0] == "header":
            self.lb.selection_clear(0, "end")

    def masechta(self):
        sel = self.lb.curselection()
        if sel and self.rows[sel[0]][0] != "header":
            return self.rows[sel[0]][1]
        return self.search.get().strip()

    def remember_masechta(self, mas):
        recent = [m for m in self.cfg.get("recent", []) if m != mas]
        self.cfg["recent"] = ([mas] + recent)[:8]

    # ---------- run ----------
    def start(self):
        spk = next((s for s in self.cfg["speakers"] if s["name"] == self.speaker.get()), None)
        mas = self.masechta()
        missing = []
        if not spk:
            missing.append("a speaker")
        if not mas:
            missing.append("a mesechta")
        if not self.folder.get().strip():
            missing.append("a save folder")
        if missing:
            messagebox.showwarning("Missing info", "Please choose " + " and ".join(missing) + ".")
            return
        try:
            dafs = parse_daf_range(self.daf_from.get(), self.daf_to.get())
        except ValueError as e:
            messagebox.showwarning("Dapim", str(e))
            return
        factor = snap_speed(self.speed.get())
        if factor > 1.0 and not self.have_ffmpeg("Or set Playback speed back to Normal."):
            return
        keep = "both"
        if factor > 1.0:
            keep = self.ask_keep_mode()
            if keep is None:
                return
        self.remember_masechta(mas)
        try:
            self.worker_count = max(1, min(5, int(self.workers.get())))
        except (tk.TclError, ValueError):
            self.worker_count = WORKERS
        self.root.title("AllDaf Shiur Downloader")
        self.save_cfg()
        self.busy = True
        shared.ssl_ctx = make_ctx(self.skip_ssl.get())
        self.stop.clear()
        self.start_btn.config(state="disabled")
        self.stop_btn.config(state="normal")
        self.bar["value"] = 0
        args = (spk["id"], spk["name"], mas, self.mode.get(), Path(self.folder.get()).expanduser(), dafs,
                speed_text(factor), factor, keep)
        threading.Thread(target=self.worker, args=args, daemon=True).start()

    def open_folder(self):
        p = self.last_folder or Path(self.folder.get().strip() or ".").expanduser()
        if not p.exists():
            messagebox.showinfo("Open folder", "That folder doesn't exist yet. It is created when you start a download.")
            return
        if sys.platform.startswith("win"):
            os.startfile(p)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(p)])
        else:
            subprocess.Popen(["xdg-open", str(p)])

    def poll(self):
        got = False
        while True:
            try:
                kind, *a = self.q.get_nowait()
                got = True
            except queue.Empty:
                break
            if kind == "log" or kind == "done":
                self.log.config(state="normal")
                self.log.insert("end", a[0] + "\n")
                self.log.see("end")
                self.log.config(state="disabled")
            if kind == "progress":
                self.bar["value"] = a[0]
                self.status.set(a[1])
                self.current.set(a[2])
            elif kind == "update":
                tag, page, exe_url, sha_url = a
                if getattr(sys, "frozen", False) and exe_url and sha_url:
                    if messagebox.askyesno("Update available",
                                           f"Version {tag} is available (you have {VERSION}).\n\n"
                                           "Download and install it now? The program will restart."):
                        threading.Thread(target=self.apply_update, args=(tag, exe_url, sha_url), daemon=True).start()
                elif messagebox.askyesno("Update available",
                                         f"Version {tag} is available (you have {VERSION}).\n\n"
                                         "Open the download page?"):
                    webbrowser.open(page)
            elif kind == "restart":
                messagebox.showinfo("Update ready", f"Updated to {a[0]}. The program will now restart.")
                # The new copy must not inherit the old copy's temp-folder settings, or the old copy
                # can't clean up its temp folder when it closes ("Failed to remove temporary directory").
                env = {k: v for k, v in os.environ.items() if not k.startswith("_PYI") and k != "_MEIPASS2"}
                env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
                subprocess.Popen([sys.executable], env=env)
                self.close()
            elif kind == "bench_done":
                results, note = a
                self.busy = False
                self.start_btn.config(state="normal")
                self.bench_btn.config(state="normal")
                self.bar["value"] = 0
                self.status.set("Ready")
                self.current.set("")
                if note or not results:
                    messagebox.showinfo("Auto-test speed", note or "The test didn't finish. Try again.")
                else:
                    best = recommend_workers(results)
                    self.workers.set(best)
                    self.save_cfg()
                    lines = []
                    for r in results:
                        extra = (f", {r['retries']} retries" if r["retries"] else "") + \
                                (f", {r['failed']} failed" if r["failed"] else "")
                        lines.append(f"{r['w']} at a time: {r['secs']:.0f} s{extra}")
                    write_log("Speed test: " + "; ".join(lines) + f"; set to {best}")
                    messagebox.showinfo("Auto-test speed",
                                        "Results:\n" + "\n".join(lines) +
                                        f"\n\nSet to {best} at a time. You can change it any time.")
            elif kind == "info":
                messagebox.showinfo(a[0], a[1])
            elif kind == "notice":
                messagebox.showinfo("Updates", a[0])
            elif kind == "done":
                self.busy = False
                if self.root.focus_get() is None:  # window isn't active: get the user's attention
                    self.root.bell()
                    flash_window(self.root)
                self.root.title("Done - AllDaf Shiur Downloader")
                self.status.set(a[0])
                self.current.set("")
                self.start_btn.config(state="normal")
                self.stop_btn.config(state="disabled")
                self.filter_list()
        self.root.after(100 if (got or self.busy) else 400, self.poll)  # relax when idle

    def close(self):
        self.stop.set()
        self.save_cfg()
        self.root.destroy()
