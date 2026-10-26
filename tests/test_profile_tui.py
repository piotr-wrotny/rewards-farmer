import asyncio
import os
import sys
import unittest

from textual.widgets import DataTable

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tools.profile_tui import OperationResult, RewardsOperatorTUI


class FakeOps:
    def __init__(self, with_profiles: bool = True):
        self.calls: list[tuple] = []
        self._with_profiles = with_profiles
        self.proc = type("Proc", (), {"summary": lambda _self: "none", "stop_all": lambda _self: None})()

    def list_profiles(self) -> OperationResult:
        self.calls.append(("list_profiles",))
        data = {"mobile": ["r_domena_01"], "web": ["r_domena_01"]} if self._with_profiles else {"mobile": [], "web": []}
        return OperationResult("list_profiles", 0, "ok", data=data)

    def maintenance_status(self) -> OperationResult:
        self.calls.append(("maintenance_status",))
        return OperationResult("maintenance_status", 0, "MAINTENANCE=OFF")

    def server_busy_check(self) -> OperationResult:
        self.calls.append(("server_busy_check",))
        return OperationResult(
            "server_busy_check",
            0,
            "MOBILE=BUSY",
            data={
                "RUNNING_PROFILE": "r_domena_01",
                "DONE_TODAY": "r_domena_01",
                "MOBILE_RUNNING": "1",
                "ACTIVE_PROFILE": "active=r_domena_01",
            },
        )

    def start_web_login(self, profile: str) -> OperationResult:
        self.calls.append(("start_web_login", profile))
        return OperationResult("start_web_login", 0, f"profile={profile}")

    def stop_local_views(self) -> OperationResult:
        self.calls.append(("stop_local_views",))
        return OperationResult("stop_local_views", 0, "stopped")

    def resume_incomplete_mobile(self, dry_run: bool) -> OperationResult:
        self.calls.append(("resume", dry_run))
        return OperationResult("resume", 0, "preview")

    # Unused in these tests; kept for app completeness
    def prepare_mobile_profile(self, profile: str) -> OperationResult:
        self.calls.append(("prepare_mobile_profile", profile))
        return OperationResult("prepare_mobile_profile", 0, "ok")

    def start_mobile_view(self, profile: str) -> OperationResult:
        self.calls.append(("start_mobile_view", profile))
        return OperationResult("start_mobile_view", 0, "ok")

    def start_both_views(self, profile: str) -> OperationResult:
        self.calls.append(("start_both_views", profile))
        return OperationResult("start_both_views", 0, "ok")

    def run_single_daily(self, profile: str) -> OperationResult:
        self.calls.append(("run_single_daily", profile))
        return OperationResult("run_single_daily", 0, "ok")

    def run_single_daily_stream(self, profile: str, emit) -> OperationResult:  # noqa: ANN001
        self.calls.append(("run_single_daily_stream", profile))
        emit("line")
        return OperationResult("run_single_daily_stream", 0, "line")

    def add_profile_web_and_mobile(self, profile: str) -> OperationResult:
        self.calls.append(("add_profile_web_and_mobile", profile))
        return OperationResult("add_profile_web_and_mobile", 0, "ok")

    def verify_web_login(self, profile: str) -> OperationResult:
        self.calls.append(("verify_web_login", profile))
        return OperationResult("verify_web_login", 0, "ok")

    def verify_mobile_post_login(self, profile: str) -> OperationResult:
        self.calls.append(("verify_mobile_post_login", profile))
        return OperationResult("verify_mobile_post_login", 0, "ok")

    def kill_switch(self, hard: bool = False) -> OperationResult:
        self.calls.append(("kill_switch", hard))
        return OperationResult("kill_switch", 0, "ok")

    def disable_maintenance(self) -> OperationResult:
        self.calls.append(("disable_maintenance",))
        return OperationResult("disable_maintenance", 0, "ok")


class ProfileTUITests(unittest.TestCase):
    def test_keybindings_trigger_expected_operations(self):
        ops = FakeOps(with_profiles=True)
        app = RewardsOperatorTUI(ops=ops)

        async def scenario():
            async with app.run_test() as pilot:
                await pilot.pause(0.3)
                self.assertIn(("list_profiles",), ops.calls)
                base_refresh_calls = ops.calls.count(("list_profiles",))

                await pilot.press("x")
                await pilot.pause(0.2)
                await pilot.press("enter")
                await pilot.pause(0.2)
                self.assertGreater(ops.calls.count(("list_profiles",)), base_refresh_calls)

                await pilot.press("t")
                await pilot.pause(0.2)
                self.assertIn(("maintenance_status",), ops.calls)

                await pilot.press("b")
                await pilot.pause(0.2)
                table = app.query_one("#profiles", DataTable)
                row = table.get_row_at(0)
                state = row[3].plain if hasattr(row[3], "plain") else str(row[3])
                today = row[4].plain if hasattr(row[4], "plain") else str(row[4])
                self.assertEqual(state, "RUN")
                self.assertEqual(today, "DONE")

                await pilot.press("w")
                await pilot.pause(0.2)
                self.assertIn(("start_web_login", "r_domena_01"), ops.calls)

                await pilot.press("v")
                await pilot.pause(0.2)
                self.assertIn(("resume", True), ops.calls)

                await pilot.press("c")
                await pilot.pause(0.2)
                self.assertIn(("stop_local_views",), ops.calls)

        asyncio.run(scenario())

    def test_profile_modal_accepts_manual_profile_when_table_empty(self):
        ops = FakeOps(with_profiles=False)
        app = RewardsOperatorTUI(ops=ops)

        async def scenario():
            async with app.run_test() as pilot:
                await pilot.pause(0.3)
                await pilot.press("w")
                await pilot.pause(0.2)
                await pilot.press("z", "z", "1", "enter")
                await pilot.pause(0.3)
                self.assertIn(("start_web_login", "zz1"), ops.calls)

        asyncio.run(scenario())


if __name__ == "__main__":
    unittest.main()
