import json
import tempfile
import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import render
import search


class ReportTests(unittest.TestCase):
    def test_geographic_orientation(self):
        project = render.build_projection()
        hangzhou = project(120.212, 30.291)
        hengyang = project(112.620, 26.900)
        self.assertGreater(hangzhou[0], hengyang[0])
        self.assertLess(hangzhou[1], hengyang[1])

    def test_only_available_seat_price(self):
        self.assertEqual(search._price_for_available(
            {'A9': '¥1527.0', 'O': '¥437.0'}, {'商务座': '1'}), 1527.0)

    def test_standalone_demo(self):
        demo = json.loads((ROOT / 'examples' / 'demo.json').read_text(encoding='utf-8'))
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / 'report.html'
            render.render(demo, output)
            html = output.read_text(encoding='utf-8')
            self.assertIn('查看回家路线', html)
            self.assertIn('id="reportShell"', html)
            self.assertIn('待核价', html)
            self.assertNotIn('≈¥549.5', html)
            self.assertNotIn('PRIVATE_USER_MARKER', html)
            self.assertNotIn('<script src=', html)
            self.assertIn('class="prov"', html)
            self.assertIn('>湖南</text>', html)
            self.assertIn('>广东</text>', html)
            self.assertNotIn('>Guangzhou Province</text>', html)
            self.assertIn('沿途车次与换乘', html)

    def test_html_fields_and_data_cannot_close_script(self):
        demo = json.loads((ROOT / 'examples' / 'demo.json').read_text(encoding='utf-8'))
        demo['from_city'] = '<img src=x onerror=alert(1)>'
        demo['plans'][0]['notes'] = ['</script><script>alert(1)</script>']
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / 'report.html'
            render.render(demo, output)
            html = output.read_text(encoding='utf-8')
            self.assertNotIn('<img src=x onerror=alert(1)>', html)
            self.assertNotIn('</script><script>alert(1)</script>', html)
            self.assertIn('\\u003c/script>', html)


if __name__ == '__main__':
    unittest.main()
