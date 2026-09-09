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

    --only    full|search|rewards|read-to-earn|misc-cards|screenshot (default full)
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
SOURCE_LINE = re.compile(r"^.+\s·\s.+$")  # old emulator: 'Source · time' in ONE node
# ReDroid 34.0 feed splits them: 'Daily Mail' and '15h ago' are separate nodes
# (prod_2 dump 2026-09-01) — relative age is the reliable card signature.
AGE_LINE = re.compile(r"^(?=.*\d).{1,12}\b(ago|temu)$", re.IGNORECASE)
SKIP_WORDS = ("Oferta", "Koszula", "Regatta", "Search", "Rewards", "Image Creator", "Trending")
RTE_ACTIVE = re.compile(
    r'content-desc="Read to earn, , (\d+) out of (\d+) points earned"'
    r'[^>]*bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"'
)
RTE_DONE_TEXT = re.compile(r'text="Read to earn, \d+ points earned"')
SIGNIN_WALL = re.compile(r"Join Microsoft Rewards|Access now")
# Rewards-page earnable activity cards (More/Daily activities). Verified domena1-prod
# 2026-09-09: tap at center opens the SERP in BrowserActivity, points credited
# (+10/+10/+5 observed, Daily points 55/75 -> 75/75), card leaves the pool after.
ACTIVITY_CARD = re.compile(
    r'content-desc="([^"]*?, earn (\d+) points[^"]*)"'
    r'[^>]*bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"'
)
CHECKIN_TEXT = "Check in"
CHECKED_ICON = re.compile(r'text="checked"')  # filled Day-1 ring = checked in today
TOTAL_POINTS = re.compile(r'text="([\d,]+)"[^>]*>\s*<node[^>]*text="Total points"')
DAILY_POINTS = re.compile(r'text="(\d+/\d+)"[^>]*>\s*<node[^>]*text="Daily points"')

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
        self._rte_counter = None  # last (done, cap) read by rewards_state
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

    def relaunch(self):
        """Cold restart. Warm tasks resume wherever left off (e.g. Rewards
        TemplateActivity — cron-sim 2026-09-01); app_start alone does NOT fix that."""
        action("launch", PKG)
        self.d.app_stop(PKG)
        time.sleep(1)
        self.d.app_start(PKG, LAUNCH_ACTIVITY)
        time.sleep(6)

    def launch(self):
        self.relaunch()

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
            if self.d(resourceId=SEARCH_BOX).exists and self.d(resourceId=PROFILE_BUTTON).exists \
                    and ACT_HOME in self.focus():
                return True
            if ACT_CAMERA in self.focus() or "permissioncontroller" in self.focus():
                self.recover_camera()
            elif self.d(resourceId=SEARCH_BOX).exists:
                # search box but no profile button = MSN feed view over home (same
                # activity); back pops it (prod_2 dump 2026-09-01: feed header lacks
                # sa_profile_button).
                action("recover", "back out of feed view")
                self.press("back", "feed-to-home")
                time.sleep(3)
            else:
                # warm-resume views (e.g. Rewards TemplateActivity) ignore a plain
                # app_start — only a cold relaunch lands on home.
                action("recover", "relaunch to home (cold)")
                self.relaunch()
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
    # ------------------------------------------------------- required searches
    # Port of web complete_required_searches (rewards_tasks.py:258): a fixed
    # number of searches from a phrase pool built off nouns.txt + templates,
    # scroll after each, 5-6 s settle. On mobile the search box is tapped fresh
    # per query (AIToolsSuggestActivity keeps typed text between searches).
    SEARCH_QUERY_TEMPLATES = (
        "{noun} facts", "{noun} history", "{noun} benefits", "{noun} examples",
        "{noun} guide {year}", "best {noun} tips", "how to use {noun}",
        "{noun} for beginners", "{noun} near me", "{noun} latest news",
        "{noun} interesting trivia", "{noun} comparison",
    )

    def build_phrase_pool(self, size=600):
        nouns_path = os.path.join(ROOT, "nouns.txt")
        nouns = list({n.strip().lower() for n in open(nouns_path, encoding="utf-8")
                      if len(n.strip()) >= 3})
        pool = []
        while len(pool) < size and nouns:
            noun = random.choice(nouns)
            tpl = random.choice(self.SEARCH_QUERY_TEMPLATES)
            pool.append(tpl.format(noun=noun, year=random.choice((2024, 2025, 2026))))
        return pool

    def required_searches(self, count=30):
        """count searches: unique sample of the phrase pool; after each query —
        random scroll on the SERP + 5-6 s wait (web flow parity, AGENTS.md).
        Per-iteration ensure_home(): after back from the SERP the app can rest
        on AIToolsSuggestActivity / MSN feed (tunnel pilot 2026-09-09) and the
        home search box is not addressable there."""
        queries = random.sample(self.build_phrase_pool(), min(count, 600))
        ok = 0
        try:
            for i, q in enumerate(queries, 1):
                if not self.ensure_home():
                    log(f"[{i}/{len(queries)}] home unreachable — aborting batch")
                    break
                self.tap(SEARCH_BOX, f"search-box-{i}")
                time.sleep(2)
                self.type_text(q)
                time.sleep(1.5)
                self.press("enter", f"submit-search-{i}")
                opened = self.wait_activity(ACT_BROWSER, 15)
                if opened:
                    time.sleep(5)
                    # human-ish scroll: 1-3 random swipes down, then 5-6 s
                    for _ in range(random.randint(1, 3)):
                        self.swipe(0.5, 0.7, 0.5,
                                   0.7 - random.uniform(0.08, 0.2), "search-scroll")
                        time.sleep(random.uniform(0.8, 1.5))
                    time.sleep(random.uniform(5, 6))
                    self.press("back", f"leave-results-{i}")
                    time.sleep(3)
                    ok += 1
                    log(f"[{i}/{len(queries)}] {q!r} serp=True")
                else:
                    log(f"[{i}/{len(queries)}] {q!r} SERP NOT OPENED")
                    self.press("back", "recover-suggest")
                    time.sleep(2)
        finally:
            self.cleanup_tabs()
        return {"state": "searches_done", "articles_read": ok,
                "searches": ok, "total": len(queries)}


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

    def _rte_match(self, xml):
        """RTE card match with REAL geometry: the lazy WebView sometimes renders
        the tile with bounds=[0,0][0,0] (d3 2026-09-09 18:36) — its centre would
        be (0,0): a tap there exits to home ('feed-not-opened' symptom). Returns
        (state, card, counter): card None unless geometry is real."""
        for m in RTE_ACTIVE.finditer(xml):
            done, cap = int(m.group(1)), int(m.group(2))
            x1, y1, x2, y2 = map(int, m.groups()[2:])
            if done >= cap:
                return "done", None, (done, cap)  # 30/30 => terminal, not active
            if x2 <= x1 or y2 <= y1:
                log(f"RTE tile zero-size bounds [{x1},{y1}][{x2},{y2}] — not tappable")
                continue
            return "rte", ((x1 + x2) // 2, (y1 + y2) // 2), (done, cap)
        return None, None, None

    def rewards_state(self):
        """Classify the Rewards page: 'rte' (tappable card), 'done', 'unrendered'
        (RTE tile present but only zero-size nodes — lazy WebView), 'wall'.
        Search-done tiles live ABOVE the RTE tile in the WebView — the scroll
        hunt must not run before the full-page done check (d3 2026-09-09)."""
        xml = self.d.dump_hierarchy()
        for _ in range(11):  # old-flow find_read_to_earn: dump + 10 scroll rounds
            state, card, counter = self._rte_match(xml)
            if state:
                self._rte_counter = counter
                return state, card
            # no scrollable done yet: page-level terminal signals first
            if self.TILE_RTE_DONE.search(xml) or RTE_DONE_TEXT.search(xml):
                self._rte_counter = None
                return "done", None
            if SIGNIN_WALL.search(xml):
                return "wall", None
            if self.TILE_RTE.search(xml):
                return "unrendered", None  # tile desc present, geometry zero-size
            self.scroll_feed()
            time.sleep(2)
            xml = self.d.dump_hierarchy()
        return "unknown", None

    # ------------------------------------------------------------- article loop
    def candidate_articles(self):
        """Old-flow heuristics (:173-202) calibrated to ReDroid 34.0 dump (prod_2
        2026-09-01): source and age are SEPARATE nodes ('Daily Mail' / '15h ago') and
        the age line overlaps the title box (its top can be ABOVE the title bottom,
        measured -10..+120 vs title top) — anchor on title TOP with a -40 margin;
        every title appears twice (keep the tallest — the short duplicate's center
        lands on the Like/Share row)."""
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
        best = {}  # title -> tallest node (old flow had single-height cards)
        for n in nodes:
            if len(n[4]) > 25 and (n[4] not in best or (n[1] - n[0]) > (best[n[4]][1] - best[n[4]][0])):
                best[n[4]] = n
        titles = list(best.values())
        ages = [n for n in nodes if AGE_LINE.match(n[4])]
        sources = [n for n in nodes if SOURCE_LINE.match(n[4])]  # old single-node layout
        # Age-less RTE feed (domena2-prod 2026-09-09): source name WITHOUT time
        # Like/Share rows sit far below (~380 px). Accept a short source-name-ish
        # node just under the title as the pairing signal.
        srcnames = [n for n in nodes
                    if 0 < len(n[4]) <= 40 and n[4] not in ("Share", "See More")
                    and not AGE_LINE.match(n[4]) and not SOURCE_LINE.match(n[4])
                    and "Like" not in n[4]]
        durs = [n for n in nodes if VIDEO_BADGE.match(n[4]) and n[0] > 100]
        out = []
        for t in titles:
            if any(k in t[4] for k in SKIP_WORDS):
                continue
            has_source = (any(-40 < a[0] - t[0] < 200 for a in ages)         # ReDroid
                          or any(0 < s[0] - t[1] < 260 for s in sources)     # old layout
                          or any(0 < s[0] - t[0] < 120 and s[3] < t[3]       # age-less feed
                                 for s in srcnames))
            if not has_source:
                continue
            if any(0 < t[0] - v[1] < 400 for v in durs):
                continue  # video card
            cy = (t[0] + t[1]) // 2
            if any(a0 < cy < a1 for a0, a1 in ad_bands):
                continue  # ad card
            out.append((t[4], (t[2] + t[3]) // 2, cy))
        return out

    def feed_visible(self):
        """Feed confirmation. Old flow: one text node 'Source · time'. ReDroid dump
        (prod_2 2026-09-01) splits source and relative-time into separate nodes, so
        also accept a standalone relative-time like '15h ago' / '15 godz. temu'.
        domena2-prod 2026-09-09: the RTE feed can render articles with NO age node
        at all (fresh feed: 'Showbizz Daily' + '1k Like'/'Share'/'See More' rows
        only) — accept Like/Share/See More card anatomy as a feed signal too.
        Fallback needs ≥2 Like rows AND ≥2 long article titles: a single-article
        or social-post view shows the same widgets but only one card."""
        texts = [m.group(1) for m in
                 re.finditer(r'text="([^"]*)"', self.d.dump_hierarchy())]
        if any(SOURCE_LINE.match(t) or AGE_LINE.match(t) for t in texts):
            return True
        n_likes = sum(1 for t in texts if t.endswith("Like"))
        n_titles = sum(1 for t in texts if len(t) > 25)
        return n_likes >= 2 and n_titles >= 2

    def read_article(self, dwell):
        end = time.time() + dwell
        while time.time() < end:
            # old-flow swipe, proportionally converted (old x=540 was SCREEN CENTER of 1080)
            self.swipe(0.5, 0.625, 0.5, random.uniform(0.437, 0.521), "article-read", 0.2)
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

    # ------------------------------------------------------------ misc cards
    # Port of the web flow's misc cards + the streak check-in the web flow gets
    # from 'Read to earn'-style streaks (complete_misc_cards, rewards_tasks.py
    # :236-255). On the app's Rewards page (sapphire TemplateActivity WebView)
    # every earnable card is one content-desc node '<title>, <blurb>, earn N
    # points' — verified domena1-prod 2026-09-09: tapping its centre opens the
    # card's SERP/quiz in BrowserActivity, a dwell + back credits the points
    # (Daily points 55/75 -> 75/75) and the node loses the 'earn N points'
    # label, so pool exhaustion IS the web flow's card_is_complete check.
    # CRITICAL: back while focus is still TemplateActivity EXITS Rewards to the
    # browser home — only press back when the card actually left the page.
    CARD_BAND = (200, 1020)  # tap-safe y window (below chrome, above navbar)

    def _read_points(self, which):
        """Balance rows live only in the profile menu (authoritative,
        domena1-prod 2026-09-09: '97 Total points', '75/75 Daily points')."""
        if ACT_REWARDS in self.focus():
            self.press("back", "rewards-to-home")  # ONE back exits to home
            time.sleep(3)
        if not self.ensure_home():
            raise RuntimeError("home not reachable for balance read")
        self.tap(PROFILE_BUTTON, "profile-button-balance")
        time.sleep(4)
        xml = self.d.dump_hierarchy()
        m = which.search(xml)
        self.press("back", "leave-profile-menu")
        time.sleep(2)
        return m.group(1) if m else None

    def total_points(self):
        return self._read_points(TOTAL_POINTS)

    def daily_points(self):
        return self._read_points(DAILY_POINTS)

    def check_in(self):
        """Streak check-in (text node in the Streaks card; NOT clickable=true —
        raw coordinate click at its centre reaches the WebView handler).
        Success signal: Day-1 ring renders alt-text 'checked' (domena1-prod
        2026-09-09; the '0 day' label lags and stays after checking)."""
        xml = self.d.dump_hierarchy()
        if CHECKED_ICON.search(xml):
            log("check-in: already checked in today (checked icon present)")
            return "already"
        m = re.search(r'<node[^>]*text="' + CHECKIN_TEXT + r'"[^>]*bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"', xml)
        if not m:
            log("check-in: 'Check in' node not found — skipping")
            return "missing"
        x1, y1, x2, y2 = map(int, m.groups())
        self.tap(((x1 + x2) // 2, (y1 + y2) // 2), "check-in")
        time.sleep(4)
        ok = CHECKED_ICON.search(self.d.dump_hierarchy()) is not None
        log(f"check-in: {'confirmed' if ok else 'UNCONFIRMED (no checked icon)'}")
        return "ok" if ok else "unconfirmed"

    def _visible_activity_card(self, xml):
        for m in ACTIVITY_CARD.finditer(xml):
            title = m.group(1).split(",")[0].strip()
            x1, y1, x2, y2 = map(int, m.groups()[2:])
            cy = (y1 + y2) // 2
            if self.CARD_BAND[0] < cy < self.CARD_BAND[1]:
                return title, int(m.group(2)), (x1 + x2) // 2, cy
        return None

    def _quiz_flow(self, max_questions=6):
        """Copilot quiz in BrowserActivity (Rewards 'earn N points' card that is a
        quiz, e.g. Wizarding Creator, d3 2026-09-09 18:50). Answers do NOT need to
        be correct (user directive) — tap the first A-D option, advance via
        Next/View result until the terminal screen, then leave the tab.
        Options are clickable nodes carrying content-desc='A. …'; the advance
        buttons carry text='Next'/'View result' (separate nodes)."""
        opt = re.compile(r"^[A-D]\. ")
        adv = re.compile(r"^(Next|View result|Continue|Finish|Try again)$")
        for i in range(max_questions * 3):
            xml = self.d.dump_hierarchy()
            moved = False
            for m in re.finditer(
                    r'(?:content-desc|text)="([^"]*)"[^>]*clickable="true"[^>]*'
                    r'bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"', xml):
                t = m.group(1)
                if not (opt.match(t) or adv.match(t.strip())):
                    continue
                x1, y1, x2, y2 = map(int, m.groups()[1:])
                if x2 <= x1:
                    continue
                action("tap", f"quiz {'option' if opt.match(t) else 'advance'}: {t[:24]}")
                self.d.click((x1 + x2) // 2, (y1 + y2) // 2)
                time.sleep(5)
                moved = True
                break
            if not moved:
                # no options, no advance buttons: terminal screen (score view)
                if "poprawne" in xml or "Score" in xml or "Continue exploring" in xml:
                    log(f"quiz finished after {i} taps")
                    break
                self.press("back", "quiz-unknown-screen")
                time.sleep(3)
                break
        self.press("back", "leave-quiz")
        time.sleep(3)

    def misc_cards(self, max_cards=None):
        """Click every 'earn N points' card until the pool drains (scrolling
        re-reads each round; completed cards drop out of the pool)."""
        done, scrolls, attempted = [], 0, set()
        while scrolls < 25:
            if ACT_REWARDS not in self.focus():
                log("misc cards: left Rewards page unexpectedly — reopening")
                if not self.open_rewards():
                    break
            xml = self.d.dump_hierarchy()
            card = self._visible_activity_card(xml)
            if card is None:
                scrolls += 1
                self.scroll_feed()
                time.sleep(2.2)
                continue
            title, pts, cx, cy = card
            scrolls = 0
            if title in attempted:
                # pool card we already tried but that never left the pool:
                # scroll past it instead of clicking forever
                self.scroll_feed()
                time.sleep(2.2)
                scrolls += 1
                continue
            attempted.add(title)
            self.tap((cx, cy), f"activity-card:{title[:30]}")
            time.sleep(6)
            left = ACT_REWARDS not in self.focus()
            if left:
                if ACT_BROWSER in self.focus() and self.d(textMatches=r"^[A-D]\. ").exists:
                    self._quiz_flow()
                else:
                    self.shot(f"activity-opened-{len(done) + 1}")
                    self.read_article(random.uniform(5, 10))
                    self.press("back", "leave-activity")
                    time.sleep(3)
            # completion signal: a credited card loses its 'earn N points' desc
            # (domena1-prod 2026-09-09: after the +5/+10 credits the card left
            # the pool; a full walk then finds no more earnable cards).
            gone = not re.search(re.escape(title) + r"[^\"]*earn \d+ points",
                                 self.d.dump_hierarchy())
            done.append((title, pts, gone))
            log(f"[{len(done)}] card {title[:44]!r} +{pts} credited={gone}")
            if max_cards and len(done) >= max_cards:
                break
        return done
    # ------------------------------------------------------------- tab hygiene
    # Verbatim port of deploy/read_to_earn.py :48-108 (spec:
    # docs/superpowers/specs/2026-09-01-read-to-earn-port-spec.md §3).
    def open_tabs_manager(self):
        for _ in range(3):
            if self.d(description="Tabs").exists:
                action("tap", "tabs-button")
                self.d(description="Tabs").click()
                time.sleep(2.5)
                self.act_shot("tabs-manager")
                return True
            self.press("back", "find-tabs-button")
            time.sleep(2)
        return False

    def close_tabs(self, keep_feed, max_rounds=40):
        """Close tab-manager entries; keep_feed keeps tabs named 'Rewards…'."""
        closed = 0
        for _ in range(max_rounds):
            xml = self.d.dump_hierarchy()
            target = None
            for m in re.finditer(
                r'content-desc="Close tab: ([^"]*)"[^>]*bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"', xml
            ):
                name = m.group(1)
                if keep_feed is not None and name.startswith("Rewards"):
                    continue
                x1, y1, x2, y2 = map(int, m.groups()[1:])
                target = ((x1 + x2) // 2, (y1 + y2) // 2)
                action("tap", f"close-tab {name[:40]}")
                break
            if target is None:
                break
            self.d.click(*target)
            closed += 1
            self.act_shot(f"tab-closed-{closed}")
            time.sleep(1.5)
        return closed

    def switch_to_feed_tab(self):
        xml = self.d.dump_hierarchy()
        m = re.search(r'content-desc="Tab: Rewards"[^>]*bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"', xml)
        if not m:
            return False
        x1, y1, x2, y2 = map(int, m.groups())
        self.tap(((x1 + x2) // 2, (y1 + y2) // 2), "switch-feed-tab")
        time.sleep(5)
        return True

    def close_article_tab_return_to_feed(self):
        """Mature post-article path (defined in old flow; runtime used back-press)."""
        if not self.open_tabs_manager():
            return False
        self.close_tabs(keep_feed=True)
        if not self.switch_to_feed_tab():
            self.press("back", "leave-tab-manager")
            time.sleep(2)
            return False
        return True

    def cleanup_tabs(self):
        """End-of-run invariant (old flow): all browser tabs closed."""
        if not self.open_tabs_manager():
            log("tab manager unavailable — nothing to clean")
            return 0
        n = self.close_tabs(keep_feed=None)
        self.press("back", "leave-tab-manager")
        time.sleep(2)
        log(f"cleanup: closed {n} tabs")
        return n

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
            if ACT_HOME in self.focus() and self.d(resourceId=SEARCH_BOX).exists \
                    and self.d(resourceId=PROFILE_BUTTON).exists:
                self.shot("home-ready")
                return
            if ACT_CAMERA in self.focus():
                self.recover_camera()
            elif self.d(resourceId=SEARCH_BOX).exists:
                self.press("back", "feed-to-home")  # MSN feed view, not home
            else:
                self.relaunch()  # warm-resume (e.g. Rewards page) needs a cold start
            time.sleep(1)
        self.shot("home-timeout")
        raise RuntimeError(f"never reached home ({ACT_HOME}); focus={self.focus()}")

    def screenshot_step(self):
        name = self.shot("screenshot")  # shot() returns the file stem
        return {"state": "home", "articles_read": 0, "screenshot": name}

    def walk_rewards_path(self):
        """One session = one successful Read-to-earn click (old flow :155-167).
        Returns (state, opened); opened False is terminal: done/wall/unknown/no-feed."""
        if not self.open_rewards():
            self.shot("rewards-page-unexpected")
            log(f"WARNING: rewards page focus={self.activity()} (continuing anyway)")
        for attempt in range(3):
            state, card = self.rewards_state()
            self.shot(f"rewards-state-{state}-{attempt+1}")
            log(f"rewards state (attempt {attempt+1}): {state} card={card}")
            if state == "unrendered":
                # tile desc present, zero-size geometry: lazy WebView not laid
                # out yet — settle and retry within the same attempt budget
                log(f"attempt {attempt+1}: RTE tile unrendered — settling 8s")
                time.sleep(8)
                continue
            if state != "rte":
                return state, False
            # stale-bounds guard: the card coords from a stale dump may hit a
            # blank WebView (d3 2026-09-09 18:36). Re-check the tile is present
            # with real bounds right before tapping.
            fresh = self.rewards_state()
            if fresh[0] != "rte" or fresh[1] is None:
                log(f"attempt {attempt+1}: tile vanished on re-read — retrying")
                time.sleep(5)
                continue
            self.tap(fresh[1], "read-to-earn-card")
            time.sleep(8)
            self.shot("read-to-earn-feed")
            if self.feed_visible():
                return state, True
            log(f"attempt {attempt+1}: feed not visible after tap — retrying")
            time.sleep(5)
        log("click on Read to earn did not open the feed after 3 attempts — terminal")
        return "feed-not-opened", False

    def read_to_earn_flow(self, max_total=60, max_per_session=5, max_sessions=20):
        """Session model, 1:1 with old run() (:222-279): 5 articles/session, one
        RTE click = one session, seen-set global, idle cap 8, cleanup all tabs at end."""
        seen = set()
        total = sessions = 0
        state = "start"
        last_counter = None  # RTE tile (done, cap) at last session start
        try:
            while total < max_total and sessions < max_sessions:
                state, opened = self.walk_rewards_path()
                if opened:
                    # benefit-driven stop: the tile counter is read by the same
                    # rewards_state the walk just did — no extra navigation.
                    # Counter unchanged across a FULL session => nothing credited.
                    cur = self._rte_counter
                    if last_counter is not None and cur == last_counter:
                        log(f"Read to earn: tile counter {cur} unchanged after a "
                            f"full session (Δ=0) — no further benefit, stopping")
                        state = "no-benefit"
                        break
                    last_counter = cur
                if not opened:
                    if state == "wall":
                        log("LOGGED-OUT SIGN-IN WALL — Read-to-earn requires an account. "
                            "Stopping at wall with evidence.")
                    elif state == "done":
                        log("Read to earn already complete for today (terminal state).")
                    else:
                        log(f"Read to earn exhausted or unavailable ({state}) — terminal")
                    break
                sessions += 1
                read_in_session = idle_scrolls = 0
                while read_in_session < max_per_session and total < max_total:
                    cands = [c for c in self.candidate_articles() if c[0] not in seen]
                    if not cands:
                        idle_scrolls += 1
                        if idle_scrolls > 8:
                            log("no fresh articles left in this feed")
                            break
                        self.scroll_feed()
                        time.sleep(2)
                        continue
                    idle_scrolls = 0
                    title, cx, cy = random.choice(cands[:3])
                    seen.add(title)
                    self.tap((cx, cy), "article-card")
                    time.sleep(random.uniform(5, 7))
                    self.shot(f"session{sessions}-article-{total + 1}")
                    self.read_article(random.uniform(5, 10))
                    self.press("back", "leave-article")
                    time.sleep(random.uniform(3, 4.5))
                    read_in_session += 1
                    total += 1
                    log(f"[{total}] session {sessions} ({read_in_session}/{max_per_session}): {title[:55]}")
        finally:
            self.cleanup_tabs()
        return {"state": state, "articles_read": total, "sessions": sessions}

    def rewards_tail(self, iterations):
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

    def misc_cards_flow(self, max_cards=None):
        """check-in + drain the 'earn N points' pool, then tab cleanup and the
        authoritative balance readout (profile menu)."""
        try:
            daily_before = self.daily_points()
        except Exception as e:  # noqa: BLE001 — balance readout must not fail the run
            log(f"balance readout (before) failed: {type(e).__name__}: {e}")
            daily_before = None
        closed = 0
        try:
            if not self.open_rewards():
                self.shot("rewards-page-unexpected")
                log(f"WARNING: rewards page focus={self.activity()} (continuing anyway)")
            # check-in FIRST: rewards_state() scrolls hunting the RTE card and
            # the virtualised WebView then drops the Streaks card (top of page)
            # from the hierarchy — 'Check in' becomes invisible (domena2-prod
            # 2026-09-09: checkin=missing with the button never seen).
            ci = self.check_in()
            state, _ = self.rewards_state()
            if state == "wall":
                log("LOGGED-OUT SIGN-IN WALL — misc cards need an account (prod path).")
                return {"state": "wall", "articles_read": 0}
            cards = self.misc_cards(max_cards=max_cards)
        finally:
            # terminal invariant (AGENTS.md): the flow ALWAYS ends with every
            # browser tab closed — next run starts clean. Also fires on the
            # early `wall` return and on exceptions.
            closed = self.cleanup_tabs()
        try:
            daily_after = self.daily_points()
        except Exception as e:  # noqa: BLE001 — balance readout must not fail the run
            log(f"balance readout failed: {type(e).__name__}: {e}")
            daily_after = None
        credited = sum(pts for _, pts, gone in cards if gone)
        log(f"misc cards: {len(cards)} clicked, {credited} pts credited, "
            f"checkin={ci}, daily={daily_before}->{daily_after}, tabs_closed={closed}")
        return {"state": "misc_done", "articles_read": len(cards),
                "cards": [{"title": t, "pts": p, "credited": g} for t, p, g in cards],
                "checkin": ci, "points_credited": credited,
                "daily_points_after": daily_after}

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
        if only == "misc-cards":
            return self.misc_cards_flow()
        if only == "required-searches":
            return self.required_searches(count=iterations)
        if only == "daily":
            return self.daily_flow()  # tiles cap every stage internally
        # 'read-to-earn' = full session model (iterations = max_total articles);
        # 'rewards'/'full' keep the flat evidence loop. 'full' searches first
        # (the original proven sequence).
        if only == "read-to-earn":
            return self.read_to_earn_flow(max_total=iterations)
        if only == "full":
            serp = self.search_and_results()
            log(f"search results BrowserActivity opened: {serp}")
            if not self.ensure_home():
                raise RuntimeError("home not reachable after search")
        return self.rewards_tail(iterations)


    # ---- tile-driven daily state machine (d3, 2026-09-09) -------------------
    # Every stage is driven by a Rewards TILE state, not a fixed counter. The
    # driver re-reads the Rewards page each round and acts ONLY on tiles whose
    # done-signal is absent (user directive: recognize "tile needs nothing").
    # Live desc formats (d3 2026-09-09 inventory, note the ", , " double comma):
    #   Search to earn, , 0 out of 15 points earned   -> active, done 0/15
    #   Read to earn, , 0 out of 30 points earned     -> active, done 0/30
    #   Search to earn, , 15 points earned            -> done (no 'out of')
    TILE_SEARCH = re.compile(r'content-desc="Search to earn, , (\d+) out of (\d+)')
    TILE_RTE = re.compile(r'content-desc="Read to earn, , (\d+) out of (\d+)')
    TILE_SEARCH_DONE = re.compile(r'content-desc="Search to earn, , (\d+) points earned"')
    TILE_RTE_DONE = re.compile(r'content-desc="Read to earn, , (\d+) points earned"')

    def read_tiles(self):
        """Tile snapshot from the CURRENT hierarchy. rendered=False when the
        lazy WebView shows no balance rows — a blank render is NEVER terminal."""
        xml = self.d.dump_hierarchy()
        rendered = TOTAL_POINTS.search(xml) is not None or DAILY_POINTS.search(xml) is not None
        t = {"search": None, "rte": None, "cards": 0, "checkin": False,
             "rendered": rendered}
        m = self.TILE_SEARCH.search(xml) or self.TILE_SEARCH_DONE.search(xml)
        if m:
            if "out of" in m.group(0):
                t["search"] = (int(m.group(1)), int(m.group(2)))
            else:
                v = int(m.group(1)); t["search"] = (v, v)
        m = self.TILE_RTE.search(xml)
        if m:
            t["rte"] = (int(m.group(1)), int(m.group(2)))
        t["cards"] = len(ACTIVITY_CARD.findall(xml))
        t["checkin"] = CHECKED_ICON.search(xml) is None and \
            ('text="' + CHECKIN_TEXT + '"') in xml
        return t
    def all_terminal(self, tiles):
        """True ONLY on a rendered page where every tile shows its done-signal."""
        if not tiles.get("rendered"):
            return False
        search_done = tiles["search"] is None or tiles["search"][0] >= tiles["search"][1]
        rte_done = tiles["rte"] is None or tiles["rte"][0] >= tiles["rte"][1]
        return search_done and rte_done and tiles["cards"] == 0 and not tiles["checkin"]

    def daily_flow(self, rte_max=60, search_safety_cap=10, max_rounds=6):
        """Tile-driven daily chain: loop { read tiles -> act ONLY on active tiles
        -> re-read balance }. Stage order per round (cheapest-first): check-in ->
        pool cards -> read-to-earn -> searches (search LAST: 15 pts = 5 SERPs;
        d3 2026-09-09: 3 SERP = +9 pts CONFIRMED on fresh account). A full round
        with zero point delta = saturated account -> stop regardless of tiles."""
        def _points():
            try:
                return self.daily_points()
            except Exception as e:  # noqa: BLE001
                log(f"daily_points readout failed: {type(e).__name__}: {e}")
                return None

        results = {"rounds": []}
        p0 = _points()
        log(f"daily: start daily_points={p0}")
        prev_points = p0
        for rnd in range(1, max_rounds + 1):
            if not self.open_rewards():
                self.shot("rewards-page-unexpected")
                log(f"round {rnd}: rewards page unreachable — stopping")
                break
            tiles = self.read_tiles()
            log(f"round {rnd}: tiles={tiles}")
            if self.all_terminal(tiles):
                log(f"round {rnd}: ALL TILES TERMINAL — done")
                break
            rr = {}
            if tiles["checkin"]:
                rr["checkin"] = self.check_in()
            if tiles["cards"]:
                rr["cards"] = self.misc_cards()
            if tiles["rte"] and tiles["rte"][0] < tiles["rte"][1]:
                rr["rte"] = self.read_to_earn_flow(
                    max_total=min(rte_max, tiles["rte"][1] - tiles["rte"][0]))
            if tiles["search"] and tiles["search"][0] < tiles["search"][1]:
                cap = min(search_safety_cap, tiles["search"][1] - tiles["search"][0])
                rr["searches"] = self.required_searches(count=max(1, cap // 3))
            results["rounds"].append(rr)
            pts = _points()
            log(f"round {rnd}: points {prev_points} -> {pts}")
            if pts is not None and pts == prev_points and rnd > 1:
                log(f"round {rnd}: ZERO delta across the round — saturated, stopping")
                break
            prev_points = pts
        p1 = _points()
        results["daily_points"] = {"start": p0, "end": p1}
        log(f"daily: end daily_points={p0}->{p1}")
        return {"state": "daily_done", "articles_read":
                sum(r.get("rte", {}).get("articles_read", 0)
                    for r in results["rounds"] if isinstance(r, dict)), **results}

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
                   choices=("full", "search", "rewards", "read-to-earn", "misc-cards",
                            "required-searches", "daily", "screenshot"))
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
