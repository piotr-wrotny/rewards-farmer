#!/usr/bin/env python3
"""Textual operator TUI for Rewards Farmer onboarding and maintenance."""

from __future__ import annotations

import argparse
import shlex
import subprocess
import sys
import traceback
import webbrowser
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from textual import on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, DataTable, Footer, Header, Input, Label, OptionList, RichLog, Static
from textual.widgets.option_list import Option


@dataclass
class Config:
    server: str
    remote_repo: str
    ssh_bin: str
    adb_bin: str
    scrcpy_bin: str
    local_web_port: int
    remote_web_port: int
    local_mobile_port: int
    remote_mobile_port: int


@dataclass
class OperationResult:
    name: str
    rc: int
    output: str
    data: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class MenuEntry:
    action: str
    label: str
    shortcut: str
    command: str
    description: str


@dataclass
class ProcessRegistry:
    processes: dict[str, subprocess.Popen] = field(default_factory=dict)

    def is_running(self, name: str) -> bool:
        proc = self.processes.get(name)
        return proc is not None and proc.poll() is None

    def start(self, name: str, cmd: list[str]) -> None:
        if self.is_running(name):
            return
        proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.processes[name] = proc

    def stop(self, name: str) -> None:
        proc = self.processes.get(name)
        if proc is None:
            return
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proc.kill()
        self.processes.pop(name, None)

    def stop_all(self) -> None:
        for name in list(self.processes):
            self.stop(name)

    def summary(self) -> str:
        if not self.processes:
            return "none"
        rows = []
        for name, proc in self.processes.items():
            status = "running" if proc.poll() is None else f"exited({proc.returncode})"
            rows.append(f"{name}:{status}")
        return ", ".join(rows)


