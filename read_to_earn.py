"""Bing mobile 'Read to earn' automation (uiautomator2) — independent of the Linux server.

Behavior:
- Path per run: bottom-right 'Apps' icon -> 'Rewards' menu entry -> 'Read to earn' card
  (clickable card with desc 'Read to earn, , N out of 30 points earned'). Text-only
  'Read to earn, N points earned' (no clickable card) = task DONE -> terminal state.
- One session = one successful Read-to-earn click; up to 5 unique articles per session,
  never re-clicking an article across all sessions. Videos (duration badge 'm:ss')
  and ad cards ('. Ad,') are skipped.
- End of flow (Read to earn exhausted): ALL browser tabs are closed -> zero open tabs.

Usage: python read_to_earn.py [adb-serial]
Requires: pip install uiautomator2; Android emulator/device with Bing app signed in;
`python -m uiautomator2 init` once per device.
"""
import random
import re
import sys
import time

import uiautomator2 as u2

PKG = "com.microsoft.bing"
VIDEO_BADGE = re.compile(r"^\d+:\d\d$")
SOURCE_LINE = re.compile(r"^.+\s·\s.+$")
SKIP_WORDS = ("Oferta", "Koszula", "Regatta", "Search", "Rewards", "Image Creator", "Trending")


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def dump_texts(xml):
    nodes = []
    for m in re.finditer(
        r'<node[^>]*?text="([^"]*)"[^>]*?bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"[^>]*?>', xml
    ):
        t = m.group(1)
        x1, y1, x2, y2 = map(int, m.groups()[1:])
        if t:
            nodes.append((y1, y2, x1, x2, t))
    nodes.sort()
    return nodes


# ---------------------------------------------------------------- tab management

def open_tabs_manager(d):
    for _ in range(3):
        if d(description="Tabs").exists:
            d(description="Tabs").click()
            time.sleep(2.5)
            return
        d.press("back")
        time.sleep(2)
    raise RuntimeError("cannot open tab manager")


