import gzip
import json
import struct
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "host"))
import hotkeys  # noqa: E402
import rayconfig  # noqa: E402

PAYLOAD = {
    "settings": {"general": {"windowMode": "compact", "popToRootTimeout": 30, "uiZoom": 1.2,
                             "escapeKeyBehavior": "nonsense", "theme": "x", "showFavoritesInCompactMode": 1}},
    "quicklinks": {"quicklinks": [{}, {}], "schemaVersion": 1},
    "snippets": {"snippets": [{}]},
    "ai": {"chats": []},
}


def v3(payload, header=None):
    head = gzip.compress(json.dumps(header or {"schemaVersion": 3}).encode())
    return rayconfig.MAGIC + struct.pack("<I", len(head)) + head + gzip.compress(json.dumps(payload).encode())


class RayconfigTests(unittest.TestCase):
    def test_v3_keeps_valid_general_settings_only(self):
        general = rayconfig.general_settings(rayconfig.load(v3(PAYLOAD)))
        self.assertEqual(general, {"windowMode": "compact", "popToRootTimeout": 30, "uiZoom": 1.2})

    def test_classic_gzip_is_read(self):
        data = gzip.compress(json.dumps(PAYLOAD).encode())
        self.assertEqual(rayconfig.general_settings(rayconfig.load(data))["windowMode"], "compact")

    def test_other_categories_are_counted_not_imported(self):
        self.assertEqual(rayconfig.skipped(PAYLOAD), {"quicklinks": 2, "snippets": 1, "ai": 0})

    def test_encrypted_exports_are_refused_with_advice(self):
        with self.assertRaisesRegex(rayconfig.RayconfigError, "without a password"):
            rayconfig.load(v3(PAYLOAD, {"schemaVersion": 3, "encryption": {"iv": "00", "salt": "00"}}))
        with self.assertRaisesRegex(rayconfig.RayconfigError, "without a password"):
            rayconfig.load(b"\x00" * 64)

    def test_summarize_reads_a_file(self):
        with tempfile.NamedTemporaryFile(suffix=".rayconfig") as f:
            f.write(v3(PAYLOAD))
            f.flush()
            self.assertEqual(rayconfig.summarize(f.name)["general"]["windowMode"], "compact")


class HotkeyTests(unittest.TestCase):
    def test_bindings_quote_the_command_id(self):
        [line] = hotkeys.bindings({"app:my app.desktop": "$mod+Shift+f"}, "/bin/x-cast")
        self.assertEqual(line, "bindsym $mod+Shift+f exec --no-startup-id /bin/x-cast run 'app:my app.desktop'")

    def test_bad_keys_are_rejected(self):
        for key in ("$mod+", "a; exec rm", "$mod+d\nexec x"):
            with self.assertRaises(ValueError):
                hotkeys.bindings({"app:x": key}, "/bin/x-cast")

    def test_none_means_no_bindings(self):
        self.assertEqual(hotkeys.bindings(None, "/bin/x-cast"), [])


if __name__ == "__main__":
    unittest.main()
