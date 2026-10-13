#!/usr/bin/env python3
"""Compute web run duration stats from log file timestamps and file mtimes."""

from __future__ import annotations

import argparse
import datetime as dt
import re
from pathlib import Path
from statistics import mean, median

PROFILES = (
    "default",
    "domena1-prod",
    "prod_1",
    "domena2-prod",
    "domena3-prod",
    "domena4-prod",
    "domena5-prod",
    "domena6-prod",
    "domena7-prod",
    "domena8-prod",
    "domena9-prod",
    "domena10-prod",
    "domena11-prod",
)


def compile_pattern(profile: str) -> re.Pattern[str]:
    if profile == "default":
        return re.compile(r"^web-run-(\d{8}-\d{6})\.log$")
    return re.compile(rf"^web-run-{re.escape(profile)}-(\d{{8}}-\d{{6}})\.log$")


def parse_start(name: str, pattern: re.Pattern[str]) -> dt.datetime | None:
    match = pattern.match(name)
    if not match:
        return None
    return dt.datetime.strptime(match.group(1), "%Y%m%d-%H%M%S")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--logs-dir", default="logs")
    parser.add_argument("--days", type=int, default=14)
    args = parser.parse_args()

    log_dir = Path(args.logs_dir)
    now = dt.datetime.now()
    rows: dict[str, list[float]] = {profile: [] for profile in PROFILES}

    for profile in PROFILES:
        pattern = compile_pattern(profile)
        for path in log_dir.glob("web-run*.log"):
            started = parse_start(path.name, pattern)
            if started is None:
                continue
            if (now - started).days > args.days:
                continue
            ended = dt.datetime.fromtimestamp(path.stat().st_mtime)
            duration = (ended - started).total_seconds()
            if 0 <= duration <= 6 * 3600:
                rows[profile].append(duration)

    all_durations = [item for values in rows.values() for item in values]
    if not all_durations:
        print("No matching web run logs in window.")
        return

    print(
        f"window_days={args.days} samples={len(all_durations)} "
        f"overall_avg_min={mean(all_durations)/60:.1f} overall_med_min={median(all_durations)/60:.1f}"
    )
    print("profile\tn\tavg_min\tmed_min\tmax_min")
    for profile in PROFILES:
        values = rows[profile]
        if not values:
            continue
        print(
            f"{profile}\t{len(values)}\t{mean(values)/60:.1f}\t{median(values)/60:.1f}\t{max(values)/60:.1f}"
        )


if __name__ == "__main__":
    main()

