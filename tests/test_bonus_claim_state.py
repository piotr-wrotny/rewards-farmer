import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from selenium.common.exceptions import TimeoutException

import rewards_tasks


class BonusClaimStateTests(unittest.TestCase):
    def setUp(self):
        self.tasks = rewards_tasks.RewardsTaskUtils.__new__(rewards_tasks.RewardsTaskUtils)
        class _Elements:
            def get_bonus_button_on_dashboard(self):
                return object()

            def get_claim_bonus_points_button(self):
                return object()

        self.tasks.elements = _Elements()

    def test_read_bonus_claim_state_when_claim_available(self):
        calls = {"count": 0}

        def fake_wait(_getter, timeout=10):
            calls["count"] += 1
            return object()

        self.tasks.wait_for_element = fake_wait

        state = self.tasks.read_bonus_claim_state()

        self.assertEqual(state, {"ready_to_claim_visible": True, "claim_available": True})
        self.assertEqual(calls["count"], 2)

    def test_read_bonus_claim_state_when_sidebar_missing(self):
        def fake_wait(_getter, timeout=10):
            raise TimeoutException("missing")

        self.tasks.wait_for_element = fake_wait

        state = self.tasks.read_bonus_claim_state()

        self.assertEqual(state, {"ready_to_claim_visible": False, "claim_available": False})

    def test_claim_bonus_points_logs_claimed_true(self):
        self.tasks.switch_to_dashboard = lambda: None

        before_after = iter([
            {"ready_to_claim_visible": True, "claim_available": True},
            {"ready_to_claim_visible": True, "claim_available": False},
        ])
        self.tasks.read_bonus_claim_state = lambda: next(before_after)
        self.tasks.wait_for_then_click = lambda _getter: None

        with patch("rewards_tasks.time.sleep", return_value=None):
            with patch("builtins.print") as print_mock:
                self.tasks.claim_bonus_points()

        printed = "\n".join(" ".join(str(x) for x in args) for args, _ in print_mock.call_args_list)
        self.assertIn("Bonus claim result: claimed=True", printed)

    def test_claim_bonus_points_logs_warning_when_no_claim_button(self):
        self.tasks.switch_to_dashboard = lambda: None
        self.tasks.read_bonus_claim_state = lambda: {"ready_to_claim_visible": True, "claim_available": False}

        def fake_click(getter):
            # bonus button click succeeds, claim button click times out
            if getter == self.tasks.elements.get_claim_bonus_points_button:
                raise TimeoutException("no claim")
            return None

        class _Elements:
            def get_bonus_button_on_dashboard(self):
                return object()

            def get_claim_bonus_points_button(self):
                return object()

        self.tasks.elements = _Elements()
        self.tasks.wait_for_then_click = fake_click

        with patch("builtins.print") as print_mock:
            self.tasks.claim_bonus_points()

        printed = "\n".join(" ".join(str(x) for x in args) for args, _ in print_mock.call_args_list)
        self.assertIn("Could not find the 'Claim Bonus Points' button", printed)


if __name__ == "__main__":
    unittest.main()
