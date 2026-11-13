"""Unit tests for the gate itself (run in CI): python -m unittest discover -s ai-assistant"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import assistant  # noqa: E402
import gate  # noqa: E402

FX = Path(__file__).resolve().parent / "fixtures"


def run(name):
    rule, tests = assistant.extract_blocks((FX / f"{name}.md").read_text(encoding="utf-8"))
    return gate.run_gate(rule, tests)


class GateTests(unittest.TestCase):
    def test_accepts_correct_draft(self):
        r = run("draft_2_accepted")
        self.assertTrue(r.accepted, r.report())

    def test_rejects_logic_bug_via_its_own_tests(self):
        r = run("draft_1_rejected")
        self.assertFalse(r.accepted)
        self.assertEqual([s.name for s in r.stages if not s.ok], ["tests"])

    def test_rejects_unsafe_draft_statically(self):
        r = run("draft_3_unsafe")
        self.assertFalse(r.accepted)
        self.assertEqual(r.stages[0].name, "static")


if __name__ == "__main__":
    unittest.main()
