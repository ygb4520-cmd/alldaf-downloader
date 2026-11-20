"""Small pure helpers: names, numbers, titles, daf ranges, and the activity log."""
import re
import sys
import time
from pathlib import Path
from .config import BENCH_TOLERANCE, HEBREW_MASECHTOS, LOG_FILE, SPEED_MAX, SPEED_MIN, SPEED_STEP, WORKERS


def parse_version(v):
    return tuple(int(x) for x in re.findall(r"\d+", v))


def parse_author_id(raw):
    """Author ID from a bare number or an alldaf.org author link (trailing / or ?query are fine)."""
    m = re.search(r"(\d+)/?$", re.split(r"[?#]", (raw or "").strip())[0].rstrip())
    return int(m.group(1)) if m else None


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
    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent)) / name


def write_log(text):
    """Append one line to the activity log. The log is trimmed so it doesn't grow forever."""
    try:
        if LOG_FILE.exists() and LOG_FILE.stat().st_size > 500_000:
            LOG_FILE.write_text(LOG_FILE.read_text(encoding="utf-8", errors="replace")[-200_000:], encoding="utf-8")
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')}  {text}\n")
    except OSError:
        pass


def snap_speed(v):
    """Clamp to the slider range and round to the nearest step, e.g. 1.2999999 -> 1.30."""
    v = min(SPEED_MAX, max(SPEED_MIN, float(v)))
    return round(round(v / SPEED_STEP) * SPEED_STEP, 2)


def speed_text(v):
    return "Normal" if v <= 1.0 else f"{v:.2f}x"


def gematria(n):
    """Hebrew letters for a number, e.g. 121 -> קכא, 15 -> טו, 16 -> טז (for daf numbers)."""
    out = ""
    for value, letter in ((400, "ת"), (300, "ש"), (200, "ר"), (100, "ק")):
        while n >= value:
            out += letter
            n -= value
    if n == 15:
        return out + "טו"
    if n == 16:
        return out + "טז"
    for value, letters in ((90, "צ"), (80, "פ"), (70, "ע"), (60, "ס"), (50, "נ"), (40, "מ"),
                           (30, "ל"), (20, "כ"), (10, "י")):
        if n >= value:
            out += letters
            n -= value
    ones = "אבגדהוזחט"
    return out + (ones[n - 1] if n else "")


def title_with_speed(stem, label):
    """'Pesachim 121' -> 'Pesachim 121 (1.50x) פסחים דף קכא', the alldaf.org layout with the speed after the English."""
    m = re.match(r"^(.+?) (\d+)", stem)
    if not m or m.group(1) not in HEBREW_MASECHTOS:
        return f"{stem} ({label})"
    mes, daf = m.group(1), int(m.group(2))
    rest = stem[m.end():]  # e.g. " (Yerushalmi)" if there is one
    return f"{mes} {daf} ({label}) {HEBREW_MASECHTOS[mes]} דף {gematria(daf)}{rest}"


def fast_name(src, label):
    """File name for a faster copy, with the speed in parentheses: 'Pesachim 7.mp3' -> 'Pesachim 7 (1.50x).mp3'."""
    return f"{src.stem} ({label}){src.suffix}"


def count_downloaded(base, speaker, mesechta):
    """How many .mp3 files are already saved for this speaker and mesechta (not counting Fast copies)."""
    mdir = base / safe_name(speaker) / safe_name(mesechta)
    return len(list(mdir.glob("*.mp3"))) if mdir.exists() else 0


def recommend_workers(results):
    """Lowest setting that is within BENCH_TOLERANCE of the fastest clean run and had no retries."""
    clean = [r for r in results if r["failed"] == 0]
    if not clean:
        return WORKERS
    calm = [r for r in clean if r["retries"] == 0] or clean  # prefer runs the server didn't push back on
    fastest = min(r["secs"] for r in calm)
    ok = [r for r in calm if r["secs"] <= fastest * (1 + BENCH_TOLERANCE)]
    return min(r["w"] for r in ok)
