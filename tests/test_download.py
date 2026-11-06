"""Runs the real download()/worker() code against a small local HTTP server that supports Range."""
import http.server, pathlib, queue, sys, tempfile, threading, unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import alldaf_downloader as ad

DATA = {f"/{i}.mp3": bytes([i]) * (300_000 + i) for i in range(6)}
CUT = {"on": False}


class H(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        body, start = DATA[self.path], 0
        rng = self.headers.get("Range")
        if rng:
            start = int(rng.split("=")[1].rstrip("-"))
            self.send_response(206)
            self.send_header("Content-Range", f"bytes {start}-{len(body) - 1}/{len(body)}")
        else:
            self.send_response(200)
        out = body[start:]
        self.send_header("Content-Length", str(len(out)))
        self.end_headers()
        if CUT["on"] and not rng:
            self.wfile.write(out[:100_000])  # drop the connection early the first time
            CUT["on"] = False
            return
        self.wfile.write(out)


def make_app():
    a = ad.App.__new__(ad.App)
    a.q, a.stop, a.busy, a.last_folder = queue.Queue(), threading.Event(), False, None
    return a


class Download(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
        cls.base = f"http://127.0.0.1:{cls.srv.server_port}"
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()

    def test_resume_and_truncation(self):
        app, d = make_app(), pathlib.Path(tempfile.mkdtemp())
        path = d / "x.mp3"
        # a leftover partial file is continued, not restarted
        (d / "x.mp3.part").write_bytes(DATA["/1.mp3"][:1000])
        self.assertTrue(app.download(self.base + "/1.mp3", path, lambda f: None))
        self.assertEqual(path.read_bytes(), DATA["/1.mp3"])
        self.assertFalse((d / "x.mp3.part").exists())
        # a connection that drops early raises, keeps the .part, and the retry finishes the file
        CUT["on"] = True
        path2 = d / "y.mp3"
        with self.assertRaises(Exception):
            app.download(self.base + "/2.mp3", path2, lambda f: None)
        self.assertFalse(path2.exists())
        self.assertTrue((d / "y.mp3.part").exists())
        self.assertTrue(app.download(self.base + "/2.mp3", path2, lambda f: None))
        self.assertEqual(path2.read_bytes(), DATA["/2.mp3"])

    def test_worker_downloads_all_in_parallel(self):
        app, d = make_app(), pathlib.Path(tempfile.mkdtemp())
        recs = [{"id": i, "title": f"T {i}", "s3Url": f"{self.base}/{i}.mp3", "sortDaf": i} for i in range(6)]
        app.fetch = lambda a, m: recs
        app.worker(1, "Spk", "Berachos", "Bavli", d)
        msgs = []
        while not app.q.empty():
            msgs.append(app.q.get())
        self.assertIn("6 downloaded", msgs[-1][1])
        for i in range(6):
            self.assertEqual((d / "Spk" / "Berachos" / f"T {i}.mp3").read_bytes(), DATA[f"/{i}.mp3"])
        # second run: everything already there
        app.worker(1, "Spk", "Berachos", "Bavli", d)
        last = None
        while not app.q.empty():
            last = app.q.get()
        self.assertIn("0 downloaded", last[1])

    def test_api_shape_check(self):
        app = make_app()
        app.get_page = lambda inp: {"records": [{"nope": 1}], "total": 1}
        with self.assertRaises(ad.ApiChanged):
            app.fetch(1, "Berachos")
        app.get_page = lambda inp: ["not a dict"]
        with self.assertRaises(ad.ApiChanged):
            app.fetch(1, "Berachos")


if __name__ == "__main__":
    unittest.main()
