from __future__ import annotations

import datetime as dt
import io
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools" / "web_runtime_stats.py"


def _touch_with_mtime(path: Path, mtime: dt.datetime) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("log\n", encoding="utf-8")
    ts = mtime.timestamp()
    os.utime(path, (ts, ts))


def test_script_prints_aggregate_and_profiles_for_matching_logs(tmp_path: Path) -> None:
    now = dt.datetime.now()
    started_default = now - dt.timedelta(days=1, minutes=15)
    ended_default = started_default + dt.timedelta(minutes=8)
    default_name = f"web-run-{started_default.strftime('%Y%m%d-%H%M%S')}.log"
    _touch_with_mtime(tmp_path / default_name, ended_default)

    started_profile = now - dt.timedelta(days=1, minutes=30)
    ended_profile = started_profile + dt.timedelta(minutes=10)
    profile_name = f"web-run-domena1-prod-{started_profile.strftime('%Y%m%d-%H%M%S')}.log"
    _touch_with_mtime(tmp_path / profile_name, ended_profile)

    old_started = now - dt.timedelta(days=40)
    old_name = f"web-run-{old_started.strftime('%Y%m%d-%H%M%S')}.log"
    _touch_with_mtime(tmp_path / old_name, old_started + dt.timedelta(minutes=9))

    bad_name = "web-run-domena2-prod-20261026-120000.log"
    _touch_with_mtime(tmp_path / bad_name, now + dt.timedelta(minutes=1))

    run = subprocess.run(
        [sys.executable, str(SCRIPT), "--logs-dir", str(tmp_path), "--days", "14"],
        check=True,
        capture_output=True,
        text=True,
    )
    out = run.stdout
    assert "window_days=14 samples=2" in out
    assert "profile\tn\tavg_min\tmed_min\tmax_min" in out
    assert "default\t1\t8.0\t8.0\t8.0" in out
    assert "domena1-prod\t1\t10.0\t10.0\t10.0" in out
    assert "domena2-prod" not in out


def test_script_reports_no_data_for_empty_window(tmp_path: Path) -> None:
    started = dt.datetime.now() - dt.timedelta(days=50)
    name = f"web-run-{started.strftime('%Y%m%d-%H%M%S')}.log"
    _touch_with_mtime(tmp_path / name, started + dt.timedelta(minutes=5))

    run = subprocess.run(
        [sys.executable, str(SCRIPT), "--logs-dir", str(tmp_path), "--days", "7"],
        check=True,
        capture_output=True,
        text=True,
    )
    assert run.stdout.strip() == "No matching web run logs in window."
