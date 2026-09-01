"""Bing mobile flow on server-side ReDroid (com.microsoft.bing), per profile variant.

Profile `test` runs WITHOUT a Microsoft account (pm clear allowed), so first-run noise
(FRE, permission prompts, region popup) is traversed every run and auto-handled.
`prod_N` profiles run signed-in on the owner's credentials: that noise never appears
and the handlers below are a safety net, not flow steps. Full step map + test/prod
split: docs/bing-mobile-flow.md.

Path (per Proof-Of-Concept-Artifacts): launch -> FRE dismiss -> home ready-check ->
search -> results (BrowserActivity) -> Rewards (profile menu) -> Read to earn attempt ->
article loop -> evidence in artifacts/.
Every run is keyed to a profile variant (test|prod_1|prod_2|...): evidence lands in
artifacts/<profile>/screenshots|ui. With --debug, EVERY executed action
(tap/swipe/key/text/permission/launch/back) also produces a screenshot
(default: on for profile=test, off for prod).

Terminal logged-out state (profile=test): Rewards page shows the "Join Microsoft
Rewards" wall ("Access now" -> OneAuth sign-in -> needs account). The flow detects
the wall, records evidence and stops cleanly (exit 0) instead of failing.

Usage (normally via ./bing.sh on the server; from the Windows dev machine open the
SSH tunnel first):
    ssh -N -L 15555:127.0.0.1:5555 piotr.wrotny@10.17.103.115
    python src/bing_mobile_flow.py [--profile P] [--only ACTION] [--iters N]
                                   [--debug|--no-debug] [--clear] [--serial S] [--server U@H]

    --only    full|search|rewards|read-to-earn|screenshot (default full)
    --clear   wipe Bing app data on the server (pm clear) so the next attempt starts
              fresh: FRE, permission dialogs and onboarding reappear. ONLY for
              profile=test — prod profiles stay signed in and are never cleared.

Exit codes: 0 ok (incl. terminal wall/done), 2 flow failure, 3 infra.

Requires: pip install uiautomator2; adb on PATH or at bin/platform-tools/adb.exe.
"""
import argparse
import json
import os
import random
import re
import shutil
import socket
import subprocess
import sys
import time

import uiautomator2 as u2

PKG = "com.microsoft.bing"
LAUNCH_ACTIVITY = "com.microsoft.sapphire.app.main.SapphireMainActivity"
ACT_FRE = "BingAppGlobalFreActivity"
ACT_HOME = "MainSapphireActivity"
ACT_BROWSER = "BrowserActivity"
ACT_CAMERA = "CameraActivity"
ACT_REWARDS = "TemplateActivity"
ACT_MARKET_POPUP = "ToModifyMarketPopupActivity"
FRE_NO_BUTTON = "com.microsoft.bing:id/sapphire_fre_bing_no_button"
SEARCH_BOX = "com.microsoft.bing:id/sa_search_box"
PROFILE_BUTTON = "com.microsoft.bing:id/sa_profile_button"

PERMISSION_ALLOW_IDS = (
    "com.android.permissioncontroller:id/permission_allow_button",
    "com.android.permissioncontroller:id/permission_allow_foreground_only_button",
    "com.android.permissioncontroller:id/permission_allow_one_time_button",
)

VIDEO_BADGE = re.compile(r"^\d+:\d\d$")
SOURCE_LINE = re.compile(r"^.+\s·\s.+$")
SKIP_WORDS = ("Oferta", "Koszula", "Regatta", "Search", "Rewards", "Image Creator", "Trending")
RTE_ACTIVE = re.compile(
    r'content-desc="Read to earn, , \d+ out of \d+ points earned"'
    r'[^>]*bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"'
)
RTE_DONE_TEXT = re.compile(r'text="Read to earn, \d+ points earned"')
SIGNIN_WALL = re.compile(r"Join Microsoft Rewards|Access now")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ART_DIR = os.path.join(ROOT, "artifacts")  # artifacts/<profile>/{screenshots,ui}


def profile_dirs(profile):
    base = os.path.join(ART_DIR, profile)
    return os.path.join(base, "screenshots"), os.path.join(base, "ui")


class InfraError(RuntimeError):
    """Container/adb/driver infrastructure problem (exit 3)."""


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def action(context, detail="", trigger="flow"):
    """Repo-wide action log convention (see AGENTS.md)."""
    log(f"[ACTION] {context} [{detail}] trigger={trigger}")


