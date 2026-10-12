import os
import sys
import types
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

if "uiautomator2" not in sys.modules:
    fake_u2 = types.SimpleNamespace(
        connect=lambda *_args, **_kwargs: None,
        exceptions=types.SimpleNamespace(DeviceError=Exception, RPCError=Exception),
    )
    sys.modules["uiautomator2"] = fake_u2

import bing_mobile_flow as bmf  # noqa: E402


class FakeSocket:
    def __init__(self, connect_ex_result=0):
        self._res = connect_ex_result

    def settimeout(self, _):
        return None

    def connect_ex(self, _):
        return self._res

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class SerialNormalizationTests(unittest.TestCase):
    def test_normalize_serial_passes_host_port(self):
        self.assertEqual(bmf.normalize_serial("127.0.0.1:5557"), "127.0.0.1:5557")

    def test_normalize_serial_rejects_invalid_format(self):
        with self.assertRaises(bmf.InfraError):
            bmf.normalize_serial("127.0.0.1")


class CheckSerialTests(unittest.TestCase):
    @patch.object(bmf.shutil, "which", return_value="adb")
    def test_check_serial_rejects_wrong_slot_when_port_not_listening(self, _which):
        with patch.object(bmf.socket, "socket", return_value=FakeSocket(connect_ex_result=1)):
            with self.assertRaises(bmf.InfraError) as err:
                bmf.check_serial("127.0.0.1:5558")
        self.assertIn("nothing listening on 127.0.0.1:5558", str(err.exception))

    @patch.object(bmf.shutil, "which", return_value="adb")
    def test_check_serial_passes_when_listed(self, _which):
        connect_done = SimpleNamespace(stdout="", output="")
        devices_out = SimpleNamespace(stdout="List of devices attached\n127.0.0.1:5557\tdevice\n", output="")
        run_mock = MagicMock(side_effect=[connect_done, devices_out])
        with patch.object(bmf.socket, "socket", return_value=FakeSocket(connect_ex_result=0)):
            with patch.object(bmf.subprocess, "run", run_mock):
                bmf.check_serial("127.0.0.1:5557")


class ClearAppDataTests(unittest.TestCase):
    def test_clear_app_data_uses_runtime_serial(self):
        flow = bmf.BingMobileFlow.__new__(bmf.BingMobileFlow)
        flow.serial = "127.0.0.1:5557"
        ok = SimpleNamespace(returncode=0, stdout="Success\n", stderr="")
        with patch.object(bmf.subprocess, "run", return_value=ok) as run_mock:
            with patch.object(bmf, "log"):
                bmf.BingMobileFlow.clear_app_data(flow, "srv")

        args = run_mock.call_args.args[0]
        self.assertIn("adb -s 127.0.0.1:5557 shell pm clear com.microsoft.bing", args[2])

    def test_clear_app_data_allows_explicit_server_serial(self):
        flow = bmf.BingMobileFlow.__new__(bmf.BingMobileFlow)
        flow.serial = "127.0.0.1:15555"
        ok = SimpleNamespace(returncode=0, stdout="Success\n", stderr="")
        with patch.object(bmf.subprocess, "run", return_value=ok) as run_mock:
            with patch.object(bmf, "log"):
                bmf.BingMobileFlow.clear_app_data(flow, "srv", "127.0.0.1:5558")

        args = run_mock.call_args.args[0]
        self.assertIn("adb -s 127.0.0.1:5558 shell pm clear com.microsoft.bing", args[2])


if __name__ == "__main__":
    unittest.main()
