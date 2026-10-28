"""AllDaf Shiur Downloader: download every shiur by one speaker on one mesechta.
Needs only Python 3 (tkinter is included with the python.org installer). Run:  python alldaf_downloader.py
"""
import json, os, queue, re, ssl, threading, time
import urllib.parse, urllib.request
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog

API = "https://alldaf.org/api/trpc/posts.fetchList"
HEADERS = {"User-Agent": "Mozilla/5.0"}
SSL_CTX = None  # set from the checkbox before each run


def make_ctx(skip_check):
    """None = normal checking. Skipping checks is only for networks whose proxy breaks certificate checks."""
    if not skip_check:
        return None
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx
CONFIG = Path.home() / ".alldaf_downloader.json"
# Spellings copied from the mesechta list on alldaf.org
MASECHTOS = ["Berachos", "Shabbos", "Eruvin", "Pesachim", "Shekalim", "Yoma", "Succah", "Beitzah",
             "Rosh Hashanah", "Taanis", "Megilah", "Moed Katan", "Chagiga", "Yevamos", "Kesuvos",
             "Nedarim", "Nazir", "Sotah", "Gitin", "Kidushin", "Bava Kama", "Bava Metzia", "Bava Basra",
             "Sanhedrin", "Makos", "Shevuos", "Avodah Zarah", "Horayos", "Zevachim", "Menachos", "Chulin",
             "Bechoros", "Erchin", "Temurah", "Kerisus", "Meilah", "Nidah"]
DEFAULT_SPEAKERS = [{"name": "Rabbi Zecharia Resnik", "id": 133821}]


def fmt_eta(s):
    s = int(max(0, s))
    h, m, sec = s // 3600, s % 3600 // 60, s % 60
    return f"{h}h {m:02d}m" if h else (f"{m}m {sec:02d}s" if m else f"{sec}s")


def is_yerushalmi(r):
    return "yerushalmi" in ((r.get("series") or {}).get("name", "") + " " + r.get("title", "")).lower()


