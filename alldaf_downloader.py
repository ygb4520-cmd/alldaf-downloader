"""AllDaf Shiur Downloader: download every shiur by one speaker on one mesechta.
Files go to <folder>\\<speaker>\\<mesechta>\\. Needs only Python 3. Run:  python alldaf_downloader.py
"""
import difflib, hashlib, json, os, queue, re, shutil, ssl, subprocess, sys, threading, time
import urllib.error, urllib.parse, urllib.request, webbrowser
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog

API = "https://alldaf.org/api/trpc/posts.fetchList"
SEARCH_API = "https://alldaf.org/api/trpc/opensearch.all"
HEADERS = {"User-Agent": "Mozilla/5.0"}
SSL_CTX = None  # set from the checkbox before each run
VERSION = "1.13"  # bump this (and the release tag) when you publish a new .exe
REPO = "ygb4520-cmd/alldaf-downloader"
CONFIG = Path.home() / ".alldaf_downloader.json"
RETRIES = 5          # attempts for each network request
WORKERS = 3          # shiurim downloaded at the same time (the default; changeable in the window)
LOG_FILE = Path.home() / "alldaf_downloader.log"  # activity log, kept between runs
API_MSG = ("alldaf.org sent back something unexpected, so the site may have changed. "
           "Try 'Check for updates'; if you are up to date, the downloader needs a fix.")


class ApiChanged(Exception):
    """The site's reply did not look the way this program expects."""

# colors taken from the Talmud cover
BURGUNDY = "#5b1a22"
GOLD = "#c9a227"
GOLD_LIGHT = "#f3e3a8"   # tint for recently used mesechtos
CREAM = "#f8f3e6"        # window background
PANEL = "#fffdf7"        # list, entry and log background
INK = "#2b1417"
MUTED = "#8a7d6a"

# Bavli tractates in standard order, spellings as used on alldaf.org
MASECHTOS = ["Berachos", "Shabbos", "Eruvin", "Pesachim", "Yoma", "Sukkah", "Beitzah", "Rosh Hashanah",
             "Taanis", "Megillah", "Moed Katan", "Chagigah", "Yevamos", "Kesubos", "Nedarim", "Nazir",
             "Sotah", "Gitin", "Kidushin", "Bava Kama", "Bava Metzia", "Bava Basra", "Sanhedrin", "Makos",
             "Shevuos", "Avodah Zarah", "Horayos", "Zevachim", "Menachos", "Chulin", "Bechoros", "Erchin",
             "Temurah", "Kerisos", "Meilah", "Tamid", "Nidah"]
DEFAULT_SPEAKERS = [{"name": "Rabbi Zecharia Resnik", "id": 133821}]

# Shown in the "What's new" window. Newest first. Add an entry for each release.
CHANGELOG = [
    ("1.13", ["Buttons split into two rows, so Check for updates is no longer cut off."]),
    ("1.12", [
        "Test connection button: checks alldaf.org and GitHub and explains secure-connection problems.",
        "'Did you mean?' suggestions when a mesechta name finds no shiurim.",
        "Activity is saved to alldaf_downloader.log in your user folder.",
        "A finished run flashes the taskbar and shows Done in the title.",
        "Free-space check before downloading, so a run doesn't fail halfway.",
        "Parallel downloads setting (1 to 5) next to the progress bar.",
        "What's new window, which opens by itself after each update.",
    ]),
    ("1.9 to 1.11", [
        "Dapim box: download only a range of pages, for example 2 to 10.",
        "Speaker search by name when adding a speaker.",
        "Open folder button.",
        "Updates are checked against a SHA-256 checksum before they install.",
        "Windows-reserved file names are made safe.",
        "A clear message if the alldaf.org reply changes shape.",
    ]),
    ("1.6 to 1.8", [
        "Redesigned window with a banner and styled buttons.",
        "Missing-field warning names only what is missing.",
        "The search hint sits inside the search box and hides when you click in.",
    ]),
    ("1.5", ["Colors from the Talmud cover; Recently used and All mesechtos labels."]),
    ("1.4", ["The old copy is removed after an update."]),
    ("1.3", ["Fixed the temporary-folder warning after an update restart."]),
    ("1.2", ["Retries on connection errors; recently used mesechtos on top; cover icon."]),
    ("1.1", ["Automatic updates; files saved in Shiurim\\<speaker>\\<mesechta>\\ folders."]),
    ("1.0", ["First window version: pick a speaker, mesechta, and Bavli, Yerushalmi, or Both."]),
]


