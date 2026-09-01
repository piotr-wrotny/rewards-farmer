"""Bing mobile TEST flow on server-side ReDroid (com.microsoft.bing) — logged-out dev mode.

TEST flow only: runs WITHOUT a Microsoft account after `pm clear`, so first-run noise
(FRE, permission prompts, region popup) is traversed every run and auto-handled. The
PRODUCTION flow runs signed-in on the owner's credentials: that noise never appears and
the handlers below are a safety net, not flow steps. Full step map + test/prod split:
docs/bing-mobile-flow.md.

Path (per Proof-Of-Concept-Artifacts): launch -> FRE dismiss -> home ready-check ->
search -> results (BrowserActivity) -> Rewards (profile menu) -> Read to earn attempt ->
article loop -> evidence in artifacts/.

Dev mode runs WITHOUT a Microsoft account. Every flow step is verified by a screenshot
in artifacts/screenshots/ (plus UI dumps in artifacts/ui/). With --debug, EVERY executed
action (tap/swipe/key/text/permission/launch/back) also produces a screenshot.

Terminal logged-out state: Rewards page shows the "Join Microsoft Rewards" wall
("Access now" -> OneAuth sign-in -> needs network/account). The flow detects the wall,
records evidence and stops cleanly instead of failing.

Usage (Windows dev machine, SSH tunnel to the server first):
    ssh -N -L 15555:127.0.0.1:5555 piotr.wrotny@10.17.103.115
    python src/bing_mobile_flow.py [--iters N] [--debug] [--clear] [--serial S] [--server U@H]

    --clear   wipe Bing app data on the server (pm clear) so the next attempt starts
              fresh: FRE, permission dialogs and onboarding reappear. Dev/test only —
              on Prod the app stays signed in and data is never cleared here.
    --debug   screenshot every single executed action (default: step milestones only)

Requires: pip install uiautomator2; adb on PATH or at bin/platform-tools/adb.exe.
"""
import argparse
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
ART_DIR = os.path.join(ROOT, "artifacts")
SHOT_DIR = os.path.join(ART_DIR, "screenshots")
UI_DIR = os.path.join(ART_DIR, "ui")


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def action(context, detail="", trigger="flow"):
    """Repo-wide action log convention (see AGENTS.md)."""
    log(f"[ACTION] {context} [{detail}] trigger={trigger}")


class BingMobileFlow:
    def __init__(self, serial, debug=False, query="hello world"):
        self.serial = serial
        self.debug = debug
        self.query = query
        self.seq = 0
        os.makedirs(SHOT_DIR, exist_ok=True)
        os.makedirs(UI_DIR, exist_ok=True)
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
        path = os.path.join(SHOT_DIR, name + ".png")
        self.d.screenshot(path)
        log(f"[SHOT] {path} focus={self.activity()}")
        if ui_dump:
            xml = self.d.dump_hierarchy()
            with open(os.path.join(UI_DIR, name + ".xml"), "w", encoding="utf-8") as f:
                f.write(xml)
        return name

    def act_shot(self, label):
        """Per-action screenshot: always in --debug, no-op otherwise."""
        if self.debug:
            self.shot(f"action-{label}", ui_dump=False)

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
    def run(self, iterations):
        log(f"connected serial={self.serial} screen={self.w}x{self.h} debug={self.debug}")
        self.launch()
        self.shot("after-launch")
        if self.dismiss_fre():
            log("FRE dismissed")
        # home wait loop: permission dialogs can hold focus for a while after pm clear
        end = time.time() + 40
        home = False
        while time.time() < end:
            self.accept_permissions()
            self.dismiss_popups()
            if ACT_HOME in self.focus() and self.d(resourceId=SEARCH_BOX).exists:
                home = True
                break
            if ACT_CAMERA in self.focus():
                self.recover_camera()
            time.sleep(1)
        if not home:
            self.shot("home-timeout")
            raise RuntimeError(f"never reached home ({ACT_HOME}); focus={self.focus()}")
        self.shot("home-ready")

        serp = self.search_and_results()
        log(f"search results BrowserActivity opened: {serp}")
        if not self.ensure_home():
            raise RuntimeError("home not reachable after search")

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
        read = self.article_loop(iterations)
        return {"state": state, "articles_read": read}


def check_serial(serial):
    """Make sure adb sees the ReDroid serial (tunnel port must be forwarded already)."""
    adb = shutil.which("adb") or os.path.join(ROOT, "bin", "platform-tools", "adb.exe")
    host, _, port_s = serial.partition(":")
    if host == "127.0.0.1" and port_s:
        port = int(port_s)
        with socket.socket() as s:
            s.settimeout(2)
            if s.connect_ex(("127.0.0.1", port)) != 0:
                sys.exit(
                    f"ERROR: nothing listening on 127.0.0.1:{port}. Start the SSH tunnel first:\n"
                    "  ssh -N -L 15555:127.0.0.1:5555 piotr.wrotny@10.17.103.115"
                )
        subprocess.run([adb, "connect", serial], capture_output=True, text=True)
    out = subprocess.run([adb, "devices"], capture_output=True, text=True).stdout
    if serial not in out:
        sys.exit(f"ERROR: {serial} not in adb devices:\n{out}")


def main():
    p = argparse.ArgumentParser(description="Bing mobile flow on ReDroid (dev, logged-out)")
    p.add_argument("--serial", default="127.0.0.1:15555")
    p.add_argument("--server", default="piotr.wrotny@10.17.103.115", help="ssh target for --clear")
    p.add_argument("--iters", type=int, default=10, help="articles to read")
    p.add_argument("--query", default="hello world", help="search query for the search step")
    p.add_argument("--debug", action="store_true", help="screenshot every executed action")
    p.add_argument("--clear", action="store_true",
                   help="dev-only: wipe Bing app data first (pm clear)")
    a = p.parse_args()

    check_serial(a.serial)
    flow = BingMobileFlow(a.serial, debug=a.debug, query=a.query)
    if a.clear:
        flow.clear_app_data(a.server)
        time.sleep(3)
    result = flow.run(a.iters)
    log(f"DONE state={result['state']} articles_read={result['articles_read']}")
    log(f"evidence: {SHOT_DIR}")


if __name__ == "__main__":
    main()
