"""Speed / title helpers for faster copies (no ffmpeg needed: subprocess is faked)."""
import pathlib, sys, unittest
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import alldaf_downloader as ad


def tempo_of(factor, title=None):
    with mock.patch.object(ad.subprocess, "run", return_value=SimpleNamespace(returncode=0, stderr=b"")) as run:
        ad.speed_up(pathlib.Path("in.mp3"), pathlib.Path("out.mp3"), factor, title)
    cmd = run.call_args[0][0]
    return cmd[cmd.index("-filter:a") + 1], cmd


class Speed(unittest.TestCase):
    def test_single_step_tempo(self):
        self.assertEqual(tempo_of(1.5)[0], "atempo=1.50")
        self.assertEqual(tempo_of(2.0)[0], "atempo=2.00")

    def test_chained_tempo_above_2x(self):
        self.assertEqual(tempo_of(2.5)[0], "atempo=2.0,atempo=1.25")

    def test_title_metadata_and_paths(self):
        _, cmd = tempo_of(1.5, "Pesachim 7 (1.50x)")
        self.assertIn("title=Pesachim 7 (1.50x)", cmd)
        self.assertEqual(cmd[-1], "out.mp3")
        self.assertNotIn("-metadata", tempo_of(1.5)[1])

    def test_ffmpeg_failure_raises(self):
        with mock.patch.object(ad.subprocess, "run", return_value=SimpleNamespace(returncode=1, stderr=b"boom")):
            with self.assertRaisesRegex(RuntimeError, "boom"):
                ad.speed_up(pathlib.Path("a.mp3"), pathlib.Path("b.mp3"), 1.5)

    def test_snap_and_text(self):
        self.assertEqual(ad.snap_speed(1.2999999), 1.3)
        self.assertEqual(ad.snap_speed(9), 2.5)
        self.assertEqual(ad.snap_speed(0.2), 1.0)
        self.assertEqual(ad.speed_text(1.0), "Normal")
        self.assertEqual(ad.speed_text(1.5), "1.50x")


class Titles(unittest.TestCase):
    def test_title_with_speed(self):
        self.assertEqual(ad.title_with_speed("Pesachim 121", "1.50x"), "Pesachim 121 (1.50x) פסחים דף קכא")
        self.assertEqual(ad.title_with_speed("Berachos 7 (Yerushalmi)", "1.50x"),
                         "Berachos 7 (1.50x) ברכות דף ז (Yerushalmi)")
        self.assertEqual(ad.title_with_speed("Weird title", "1.50x"), "Weird title (1.50x)")

    def test_fast_name(self):
        self.assertEqual(ad.fast_name(pathlib.Path("Pesachim 7.mp3"), "1.50x"), "Pesachim 7 (1.50x).mp3")

    def test_gematria(self):
        for n, want in ((1, "א"), (15, "טו"), (16, "טז"), (121, "קכא"), (115, "קטו"), (200, "ר"), (476, "תעו")):
            self.assertEqual(ad.gematria(n), want, n)


if __name__ == "__main__":
    unittest.main()