def make_ctx(skip_check):
    """None = normal checking. Skipping checks is only for networks whose proxy breaks certificate checks."""
    if not skip_check:
        return None
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def parse_version(v):
    return tuple(int(x) for x in re.findall(r"\d+", v))


def parse_author_id(raw):
    """Author ID from a bare number or an alldaf.org author link (trailing / or ?query are fine)."""
    m = re.search(r"(\d+)/?$", re.split(r"[?#]", (raw or "").strip())[0].rstrip())
    return int(m.group(1)) if m else None


def parse_authors(data):
    """Validate the site's search reply and return [{"id", "name"}, ...] (empty list = no match)."""
    if not isinstance(data, dict):
        raise ApiChanged(API_MSG)
    authors = data.get("authors") or []
    if not isinstance(authors, list) or any(
            not isinstance(a, dict) or not isinstance(a.get("id"), int) or not isinstance(a.get("name"), str)
            for a in authors):
        raise ApiChanged(API_MSG)
    return [{"id": a["id"], "name": a["name"].strip()} for a in authors]


def search_authors(query, ctx):
    """Look a speaker up by name on alldaf.org (the same search the site's search box uses)."""
    inp = {"0": {"query": query, "size": 10, "platform": "AllDaf"}}
    url = SEARCH_API + "?batch=1&input=" + urllib.parse.quote(json.dumps(inp, separators=(",", ":")), safe="")
    with urllib.request.urlopen(urllib.request.Request(url, headers=HEADERS), timeout=20, context=ctx) as r:
        body = r.read()
    try:
        data = json.loads(body)[0]["result"]["data"]
    except (ValueError, KeyError, IndexError, TypeError):
        raise ApiChanged(API_MSG)
    return parse_authors(data)


def record_daf(r):
    """Daf number of a shiur (the 'sortDaf' field is a counter across all of Shas, not the daf).
    Uses the site's own 'dafMasechta' label (e.g. 'Bava Kama 2'), else the first number in the title."""
    for m in r.get("metadata") or []:
        if isinstance(m, dict) and m.get("name") == "dafMasechta":
            nums = re.findall(r"\d+", str(m.get("value", "")))
            if nums:
                return int(nums[-1])
    nums = re.findall(r"\d+", r.get("title", ""))
    return int(nums[0]) if nums else None


def parse_daf_range(lo, hi):
    """('', '') -> (None, None). Raises ValueError with a friendly message for bad input."""
    def one(t):
        t = t.strip()
        if not t:
            return None
        if not t.isdigit() or int(t) < 1:
            raise ValueError("Dapim must be whole numbers, like 20 to 40 (or leave them blank for all).")
        return int(t)
    a, b = one(lo), one(hi)
    if a is not None and b is not None and a > b:
        raise ValueError("The first daf is after the last one.")
    return a, b


