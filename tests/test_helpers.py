import pathlib, sys, unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import alldaf_downloader as ad


class Helpers(unittest.TestCase):
    def test_safe_name(self):
        self.assertEqual(ad.safe_name("Berachos 92"), "Berachos 92")
        self.assertEqual(ad.safe_name('a:b?"'), "a_b__")
        self.assertEqual(ad.safe_name("Daf 5. "), "Daf 5")
        self.assertEqual(ad.safe_name("CON"), "_CON")
        self.assertEqual(ad.safe_name(""), "_")

    def test_author_id(self):
        self.assertEqual(ad.parse_author_id("133821"), 133821)
        self.assertEqual(ad.parse_author_id("https://alldaf.org/authors/133821/"), 133821)
        self.assertEqual(ad.parse_author_id("alldaf.org/authors/133821?x=1#top"), 133821)
        self.assertIsNone(ad.parse_author_id("abc"))
        self.assertIsNone(ad.parse_author_id(None))

    def test_versions(self):
        self.assertGreater(ad.parse_version("v1.10"), ad.parse_version("1.9"))
        self.assertEqual(ad.parse_version("v1.8"), (1, 8))

    def test_eta_and_yerushalmi(self):
        self.assertEqual(ad.fmt_eta(75), "1m 15s")
        self.assertEqual(ad.fmt_eta(3700), "1h 01m")
        self.assertTrue(ad.is_yerushalmi({"title": "Yerushalmi Berachos 1"}))
        self.assertFalse(ad.is_yerushalmi({"title": "Berachos 1", "series": None}))


if __name__ == "__main__":
    unittest.main()
