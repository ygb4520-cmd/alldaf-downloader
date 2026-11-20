"""Auto-test for the best number of parallel downloads."""
import shutil
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tkinter import messagebox
from .config import BENCH_FILES, BENCH_ORDER, shared
from .net import make_ctx


class SpeedTestMixin:
    # ---------- speed test ----------
    def auto_test(self):
        if self.busy:
            messagebox.showinfo("Auto-test speed", "Wait for the current download to finish first.")
            return
        spk = next((s for s in self.cfg["speakers"] if s["name"] == self.speaker.get()), None)
        mas = self.masechta()
        if not spk or not mas:
            messagebox.showwarning("Auto-test speed", "Choose a speaker and a mesechta first. The test uses "
                                   "that mesechta's shiurim.")
            return
        if not messagebox.askyesno("Auto-test speed",
                                   f"This downloads {BENCH_FILES} shiurim {len(BENCH_ORDER)} times, which can be "
                                   "a few hundred MB in total. The files go to a temporary folder and are deleted "
                                   "afterwards. Continue?"):
            return
        shared.ssl_ctx = make_ctx(self.skip_ssl.get())
        self.stop.clear()
        self.busy = True
        self.start_btn.config(state="disabled")
        self.bench_btn.config(state="disabled")
        self.bar["value"] = 0
        threading.Thread(target=self.run_auto_test, args=(spk["id"], mas), daemon=True).start()

    def run_auto_test(self, author_id, masechta):
        results, note = [], ""
        tmp = Path(tempfile.mkdtemp(prefix="alldaf_speedtest_"))
        try:
            recs = [r for r in self.fetch(author_id, masechta) if r.get("s3Url")]
            sample = recs[:BENCH_FILES]
            if len(sample) < 3:
                note = "Need at least 3 shiurim on this mesechta to test. Choose one with more shiurim."
            else:
                for step, w in enumerate(BENCH_ORDER, 1):
                    if self.stop.is_set():
                        break
                    self.q.put(("progress", (step - 1) / len(BENCH_ORDER) * 100,
                                f"Testing {w} at a time ({step} of {len(BENCH_ORDER)})...", ""))
                    before, failed = self.retry_count, []

                    def fetch_one(item, w=w):
                        i, r = item
                        path = tmp / f"{w}_{i}.mp3"
                        try:
                            if not self.retry(lambda: self.download(r["s3Url"], path, lambda f: None),
                                              "speed test"):
                                failed.append(path.name)
                        except Exception:
                            failed.append(path.name)

                    t0 = time.monotonic()
                    with ThreadPoolExecutor(w) as ex:
                        list(ex.map(fetch_one, enumerate(sample)))
                    results.append({"w": w, "secs": time.monotonic() - t0,
                                    "retries": self.retry_count - before, "failed": len(failed)})
                    for p in tmp.glob(f"{w}_*"):
                        p.unlink(missing_ok=True)
        except Exception as e:
            note = f"The speed test stopped: {e}"
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        self.q.put(("bench_done", results, note))
