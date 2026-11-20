"""Reading the shiur list and downloading files."""
import difflib
import json
import os
import shutil
import threading
import time
import urllib.error, urllib.parse, urllib.request
from concurrent.futures import ThreadPoolExecutor
from .config import API, API_MSG, HEADERS, MASECHTOS, RETRIES, shared
from .net import ApiChanged, estimate_bytes
from .util import fast_name, fmt_eta, is_yerushalmi, record_daf, safe_name, write_log


class DownloadMixin:
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
                self.retry_count += 1
                self.say(f"Connection problem while {label} ({e}). Retrying in {delay}s "
                         f"(attempt {attempt + 1} of {RETRIES})...")
                for _ in range(delay * 10):
                    if self.stop.is_set():
                        raise
                    time.sleep(0.1)
                delay = min(delay * 2, 30)

    def say(self, text):
        self.q.put(("log", text))
        write_log(text)

    def get_page(self, inp):
        url = API + "?batch=1&input=" + urllib.parse.quote(json.dumps(inp, separators=(",", ":")), safe="")
        with urllib.request.urlopen(urllib.request.Request(url, headers=HEADERS), timeout=30,
                                    context=shared.ssl_ctx) as r:
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
            r = urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=30, context=shared.ssl_ctx)
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

    def worker(self, author_id, speaker_name, masechta, mode, base_folder, dafs=(None, None),
               speed_label="Normal", factor=1.0, keep="both"):
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
                if ok and factor > 1.0 and not self.stop.is_set():
                    # make this shiur's faster copy now, while the others are still downloading
                    self.make_fast_copy(path, fast_dir / fast_name(path, speed_label), factor, keep)
                if not ok and not self.stop.is_set():
                    self.say(f"Failed after {RETRIES} tries: {path.name} ({err})")
                refresh()

            fast_dir = folder / f"Fast {speed_label}"
            if todo:
                with ThreadPoolExecutor(self.worker_count) as ex:
                    list(ex.map(lambda t: run_one(*t), [(i, u, p) for i, (u, p, _) in enumerate(todo)]))
            if factor > 1.0 and not self.stop.is_set():
                pairs = []
                for _, path, legacy in jobs:
                    src = path if path.exists() else legacy
                    if src.exists():
                        pairs.append((src, fast_dir / fast_name(src, speed_label)))
                if pairs:
                    self.convert_pool(pairs, factor, keep, f"Speeding up ({speed_label})")
                    if not self.stop.is_set():
                        self.say(f"Faster copies ({speed_label}) are in {fast_dir}")
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
