from __future__ import annotations

import argparse
import asyncio
import os
import unittest
from unittest.mock import patch

sys_path_root = os.path.join(os.path.dirname(__file__), "..")
if sys_path_root not in os.sys.path:
    os.sys.path.insert(0, sys_path_root)

from tools.profile_tui import (  # noqa: E402
    Config,
    OperationResult,
    ProfileOps,
    RewardsOperatorTUI,
    _sanitize_terminal_text,
)


class FakeProfileOps(ProfileOps):
    def __init__(self, result: OperationResult):
        super().__init__(
            Config(
                server="srv",
                remote_repo="~/repo",
                ssh_bin="ssh",
                adb_bin="adb",
                scrcpy_bin="scrcpy",
                local_web_port=6080,
                remote_web_port=6080,
                local_mobile_port=15555,
                remote_mobile_port=5555,
            ),
            open_browser=False,
        )
        self._result = result
        self.captured_remote_script = ""

    def _remote_result(self, name: str, remote_script: str, data=None):  # type: ignore[override]
        self.captured_remote_script = remote_script
        return OperationResult(name=name, rc=self._result.rc, output=self._result.output, data=data or {})

    def _remote_result_stream(self, name: str, remote_script: str, on_line, data=None):  # type: ignore[override]
        self.captured_remote_script = remote_script
        on_line("line one")
        return OperationResult(name=name, rc=0, output="line one", data=data or {})


class ProfileTUIUnitTests(unittest.TestCase):
    def test_sanitize_terminal_text_removes_ansi_and_control(self):
        raw = "\x1b[?1003h\x1b[31mERR\x1b[0m\r\x07ok"
        self.assertEqual(_sanitize_terminal_text(raw), "ERRok")

    def test_parse_profiles_including_auth_and_today(self):
        ops = ProfileOps(
            Config("srv", "~/repo", "ssh", "adb", "scrcpy", 1, 2, 3, 4),
            open_browser=False,
        )
        payload = "\n".join(
            [
                "__MOBILE__",
                "d1",
                "__WEB__",
                "d1",
                "__MOBILE_AUTH__",
                "d1=logged_in",
                "__WEB_AUTH__",
                "d1=logged_out",
                "__TODAY_STATUS__",
                "d1=done",
            ],
        )
        mobile, web, mobile_auth, web_auth, today = ops._parse_profiles(payload)
        self.assertEqual(mobile, ["d1"])
        self.assertEqual(web, ["d1"])
        self.assertEqual(mobile_auth["d1"], "logged_in")
        self.assertEqual(web_auth["d1"], "logged_out")
        self.assertEqual(today["d1"], "done")

    def test_list_profiles_parses_all_sections(self):
        payload = "\n".join(
            [
                "__MOBILE__",
                "p1",
                "__WEB__",
                "p1",
                "__MOBILE_AUTH__",
                "p1=logged_in",
                "__WEB_AUTH__",
                "p1=logged_in",
                "__TODAY_STATUS__",
                "p1=incomplete",
            ],
        )
        ops = FakeProfileOps(OperationResult("list_profiles", 0, payload))
        result = ops.list_profiles()
        self.assertEqual(result.data["mobile"], ["p1"])
        self.assertEqual(result.data["web"], ["p1"])
        self.assertEqual(result.data["mobile_auth"]["p1"], "logged_in")
        self.assertEqual(result.data["web_auth"]["p1"], "logged_in")
        self.assertEqual(result.data["today_status"]["p1"], "incomplete")

    def test_server_busy_check_parses_kv_pairs(self):
        payload = "\n".join(
            [
                "MAINTENANCE=ON",
                "RUNNING_PROFILE=d1",
                "DONE_TODAY=d1,d2",
                "MOBILE_RUNNING=1",
                "MOBILE_PROCESSES_BEGIN",
                "123 ./bing.sh run daily --profile d1",
                "MOBILE_PROCESSES_END",
            ],
        )
        ops = FakeProfileOps(OperationResult("server_busy_check", 0, payload))
        result = ops.server_busy_check()
        self.assertEqual(result.data["MAINTENANCE"], "ON")
        self.assertEqual(result.data["RUNNING_PROFILE"], "d1")
        self.assertEqual(result.data["DONE_TODAY"], "d1,d2")
        self.assertEqual(result.data["MOBILE_RUNNING"], "1")

    def test_run_batch_plan_stream_builds_script_with_maintenance_guard(self):
        ops = FakeProfileOps(OperationResult("run_batch_plan", 0, "ok"))
        result = ops.run_batch_plan_stream(["p1"], run_mobile=True, run_web=False, on_line=lambda _line: None)
        self.assertEqual(result.rc, 0)
        self.assertIn("scripts/server_maintenance.sh enable", ops.captured_remote_script)
        self.assertIn("scripts/server_maintenance.sh disable", ops.captured_remote_script)
        self.assertIn("BING_IGNORE_MAINTENANCE=1 ./bing.sh run daily --profile", ops.captured_remote_script)
        self.assertIn("RUN_WEB=0", ops.captured_remote_script)

    def test_run_batch_plan_stream_rejects_empty_selection(self):
        ops = ProfileOps(Config("srv", "~/repo", "ssh", "adb", "scrcpy", 1, 2, 3, 4), open_browser=False)
        result = ops.run_batch_plan_stream([], run_mobile=True, run_web=False, on_line=lambda _line: None)
        self.assertEqual(result.rc, 2)

    def test_set_status_escapes_markup_like_batch_title(self):
        class TinyOps:
            def __init__(self):
                self.proc = type("Proc", (), {"summary": lambda _self: "none", "stop_all": lambda _self: None})()

            def list_profiles(self):
                return OperationResult(
                    "list_profiles",
                    0,
                    "ok",
                    data={"mobile": ["p1"], "web": ["p1"], "mobile_auth": {"p1": "unknown"}, "web_auth": {"p1": "unknown"}, "today_status": {}},
                )

        app = RewardsOperatorTUI(ops=TinyOps())

        async def scenario():
            async with app.run_test() as pilot:
                await pilot.pause(0.2)
                app._set_status("Running: Batch run [1 profiles, mobile=on web=off]")
                await pilot.pause(0.1)

        asyncio.run(scenario())

    def test_main_defaults_to_no_mouse(self):
        ns = argparse.Namespace(
            server="s",
            remote_repo="~/r",
            ssh_bin="ssh",
            adb_bin="adb",
            scrcpy_bin="scrcpy",
            local_web_port=1,
            remote_web_port=2,
            local_mobile_port=3,
            remote_mobile_port=4,
            no_browser=False,
            mouse=False,
            no_mouse=False,
        )
        with patch("tools.profile_tui.parse_args", return_value=ns), patch(
            "tools.profile_tui.RewardsOperatorTUI.run",
        ) as run_mock:
            from tools import profile_tui

            profile_tui.main()
            run_mock.assert_called_once_with(mouse=False)


if __name__ == "__main__":
    unittest.main()
