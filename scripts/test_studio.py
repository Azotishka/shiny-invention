"""Read-only Studio checks: do not treat browser preview as a hardware simulator."""
from pathlib import Path
import re
import shutil
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
STUDIO = ROOT / "studio"


class StudioChecks(unittest.TestCase):
    def test_local_inspector_is_linked(self):
        index = (STUDIO / "index.html").read_text(encoding="utf-8")
        self.assertIn('href="ota-inspector.html"', index)
        self.assertIn("NW v0.6", index)

    def test_inspector_cannot_write_firmware_or_send_dump(self):
        source = (STUDIO / "ota-inspector.html").read_text(encoding="utf-8")
        self.assertIn("arrayBuffer()", source)
        self.assertIn("4*1024*1024", source)
        self.assertIn("0x8000", source)
        for forbidden in ("fetch(", "XMLHttpRequest", "sendBeacon", "navigator.serial",
                          "writeFlash(", "Update.begin(", "FormData("):
            with self.subTest(token=forbidden):
                self.assertNotIn(forbidden, source)

    @unittest.skipUnless(shutil.which("node"), "Node.js is not installed")
    def test_inline_scripts_parse_in_node(self):
        for page in ("index.html", "ota-inspector.html"):
            source = (STUDIO / page).read_text(encoding="utf-8")
            scripts = re.findall(r"<script>(.*?)</script>", source, flags=re.DOTALL)
            self.assertEqual(len(scripts), 1)
            process = subprocess.run(
                ["node", "--check", "-"], input=scripts[0],
                capture_output=True, text=True, timeout=10, check=False)
            self.assertEqual(process.returncode, 0, process.stderr)


if __name__ == "__main__":
    unittest.main()
