"""SVG canvas mirrors the subset of PIL ImageDraw used by the plan scripts."""
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from PIL import ImageFont
from scripts.svgdraw import SvgCanvas

NS = {'s': 'http://www.w3.org/2000/svg'}


class SvgCanvasTests(unittest.TestCase):
    def test_shapes_text_escape_and_measure(self):
        f = ImageFont.load_default()
        c = SvgCanvas(200, 100, '#FFFFFF')
        c.polygon([(0, 0), (10, 0), (10, 10)], fill='#112233', outline='#445566', width=2)
        c.line([(0, 0), (50, 50)], fill='#000000', width=3)
        c.rectangle((1, 2, 30, 40), fill='#ABCDEF')
        c.rounded_rectangle((5, 5, 60, 30), radius=4, fill=None, outline='#000000', width=1)
        c.ellipse((10, 10, 20, 20), fill='#FF0000')
        c.text((10, 20), 'A <B> & "C"', font=f, fill='#123456')
        self.assertGreater(c.textlength('wide text', font=f), c.textlength('w', font=f))
        with tempfile.TemporaryDirectory() as t:
            out = Path(t) / 'p.svg'; c.save(out)
            root = ET.parse(out).getroot()
        self.assertEqual(root.get('viewBox'), '0 0 200 100')
        self.assertEqual(len(root.findall('.//s:polygon', NS)), 1)
        self.assertEqual(len(root.findall('.//s:polyline', NS)) + len(root.findall('.//s:line', NS)), 1)
        self.assertEqual(len(root.findall('.//s:rect', NS)), 3)   # background + rectangle + rounded
        self.assertEqual(root.findall('.//s:text', NS)[0].text, 'A <B> & "C"')
        rr = [r for r in root.findall('.//s:rect', NS) if r.get('rx')][0]
        self.assertEqual(rr.get('fill'), 'none')


if __name__ == '__main__':
    unittest.main()
