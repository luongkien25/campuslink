"""
Unit tests kiem chung san pham cua TV4 (FR-INF-21, NFR-08, NFR-14, NFR-16, SRS 6.2).
Chay: python3 -m unittest discover -s tests -v
"""

from __future__ import annotations

import csv
import pathlib
import re
import unittest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent


class TestTV4Deliverables(unittest.TestCase):
    def test_cost_csv_exists_and_matches_evidence_copy(self) -> None:
        root_csv = REPO_ROOT / "cost.csv"
        ev_csv = REPO_ROOT / "evidence" / "cost.csv"
        self.assertTrue(root_csv.is_file(), "Thieu cost.csv o goc repo")
        self.assertTrue(ev_csv.is_file(), "Thieu evidence/cost.csv")
        self.assertEqual(
            root_csv.read_text(encoding="utf-8"),
            ev_csv.read_text(encoding="utf-8"),
            "cost.csv va evidence/cost.csv phai dong bo",
        )

    def test_cost_csv_schema_and_credit_checkpoints(self) -> None:
        root_csv = REPO_ROOT / "cost.csv"
        with root_csv.open(encoding="utf-8", newline="") as fh:
            rows = list(csv.DictReader(fh))
        self.assertGreaterEqual(len(rows), 35, "cost.csv phai co du cac phien G0 va Issue #4")
        credits = [r["credit_remaining_usd"] for r in rows if r["credit_remaining_usd"] != "-"]
        self.assertEqual(
            credits,
            ["131.38", "129.57", "125.58", "123.79", "115.00", "112.38"],
            "Chuoi credit con lai phai khop bang Theo doi credit trong g0-checklist.md",
        )

    def test_acceptance_md_has_8_categories_and_valid_links(self) -> None:
        acc_path = REPO_ROOT / "docs" / "acceptance.md"
        self.assertTrue(acc_path.is_file(), "Thieu docs/acceptance.md")
        text = acc_path.read_text(encoding="utf-8")
        for idx in range(1, 9):
            self.assertIn(f"**{idx}. ", text, f"Thieu hang muc {idx} trong docs/acceptance.md")
        links = re.findall(r"\]\(([^)]+)\)", text)
        self.assertGreaterEqual(len(links), 80)
        for rel in links:
            target = (acc_path.parent / rel).resolve()
            self.assertTrue(target.exists(), f"Link hong trong docs/acceptance.md: {rel}")

    def test_versions_lock_has_pg_and_redis_versions(self) -> None:
        vlock = (REPO_ROOT / "docs" / "versions.lock").read_text(encoding="utf-8")
        self.assertIn("postgresql_version=16.15", vlock)
        self.assertIn("redis_version=7.0.15", vlock)
        self.assertIn("recorded_by=TV4", vlock)

    def test_no_secret_in_argv_in_tests_scripts(self) -> None:
        for script in (REPO_ROOT / "tests").rglob("*.sh"):
            content = script.read_text(encoding="utf-8")
            self.assertNotRegex(
                content,
                r'-H\s+"X-Api-Key:\s*\$\{?(SHLINK_)?API_KEY',
                f"Khong duoc truyen API key qua argv trong {script.name}",
            )


if __name__ == "__main__":
    unittest.main()
