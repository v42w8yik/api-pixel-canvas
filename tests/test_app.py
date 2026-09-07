import json
import struct
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))

from app import Canvas, MAX_PIXELS_PER_REQUEST, validate_pixel


class CanvasTests(unittest.TestCase):
    def test_set_pixel_and_clear(self):
        canvas = Canvas()
        canvas.set_pixels([{"x": 10, "y": 20, "color": "#FF88AA"}])
        version, pixels = canvas.snapshot()
        self.assertEqual(version, 1)
        self.assertEqual(pixels[20 * 64 + 10], "#ff88aa")
        canvas.clear()
        self.assertEqual(canvas.snapshot()[1][20 * 64 + 10], "#ffffff")

    def test_batch_is_atomic_when_one_pixel_is_invalid(self):
        canvas = Canvas()
        with self.assertRaises(ValueError):
            canvas.set_pixels([
                {"x": 1, "y": 1, "color": "#000000"},
                {"x": 64, "y": 1, "color": "#000000"},
            ])
        self.assertEqual(canvas.snapshot()[0], 0)

    def test_validation(self):
        for bad in [
            {"x": -1, "y": 0, "color": "#000000"},
            {"x": True, "y": 0, "color": "#000000"},
            {"x": 0, "y": 0, "color": "red"},
        ]:
            with self.assertRaises(ValueError):
                validate_pixel(bad)

    def test_png_header_and_dimensions(self):
        png = Canvas().png()
        self.assertEqual(png[:8], b"\x89PNG\r\n\x1a\n")
        self.assertEqual(struct.unpack(">II", png[16:24]), (64, 64))

    def test_limit_is_at_least_full_canvas(self):
        self.assertGreaterEqual(MAX_PIXELS_PER_REQUEST, 64 * 64)


if __name__ == "__main__":
    unittest.main()
