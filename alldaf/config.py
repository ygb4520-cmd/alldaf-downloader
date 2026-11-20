"""Settings, constants, colors and the what's-new list."""
import os
import sys
from pathlib import Path


API = "https://alldaf.org/api/trpc/posts.fetchList"


SEARCH_API = "https://alldaf.org/api/trpc/opensearch.all"


HEADERS = {"User-Agent": "Mozilla/5.0"}


VERSION = "1.22"  # bump this (and the release tag) when you publish a new .exe


REPO = "ygb4520-cmd/alldaf-downloader"


CONFIG = Path.home() / ".alldaf_downloader.json"


RETRIES = 5          # attempts for each network request


WORKERS = 3          # shiurim downloaded at the same time (the default; changeable in the window)


LOG_FILE = Path.home() / "alldaf_downloader.log"  # activity log, kept between runs


FFMPEG_INSTALL_CMD = "winget install Gyan.FFmpeg"


BENCH_FILES = 6                 # shiurim used in each speed test


BENCH_ORDER = [1, 3, 5, 2, 4]   # settings to test, in this order (mixed to reduce server caching bias)


BENCH_TOLERANCE = 0.10          # a setting within 10% of the fastest counts as "as fast"


SPEED_MIN, SPEED_MAX, SPEED_STEP = 1.0, 2.5, 0.1  # playback speed slider range


NO_WINDOW = 0x08000000 if sys.platform.startswith("win") else 0  # hide the ffmpeg console window


CONVERT_WORKERS = max(1, min(4, (os.cpu_count() or 2) - 1))  # faster copies made at the same time


API_MSG = ("alldaf.org sent back something unexpected, so the site may have changed. "
           "Try 'Check for updates'; if you are up to date, the downloader needs a fix.")


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
    ("1.22", ["If ffmpeg (needed for faster copies) is missing, a short setup box shows the install command with "
              "a Copy button instead of a plain warning."]),
    ("1.21", ["Faster copies show the speed right after the English title, for example "
              "Pesachim 121 (1.50x) פסחים דף קכא."]),
    ("1.20", ["Faster copies keep the full title layout in their title tag, "
              "like Pesachim 121 פסחים דף קכא."]),
    ("1.19", ["Faster copies also carry the speed in their title tag, for example Pesachim 7 (1.50x), "
              "so players show it too."]),
    ("1.18", ["Faster copies are made in parallel (based on your CPU cores), and each one is made as soon as its "
              "shiur finishes downloading, so less waiting at the end."]),
    ("1.17", ["Faster copies show their speed in the file name, for example Pesachim 7 (1.50x).mp3."]),
    ("1.16", ["Each download with a playback speed asks whether to keep both the normal and faster copies, "
              "or only the faster ones (the normal file is deleted once its faster copy is made)."]),
    ("1.15", ["Playback speed slider (1.00x to 2.50x): saves a faster copy of each shiur in a Fast folder. "
              "Make faster copies... works on any mesechta (it offers to download one that isn't there yet), "
              "all of a speaker's shiurim, or files you pick. Needs ffmpeg, installed once with: "
              "winget install Gyan.FFmpeg.",
              "The window can't be made smaller than its content, and the activity log keeps a steady size."]),
    ("1.14", ["Auto-test speed button: tries 1 to 5 parallel downloads on a sample and sets the best one."]),
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


HEBREW_MASECHTOS = {
    "Berachos": "ברכות", "Shabbos": "שבת", "Eruvin": "עירובין", "Pesachim": "פסחים", "Yoma": "יומא",
    "Sukkah": "סוכה", "Beitzah": "ביצה", "Rosh Hashanah": "ראש השנה", "Taanis": "תענית", "Megillah": "מגילה",
    "Moed Katan": "מועד קטן", "Chagigah": "חגיגה", "Yevamos": "יבמות", "Kesubos": "כתובות", "Nedarim": "נדרים",
    "Nazir": "נזיר", "Sotah": "סוטה", "Gitin": "גיטין", "Kidushin": "קידושין", "Bava Kama": "בבא קמא",
    "Bava Metzia": "בבא מציעא", "Bava Basra": "בבא בתרא", "Sanhedrin": "סנהדרין", "Makos": "מכות",
    "Shevuos": "שבועות", "Avodah Zarah": "עבודה זרה", "Horayos": "הוריות", "Zevachim": "זבחים",
    "Menachos": "מנחות", "Chulin": "חולין", "Bechoros": "בכורות", "Erchin": "ערכין", "Temurah": "תמורה",
    "Kerisos": "כריתות", "Meilah": "מעילה", "Tamid": "תמיד", "Nidah": "נידה",
}


class _Shared:
    """State shared across modules."""
    ssl_ctx = None  # set from the checkbox before each run


shared = _Shared()