def check_for_update(skip_ssl):
    """Return a dict with tag, page, exe_url, sha_url if the latest GitHub release is newer than VERSION."""
    req = urllib.request.Request(f"https://api.github.com/repos/{REPO}/releases/latest",
                                 headers={"User-Agent": "AllDaf-Downloader",
                                          "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=10, context=make_ctx(skip_ssl)) as r:
        data = json.load(r)

    tag = data.get("tag_name", "")
    if not tag or parse_version(tag) <= parse_version(VERSION):
        return None
    assets = data.get("assets", [])

    def find(suffix):
        return next((a.get("browser_download_url") for a in assets
                     if a.get("name", "").lower().endswith(suffix)), None)

    return {"tag": tag, "page": data.get("html_url", f"https://github.com/{REPO}/releases"),
            "exe_url": find(".exe"), "sha_url": find(".sha256")}


def download_update(exe_url, sha_url):
    """Download the new .exe next to the running one, check it against the release's SHA-256 file,
    then swap the files. Certificates are always checked here: this file gets run, so it must be authentic."""
    current = Path(sys.executable)
    new = current.with_name(current.stem + ".new.exe")
    old = current.with_name(current.stem + ".old.exe")
    with urllib.request.urlopen(urllib.request.Request(sha_url, headers=HEADERS), timeout=30) as r:
        m = re.search(r"\b[0-9a-fA-F]{64}\b", r.read(4096).decode("ascii", "replace"))
    if not m:
        raise IOError("the release's checksum file is not readable")
    want = m.group(0).lower()
    digest = hashlib.sha256()
    with urllib.request.urlopen(urllib.request.Request(exe_url, headers=HEADERS), timeout=60) as r, \
            open(new, "wb") as out:
        size, got = int(r.headers.get("Content-Length") or 0), 0
        while True:
            chunk = r.read(65536)
            if not chunk:
                break
            out.write(chunk)
            digest.update(chunk)
            got += len(chunk)
    if (size and got != size) or digest.hexdigest() != want:
        new.unlink()
        raise IOError("the downloaded update did not match its checksum, so it was discarded")
    # Windows lets a running .exe be renamed but not overwritten, so move the old one aside first
    try:
        old.unlink()
    except OSError:
        pass
    os.replace(current, old)
    try:
        os.replace(new, current)
    except Exception:
        os.replace(old, current)  # put the old version back if the swap fails
        raise
    return current


def cleanup_old_exe():
    """Remove the previous version left behind by an update. The old copy stays locked until it finishes
    closing, so keep retrying in the background for a minute."""
    if getattr(sys, "frozen", False):
        exe = Path(sys.executable)
        old = exe.with_name(exe.stem + ".old.exe")

        def try_delete():
            for _ in range(30):
                try:
                    old.unlink()
                    return
                except FileNotFoundError:
                    return
                except OSError:
                    time.sleep(2)

        threading.Thread(target=try_delete, daemon=True).start()


WIN_RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}


def safe_name(s):
    s = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "_", s).strip().rstrip(". ")
    if s.split(".")[0].upper() in WIN_RESERVED:
        s = "_" + s
    return s or "_"


def fmt_eta(s):
    s = int(max(0, s))
    h, m, sec = s // 3600, s % 3600 // 60, s % 60
    return f"{h}h {m:02d}m" if h else (f"{m}m {sec:02d}s" if m else f"{sec}s")


def is_yerushalmi(r):
    return "yerushalmi" in ((r.get("series") or {}).get("name", "") + " " + r.get("title", "")).lower()


def resource_path(name):
    """Bundled file: next to this script, or inside the PyInstaller bundle."""
    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent)) / name


def write_log(text):
    """Append one line to the activity log. The log is trimmed so it doesn't grow forever."""
    try:
        if LOG_FILE.exists() and LOG_FILE.stat().st_size > 500_000:
            LOG_FILE.write_text(LOG_FILE.read_text(encoding="utf-8", errors="replace")[-200_000:], encoding="utf-8")
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')}  {text}\n")
    except OSError:
        pass


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


def estimate_bytes(url):
    """Size of one file, from a HEAD request (no download)."""
    req = urllib.request.Request(url, method="HEAD", headers=HEADERS)
    with urllib.request.urlopen(req, timeout=15, context=SSL_CTX) as r:
        return int(r.headers.get("Content-Length") or 0)


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


