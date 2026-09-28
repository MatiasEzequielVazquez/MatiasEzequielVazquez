"""
Unit tests for scripts/update_langs.py
"""

import os
import sys
import tempfile
import unittest

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from scripts.update_langs import (
    render_bar,
    filter_repos,
    build_section,
    update_readme,
    get_env_list,
    get_env_bool,
    get_env_int,
    BLOCK_FULL,
    BLOCK_EMPTY,
    MARKER_START,
    MARKER_END,
)


class TestUpdateLangs(unittest.TestCase):
    def test_render_bar_limits(self):
        length = 20
        # 0% or negative should be completely empty
        self.assertEqual(render_bar(0.0, length=length), BLOCK_EMPTY * length)
        self.assertEqual(render_bar(-5.0, length=length), BLOCK_EMPTY * length)

        # 100% or greater should be completely full
        self.assertEqual(render_bar(100.0, length=length), BLOCK_FULL * length)
        self.assertEqual(render_bar(150.0, length=length), BLOCK_FULL * length)

    def test_render_bar_lengths(self):
        # Bar should always have the exact specified character length
        for length in (10, 20, 25):
            for pct in [0.1, 1.2, 5.0, 12.5, 33.3, 50.0, 87.6, 99.9]:
                bar_smooth = render_bar(pct, length=length, style="smooth")
                bar_solid = render_bar(pct, length=length, style="solid")
                self.assertEqual(len(bar_smooth), length, f"Smooth failed for pct={pct}, length={length}")
                self.assertEqual(len(bar_solid), length, f"Solid failed for pct={pct}, length={length}")

    def test_render_bar_smooth_subblocks(self):
        # 0.6% on length 20 = round(0.006 * 20 * 8) = 1 subblock unit ('▏')
        bar_eighth = render_bar(0.6, length=20, style="smooth")
        self.assertEqual(len(bar_eighth), 20)
        self.assertTrue(bar_eighth.startswith("▏"))

        # 1.0% on length 20 = round(0.01 * 20 * 8) = 2 subblock units ('▎')
        bar_quarter = render_bar(1.0, length=20, style="smooth")
        self.assertEqual(len(bar_quarter), 20)
        self.assertTrue(bar_quarter.startswith("▎"))

    def test_filter_repos(self):
        sample_repos = [
            {"name": "repo1", "fork": False, "archived": False},
            {"name": "repo2", "fork": True, "archived": False},
            {"name": "repo3", "fork": False, "archived": True},
            {"name": "repo4", "fork": False, "archived": False},
            {"name": "profile-repo", "fork": False, "archived": False},
        ]

        filtered = filter_repos(
            sample_repos,
            ignore_forks=True,
            ignore_archived=True,
            exclude_repos={"profile-repo"},
        )
        names = [r["name"] for r in filtered]
        self.assertEqual(names, ["repo1", "repo4"])

    def test_build_section(self):
        lang_totals = {
            "Python": 8000,
            "Rust": 2000,
        }
        section = build_section(lang_totals, top_n=2, bar_length=10, bar_style="solid")
        self.assertIn("Python", section)
        self.assertIn("Rust", section)
        self.assertIn("80.0%", section)
        self.assertIn("20.0%", section)
        self.assertIn("```text", section)

    def test_build_section_empty(self):
        section = build_section({})
        self.assertIn("No language data detected", section)

    def test_update_readme(self):
        with tempfile.NamedTemporaryFile("w+", delete=False, encoding="utf-8") as tmp:
            tmp.write(
                f"# Title\n\n{MARKER_START}\nOld Content\n{MARKER_END}\n\nFooter"
            )
            tmp_path = tmp.name

        try:
            update_readme("New Dynamic Content", readme_path=tmp_path)
            with open(tmp_path, "r", encoding="utf-8") as f:
                content = f.read()
            self.assertIn("New Dynamic Content", content)
            self.assertNotIn("Old Content", content)
            self.assertIn("# Title", content)
            self.assertIn("Footer", content)
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    def test_env_helpers(self):
        os.environ["TEST_LIST"] = "A, B, C"
        os.environ["TEST_BOOL_TRUE"] = "true"
        os.environ["TEST_BOOL_FALSE"] = "0"
        os.environ["TEST_INT"] = "42"

        self.assertEqual(get_env_list("TEST_LIST"), {"A", "B", "C"})
        self.assertTrue(get_env_bool("TEST_BOOL_TRUE", False))
        self.assertFalse(get_env_bool("TEST_BOOL_FALSE", True))
        self.assertEqual(get_env_int("TEST_INT", 10), 42)


if __name__ == "__main__":
    unittest.main()