class ProfileOps:
    def __init__(self, cfg: Config, open_browser: bool = True) -> None:
        self.cfg = cfg
        self.proc = ProcessRegistry()
        self.open_browser = open_browser

    @staticmethod
    def validate_profile(profile: str) -> None:
        if not profile or any(ch not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-" for ch in profile):
            raise ValueError("Profile name can contain only [a-zA-Z0-9_-].")

    def ssh_cmd(self, remote_script: str) -> list[str]:
        return [self.cfg.ssh_bin, "-o", "BatchMode=yes", self.cfg.server, remote_script]

    def remote_repo_expr(self) -> str:
        repo = self.cfg.remote_repo.strip()
        if repo.startswith("~/"):
            return f"$HOME/{repo[2:]}"
        if repo == "~":
            return "$HOME"
        return shlex.quote(repo)

    def run_remote_capture(self, remote_script: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            self.ssh_cmd(remote_script),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )

    @staticmethod
    def _merge_output(res: subprocess.CompletedProcess) -> str:
        out = (res.stdout or "").rstrip()
        err = (res.stderr or "").rstrip()
        if err:
            return f"{out}\n[stderr]\n{err}".strip()
        return out

    def _remote_result(self, name: str, remote_script: str, data: dict[str, Any] | None = None) -> OperationResult:
        res = self.run_remote_capture(remote_script)
        return OperationResult(name=name, rc=res.returncode, output=self._merge_output(res), data=data or {})

    def _remote_result_stream(
        self,
        name: str,
        remote_script: str,
        on_line: Callable[[str], None],
        data: dict[str, Any] | None = None,
    ) -> OperationResult:
        proc = subprocess.Popen(
            self.ssh_cmd(remote_script),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        lines: list[str] = []
        if proc.stdout is not None:
            for raw in proc.stdout:
                line = raw.rstrip("\n")
                lines.append(line)
                on_line(line)
        rc = proc.wait()
        return OperationResult(name=name, rc=rc, output="\n".join(lines), data=data or {})

    def _parse_profiles(self, text: str) -> tuple[list[str], list[str]]:
        mobile: list[str] = []
        web: list[str] = []
        section = ""
        for raw in text.splitlines():
            line = raw.strip()
            if line == "__MOBILE__":
                section = "mobile"
                continue
            if line == "__WEB__":
                section = "web"
                continue
            if not line:
                continue
            if section == "mobile":
                mobile.append(line)
            elif section == "web":
                web.append(line)
        return mobile, web

    def list_profiles(self) -> OperationResult:
        remote = f"""
set -e
cd {self.remote_repo_expr()}
echo "__MOBILE__"
ls -1 ~/redroid-variants 2>/dev/null | sort || true
echo "__WEB__"
ls -1 {self.remote_repo_expr()}/edge-profiles 2>/dev/null | sort || true
"""
        result = self._remote_result("list_profiles", remote)
        mobile, web = self._parse_profiles(result.output)
        result.data = {"mobile": mobile, "web": web}
        return result

    def server_busy_check(self) -> OperationResult:
        remote = f"""
cd {self.remote_repo_expr()}
MAINTENANCE_FILE="${{REWARDS_MAINTENANCE_FILE:-$PWD/.maintenance-mode}}"
if [ -f "$MAINTENANCE_FILE" ]; then MAINTENANCE_STATE=ON; else MAINTENANCE_STATE=OFF; fi
LOCK_HOLDERS="$(fuser /tmp/bing-5555.lock 2>/dev/null | tr -s ' ' | sed 's/^ //')"
WEB_LOGIN="$(docker ps --format '{{{{.Names}}}}' | grep '^rewards-web-login-' | paste -sd, - || true)"
WEB_IMAGE_RUNS="$(docker ps -q --filter ancestor='rewards-farmer-main-rewards-farmer:latest' | wc -l)"
MOBILE_PROC="$(ps -eo pid,cmd | grep -E 'bing.sh run|bing.sh use' | grep -v grep || true)"
ACTIVE_PROFILE="$(./bing.sh current 2>/dev/null || true)"
echo "MAINTENANCE=$MAINTENANCE_STATE"
echo "LOCK_HOLDERS=$LOCK_HOLDERS"
echo "WEB_LOGIN_CONTAINERS=$WEB_LOGIN"
echo "WEB_IMAGE_RUNS=$WEB_IMAGE_RUNS"
echo "ACTIVE_PROFILE=$ACTIVE_PROFILE"
echo "MOBILE_PROCESSES_BEGIN"
echo "$MOBILE_PROC"
echo "MOBILE_PROCESSES_END"
"""
        result = self._remote_result("server_busy_check", remote)
        data: dict[str, str] = {}
        for line in result.output.splitlines():
            if "=" in line and not line.startswith("MOBILE_PROCESSES_"):
                key, value = line.split("=", 1)
                data[key.strip()] = value.strip()
        result.data = data
        return result

    def maintenance_status(self) -> OperationResult:
        remote = f"""
set -e
cd {self.remote_repo_expr()}
bash scripts/server_maintenance.sh status
"""
        return self._remote_result("maintenance_status", remote)

    def kill_switch(self, hard: bool = False) -> OperationResult:
        hard_flag = "--hard" if hard else ""
        remote = f"""
set -e
cd {self.remote_repo_expr()}
bash scripts/server_maintenance.sh kill-switch {hard_flag}
"""
        return self._remote_result("kill_switch_hard" if hard else "kill_switch_soft", remote)

    def disable_maintenance(self) -> OperationResult:
        remote = f"""
set -e
cd {self.remote_repo_expr()}
bash scripts/server_maintenance.sh disable
"""
        return self._remote_result("disable_maintenance", remote)

    def resume_incomplete_mobile(self, dry_run: bool) -> OperationResult:
        if dry_run:
            remote = f"""
set -e
cd {self.remote_repo_expr()}
bash scripts/resume_incomplete_mobile.sh --dry-run
"""
            return self._remote_result("resume_preview", remote)

        remote = f"""
set -e
cd {self.remote_repo_expr()}
TS="$(date +%Y%m%d-%H%M%S)"
LOG_FILE="logs/resume-run-$TS.log"
nohup bash scripts/resume_incomplete_mobile.sh --max 6 > "$LOG_FILE" 2>&1 < /dev/null &
PID="$!"
sleep 1
if kill -0 "$PID" 2>/dev/null; then
  STATE="running"
else
  STATE="exited_early"
fi
echo "resume_started=1"
echo "pid=$PID"
echo "log=$LOG_FILE"
echo "state=$STATE"
"""
        return self._remote_result("resume_run", remote)

    def resume_log_tail(self) -> OperationResult:
        remote = f"""
set -e
cd {self.remote_repo_expr()}
echo "running_processes_begin"
pgrep -af 'resume_incomplete_mobile.sh --max 6' || true
echo "running_processes_end"
LATEST="$(ls -1t logs/resume-run-*.log 2>/dev/null | head -1 || true)"
if [ -z "$LATEST" ]; then
  echo "latest_log=none"
  exit 0
fi
echo "latest_log=$LATEST"
echo "tail_begin"
tail -n 60 "$LATEST" || true
echo "tail_end"
"""
        return self._remote_result("resume_tail", remote)

    def prepare_mobile_profile(self, profile: str) -> OperationResult:
        self.validate_profile(profile)
        remote = f"""
set -e
cd {self.remote_repo_expr()}
scripts/mobile_prepare_new_profile.sh {profile}
"""
        return self._remote_result("prepare_mobile_profile", remote)

    def verify_web_login(self, profile: str) -> OperationResult:
        self.validate_profile(profile)
        remote = f"""
set -e
cd {self.remote_repo_expr()}
./run_task.sh login_check {profile}
"""
        return self._remote_result("verify_web_login", remote)

    def verify_mobile_post_login(self, profile: str) -> OperationResult:
        self.validate_profile(profile)
        remote = f"""
set -e
cd {self.remote_repo_expr()}
scripts/mobile_profile_preflight.sh post-login {profile}
"""
        return self._remote_result("verify_mobile_post_login", remote)

    def start_web_login(self, profile: str) -> OperationResult:
        self.validate_profile(profile)
        remote = f"""
set -e
cd {self.remote_repo_expr()}
./web_login.sh {profile} {int(self.cfg.remote_web_port)}
"""
        result = self._remote_result("start_web_login", remote)
        if result.rc != 0:
            return result
        self.proc.start(
            "web_tunnel",
            [
                self.cfg.ssh_bin,
                "-N",
                "-L",
                f"{self.cfg.local_web_port}:127.0.0.1:{self.cfg.remote_web_port}",
                self.cfg.server,
            ],
        )
        url = f"http://localhost:{self.cfg.local_web_port}/vnc.html"
        if self.open_browser:
            webbrowser.open(url)
        result.output = f"{result.output}\nStarted WEB tunnel: {url}".strip()
        return result

    def start_mobile_view(self, profile: str) -> OperationResult:
        self.validate_profile(profile)
        remote = f"""
set -e
cd {self.remote_repo_expr()}
BING_ADB_TIMEOUT_SECONDS=5 ./bing.sh use {profile}
"""
        result = self._remote_result("start_mobile_view", remote)
        if result.rc != 0:
            return result

        self.proc.start(
            "mobile_tunnel",
            [
                self.cfg.ssh_bin,
                "-N",
                "-L",
                f"{self.cfg.local_mobile_port}:127.0.0.1:{self.cfg.remote_mobile_port}",
                self.cfg.server,
            ],
        )
        extra_lines: list[str] = []
        try:
            connect = subprocess.run(
                [self.cfg.adb_bin, "connect", f"127.0.0.1:{self.cfg.local_mobile_port}"],
                capture_output=True,
                text=True,
                check=False,
            )
            if connect.stdout.strip():
                extra_lines.append(connect.stdout.strip())
            if connect.stderr.strip():
                extra_lines.append(connect.stderr.strip())
        except FileNotFoundError:
            extra_lines.append(f"adb not found: {self.cfg.adb_bin}")
            result.rc = 1

        if result.rc == 0:
            try:
                self.proc.start(
                    "scrcpy",
                    [self.cfg.scrcpy_bin, "-s", f"127.0.0.1:{self.cfg.local_mobile_port}"],
                )
                extra_lines.append("Started MOBILE tunnel + scrcpy.")
            except FileNotFoundError:
                extra_lines.append(f"scrcpy not found: {self.cfg.scrcpy_bin}")
                result.rc = 1

        if extra_lines:
            result.output = f"{result.output}\n" + "\n".join(extra_lines)
        return result

    def start_both_views(self, profile: str) -> OperationResult:
        web = self.start_web_login(profile)
        if web.rc != 0:
            return web
        mobile = self.start_mobile_view(profile)
        return OperationResult(
            name="start_both_views",
            rc=mobile.rc,
            output=f"{web.output}\n\n{mobile.output}".strip(),
        )

    def add_profile_web_and_mobile(self, profile: str) -> OperationResult:
        prep = self.prepare_mobile_profile(profile)
        if prep.rc != 0:
            return OperationResult(
                name="add_profile_web_and_mobile",
                rc=prep.rc,
                output=f"[1/3] prepare mobile failed\n{prep.output}".strip(),
            )
        web = self.start_web_login(profile)
        if web.rc != 0:
            return OperationResult(
                name="add_profile_web_and_mobile",
                rc=web.rc,
                output=f"[1/3] prepare mobile ok\n{prep.output}\n\n[2/3] web login failed\n{web.output}".strip(),
            )
        mobile = self.start_mobile_view(profile)
        return OperationResult(
            name="add_profile_web_and_mobile",
            rc=mobile.rc,
            output=(
                f"[1/3] prepare mobile\n{prep.output}\n\n"
                f"[2/3] web login\n{web.output}\n\n"
                f"[3/3] mobile view\n{mobile.output}"
            ).strip(),
        )

    def run_single_daily_stream(self, profile: str, on_line: Callable[[str], None]) -> OperationResult:
        self.validate_profile(profile)
        remote = f"""
set -u -o pipefail
cd {self.remote_repo_expr()}
PROFILE="{profile}"
WEB_PROFILE_DIR="{self.remote_repo_expr()}/edge-profiles/$PROFILE"
TMP_USE="$(mktemp)"
TMP_REWARDS="$(mktemp)"
TMP_WEB="$(mktemp)"
cleanup() {{
  rm -f "$TMP_USE" "$TMP_REWARDS" "$TMP_WEB" 2>/dev/null || true
}}
trap cleanup EXIT

echo "[single-run] profile=$PROFILE"
echo "[single-run] step=mobile_slot_activate"
BING_ADB_TIMEOUT_SECONDS=10 ./bing.sh use "$PROFILE" 2>&1 | tee "$TMP_USE"
USE_RC=${{PIPESTATUS[0]}}

MOBILE_STATE="skipped_slot_unavailable"
if [ "$USE_RC" -eq 0 ]; then
  echo "[single-run] step=mobile_rewards_probe"
  ./bing.sh run rewards --profile "$PROFILE" --iters 0 --no-debug 2>&1 | tee "$TMP_REWARDS"
  REWARDS_RC=${{PIPESTATUS[0]}}
  if grep -q 'state=done' "$TMP_REWARDS"; then
    MOBILE_STATE="no_actions_done_state"
    echo "[single-run] mobile=no_actions (state=done)"
  elif grep -q 'state=wall' "$TMP_REWARDS"; then
    MOBILE_STATE="login_required_wall_state"
    echo "[single-run] mobile=login_required (state=wall)"
  elif [ "$REWARDS_RC" -eq 0 ]; then
    MOBILE_STATE="actions_processed_or_partially_done"
    echo "[single-run] mobile=processed"
  else
    MOBILE_STATE="rewards_flow_error_rc_$REWARDS_RC"
    echo "[single-run] mobile=error rc=$REWARDS_RC"
  fi
else
  echo "[single-run] mobile=skip reason=slot_unavailable_or_boot_not_ready rc=$USE_RC"
fi

WEB_STATE="skipped_not_available"
if [ ! -d "$WEB_PROFILE_DIR" ]; then
  echo "[single-run] web=skip reason=missing_web_profile_dir path=$WEB_PROFILE_DIR"
else
  WEB_LOGIN_ACTIVE="$(docker ps --format '{{{{.Names}}}}' | grep '^rewards-web-login-' | paste -sd, - || true)"
  if [ -n "$WEB_LOGIN_ACTIVE" ]; then
    WEB_STATE="skipped_web_login_container_active"
    echo "[single-run] web=skip reason=web_login_container_active containers=$WEB_LOGIN_ACTIVE"
  else
    echo "[single-run] step=web_bonus_claim"
    ./run_task.sh bonus_points "$PROFILE" 2>&1 | tee "$TMP_WEB"
    WEB_RC=${{PIPESTATUS[0]}}
    if [ "$WEB_RC" -eq 0 ]; then
      WEB_STATE="bonus_claim_ok_or_no_claimables"
      echo "[single-run] web=processed"
    else
      WEB_STATE="bonus_claim_error_rc_$WEB_RC"
      echo "[single-run] web=error rc=$WEB_RC"
    fi
  fi
fi

echo "[single-run] summary mobile=$MOBILE_STATE web=$WEB_STATE"
exit 0
"""
        return self._remote_result_stream("run_single_daily", remote, on_line)

    def run_single_daily(self, profile: str) -> OperationResult:
        return self.run_single_daily_stream(profile, lambda _line: None)

    def stop_local_views(self) -> OperationResult:
        self.proc.stop("scrcpy")
        self.proc.stop("mobile_tunnel")
        self.proc.stop("web_tunnel")
        return OperationResult(name="stop_local_views", rc=0, output="Stopped local tunnels/views.")


class ProfileInputScreen(ModalScreen[str | None]):
    def __init__(self, title: str) -> None:
        super().__init__()
        self.title = title

    def compose(self) -> ComposeResult:
        with Vertical(id="profile-modal"):
            yield Label(self.title, id="profile-title")
            yield Input(placeholder="e.g. r_domena_01", id="profile-input")
            with Horizontal(id="profile-buttons"):
                yield Button("Cancel", id="cancel")
                yield Button("OK", id="ok", variant="primary")

    def on_mount(self) -> None:
        self.query_one("#profile-input", Input).focus()

    @on(Button.Pressed, "#cancel")
    def on_cancel(self) -> None:
        self.dismiss(None)

    @on(Button.Pressed, "#ok")
    def on_ok(self) -> None:
        value = self.query_one("#profile-input", Input).value.strip()
        self.dismiss(value or None)

    @on(Input.Submitted, "#profile-input")
    def on_submit(self, event: Input.Submitted) -> None:
        value = event.value.strip()
        self.dismiss(value or None)


class ConfirmScreen(ModalScreen[bool]):
    def __init__(self, title: str, message: str) -> None:
        super().__init__()
        self.title = title
        self.message = message

    def compose(self) -> ComposeResult:
        with Vertical(id="confirm-modal"):
            yield Label(self.title, id="confirm-title")
            yield Static(self.message, id="confirm-message")
            with Horizontal(id="confirm-buttons"):
                yield Button("Cancel", id="cancel")
                yield Button("Confirm", id="confirm", variant="error")

    @on(Button.Pressed, "#cancel")
    def on_cancel(self) -> None:
        self.dismiss(False)

    @on(Button.Pressed, "#confirm")
    def on_confirm(self) -> None:
        self.dismiss(True)


class ActionMenuScreen(ModalScreen[str | None]):
    def __init__(self, items: list[MenuEntry]) -> None:
        super().__init__()
        self.items = items
        self.by_action = {item.action: item for item in items}

    def compose(self) -> ComposeResult:
        with Vertical(id="action-menu-modal"):
            yield Label("Operator menu (X)", id="action-menu-title")
            options = [Option(f"{item.shortcut:>10}  {item.label}", id=item.action) for item in self.items]
            yield OptionList(*options, id="action-menu-list")
            yield Static("", id="action-menu-details")
            yield Static("Enter: run · Esc: close", id="action-menu-hint")

    def on_mount(self) -> None:
        option_list = self.query_one("#action-menu-list", OptionList)
        option_list.focus()
        if self.items:
            self._update_details(self.items[0].action)

    @on(OptionList.OptionSelected, "#action-menu-list")
    def on_option_selected(self, event: OptionList.OptionSelected) -> None:
        self.dismiss(event.option_id)

    @on(OptionList.OptionHighlighted, "#action-menu-list")
    def on_option_highlighted(self, event: OptionList.OptionHighlighted) -> None:
        if event.option_id:
            self._update_details(event.option_id)

    def _update_details(self, action_name: str) -> None:
        entry = self.by_action.get(action_name)
        if not entry:
            return
        details = (
            f"[b]Command[/b]: {entry.command}\n"
            f"[b]Explanation[/b]: {entry.description}"
        )
        self.query_one("#action-menu-details", Static).update(details)

    def action_dismiss_menu(self) -> None:
        self.dismiss(None)

    BINDINGS = [Binding("escape", "dismiss_menu", "Close")]


class RewardsOperatorTUI(App[None]):
    CSS = """
    Screen {
        layout: vertical;
    }

    #main {
        height: 1fr;
    }

    #left {
        width: 44;
        min-width: 36;
        border: round $primary;
        padding: 1;
        margin-right: 1;
    }

    #right {
        border: round $secondary;
        padding: 1;
    }

    .panel-title {
        text-style: bold;
        color: $accent;
    }

    #profiles {
        height: 1fr;
    }

    #status {
        border: round $accent;
        padding: 0 1;
        height: auto;
        margin-bottom: 1;
    }

    #processes {
        border: round $surface;
        padding: 0 1;
        height: auto;
        margin-bottom: 1;
    }

    #log {
        height: 1fr;
        border: heavy $surface;
    }

    #profile-modal, #confirm-modal {
        width: 70;
        height: auto;
        border: round $primary;
        background: $panel;
        padding: 1 2;
        align: center middle;
    }

    #profile-buttons, #confirm-buttons {
        margin-top: 1;
        height: auto;
        align-horizontal: right;
    }

    #action-menu-modal {
        width: 80;
        height: auto;
        border: round $accent;
        background: $panel;
        padding: 1 2;
        align: center middle;
    }

    #action-menu-title {
        text-style: bold;
        color: $accent;
        margin-bottom: 1;
    }

    #action-menu-list {
        max-height: 16;
        min-height: 10;
    }

    #action-menu-details {
        border: round $surface;
        padding: 0 1;
        margin-top: 1;
        height: auto;
    }

    #action-menu-hint {
        margin-top: 1;
        color: $foreground 60%;
    }
    """

    ACTION_MENU_ITEMS = [
        MenuEntry(
            "refresh_profiles",
            "Refresh profiles",
            "L",
            "ls ~/redroid-variants + ls edge-profiles",
            "Reloads mobile/web profile inventory in the left table.",
        ),
        MenuEntry(
            "busy_check",
            "Server busy check",
            "B",
            "fuser/docker/ps probes",
            "Shows lock holders, running containers and active profile context.",
        ),
        MenuEntry(
            "add_profile",
            "Add profile (web+mobile)",
            "A",
            "mobile_prepare_new_profile + web_login + bing use",
            "Runs full onboarding helper flow for a new profile name.",
        ),
        MenuEntry(
            "prepare_mobile",
            "Prepare mobile profile",
            "P",
            "scripts/mobile_prepare_new_profile.sh <profile>",
            "Rebuilds mobile profile seed and validates pre-login wall gate.",
        ),
        MenuEntry(
            "start_web",
            "Start web view",
            "W",
            "./web_login.sh <profile> + ssh tunnel",
            "Starts noVNC login container and opens local web tunnel.",
        ),
        MenuEntry(
            "start_mobile",
            "Start mobile view",
            "M",
            "./bing.sh use <profile> + adb/scrcpy tunnel",
            "Switches active profile and opens local scrcpy view path.",
        ),
        MenuEntry(
            "start_both",
            "Start both views",
            "O",
            "web_login + mobile_view sequence",
            "Starts WEB and MOBILE view workflow for one selected profile.",
        ),
        MenuEntry(
            "run_single_daily",
            "Run single orchestrated flow",
            "S",
            "mobile: bing use + bing run rewards; web: run_task bonus_points",
            "Runs one controlled mobile+web pass and skips when no actions/slot unavailable.",
        ),
        MenuEntry(
            "verify_web",
            "Verify web login",
            "1",
            "./run_task.sh login_check <profile>",
            "Confirms Edge profile is signed in (state=signed_in).",
        ),
        MenuEntry(
            "verify_mobile",
            "Verify mobile post-login",
            "2",
            "scripts/mobile_profile_preflight.sh post-login <profile>",
            "Checks mobile profile is ready after manual Bing login.",
        ),
        MenuEntry(
            "maintenance_status",
            "Maintenance status",
            "T",
            "scripts/server_maintenance.sh status",
            "Prints maintenance flag and active server process/container state.",
        ),
        MenuEntry(
            "kill_soft",
            "Kill switch soft",
            "K",
            "scripts/server_maintenance.sh kill-switch",
            "Enables maintenance and gracefully stops active automation.",
        ),
        MenuEntry(
            "kill_hard",
            "Kill switch hard",
            "Shift+H",
            "scripts/server_maintenance.sh kill-switch --hard",
            "Escalates to force-stop after soft timeout when needed.",
        ),
        MenuEntry(
            "maintenance_disable",
            "Disable maintenance",
            "D",
            "scripts/server_maintenance.sh disable",
            "Removes maintenance gate and allows normal automation flow.",
        ),
        MenuEntry(
            "resume_preview",
            "Resume preview",
            "V",
            "scripts/resume_incomplete_mobile.sh --dry-run",
            "Shows which profiles are incomplete without starting runs.",
        ),
        MenuEntry(
            "resume_run",
            "Resume run",
            "R",
            "nohup scripts/resume_incomplete_mobile.sh --max 6 > logs/resume-run-*.log &",
            "Starts resume in background and returns PID/log path immediately.",
        ),
        MenuEntry(
            "resume_tail",
            "Resume tail/status",
            "Y",
            "pgrep resume_incomplete_mobile + tail latest logs/resume-run-*.log",
            "Shows whether resume is still running and tails latest resume log.",
        ),
        MenuEntry(
            "stop_views",
            "Stop local views",
            "C",
            "stop local ssh tunnels + scrcpy",
            "Closes local helper processes opened from the TUI.",
        ),
    ]

    BINDINGS = [
        Binding("q", "app_quit", "Quit"),
        Binding("x", "open_action_menu", "Menu"),
        Binding("l", "refresh_profiles", "Refresh profiles", show=False),
        Binding("b", "busy_check", "Busy check", show=False),
        Binding("a", "add_profile", "Add web+mobile", show=False),
        Binding("p", "prepare_mobile", "Prepare mobile", show=False),
        Binding("w", "start_web", "Start web view", show=False),
        Binding("m", "start_mobile", "Start mobile view", show=False),
        Binding("o", "start_both", "Start both views", show=False),
        Binding("s", "run_single_daily", "Run single daily", show=False),
        Binding("1", "verify_web", "Verify web", show=False),
        Binding("2", "verify_mobile", "Verify mobile", show=False),
        Binding("t", "maintenance_status", "Maintenance status", show=False),
        Binding("k", "kill_soft", "Kill soft", show=False),
        Binding("shift+h", "kill_hard", "Kill hard", show=False),
        Binding("d", "maintenance_disable", "Maintenance off", show=False),
        Binding("v", "resume_preview", "Resume preview", show=False),
        Binding("r", "resume_run", "Resume run", show=False),
        Binding("y", "resume_tail", "Resume tail", show=False),
        Binding("c", "stop_views", "Stop local views", show=False),
    ]

    def __init__(self, ops: ProfileOps | None = None) -> None:
        super().__init__()
        self.ops = ops or ProfileOps(default_cfg())
        self.operation_running = False

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal(id="main"):
            with Vertical(id="left"):
                yield Static("Profiles", classes="panel-title")
                yield DataTable(id="profiles")
            with Vertical(id="right"):
                yield Static("Idle", id="status")
                yield Static("Local processes: none", id="processes")
                yield RichLog(id="log", wrap=False, markup=True, highlight=True)
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#profiles", DataTable)
        table.add_columns("Profile", "Mobile", "Web")
        table.cursor_type = "row"
        table.zebra_stripes = True
        self.action_refresh_profiles()

    def action_app_quit(self) -> None:
        self.exit()

    def on_unmount(self) -> None:
        self.ops.proc.stop_all()

    def _selected_profile(self) -> str | None:
        table = self.query_one("#profiles", DataTable)
        if table.row_count == 0:
            return None
        row_index = table.cursor_row
        if row_index is None or row_index < 0:
            row_index = 0
        row = table.get_row_at(row_index)
        profile = str(row[0]).strip()
        return profile or None

    def _set_status(self, text: str) -> None:
        self.query_one("#status", Static).update(text)
        self.query_one("#processes", Static).update(f"Local processes: {self.ops.proc.summary()}")

    def _log_result(self, title: str, result: OperationResult) -> None:
        log = self.query_one("#log", RichLog)
        state = "OK" if result.rc == 0 else "ERR"
        log.write(f"[bold]{title}[/bold] [{state}] rc={result.rc}")
        if result.output.strip():
            for line in result.output.splitlines():
                log.write(line)
        else:
            log.write("(no output)")
        log.write("")

    def _log_live_line(self, line: str) -> None:
        self.query_one("#log", RichLog).write(line)

    def _run_operation(
        self,
        title: str,
        operation: Callable[[], OperationResult] | None = None,
        on_complete: Callable[[OperationResult], None] | None = None,
        stream_operation: Callable[[Callable[[str], None]], OperationResult] | None = None,
    ) -> None:
        if self.operation_running:
            self.notify("Another operation is running", severity="warning")
            return
        self.operation_running = True
        self._set_status(f"Running: {title}")

        def worker() -> None:
            streamed = stream_operation is not None

            def emit(line: str) -> None:
                self.call_from_thread(self._log_live_line, line)

            try:
                if stream_operation is not None:
                    result = stream_operation(emit)
                elif operation is not None:
                    result = operation()
                else:
                    raise RuntimeError("No operation provided")
            except Exception as exc:  # noqa: BLE001
                result = OperationResult(
                    name=title,
                    rc=1,
                    output=f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}",
                )
                streamed = False
            self.call_from_thread(self._finish_operation, title, result, on_complete, streamed)

        self.run_worker(worker, thread=True, name=title, group="ops")

    def _finish_operation(
        self,
        title: str,
        result: OperationResult,
        on_complete: Callable[[OperationResult], None] | None,
        streamed: bool,
    ) -> None:
        self.operation_running = False
        if streamed:
            state = "OK" if result.rc == 0 else "ERR"
            self.query_one("#log", RichLog).write(f"[bold]{title}[/bold] [{state}] rc={result.rc}")
            self.query_one("#log", RichLog).write("")
        else:
            self._log_result(title, result)
        if result.rc == 0:
            self._set_status(f"Idle (last: {title} OK)")
            self.notify(f"{title}: OK")
        else:
            self._set_status(f"Idle (last: {title} FAILED rc={result.rc})")
            self.notify(f"{title}: FAILED rc={result.rc}", severity="error")
        if on_complete is not None:
            on_complete(result)

    def _update_profile_table(self, result: OperationResult) -> None:
        mobile = set(result.data.get("mobile", []))
        web = set(result.data.get("web", []))
        profiles = sorted(mobile | web)
        table = self.query_one("#profiles", DataTable)
        table.clear(columns=False)
        for profile in profiles:
            table.add_row(profile, "yes" if profile in mobile else "no", "yes" if profile in web else "no", key=profile)

    def _run_profile_operation(
        self,
        title: str,
        operation: Callable[[str], OperationResult],
        refresh_profiles: bool = False,
    ) -> None:
        selected = self._selected_profile()

        def execute(profile: str) -> None:
            self._run_operation(
                f"{title} [{profile}]",
                lambda: operation(profile),
                (lambda _: self.action_refresh_profiles()) if refresh_profiles else None,
            )

        if selected:
            execute(selected)
            return

        self.push_screen(
            ProfileInputScreen("Profile name"),
            callback=lambda value: execute(value) if value else None,
        )

    def _run_profile_stream_operation(
        self,
        title: str,
        stream_operation: Callable[[str, Callable[[str], None]], OperationResult],
    ) -> None:
        selected = self._selected_profile()

        def execute(profile: str) -> None:
            self._run_operation(
                f"{title} [{profile}]",
                stream_operation=lambda emit: stream_operation(profile, emit),
            )

        if selected:
            execute(selected)
            return

        self.push_screen(
            ProfileInputScreen("Profile name"),
            callback=lambda value: execute(value) if value else None,
        )

    def action_refresh_profiles(self) -> None:
        self._run_operation("Refresh profiles", self.ops.list_profiles, self._update_profile_table)

    def action_open_action_menu(self) -> None:
        self.push_screen(
            ActionMenuScreen(self.ACTION_MENU_ITEMS),
            callback=self._dispatch_action_menu,
        )

    def _dispatch_action_menu(self, action_name: str | None) -> None:
        if not action_name:
            return
        action = getattr(self, f"action_{action_name}", None)
        if callable(action):
            action()

    def action_busy_check(self) -> None:
        self._run_operation("Server busy check", self.ops.server_busy_check)

    def action_add_profile(self) -> None:
        self.push_screen(
            ProfileInputScreen("New profile name"),
            callback=lambda value: self._run_operation(
                f"Add profile [{value}]",
                lambda: self.ops.add_profile_web_and_mobile(value),
                (lambda _: self.action_refresh_profiles()),
            )
            if value
            else None,
        )

    def action_prepare_mobile(self) -> None:
        self._run_profile_operation("Prepare mobile", self.ops.prepare_mobile_profile, refresh_profiles=True)

    def action_start_web(self) -> None:
        self._run_profile_operation("Start web view", self.ops.start_web_login)

    def action_start_mobile(self) -> None:
        self._run_profile_operation("Start mobile view", self.ops.start_mobile_view)

    def action_start_both(self) -> None:
        self._run_profile_operation("Start both views", self.ops.start_both_views)

    def action_run_single_daily(self) -> None:
        self._run_profile_stream_operation("Run single orchestrated flow", self.ops.run_single_daily_stream)

    def action_verify_web(self) -> None:
        self._run_profile_operation("Verify web", self.ops.verify_web_login)

    def action_verify_mobile(self) -> None:
        self._run_profile_operation("Verify mobile", self.ops.verify_mobile_post_login)

    def action_maintenance_status(self) -> None:
        self._run_operation("Maintenance status", self.ops.maintenance_status)

    def action_kill_soft(self) -> None:
        self._run_operation("Kill switch soft", lambda: self.ops.kill_switch(hard=False))

    def action_kill_hard(self) -> None:
        self.push_screen(
            ConfirmScreen("Hard kill switch", "Force stop after soft timeout. Continue?"),
            callback=lambda confirmed: self._run_operation("Kill switch hard", lambda: self.ops.kill_switch(hard=True))
            if confirmed
            else None,
        )

    def action_maintenance_disable(self) -> None:
        self._run_operation("Disable maintenance", self.ops.disable_maintenance)

    def action_resume_preview(self) -> None:
        self._run_operation("Resume preview", lambda: self.ops.resume_incomplete_mobile(dry_run=True))

    def action_resume_run(self) -> None:
        self._run_operation("Resume run", lambda: self.ops.resume_incomplete_mobile(dry_run=False))

    def action_resume_tail(self) -> None:
        self._run_operation("Resume tail", self.ops.resume_log_tail)

    def action_stop_views(self) -> None:
        self._run_operation("Stop local views", self.ops.stop_local_views)


def default_cfg() -> Config:
    root = Path(__file__).resolve().parents[1]
    adb_default = root / "bin" / "platform-tools" / "adb.exe"
    scrcpy_default = root / "bin" / "scrcpy" / "scrcpy.exe"
    return Config(
        server="piotr.wrotny@10.17.103.115",
        remote_repo="~/rewards-farmer-main",
        ssh_bin="ssh",
        adb_bin=str(adb_default if adb_default.exists() else "adb"),
        scrcpy_bin=str(scrcpy_default if scrcpy_default.exists() else "scrcpy"),
        local_web_port=6080,
        remote_web_port=6080,
        local_mobile_port=15555,
        remote_mobile_port=5555,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Rewards Farmer operator TUI")
    cfg = default_cfg()
    parser.add_argument("--server", default=cfg.server)
    parser.add_argument("--remote-repo", default=cfg.remote_repo)
    parser.add_argument("--ssh-bin", default=cfg.ssh_bin)
    parser.add_argument("--adb-bin", default=cfg.adb_bin)
    parser.add_argument("--scrcpy-bin", default=cfg.scrcpy_bin)
    parser.add_argument("--local-web-port", type=int, default=cfg.local_web_port)
    parser.add_argument("--remote-web-port", type=int, default=cfg.remote_web_port)
    parser.add_argument("--local-mobile-port", type=int, default=cfg.local_mobile_port)
    parser.add_argument("--remote-mobile-port", type=int, default=cfg.remote_mobile_port)
    parser.add_argument("--no-browser", action="store_true", help="Do not auto-open browser when starting web tunnel")
    parser.add_argument("--no-mouse", action="store_true", help="Disable mouse support in terminal UI")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    cfg = Config(
        server=args.server,
        remote_repo=args.remote_repo,
        ssh_bin=args.ssh_bin,
        adb_bin=args.adb_bin,
        scrcpy_bin=args.scrcpy_bin,
        local_web_port=args.local_web_port,
        remote_web_port=args.remote_web_port,
        local_mobile_port=args.local_mobile_port,
        remote_mobile_port=args.remote_mobile_port,
    )
    ops = ProfileOps(cfg=cfg, open_browser=not args.no_browser)
    app = RewardsOperatorTUI(ops=ops)
    app.run(mouse=not args.no_mouse)
    return 0


if __name__ == "__main__":
    sys.exit(main())