class BingMobileFlow:
    def __init__(self, serial, debug=False, query="hello world", profile="test"):
        self.serial = serial
        self.debug = debug
        self.query = query
        self.profile = profile
        self.seq = 0
        self.shot_dir, self.ui_dir = profile_dirs(profile)
        os.makedirs(self.shot_dir, exist_ok=True)
        os.makedirs(self.ui_dir, exist_ok=True)
        self.d = u2.connect(serial)
        self.d.implicitly_wait(5)
        self.w = self.d.info["displayWidth"]
        self.h = self.d.info["displayHeight"]

    # ------------------------------------------------------------- evidence
    def focus(self):
        out = self.d.shell("dumpsys window 2>/dev/null | grep -m1 mCurrentFocus").output
        return out.strip()

    def activity(self):
        f = self.focus()
        return f.split("/")[-1].split()[0] if "/" in f else "?"

    def wait_activity(self, needle, timeout=20):
        for _ in range(timeout * 2):
            if needle in self.focus():
                return True
            time.sleep(0.5)
        return False

    def shot(self, label, ui_dump=True):
        self.seq += 1
        name = f"{self.seq:02d}-{re.sub(r'[^a-z0-9]+', '-', label.lower()).strip('-')}"
        path = os.path.join(self.shot_dir, name + ".png")
        self.d.screenshot(path)
        log(f"[SHOT] {path} focus={self.activity()}")
        if ui_dump:
            xml = self.d.dump_hierarchy()
            with open(os.path.join(self.ui_dir, name + ".xml"), "w", encoding="utf-8") as f:
                f.write(xml)
        return name


    # ------------------------------------------------------------- primitives
    def tap(self, target, label):
        action("tap", label)
        if isinstance(target, tuple) and target and target[0] == "text":
            self.d(text=target[1]).click()
        elif isinstance(target, str):
            self.d(resourceId=target).click()
        else:
            self.d.click(*target)
        self.act_shot(f"tap-{label}")

    def act_shot(self, label):
        """Per-action screenshot: always in --debug, no-op otherwise."""
        if self.debug:
            time.sleep(1.5)  # let screen repaint after the action; screencap otherwise is stale
            self.shot(f"action-{label}", ui_dump=False)

    def swipe(self, fx, fy, tx, ty, label, duration=0.3):
        action("swipe", f"{label} ({fx:.2f},{fy:.2f})->({tx:.2f},{ty:.2f})")
        self.d.swipe(self.w * fx, self.h * fy, self.w * tx, self.h * ty, duration)
        self.act_shot(f"swipe-{label}")

    def scroll_feed(self, amount=0.45):
        self.swipe(0.5, 0.75, 0.5, 0.75 - amount, "feed")

    def press(self, key, label=""):
        action("key", key + (f" {label}" if label else ""))
        self.d.press(key)
        self.act_shot(f"key-{key}-{label}")

    def type_text(self, text):
        action("text", text)
        self.d.send_keys(text, clear=False)
        self.act_shot("type-text")

    def accept_permissions(self, rounds=3):
        """Dev mode grants every OS dialog Bing raises (camera/notifications/etc.)."""
        for _ in range(rounds):
            if "permissioncontroller" not in self.focus():
                return
            clicked = False
            for rid in PERMISSION_ALLOW_IDS:
                b = self.d(resourceId=rid)
                if b.exists:
                    action("permission", rid.split("/")[-1], trigger="system-dialog")
                    b.click()
                    clicked = True
                    break
            if not clicked:
                self.press("back", "dismiss-dialog")
            self.act_shot("permission-accepted")
            time.sleep(4)

    def recover_camera(self):
        """Logged-out fresh installs can misroute glance cards into CameraActivity."""
        while ACT_CAMERA in self.focus():
            action("recover", "back out of CameraActivity")
            self.press("back", "camera-recover")
            time.sleep(2)

    # ------------------------------------------------------------- flow steps
    def clear_app_data(self, server):
        """Dev reset: wipe Bing app data so FRE/onboarding reappear for a fresh attempt."""
        cmd = ["ssh", server, f"adb -s 127.0.0.1:5555 shell pm clear {PKG}"]
        log(f"[CLEAR] {' '.join(cmd)}")
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        log(f"[CLEAR] rc={r.returncode} out={r.stdout.strip()}")
        if "Success" not in r.stdout:
            raise RuntimeError(f"pm clear failed: {r.stdout}{r.stderr}")

    def launch(self):
        action("launch", PKG)
        self.d.app_start(PKG, LAUNCH_ACTIVITY)
        time.sleep(6)

    def dismiss_fre(self, timeout=12):
        """FRE check via its button — window focus may be held by a permission dialog."""
        end = time.time() + timeout
        shot_done = False
        while time.time() < end:
            self.accept_permissions()
            if ACT_FRE in self.focus() and not shot_done:
                self.shot("fre-screen")
                shot_done = True
            btn = self.d(resourceId=FRE_NO_BUTTON)
            later = self.d(textContains="Maybe later")
            if btn.exists or later.exists:
                if not shot_done:
                    self.shot("fre-screen")
                self.tap(FRE_NO_BUTTON if btn.exists else ("text", "Maybe later"),
                         "fre-maybe-later")
                time.sleep(8)
                self.shot("fre-dismissed")
                return True
            if self.d(resourceId=SEARCH_BOX).exists:
                return False  # already home, no FRE
            time.sleep(1)
        return False

    def dismiss_popups(self):
        """Bing template popups (e.g. 'Country/region updated') block home after FRE."""
        if ACT_MARKET_POPUP in self.focus():
            ok = self.d(text="OK")
            if ok.exists:
                action("popup", "dismiss 'Country/region updated' with OK")
                ok.click()
                time.sleep(4)
                return True
        return False

    def ensure_home(self):
        for _ in range(4):
            self.accept_permissions()
            self.dismiss_popups()
            if self.d(resourceId=SEARCH_BOX).exists and ACT_HOME in self.focus():
                return True
            if ACT_CAMERA in self.focus() or "permissioncontroller" in self.focus():
                self.recover_camera()
                continue
            action("recover", "relaunch to home")
            self.d.app_start(PKG, LAUNCH_ACTIVITY)
            time.sleep(6)
        return False

    def search_and_results(self):
        self.tap(SEARCH_BOX, "search-box")
        time.sleep(3)
        self.type_text(self.query)
        time.sleep(2)
        self.press("enter", "submit-search")
        opened = self.wait_activity(ACT_BROWSER, 15)
        time.sleep(6)  # webview settle (DNS may be down dev-side; screenshot tells)
        self.shot("search-results")
        self.press("back", "leave-results")
        time.sleep(3)
        return opened

    def open_rewards(self):
        if not self.ensure_home():
            raise RuntimeError("home screen not reachable")
        self.tap(PROFILE_BUTTON, "profile-button")
        time.sleep(5)
        self.shot("profile-menu")
        entry = self.d(text="Microsoft Rewards")
        if not entry.exists:
            self.shot("profile-menu-no-rewards-entry")
            raise RuntimeError("'Microsoft Rewards' entry missing from profile menu")
        self.tap(("text", "Microsoft Rewards"), "rewards-entry")
        time.sleep(8)
        self.accept_permissions()
        self.shot("rewards-page")
        return ACT_REWARDS in self.focus()

    def rewards_state(self):
        """Classify the Rewards page: 'rte' (card present), 'done', 'wall' (logged-out)."""
        xml = self.d.dump_hierarchy()
        m = RTE_ACTIVE.search(xml)
        if m:
            x1, y1, x2, y2 = map(int, m.groups())
            return "rte", ((x1 + x2) // 2, (y1 + y2) // 2)
        if RTE_DONE_TEXT.search(xml):
            return "done", None
        if SIGNIN_WALL.search(xml):
            return "wall", None
        for _ in range(6):
            self.scroll_feed()
            time.sleep(2)
            xml = self.d.dump_hierarchy()
            m = RTE_ACTIVE.search(xml)
            if m:
                x1, y1, x2, y2 = map(int, m.groups())
                return "rte", ((x1 + x2) // 2, (y1 + y2) // 2)
            if RTE_DONE_TEXT.search(xml):
                return "done", None
        return "unknown", None

    # ------------------------------------------------------------- article loop
    def candidate_articles(self):
        xml = self.d.dump_hierarchy()
        nodes = []
        for m in re.finditer(
            r'<node[^>]*?text="([^"]*)"[^>]*?bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"[^>]*?>', xml
        ):
            t = m.group(1)
            x1, y1, x2, y2 = map(int, m.groups()[1:])
            if t:
                nodes.append((y1, y2, x1, x2, t))
        nodes.sort()
        descs = re.findall(
            r'content-desc="([^"]*)"[^>]*bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"', xml
        )
        ad_bands = [
            (int(y1) - 350, int(y2) + 350)
            for s, x1, y1, x2, y2 in descs
            if ". Ad," in s or s.startswith("Ad, ")
        ]
        titles = [n for n in nodes if len(n[4]) > 25]
        sources = [n for n in nodes if SOURCE_LINE.match(n[4])]
        durs = [n for n in nodes if VIDEO_BADGE.match(n[4]) and n[0] > 100]
        out = []
        for t in titles:
            if any(k in t[4] for k in SKIP_WORDS):
                continue
            if not any(0 < s[0] - t[1] < 260 for s in sources):
                continue
            if any(0 < t[0] - v[1] < 400 for v in durs):
                continue  # video card
            cy = (t[0] + t[1]) // 2
            if any(a0 < cy < a1 for a0, a1 in ad_bands):
                continue  # ad card
            out.append((t[4], (t[2] + t[3]) // 2, cy))
        return out

    def read_article(self, dwell):
        end = time.time() + dwell
        while time.time() < end:
            self.swipe(0.75, 0.75, 0.75, random.uniform(0.45, 0.55), "article-read", 0.2)
            time.sleep(random.uniform(1.2, 2.0))

    def article_loop(self, iterations):
        seen, done, scrolls = set(), 0, 0
        while done < iterations and scrolls < 60:
            cands = [c for c in self.candidate_articles() if c[0] not in seen]
            if not cands:
                scrolls += 1
                self.scroll_feed()
                time.sleep(2)
                continue
            title, cx, cy = random.choice(cands[:3])
            seen.add(title)
            self.tap((cx, cy), "article-card")
            self.shot(f"article-opened-{done + 1}")
            time.sleep(random.uniform(5, 7))
            self.read_article(random.uniform(5, 10))
            self.shot(f"article-read-{done + 1}")
            self.press("back", "leave-article")
            time.sleep(random.uniform(3, 4.5))
            done += 1
            log(f"[{done}/{iterations}] read: {title[:60]}")
        return done

    # ------------------------------------------------------------- orchestration
    def to_home(self):
        """Launch + settle at home with first-run noise handled. Every --only starts here."""
        log(f"connected profile={self.profile} serial={self.serial} "
            f"screen={self.w}x{self.h} debug={self.debug}")
        self.launch()
        self.shot("after-launch")
        if self.dismiss_fre():
            log("FRE dismissed")
        # home wait loop: permission dialogs can hold focus for a while after pm clear
        end = time.time() + 40
        while time.time() < end:
            self.accept_permissions()
            self.dismiss_popups()
            if ACT_HOME in self.focus() and self.d(resourceId=SEARCH_BOX).exists:
                self.shot("home-ready")
                return
            if ACT_CAMERA in self.focus():
                self.recover_camera()
            time.sleep(1)
        self.shot("home-timeout")
        raise RuntimeError(f"never reached home ({ACT_HOME}); focus={self.focus()}")

    def screenshot_step(self):
        name = self.shot("screenshot")  # shot() returns the file stem
        return {"state": "home", "articles_read": 0, "screenshot": name}

    def rewards_tail(self, iterations):
        """Rewards page -> Read to earn -> article loop (terminal: wall/done)."""
        if not self.open_rewards():
            self.shot("rewards-page-unexpected")
            log(f"WARNING: rewards page focus={self.activity()} (continuing anyway)")
        state, card = self.rewards_state()
        self.shot(f"rewards-state-{state}")
        log(f"rewards state: {state}")
        if state == "wall":
            log("LOGGED-OUT SIGN-IN WALL: 'Join Microsoft Rewards' / 'Access now'. "
                "Read-to-earn requires an account — prod path. Stopping at wall with evidence.")
            return {"state": state, "articles_read": 0}
        if state == "done":
            log("Read to earn already complete for today (terminal state).")
            return {"state": state, "articles_read": 0}
        if state != "rte":
            log("Read to earn card not found on Rewards page.")
            return {"state": state, "articles_read": 0}
        self.tap(card, "read-to-earn-card")
        time.sleep(8)
        self.shot("read-to-earn-feed")
        return {"state": state, "articles_read": self.article_loop(iterations)}

    def run_only(self, only, iterations):
        self.to_home()
        if only == "screenshot":
            return self.screenshot_step()
        if only == "search":
            serp = self.search_and_results()
            log(f"search results BrowserActivity opened: {serp}")
            if not self.ensure_home():
                raise RuntimeError("home not reachable after search")
            return {"state": "searched", "articles_read": 0, "serp": serp}
        # 'rewards'/'read-to-earn' go straight to the Rewards page; 'full' searches
        # first (the original proven sequence).
        if only == "full":
            serp = self.search_and_results()
            log(f"search results BrowserActivity opened: {serp}")
            if not self.ensure_home():
                raise RuntimeError("home not reachable after search")
        return self.rewards_tail(iterations)


def check_serial(serial):
    """Make sure adb sees the ReDroid serial (tunnel port must be forwarded already)."""
    adb = shutil.which("adb") or os.path.join(ROOT, "bin", "platform-tools", "adb.exe")
    host, _, port_s = serial.partition(":")
    if host == "127.0.0.1" and port_s:
        port = int(port_s)
        with socket.socket() as s:
            s.settimeout(2)
            if s.connect_ex(("127.0.0.1", port)) != 0:
                raise InfraError(
                    f"nothing listening on 127.0.0.1:{port}. On the server the container "
                    "must be running (./bing.sh use <profile>); from the dev machine open "
                    "the SSH tunnel first: "
                    "ssh -N -L 15555:127.0.0.1:5555 piotr.wrotny@10.17.103.115"
                )
        subprocess.run([adb, "connect", serial], capture_output=True, text=True)
    out = subprocess.run([adb, "devices"], capture_output=True, text=True).stdout
    if serial not in out:
        raise InfraError(f"{serial} not in adb devices:\n{out}")


def main():
    p = argparse.ArgumentParser(description="Bing mobile flow on ReDroid, per profile variant")
    p.add_argument("--serial", default="127.0.0.1:15555")
    p.add_argument("--server", default="piotr.wrotny@10.17.103.115", help="ssh target for --clear")
    p.add_argument("--iters", type=int, default=10, help="articles to read")
    p.add_argument("--query", default="hello world", help="search query for the search step")
    p.add_argument("--profile", default="test",
                   help="profile variant (test|prod_1|prod_2|...); evidence -> artifacts/<profile>/")
    p.add_argument("--only", default="full",
                   choices=("full", "search", "rewards", "read-to-earn", "screenshot"))
    p.add_argument("--debug", action=argparse.BooleanOptionalAction, default=None,
                   help="screenshot every executed action (default: on for profile=test)")
    p.add_argument("--clear", action="store_true",
                   help="wipe Bing app data first (pm clear; profile=test only)")
    a = p.parse_args()
    debug = a.debug if a.debug is not None else a.profile == "test"

    if a.clear and a.profile != "test":
        print("[FATAL] --clear only allowed for profile=test", file=sys.stderr)
        sys.exit(3)
    flow = None
    try:
        check_serial(a.serial)
        if a.clear and a.profile != "test":
            print("[FATAL] --clear only allowed for profile=test", file=sys.stderr)
            sys.exit(3)
        flow = BingMobileFlow(a.serial, debug=debug, query=a.query, profile=a.profile)
        if a.clear:
            flow.clear_app_data(a.server)
        result = flow.run_only(a.only, a.iters)
        log(f"DONE state={result['state']} articles_read={result['articles_read']}")
        log(f"evidence: {profile_dirs(a.profile)[0]}")
        print(json.dumps({"profile": a.profile, **result}, ensure_ascii=False))
        sys.exit(0)
    except InfraError as e:
        print(f"[FATAL] infra: {e}", file=sys.stderr)
        sys.exit(3)
    except (u2.exceptions.DeviceError, u2.exceptions.RPCError,
            subprocess.SubprocessError, RuntimeError) as e:
        if flow is not None:
            flow.shot("failed")
        print(f"[FATAL] {type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
