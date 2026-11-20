import pathlib, sys, unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from alldaf import net, util


class Helpers(unittest.TestCase):
    def test_safe_name(self):
        self.assertEqual(util.safe_name("Berachos 92"), "Berachos 92")
        self.assertEqual(util.safe_name('a:b?"'), "a_b__")
        self.assertEqual(util.safe_name("Daf 5. "), "Daf 5")
        self.assertEqual(util.safe_name("CON"), "_CON")
        self.assertEqual(util.safe_name(""), "_")

    def test_author_id(self):
        self.assertEqual(util.parse_author_id("133821"), 133821)
        self.assertEqual(util.parse_author_id("https://alldaf.org/authors/133821/"), 133821)
        self.assertEqual(util.parse_author_id("alldaf.org/authors/133821?x=1#top"), 133821)
        self.assertIsNone(util.parse_author_id("abc"))
        self.assertIsNone(util.parse_author_id(None))

    def test_versions(self):
        self.assertGreater(util.parse_version("v1.10"), util.parse_version("1.9"))
        self.assertEqual(util.parse_version("v1.8"), (1, 8))

    def test_eta_and_yerushalmi(self):
        self.assertEqual(util.fmt_eta(75), "1m 15s")
        self.assertEqual(util.fmt_eta(3700), "1h 01m")
        self.assertTrue(util.is_yerushalmi({"title": "Yerushalmi Berachos 1"}))
        self.assertFalse(util.is_yerushalmi({"title": "Berachos 1", "series": None}))

    def test_record_daf(self):
        meta = {"metadata": [{"name": "dafMasechta", "value": "Bava Kama 2"}], "title": "x", "sortDaf": 1400}
        self.assertEqual(util.record_daf(meta), 2)  # not the Shas-wide sortDaf
        self.assertEqual(util.record_daf({"title": "Shabbos 155 - Discontent"}), 155)
        self.assertEqual(util.record_daf({"title": "Succah 11a"}), 11)
        self.assertIsNone(util.record_daf({"title": "Intro"}))

    def test_daf_range(self):
        self.assertEqual(util.parse_daf_range("", " "), (None, None))
        self.assertEqual(util.parse_daf_range("20", "40"), (20, 40))
        self.assertEqual(util.parse_daf_range("", "9"), (None, 9))
        for bad in (("a", ""), ("0", ""), ("5", "3"), ("-2", "")):
            with self.assertRaises(ValueError):
                util.parse_daf_range(*bad)

    def test_parse_authors(self):
        self.assertEqual(net.parse_authors({"authors": [{"id": 5, "name": " Rabbi A "}]}), [{"id": 5, "name": "Rabbi A"}])
        self.assertEqual(net.parse_authors({"posts": []}), [])
        for bad in ([], {"authors": [{"id": "x", "name": "n"}]}, {"authors": "no"}):
            with self.assertRaises(net.ApiChanged):
                net.parse_authors(bad)


if __name__ == "__main__":
    unittest.main()