def close_tabs(d, keep_feed, max_rounds=40):
    """In tab manager, close tabs whose name fails keep_feed (keep_feed=None closes all)."""
    closed = 0
    for _ in range(max_rounds):
        xml = d.dump_hierarchy()
        target = None
        for m in re.finditer(
            r'content-desc="Close tab: ([^"]*)"[^>]*bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"', xml
        ):
            name = m.group(1)
            if keep_feed is not None and name.startswith("Rewards"):
                continue
            x1, y1, x2, y2 = map(int, m.groups()[1:])
            target = ((x1 + x2) // 2, (y1 + y2) // 2)
            break
        if target is None:
            break
        d.click(*target)
        closed += 1
        time.sleep(1.5)
    return closed


def switch_to_feed_tab(d):
    xml = d.dump_hierarchy()
    m = re.search(r'content-desc="Tab: Rewards"[^>]*bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"', xml)
    if not m:
        return False
    x1, y1, x2, y2 = map(int, m.groups())
    d.click((x1 + x2) // 2, (y1 + y2) // 2)
    time.sleep(5)
    return True

def close_article_tab_return_to_feed(d):
    """Close the just-read article tab, switch back to the feed tab. True if switched."""
    open_tabs_manager(d)
    close_tabs(d, keep_feed=True)
    switched = switch_to_feed_tab(d)
    if not switched:
        d.press("back")
        time.sleep(2)
    return switched


def cleanup_tabs(d):
    open_tabs_manager(d)
    n = close_tabs(d, keep_feed=None)
    d.press("back")
    time.sleep(2)
    return n


# ---------------------------------------------------------------- rewards path

RTE_ACTIVE = re.compile(
    r'content-desc="Read to earn, , \d+ out of \d+ points earned"'
    r'[^>]*bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"'
)
RTE_DONE_TEXT = re.compile(r'text="Read to earn, \d+ points earned"')


def find_read_to_earn(d, max_scrolls=10):
    """Scroll the Rewards page; return card center IF the ACTIVE (clickable) card exists.
    Returns ('done', None) marker via (None, 'done') when only the done text is visible."""
    for _ in range(max_scrolls):
        xml = d.dump_hierarchy()
        m = RTE_ACTIVE.search(xml)
        if m:
            x1, y1, x2, y2 = map(int, m.groups())
            return (x1 + x2) // 2, (y1 + y2) // 2
        if RTE_DONE_TEXT.search(xml):
            return None  # terminal: task complete
        d.swipe(540, 1800, 540, 700)
        time.sleep(2)
    return None


def feed_visible(d):
    return any(SOURCE_LINE.match(n[4]) for n in dump_texts(d.dump_hierarchy()))


def open_rewards_page(d):
    """app_start -> bottom-right 'Apps' icon -> 'Rewards' menu entry."""
    d.app_start(PKG)
    time.sleep(6)
    xml = d.dump_hierarchy()
    m = re.search(
        r'content-desc="Apps"[^>]*bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"', xml)
    if not m:
        log("'Apps' bottom icon not found")
        return False
    x1, y1, x2, y2 = map(int, m.groups())
    d.click((x1 + x2) // 2, (y1 + y2) // 2)
    time.sleep(4)
    xml = d.dump_hierarchy()
    m = re.search(
        r'text="Rewards"[^>]*bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"', xml)
    if not m:
        log("'Rewards' entry not found in Apps menu")
        return False
    x1, y1, x2, y2 = map(int, m.groups())
    d.click((x1 + x2) // 2, (y1 + y2) // 2)
    time.sleep(8)
    return True


def walk_rewards_path(d):
    """Open Rewards page -> click ACTIVE 'Read to earn' -> verify article feed opened.
    Returns True (feed opened), False (feed did not open — terminal or transient)."""
    if not open_rewards_page(d):
        return False
    card = find_read_to_earn(d)
    if card is None:
        log("Read to earn not clickable (task done or not found)")
        return False
    d.click(*card)
    time.sleep(8)
    if feed_visible(d):
        return True
    log("click on Read to earn did not open the feed")
    return False




# ---------------------------------------------------------------- feed parsing

def candidate_articles(d):
    """Article cards as (title, cx, cy); skips videos and ads."""
    xml = d.dump_hierarchy()
    nodes = dump_texts(xml)
    descs = re.findall(
        r'content-desc="([^"]*)"[^>]*bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"', xml
    )
    ad_bands = [(int(y1) - 350, int(y2) + 350) for s, x1, y1, x2, y2 in descs
                if ". Ad," in s or s.startswith("Ad, ")]
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


def read_article(d, dwell):
    end = time.time() + dwell
    while time.time() < end:
        d.swipe(540, 1500, 540, random.randint(1050, 1250), 0.2)
        time.sleep(random.uniform(1.2, 2.0))


# ---------------------------------------------------------------- main loop

def run(serial="emulator-5554", min_dwell=5, max_dwell=10,
        max_sessions=20, max_total=60, max_per_session=5):
    """Run until 'Read to earn' stops opening the article feed.

    Session model (per user rules):
    - One session = one successful click on 'Read to earn'; within a session read up to
      max_per_session fresh articles (never the same article twice, across ALL sessions).
    - Article tabs stay open during sessions; all tabs are closed only at the end,
      when 'Read to earn' no longer opens the feed (or caps hit).
    """
    d = u2.connect(serial)
    d.implicitly_wait(5)

    seen = set()          # titles ever read — never re-click
    total = sessions = 0
    while total < max_total and sessions < max_sessions:
        sessions += 1
        log(f"--- session {sessions}: walking Rewards -> Read to earn")
        if not walk_rewards_path(d):
            log("Read to earn exhausted or unavailable — terminal state")
            break

        read_in_session = 0
        idle_scrolls = 0
        while read_in_session < max_per_session and total < max_total:
            cands = [c for c in candidate_articles(d) if c[0] not in seen]
            if not cands:
                idle_scrolls += 1
                if idle_scrolls > 8:
                    log("no fresh articles left in this feed")
                    break
                d.swipe(540, 1600, 540, 700)
                time.sleep(2)
                continue
            idle_scrolls = 0

            title, cx, cy = random.choice(cands[:3])
            seen.add(title)
            d.click(cx, cy)
            time.sleep(random.uniform(5, 7))
            read_article(d, random.uniform(min_dwell, max_dwell))
            d.press("back")
            time.sleep(random.uniform(3, 4.5))
            read_in_session += 1
            total += 1
            log(f"[{total}] session {sessions} ({read_in_session}/{max_per_session}): {title[:55]}")

    n = cleanup_tabs(d)
    log(f"cleanup: closed {n} tabs; sessions={sessions}, articles={total}")
    return total


if __name__ == "__main__":
    serial = sys.argv[1] if len(sys.argv) > 1 else "emulator-5554"
    run(serial)

