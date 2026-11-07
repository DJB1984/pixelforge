import unittest

from pixelforge.grid import Grid, GridError

ART = "ab..\n.c..\n....\n"


class GridTest(unittest.TestCase):
    def test_roundtrip(self):
        self.assertEqual(Grid.parse(ART, 4, 3).to_text(), ART)

    def test_strict_reports_bad_row(self):
        with self.assertRaisesRegex(GridError, "row 1 has 3 chars"):
            Grid.parse("ab..\n.c.\n....", 4, 3)
        with self.assertRaisesRegex(GridError, "expected 3 rows"):
            Grid.parse("ab..\n.c..", 4, 3)

    def test_lenient_pads(self):
        g = Grid.parse("ab\n", 4, 2, strict=False)
        self.assertEqual(g.to_text(), "ab..\n....\n")

    def test_offset_flip_composite(self):
        g = Grid.parse(ART, 4, 3)
        self.assertEqual(g.offset(1, 1).to_text(), "....\n.ab.\n..c.\n")
        self.assertEqual(g.flip("h").to_text(), "..ba\n..c.\n....\n")
        self.assertEqual(g.flip("v").to_text(), "....\n.c..\nab..\n")
        top = Grid.parse("...x\nz...\n....", 4, 3)
        self.assertEqual(g.composite(top).to_text(), "ab.x\nzc..\n....\n")

    def test_bbox_diff(self):
        g = Grid.parse(ART, 4, 3)
        self.assertEqual(g.bbox(), (0, 0, 1, 1))
        self.assertIsNone(Grid.blank(2, 2).bbox())
        self.assertEqual(g.diff(g.offset(1, 0)), [(0, 0), (1, 0), (2, 0), (1, 1), (2, 1)])


if __name__ == "__main__":
    unittest.main()
