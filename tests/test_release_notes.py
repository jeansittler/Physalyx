import json
from pathlib import Path
import tempfile
import unittest

from physalix import __version__
from physalix.release_notes import (
    ReleaseNotesError,
    current_release,
    load_release_notes,
    validate_release_notes,
)


class ReleaseNotesTests(unittest.TestCase):
    def test_canonical_resource_is_valid_current_and_descending(self):
        entries = load_release_notes(require_current=True)
        self.assertEqual(entries[0]["version"], __version__)
        self.assertEqual(
            [entry["version"] for entry in entries],
            ["1.10.0", "1.9.0", "1.8.0", "1.7.0", "1.6.0", "1.5.2", "1.5.1", "1.5.0", "1.4.1", "1.4.0", "1.3.0", "1.2.5", "1.2.4", "1.2.3", "1.2.2"],
        )
        self.assertEqual(current_release(entries), entries[0])
        self.assertTrue(any("réticule" in note for entry in entries for note in entry["notes"]))

    def test_validation_sorts_and_rejects_bad_content(self):
        valid = [
            {"version": "1.2.3", "notes": ["Trois"]},
            {"version": "1.2.10", "notes": ["Dix"]},
        ]
        self.assertEqual(
            [entry["version"] for entry in validate_release_notes(valid)],
            ["1.2.10", "1.2.3"],
        )
        invalid_values = (
            None,
            [],
            {},
            [None],
            [{"version": "incorrecte", "notes": ["Note"]}],
            [{"version": "1.2.3", "notes": []}],
            [
                {"version": "1.2.3", "notes": ["Une"]},
                {"version": "1.2.3", "notes": ["Deux"]},
            ],
        )
        for value in invalid_values:
            with self.subTest(value=value), self.assertRaises(ReleaseNotesError):
                validate_release_notes(value)

    def test_required_current_version_must_be_latest(self):
        entries = [
            {"version": "1.2.3", "notes": ["Trois"]},
            {"version": "1.2.4", "notes": ["Quatre"]},
        ]
        validate_release_notes(entries, require_current=True, current_version="1.2.4")
        with self.assertRaises(ReleaseNotesError):
            validate_release_notes(entries, require_current=True, current_version="1.2.3")

    def test_missing_and_invalid_json_are_reported_cleanly(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "release-notes.json"
            with self.assertRaises(ReleaseNotesError):
                load_release_notes(path)
            path.write_text("{", encoding="utf-8")
            with self.assertRaises(ReleaseNotesError):
                load_release_notes(path)
            path.write_text(json.dumps([]), encoding="utf-8")
            with self.assertRaises(ReleaseNotesError):
                load_release_notes(path)


if __name__ == "__main__":
    unittest.main()