class App:
    def __init__(self, root):
        self.root, self.q, self.stop = root, queue.Queue(), threading.Event()
        self.cfg = {"speakers": DEFAULT_SPEAKERS, "folder": str(Path.home() / "Downloads" / "Shiurim")}
        try:
            self.cfg.update(json.loads(CONFIG.read_text(encoding="utf-8")))
        except Exception:
            pass
        root.title("AllDaf Shiur Downloader")
        root.geometry("620x680")
        f = ttk.Frame(root, padding=10)
        f.pack(fill="both", expand=True)
        f.columnconfigure(1, weight=1)

        ttk.Label(f, text="Speaker").grid(row=0, column=0, sticky="w")
        self.speaker = ttk.Combobox(f, state="readonly")
        self.speaker.grid(row=0, column=1, sticky="ew", padx=5)
        b = ttk.Frame(f)
        b.grid(row=0, column=2)
        ttk.Button(b, text="Add", width=7, command=self.add_speaker).pack(side="left")
        ttk.Button(b, text="Remove", width=8, command=self.remove_speaker).pack(side="left", padx=3)
        self.refresh_speakers()

        ttk.Label(f, text="Mesechta").grid(row=1, column=0, sticky="nw", pady=8)
        mf = ttk.Frame(f)
        mf.grid(row=1, column=1, columnspan=2, sticky="ew", pady=8, padx=5)
        mf.columnconfigure(0, weight=1)
        self.search = tk.StringVar()
        self.search.trace_add("write", lambda *_: self.filter_list())
        ttk.Entry(mf, textvariable=self.search).grid(row=0, column=0, sticky="ew")
        ttk.Label(mf, text="type to search").grid(row=0, column=1, padx=5)
        self.lb = tk.Listbox(mf, height=7, exportselection=False)
        self.lb.grid(row=1, column=0, sticky="ew", pady=3)
        sb = ttk.Scrollbar(mf, command=self.lb.yview)
        sb.grid(row=1, column=1, sticky="ns")
        self.lb.config(yscrollcommand=sb.set)
        self.filter_list("Pesachim")

        ttk.Label(f, text="Type").grid(row=2, column=0, sticky="w")
        self.mode = tk.StringVar(value="Bavli")
        rf = ttk.Frame(f)
        rf.grid(row=2, column=1, sticky="w", padx=5)
        for m in ("Bavli", "Yerushalmi", "Both"):
            ttk.Radiobutton(rf, text=m, value=m, variable=self.mode).pack(side="left", padx=4)

        ttk.Label(f, text="Save to").grid(row=3, column=0, sticky="w", pady=8)
        self.folder = tk.StringVar(value=self.cfg["folder"])
        ttk.Entry(f, textvariable=self.folder).grid(row=3, column=1, sticky="ew", padx=5)
        ttk.Button(f, text="Browse", command=self.browse).grid(row=3, column=2)

        self.skip_ssl = tk.BooleanVar(value=self.cfg.get("skip_ssl", True))
        bf = ttk.Frame(f)
        bf.grid(row=4, column=0, columnspan=3, pady=5)
        self.start_btn = ttk.Button(bf, text="Start download", command=self.start)
        self.start_btn.pack(side="left", padx=5)
        self.stop_btn = ttk.Button(bf, text="Stop", command=self.stop.set, state="disabled")
        self.stop_btn.pack(side="left", padx=5)
        ttk.Checkbutton(bf, text="Skip SSL check (proxy)", variable=self.skip_ssl).pack(side="left", padx=5)

        self.bar = ttk.Progressbar(f, maximum=100)
        self.bar.grid(row=5, column=0, columnspan=3, sticky="ew", pady=3)
        self.status, self.current = tk.StringVar(value="Ready"), tk.StringVar()
        ttk.Label(f, textvariable=self.status).grid(row=6, column=0, columnspan=3, sticky="w")
        ttk.Label(f, textvariable=self.current).grid(row=7, column=0, columnspan=3, sticky="w")
        self.log = tk.Text(f, height=10, state="disabled", wrap="word")
        self.log.grid(row=8, column=0, columnspan=3, sticky="nsew", pady=5)
        f.rowconfigure(8, weight=1)
        root.protocol("WM_DELETE_WINDOW", self.close)
        self.poll()

    # ---------- settings ----------
    def save_cfg(self):
        self.cfg["folder"] = self.folder.get()
        self.cfg["skip_ssl"] = self.skip_ssl.get()
        try:
            CONFIG.write_text(json.dumps(self.cfg, indent=2), encoding="utf-8")
        except Exception:
            pass

    def refresh_speakers(self, select=None):
        names = [s["name"] for s in self.cfg["speakers"]]
        self.speaker["values"] = names
        if names:
            self.speaker.set(select if select in names else names[0])
        else:
            self.speaker.set("")

    def add_speaker(self):
        name = simpledialog.askstring("Add speaker", "Speaker name:", parent=self.root)
        if not name:
            return
        raw = simpledialog.askstring("Add speaker", "Author ID, or paste the author page link\n"
                                     "(the number at the end of alldaf.org/authors/...):", parent=self.root)
        m = re.search(r"(\d+)\s*$", (raw or "").strip())
        if not m:
            messagebox.showerror("Add speaker", "Couldn't find an ID number.")
            return
        self.cfg["speakers"] = [s for s in self.cfg["speakers"] if s["name"] != name.strip()]
        self.cfg["speakers"].append({"name": name.strip(), "id": int(m.group(1))})
        self.save_cfg()
        self.refresh_speakers(name.strip())

    def remove_speaker(self):
        n = self.speaker.get()
        if n and messagebox.askyesno("Remove", f"Remove {n} from the list?"):
            self.cfg["speakers"] = [s for s in self.cfg["speakers"] if s["name"] != n]
            self.save_cfg()
            self.refresh_speakers()

    def browse(self):
        d = filedialog.askdirectory(initialdir=self.folder.get() or str(Path.home()))
        if d:
            self.folder.set(d)

    def filter_list(self, select=None):
        t = (select or self.search.get()).lower().strip()
        self.lb.delete(0, "end")
        for m in MASECHTOS:
            if t in m.lower():
                self.lb.insert("end", m)
        if self.lb.size():
            self.lb.selection_set(self.lb.get(0, "end").index(select) if select else 0)

    def masechta(self):
        sel = self.lb.curselection()
        return self.lb.get(sel[0]) if sel else self.search.get().strip()

    # ---------- run ----------
    def start(self):
        spk = next((s for s in self.cfg["speakers"] if s["name"] == self.speaker.get()), None)
        mas = self.masechta()
        if not spk or not mas or not self.folder.get().strip():
            messagebox.showwarning("Missing info", "Choose a speaker, a mesechta, and a folder.")
            return
        self.save_cfg()
        global SSL_CTX
        SSL_CTX = make_ctx(self.skip_ssl.get())
        self.stop.clear()
        self.start_btn.config(state="disabled")
        self.stop_btn.config(state="normal")
        self.bar["value"] = 0
        args = (spk["id"], mas, self.mode.get(), Path(self.folder.get()).expanduser())
        threading.Thread(target=self.worker, args=args, daemon=True).start()

    def say(self, text):
        self.q.put(("log", text))

    def fetch(self, author_id, masechta):
        recs, skip, total = {}, 0, None
        while not self.stop.is_set():
            inp = {"0": {"take": 12, "skip": skip, "platform": "AllDaf", "masechta": masechta, "search": "",
                         "authorId": author_id, "sort": [{"field": "createdAt", "dir": "desc"}]}}
            url = API + "?batch=1&input=" + urllib.parse.quote(json.dumps(inp, separators=(",", ":")), safe="")
            with urllib.request.urlopen(urllib.request.Request(url, headers=HEADERS), timeout=30, context=SSL_CTX) as r:
                data = json.load(r)[0]["result"]["data"]
            page = data.get("records") or []
            total = data.get("total", 0) if total is None else total
            recs.update({p["id"]: p for p in page})
            skip += 12
            self.q.put(("progress", 0, f"Reading list: {len(recs)} of {total}", ""))
            if not page or len(recs) >= total:
                break
        return list(recs.values())

    def download(self, url, path, on_frac):
        part = path.with_name(path.name + ".part")
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=HEADERS), timeout=30, context=SSL_CTX) as r, \
                    open(part, "wb") as out:
                size, got = int(r.headers.get("Content-Length") or 0), 0
                while not self.stop.is_set():
                    chunk = r.read(65536)
                    if not chunk:
                        out.close()
                        os.replace(part, path)
                        return True
                    out.write(chunk)
                    got += len(chunk)
                    if size:
                        on_frac(got / size)
            return False
        finally:
            if part.exists():
                try:
                    part.unlink()
                except OSError:
                    pass

    def worker(self, author_id, masechta, mode, folder):
        summary = "Finished."
        try:
            folder.mkdir(parents=True, exist_ok=True)
            recs = [r for r in self.fetch(author_id, masechta) if r.get("s3Url")
                    and (mode == "Both" or is_yerushalmi(r) == (mode == "Yerushalmi"))]
            if not recs:
                self.say(f"No shiurim found for '{masechta}'. If the speaker has shiurim on it, the site may spell "
                         "the name differently; check the mesechta filter on their alldaf.org author page.")
                summary = "Nothing found."
                return
            recs.sort(key=lambda r: (is_yerushalmi(r), r.get("sortDaf") or 0, r["id"]))
            used, jobs = set(), []
            for r in recs:
                base = re.sub(r'[\\/:*?"<>|]', "_", r["title"]).strip() + (" (Yerushalmi)" if is_yerushalmi(r) else "")
                name, n = base, 2
                while name in used:
                    name, n = f"{base} ({n})", n + 1
                used.add(name)
                ext = os.path.splitext(urllib.parse.urlparse(r["s3Url"]).path)[1] or ".mp3"
                jobs.append((r["s3Url"], folder / (name + ext)))
            todo = [j for j in jobs if not j[1].exists()]
            self.say(f"Found {len(jobs)} shiurim; {len(jobs) - len(todo)} already in the folder, {len(todo)} to download.")
            t0, failed, finished = time.monotonic(), [], 0
            for i, (url, path) in enumerate(todo):
                if self.stop.is_set():
                    break
                last = [0.0]

                def on_frac(fr, i=i, path=path):
                    if time.monotonic() - last[0] < 0.25:
                        return
                    last[0] = time.monotonic()
                    self.report(i + fr, len(todo), t0, path.name)

                self.report(i, len(todo), t0, path.name)
                ok = False
                for _ in range(3):
                    try:
                        ok = self.download(url, path, on_frac)
                        break
                    except Exception as e:
                        err = e
                        time.sleep(1)
                if ok:
                    finished += 1
                elif not self.stop.is_set():
                    failed.append(path.name)
                    self.say(f"Failed: {path.name} ({err})")
            summary = ("Stopped. " if self.stop.is_set() else "Done. ") + f"{finished} downloaded"
            summary += f", {len(failed)} failed." if failed else "."
        except Exception as e:
            summary = f"Error: {e}"
            self.say(summary)
        finally:
            self.q.put(("done", summary))

    def report(self, progress, total, t0, name):
        pct = progress / max(1, total) * 100
        el = time.monotonic() - t0
        eta = f" | about {fmt_eta(el / progress * (total - progress))} left" if progress >= 0.5 else ""
        self.q.put(("progress", pct, f"{int(progress)} of {total} done{eta}", name))

    def poll(self):
        while True:
            try:
                kind, *a = self.q.get_nowait()
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
            elif kind == "done":
                self.status.set(a[0])
                self.current.set("")
                self.start_btn.config(state="normal")
                self.stop_btn.config(state="disabled")
        self.root.after(100, self.poll)

    def close(self):
        self.stop.set()
        self.save_cfg()
        self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    App(root)
    root.mainloop()