class App:
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
        f.rowconfigure(8, weight=1)

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
        self.worker_count = WORKERS
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

    # ---------- retries ----------
    def retry(self, action, label):
        """Run action(); on a connection error, wait and try again, up to RETRIES times."""
        delay = 3
        for attempt in range(1, RETRIES + 1):
            try:
                return action()
            except ApiChanged:
                raise
            except Exception as e:
                if attempt == RETRIES or self.stop.is_set():
                    raise
                self.say(f"Connection problem while {label} ({e}). Retrying in {delay}s "
                         f"(attempt {attempt + 1} of {RETRIES})...")
                for _ in range(delay * 10):
                    if self.stop.is_set():
                        raise
                    time.sleep(0.1)
                delay = min(delay * 2, 30)

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

    # ---------- settings ----------
    def save_cfg(self):
        self.cfg["folder"] = self.folder.get()
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

    def refresh_speakers(self, select=None):
        names = [s["name"] for s in self.cfg["speakers"]]
        self.speaker["values"] = names
        if names:
            self.speaker.set(select if select in names else names[0])
        else:
            self.speaker.set("")

    def pick_author(self, authors):
        """Small dialog: choose one of several matching speakers. Returns the chosen dict or None."""
        win = tk.Toplevel(self.root)
        win.title("Choose speaker")
        win.configure(bg=CREAM)
        win.transient(self.root)
        win.resizable(False, False)
        ttk.Label(win, text="Which speaker?", style="Field.TLabel").pack(anchor="w", padx=14, pady=(12, 6))
        lb = tk.Listbox(win, height=min(10, len(authors)), width=46, exportselection=False, activestyle="none",
                        relief="flat", bg=PANEL, fg=INK, selectbackground=GOLD, selectforeground=BURGUNDY,
                        highlightthickness=1, highlightbackground="#e2d5bd", font=("Segoe UI", 10))
        for a in authors:
            lb.insert("end", f"{a['name']}   (ID {a['id']})")
        lb.selection_set(0)
        lb.pack(padx=14)
        result = [None]

        def ok(_e=None):
            sel = lb.curselection()
            result[0] = authors[sel[0]] if sel else None
            win.destroy()

        row = ttk.Frame(win)
        row.pack(fill="x", padx=14, pady=12)
        ttk.Button(row, text="Add", style="Gold.TButton", command=ok).pack(side="right")
        ttk.Button(row, text="Cancel", command=win.destroy).pack(side="right", padx=(0, 8))
        lb.bind("<Double-Button-1>", ok)
        win.bind("<Return>", ok)
        win.bind("<Escape>", lambda e: win.destroy())
        win.grab_set()
        lb.focus_set()
        self.root.wait_window(win)
        return result[0]

    def store_speaker(self, name, author_id):
        self.cfg["speakers"] = [s for s in self.cfg["speakers"] if s["name"] != name]
        self.cfg["speakers"].append({"name": name, "id": author_id})
        self.save_cfg()
        self.refresh_speakers(name)

    def add_speaker(self):
        q = simpledialog.askstring("Add speaker", "Type the speaker's name to look them up on alldaf.org,\n"
                                   "or paste their author page link / ID number:", parent=self.root)
        if not q or not q.strip():
            return
        q = q.strip()
        author_id = parse_author_id(q)
        if author_id is not None and (q.isdigit() or "/" in q):  # a link or bare ID: no search needed
            name = simpledialog.askstring("Add speaker", "Speaker name (as you want it shown):", parent=self.root)
            if name and name.strip():
                self.store_speaker(name.strip(), author_id)
            return
        self.root.config(cursor="watch")
        self.root.update_idletasks()
        try:
            authors = search_authors(q, make_ctx(self.skip_ssl.get()))
        except ApiChanged as e:
            messagebox.showerror("Add speaker", str(e))
            return
        except Exception as e:
            messagebox.showerror("Add speaker", f"Couldn't search alldaf.org: {e}")
            return
        finally:
            self.root.config(cursor="")
        if not authors:
            messagebox.showinfo("Add speaker", f"No speaker found for '{q}'.\nTry a shorter name, or paste "
                                "the link to their author page on alldaf.org.")
            return
        chosen = self.pick_author(authors)
        if chosen:
            self.store_speaker(chosen["name"], chosen["id"])

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
        self.remember_masechta(mas)
        try:
            self.worker_count = max(1, min(5, int(self.workers.get())))
        except (tk.TclError, ValueError):
            self.worker_count = WORKERS
        self.root.title("AllDaf Shiur Downloader")
        self.save_cfg()
        self.busy = True
        global SSL_CTX
        SSL_CTX = make_ctx(self.skip_ssl.get())
        self.stop.clear()
        self.start_btn.config(state="disabled")
        self.stop_btn.config(state="normal")
        self.bar["value"] = 0
        args = (spk["id"], spk["name"], mas, self.mode.get(), Path(self.folder.get()).expanduser(), dafs)
        threading.Thread(target=self.worker, args=args, daemon=True).start()

    def say(self, text):
        self.q.put(("log", text))
        write_log(text)

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

    def get_page(self, inp):
        url = API + "?batch=1&input=" + urllib.parse.quote(json.dumps(inp, separators=(",", ":")), safe="")
        with urllib.request.urlopen(urllib.request.Request(url, headers=HEADERS), timeout=30,
                                    context=SSL_CTX) as r:
            body = r.read()
        try:
            return json.loads(body)[0]["result"]["data"]
        except (ValueError, KeyError, IndexError, TypeError):
            raise ApiChanged(API_MSG)

    def fetch(self, author_id, masechta):
        recs, skip, total = {}, 0, None
        while not self.stop.is_set():
            inp = {"0": {"take": 12, "skip": skip, "platform": "AllDaf", "masechta": masechta, "search": "",
                         "authorId": author_id, "sort": [{"field": "createdAt", "dir": "desc"}]}}
            data = self.retry(lambda: self.get_page(inp), "reading the shiur list")
            if not isinstance(data, dict):
                raise ApiChanged(API_MSG)
            page = data.get("records") or []
            if not isinstance(page, list) or any(not isinstance(p, dict) or "id" not in p or "title" not in p
                                                 for p in page):
                raise ApiChanged(API_MSG)
            if total is None:
                total = data.get("total", 0)
                if not isinstance(total, int):
                    raise ApiChanged(API_MSG)
            recs.update({p["id"]: p for p in page})
            skip += 12
            self.q.put(("progress", 0, f"Reading list: {len(recs)} of {total}", ""))
            if not page or len(recs) >= total:
                break
        return list(recs.values())

    def download(self, url, path, on_frac):
        """Download to <name>.part and rename when complete. A leftover .part (from a dropped connection or
        Stop) is continued with an HTTP Range request instead of starting over. Returns False if stopped."""
        part = path.with_name(path.name + ".part")
        have = part.stat().st_size if part.exists() else 0
        headers = dict(HEADERS)
        if have:
            headers["Range"] = f"bytes={have}-"
        try:
            r = urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=30, context=SSL_CTX)
        except urllib.error.HTTPError as e:
            if e.code == 416:  # the leftover piece doesn't fit the file; start over next try
                part.unlink(missing_ok=True)
            raise
        with r:
            length = int(r.headers.get("Content-Length") or 0)
            if have and r.status == 206:
                mode, got, total = "ab", have, (have + length if length else 0)
            else:  # fresh start, or the server ignored the Range header and sent everything
                mode, got, total = "wb", 0, length
            with open(part, mode) as out:
                while not self.stop.is_set():
                    chunk = r.read(65536)
                    if not chunk:
                        break
                    out.write(chunk)
                    got += len(chunk)
                    if total:
                        on_frac(got / total)
                else:
                    return False  # stopped: keep the .part so the next run can continue it
        if total and got != total:
            raise IOError(f"connection dropped ({got} of {total} bytes)")
        os.replace(part, path)
        return True

    def worker(self, author_id, speaker_name, masechta, mode, base_folder, dafs=(None, None)):
        summary = "Finished."
        try:
            write_log(f"Run: {speaker_name} / {masechta} / {mode} / dapim {dafs}")
            folder = base_folder / safe_name(speaker_name) / safe_name(masechta)
            folder.mkdir(parents=True, exist_ok=True)
            self.last_folder = folder
            fetched = self.fetch(author_id, masechta)
            if self.stop.is_set():
                summary = "Stopped."
                return
            recs = [r for r in fetched if r.get("s3Url")
                    and (mode == "Both" or is_yerushalmi(r) == (mode == "Yerushalmi"))]
            if not recs:
                close = difflib.get_close_matches(masechta, MASECHTOS, n=1, cutoff=0.6)
                hint = f" Did you mean '{close[0]}'?" if close and close[0] != masechta else ""
                self.say(f"No shiurim found for '{masechta}'.{hint} If the speaker has shiurim on it, the site may "
                         "spell the name differently; check the mesechta filter on their alldaf.org author page.")
                summary = "Nothing found."
                return
            lo, hi = dafs
            if lo is not None or hi is not None:
                kept, unknown = [], 0
                for r in recs:
                    d = record_daf(r)
                    if d is None:
                        unknown += 1
                        kept.append(r)  # can't tell which daf it is, so don't silently drop it
                    elif (lo is None or d >= lo) and (hi is None or d <= hi):
                        kept.append(r)
                label = f"{lo or 'start'} to {hi or 'end'}"
                if unknown:
                    self.say(f"{unknown} shiur(im) have no daf number in their title, so they were kept anyway.")
                recs = kept
                if not recs:
                    self.say(f"No shiurim found for dapim {label}.")
                    summary = "Nothing found."
                    return
            recs.sort(key=lambda r: (is_yerushalmi(r), r.get("sortDaf") or 0, r["id"]))
            used, jobs = set(), []
            for r in recs:
                base = safe_name(r["title"]) + (" (Yerushalmi)" if is_yerushalmi(r) else "")
                name, n = base, 2
                while name in used:
                    name, n = f"{base} ({n})", n + 1
                used.add(name)
                ext = os.path.splitext(urllib.parse.urlparse(r["s3Url"]).path)[1] or ".mp3"
                # also count files saved directly in the base folder by older versions
                jobs.append((r["s3Url"], folder / (name + ext), base_folder / (name + ext)))
            todo = [j for j in jobs if not j[1].exists() and not j[2].exists()]
            self.say(f"Found {len(jobs)} shiurim in {folder}; {len(jobs) - len(todo)} already there, "
                     f"{len(todo)} to download.")

            if todo:
                try:
                    per_file = estimate_bytes(todo[0][0])
                except Exception:
                    per_file = 0
                if per_file:
                    need = per_file * len(todo) * 1.1
                    free = shutil.disk_usage(base_folder).free
                    if free < need:
                        self.say(f"Not enough free space: about {need / 1e9:.1f} GB needed, {free / 1e9:.1f} GB free. "
                                 "Free up space or choose another folder.")
                        summary = "Not started: not enough free space."
                        return
            t0, failed = time.monotonic(), []
            lock = threading.Lock()
            frac, active = {}, {}            # per-file progress and names of files in flight
            st = {"handled": 0, "finished": 0}

            def refresh():
                with lock:
                    prog = st["handled"] + sum(frac.values())
                    names = list(active.values())
                cur = (names[0] + (f"  (+{len(names) - 1} more)" if len(names) > 1 else "")) if names else ""
                self.report(prog, len(todo), t0, cur)

            def run_one(i, url, path):
                if self.stop.is_set():
                    return
                last = [0.0]

                def on_frac(fr):
                    if time.monotonic() - last[0] < 0.25:
                        return
                    last[0] = time.monotonic()
                    with lock:
                        frac[i] = fr
                    refresh()

                with lock:
                    frac[i], active[i] = 0.0, path.name
                refresh()
                try:
                    ok, err = self.retry(lambda: self.download(url, path, on_frac),
                                         f"downloading {path.name}"), None
                except Exception as e:
                    ok, err = False, e
                with lock:
                    frac.pop(i, None)
                    active.pop(i, None)
                    if ok:
                        st["finished"] += 1
                        st["handled"] += 1
                    elif not self.stop.is_set():
                        failed.append(path.name)
                        st["handled"] += 1
                if not ok and not self.stop.is_set():
                    self.say(f"Failed after {RETRIES} tries: {path.name} ({err})")
                refresh()

            if todo:
                with ThreadPoolExecutor(self.worker_count) as ex:
                    list(ex.map(lambda t: run_one(*t), [(i, u, p) for i, (u, p, _) in enumerate(todo)]))
            summary = ("Stopped. " if self.stop.is_set() else "Done. ") + f"{st['finished']} downloaded"
            summary += f", {len(failed)} failed." if failed else "."
            if failed:
                self.say("Not downloaded (run again to retry): " + ", ".join(failed))
        except Exception as e:
            summary = f"Error: {e}"
            self.say(summary)
        finally:
            write_log(summary)
            self.q.put(("done", summary))

    def report(self, progress, total, t0, name):
        pct = progress / max(1, total) * 100
        el = time.monotonic() - t0
        eta = f" | about {fmt_eta(el / progress * (total - progress))} left" if progress >= 0.5 else ""
        self.q.put(("progress", pct, f"{int(progress)} of {total} done{eta}", name))

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


if __name__ == "__main__":
    cleanup_old_exe()
    root = tk.Tk()
    App(root)
    root.mainloop()