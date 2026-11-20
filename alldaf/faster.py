"""Faster (sped-up) copies of shiurim."""
import shutil
import threading
import tkinter as tk
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tkinter import ttk, filedialog, messagebox
from .audio import speed_up
from .config import BURGUNDY, CONVERT_WORKERS, CREAM, FFMPEG_INSTALL_CMD, GOLD, INK, MASECHTOS, PANEL, SPEED_MAX, SPEED_MIN, SPEED_STEP, shared
from .net import make_ctx
from .util import count_downloaded, fast_name, parse_daf_range, safe_name, snap_speed, speed_text, title_with_speed, write_log


class FasterMixin:
    # ---------- faster copies for shiurim already downloaded ----------
    def faster_copies_dialog(self):
        if self.busy:
            messagebox.showinfo("Faster copies", "Wait for the current download to finish first.")
            return
        base = Path(self.folder.get()).expanduser()
        spk_name = self.speaker.get()
        win = tk.Toplevel(self.root)
        win.title("Make faster copies")
        win.configure(bg=CREAM)
        win.transient(self.root)
        win.resizable(False, False)
        frm = ttk.Frame(win, padding=16)
        frm.pack(fill="both", expand=True)

        ttk.Label(frm, text="Playback speed", style="Field.TLabel").grid(row=0, column=0, sticky="w")
        speed_var = tk.DoubleVar(value=snap_speed(self.speed.get()))
        shown = tk.StringVar(value=speed_text(snap_speed(speed_var.get())))

        def on_move(_=None):
            shown.set(speed_text(snap_speed(speed_var.get())))

        tk.Scale(frm, from_=SPEED_MIN, to=SPEED_MAX, resolution=SPEED_STEP, orient="horizontal",
                 variable=speed_var, showvalue=False, length=260, command=on_move,
                 bg=CREAM, fg=INK, troughcolor="#e9dfc7", activebackground=GOLD, highlightthickness=0,
                 bd=0, sliderlength=18, width=12).grid(row=0, column=1, padx=10)
        ttk.Label(frm, textvariable=shown, style="Status.TLabel", width=9).grid(row=0, column=2)

        ttk.Label(frm, text="Which shiurim", style="Field.TLabel").grid(row=1, column=0, sticky="nw", pady=(14, 0))
        scope = tk.StringVar(value="mesechta")
        options = [
            ("mesechta", "A mesechta"),
            ("speaker", f"All of {spk_name or 'this speaker'}'s downloaded shiurim"),
            ("files", "Specific files I pick"),
        ]
        for i, (value, text) in enumerate(options):
            ttk.Radiobutton(frm, text=text, value=value, variable=scope).grid(
                row=1 + i, column=1, columnspan=2, sticky="w", pady=2)

        # mesechta picker: every mesechta, with the downloaded ones marked
        pick = ttk.Frame(frm)
        pick.grid(row=4, column=0, columnspan=3, sticky="ew", pady=(10, 0))
        ttk.Label(pick, text="Pick a mesechta. Downloaded ones are marked.", style="Muted.TLabel").pack(anchor="w")
        lb = tk.Listbox(pick, height=8, exportselection=False, activestyle="none", relief="flat",
                        bg=PANEL, fg=INK, selectbackground=GOLD, selectforeground=BURGUNDY,
                        highlightthickness=1, highlightbackground=GOLD, highlightcolor=GOLD,
                        font=("Segoe UI", 10), width=42)
        lb.pack(fill="x", pady=(4, 0))
        for i, m in enumerate(MASECHTOS):
            have = count_downloaded(base, spk_name, m) if spk_name else 0
            lb.insert("end", f"{m}   ({have} downloaded)" if have else f"{m}   (not downloaded)")
            if have:
                lb.itemconfig(i, fg=BURGUNDY)

        def on_scope(*_):
            if scope.get() == "mesechta":
                pick.grid()
            else:
                pick.grid_remove()

        scope.trace_add("write", on_scope)

        def on_go():
            factor = snap_speed(speed_var.get())
            if factor <= 1.0:
                messagebox.showwarning("Faster copies", "Move the slider above Normal first.", parent=win)
                return
            if not self.have_ffmpeg(parent=win):
                return
            label = speed_text(factor)
            which = scope.get()
            if which == "mesechta":
                if not spk_name:
                    messagebox.showwarning("Faster copies", "Choose a speaker first.", parent=win)
                    return
                sel = lb.curselection()
                if not sel:
                    messagebox.showwarning("Faster copies", "Pick a mesechta from the list first.", parent=win)
                    return
                mas = MASECHTOS[sel[0]]
                mdir = base / safe_name(spk_name) / safe_name(mas)
                files = sorted(mdir.glob("*.mp3")) if mdir.exists() else []
                if not files:
                    if messagebox.askyesno(
                            "Not downloaded",
                            f"{mas} hasn't been downloaded for {spk_name} yet.\n\n"
                            f"Download it now and make faster copies at {label}?", parent=win):
                        win.destroy()
                        self.start_download_with_speed(mas, factor, label)
                    return
            elif which == "speaker":
                sdir = base / safe_name(spk_name) if spk_name else base
                files = []
                if sdir.exists():
                    for p in sdir.rglob("*.mp3"):
                        if not any(part.startswith("Fast ") for part in p.relative_to(sdir).parts):
                            files.append(p)
            else:
                picked = filedialog.askopenfilenames(parent=win, initialdir=str(base), title="Choose shiurim",
                                                     filetypes=[("MP3 files", "*.mp3")])
                files = [Path(x) for x in picked]
            files = sorted(files)
            if not files:
                messagebox.showinfo("Faster copies", "No shiurim found for that choice.", parent=win)
                return
            win.destroy()
            self.start_faster_copies(files, factor, label)

        buttons = ttk.Frame(frm)
        buttons.grid(row=5, column=0, columnspan=3, sticky="e", pady=(16, 0))
        ttk.Button(buttons, text="Cancel", command=win.destroy).pack(side="right")
        ttk.Button(buttons, text="Make copies", style="Gold.TButton", command=on_go).pack(side="right", padx=(0, 8))

    def ask_keep_mode(self):
        """Ask whether to keep both the normal and faster copies. Returns 'both', 'fast', or None if cancelled."""
        win = tk.Toplevel(self.root)
        win.title("Keep which copies?")
        win.configure(bg=CREAM)
        win.transient(self.root)
        win.resizable(False, False)
        result = {"value": None}

        def choose(value):
            result["value"] = value
            win.destroy()

        frm = ttk.Frame(win, padding=18)
        frm.pack(fill="both", expand=True)
        ttk.Label(frm, text="Keep which copies?", style="Field.TLabel").pack(anchor="w")
        ttk.Label(frm, justify="left", style="Muted.TLabel",
                  text="Keep both: the normal shiurim and the faster copies (uses about twice the space).\n"
                       "Only faster: each normal shiur is deleted once its faster copy is made.").pack(
            anchor="w", pady=(6, 14))
        buttons = ttk.Frame(frm)
        buttons.pack(fill="x")
        ttk.Button(buttons, text="Cancel", command=lambda: choose(None)).pack(side="right")
        ttk.Button(buttons, text="Only faster", command=lambda: choose("fast")).pack(side="right", padx=(0, 8))
        ttk.Button(buttons, text="Keep both", style="Gold.TButton",
                   command=lambda: choose("both")).pack(side="right", padx=(0, 8))
        win.protocol("WM_DELETE_WINDOW", lambda: choose(None))
        win.grab_set()
        self.root.wait_window(win)
        return result["value"]

    def start_download_with_speed(self, mas, factor, label):
        """Download one mesechta and make its faster copies as part of the same run."""
        keep = self.ask_keep_mode()
        if keep is None:
            return
        spk = next((s for s in self.cfg["speakers"] if s["name"] == self.speaker.get()), None)
        if not spk:
            return
        try:
            dafs = parse_daf_range(self.daf_from.get(), self.daf_to.get())
        except ValueError as e:
            messagebox.showwarning("Dapim", str(e))
            return
        self.save_cfg()
        shared.ssl_ctx = make_ctx(self.skip_ssl.get())
        self.stop.clear()
        self.busy = True
        self.start_btn.config(state="disabled")
        self.stop_btn.config(state="normal")
        self.bar["value"] = 0
        self.root.title("AllDaf Shiur Downloader")
        args = (spk["id"], spk["name"], mas, self.mode.get(), Path(self.folder.get()).expanduser(), dafs,
                label, factor, keep)
        threading.Thread(target=self.worker, args=args, daemon=True).start()

    def start_faster_copies(self, files, factor, label):
        self.stop.clear()
        self.busy = True
        self.start_btn.config(state="disabled")
        self.stop_btn.config(state="normal")
        self.bar["value"] = 0
        self.root.title("AllDaf Shiur Downloader")
        threading.Thread(target=self.run_faster_copies, args=(files, factor, label), daemon=True).start()

    def make_fast_copy(self, src, dst, factor, keep):
        """Make one faster copy. Returns 'made', 'skipped' (it already existed) or 'failed'."""
        if dst.exists():
            if keep == "fast":
                self.drop_normal(src)
            return "skipped"
        try:
            dst.parent.mkdir(exist_ok=True)
            speed_up(src, dst, factor, title=title_with_speed(src.stem, speed_text(factor)))
        except Exception as e:
            self.say(f"Speed-up failed for {src.name}: {e}")
            return "failed"
        if keep == "fast":
            self.drop_normal(src)
        return "made"

    def convert_pool(self, pairs, factor, keep, text):
        """Make faster copies for (source, destination) pairs, several at a time. Returns the counts."""
        total = len(pairs)
        counts = {"made": 0, "skipped": 0, "failed": 0}
        lock = threading.Lock()
        done = [0]

        def job(pair):
            if self.stop.is_set():
                return
            src, dst = pair
            result = self.make_fast_copy(src, dst, factor, keep)
            with lock:
                counts[result] += 1
                done[0] += 1
                self.q.put(("progress", done[0] / total * 100, f"{text}: {done[0]} of {total}", src.name))

        with ThreadPoolExecutor(CONVERT_WORKERS) as ex:
            list(ex.map(job, pairs))
        return counts

    def run_faster_copies(self, files, factor, label):
        pairs = [(src, src.parent / f"Fast {label}" / fast_name(src, label)) for src in files]
        counts = self.convert_pool(pairs, factor, "both", f"Making faster copies ({label})")
        summary = ("Stopped. " if self.stop.is_set() else "Done. ") + f"{counts['made']} faster copies made ({label})"
        if counts["skipped"]:
            summary += f", {counts['skipped']} already existed"
        if counts["failed"]:
            summary += f", {counts['failed']} failed"
        write_log(summary)
        self.q.put(("done", summary + "."))

    def drop_normal(self, src):
        """Delete a normal shiur once its faster copy exists ('Only faster' runs)."""
        try:
            src.unlink()
        except OSError as e:
            self.say(f"Couldn't delete the normal copy {src.name}: {e}")

    def on_speed_change(self, _value=None):
        self.speed_text.set(speed_text(snap_speed(self.speed.get())))

    def have_ffmpeg(self, extra="", parent=None):
        """True if ffmpeg is installed. If not, show a one-time-setup box with the install command and a
        Copy button, and return False."""
        if shutil.which("ffmpeg"):
            return True
        parent = parent or self.root
        win = tk.Toplevel(parent)
        win.title("One-time setup: ffmpeg")
        win.configure(bg=CREAM)
        win.transient(parent)
        win.resizable(False, False)
        ttk.Label(win, text="Faster copies need a free helper program called ffmpeg.", style="Field.TLabel",
                  wraplength=420).pack(anchor="w", padx=16, pady=(14, 4))
        ttk.Label(win, text="Install it once: open the Start menu, type  cmd  and press Enter, then paste "
                  "the line below and press Enter. When it finishes, close and reopen this program."
                  + (f"\n\n{extra}" if extra else ""), wraplength=420, justify="left").pack(anchor="w", padx=16)
        cmd = tk.StringVar(value=FFMPEG_INSTALL_CMD)
        box = ttk.Frame(win)
        box.pack(fill="x", padx=16, pady=12)
        box.columnconfigure(0, weight=1)
        ttk.Entry(box, textvariable=cmd, state="readonly").grid(row=0, column=0, sticky="ew", padx=(0, 8))
        copy_btn = ttk.Button(box, text="Copy", style="Gold.TButton")
        copy_btn.grid(row=0, column=1)

        def copy():
            self.root.clipboard_clear()
            self.root.clipboard_append(FFMPEG_INSTALL_CMD)
            copy_btn.config(text="Copied!")

        copy_btn.config(command=copy)
        ttk.Button(win, text="Close", command=win.destroy).pack(anchor="e", padx=16, pady=(0, 14))
        win.bind("<Escape>", lambda e: win.destroy())
        win.grab_set()
        parent.wait_window(win)
        return False
