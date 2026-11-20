"""Making faster copies with ffmpeg."""
import subprocess
from .config import NO_WINDOW


def speed_up(src, dst, factor, title=None):
    """Write a faster copy with ffmpeg; the pitch stays the same. ffmpeg's tempo filter only goes up to 2x in
    one step, so anything faster is chained: 2.0 then the rest."""
    if factor <= 2.0:
        tempo = f"atempo={factor:.2f}"
    else:
        tempo = f"atempo=2.0,atempo={factor / 2:.2f}"
    cmd = ["ffmpeg", "-loglevel", "error", "-y", "-i", str(src), "-filter:a", tempo, "-vn"]
    if title:
        cmd += ["-metadata", f"title={title}"]  # the title players show, e.g. Pesachim 7 (1.50x)
    r = subprocess.run(cmd + [str(dst)], capture_output=True, creationflags=NO_WINDOW)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.decode("utf-8", "replace").strip() or f"ffmpeg exit code {r.returncode}")
