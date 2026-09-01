
"""Bing mobile 'Read to earn' automation — uiautomator2, independent of the Linux server.

Flow:
 1. Launch Bing, open Rewards (chip on home feed or menu), find 'Read to earn' card.
 2. Open article feed, then 10x: pick a fresh non-video, non-ad article card,
    open it, scroll naturally for 5-10 s, press back.
Skips: video cards (duration badge 'm:ss' above title), ads (content-desc contains '. Ad,').
"""
import re, random, sys, time
import uiautomator2 as u2

VIDEO_BADGE = re.compile(r'^\d+:\d\d$')
SOURCE_LINE = re.compile(r'^.+\s·\s.+')
SKIP_WORDS = ("Oferta", "Koszula", "Regatta", "Search", "Rewards", "Image Creator", "Trending")

def dump_nodes(d):
    xml = d.dump_hierarchy()
    nodes = []
    for m in re.finditer(r'<node[^>]*?text="([^"]*)"[^>]*?bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"[^>]*?>', xml):
        t = m.group(1); x1, y1, x2, y2 = map(int, m.groups()[1:])
        if t: nodes.append((y1, y2, x1, x2, t))
    nodes.sort()
    descs = re.findall(r'content-desc="([^"]*)"', xml)
    return nodes, descs

def find_read_to_earn_card(d):
    for _ in range(8):
        xml = d.dump_hierarchy()
        m = re.search(r'content-desc="(Read to earn[^"]*)"[^>]*bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"', xml)
        if m and m.group(1):
            return (int(m.group(2))+int(m.group(4)))//2, (int(m.group(3))+int(m.group(5)))//2
        el = d(textContains="Read to earn")
        if el.exists:
            b = el.info["bounds"]
            return (b["left"]+b["right"])//2, (b["top"]+b["bottom"])//2
        d.swipe(540, 1800, 540, 700); time.sleep(2)
    return None

def open_read_to_earn(d):
    d.app_start("com.microsoft.bing")
    time.sleep(6)
    # path A: Rewards chip on home feed
    chip = d(text="Rewards")
    if chip.exists:
        chip.click(); time.sleep(6)
    card = find_read_to_earn_card(d)
    if card is None:
        # path B: back out to menu -> Rewards
        d.press("back"); time.sleep(2)
        menu = d(text="Microsoft Rewards")
        if menu.exists:
            menu.click(); time.sleep(6)
            card = find_read_to_earn_card(d)
    if card is None:
        raise RuntimeError("Read to earn card not found")
    d.click(*card)
    time.sleep(8)  # feed load

def candidate_articles(d):
    nodes, descs = dump_nodes(d)
    ad_ys = []
    for s in descs:
        if ". Ad," in s or s.startswith("Ad,"):
            m = re.search(r'bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"', s)
            if m:
                ad_ys.append((int(m.group(2)), int(m.group(4))))
    titles = [n for n in nodes if len(n[4]) > 25]
    sources = [n for n in nodes if SOURCE_LINE.match(n[4])]
    durs = [n for n in nodes if VIDEO_BADGE.match(n[4])]
    out = []
    for t in titles:
        if any(k in t[4] for k in SKIP_WORDS): continue
        # source line below title within card band
        src = next((s for s in sources if 0 < s[0]-t[1] < 260), None)
        if src is None: continue
        # video badge above title within card
        if any(0 < t[0]-v[1] < 400 and v[4] != time.strftime("%H:%M") for v in durs): continue
        # ad card overlap
        cy = (t[0]+t[1])//2
        if any(a0-350 < cy < a1+350 for a0, a1 in ad_ys): continue
        out.append(t[4])
    return out

def read_article(d, dwell):
    end = time.time()+dwell
    while time.time() < end:
        d.swipe(540, 1500, 540, random.randint(1050, 1250), 0.2)
        time.sleep(random.uniform(1.2, 2.0))

def run(iterations=10, serial="emulator-5554"):
    d = u2.connect(serial)
    open_read_to_earn(d)
    opened, done = set(), 0
    scrolls = 0
    while done < iterations and scrolls < 60:
        cands = [c for c in candidate_articles(d) if c not in opened]
        if not cands:
            d.swipe(540, 1600, 540, 700); scrolls += 1; time.sleep(2)
            continue
        title = random.choice(cands[:3])
        opened.add(title)
        el = d(textContains=title[:28])
        if not el.exists:
            continue
        el.click(); time.sleep(random.uniform(5, 7))
        read_article(d, random.uniform(5, 10))
        d.press("back"); time.sleep(random.uniform(3, 4.5))
        done += 1
        print(f"[{done}/{iterations}] {title[:60]}", flush=True)
    if done < iterations:
        raise RuntimeError(f"only {done}/{iterations} articles read")
    return done

if __name__ == "__main__":
    iters = int(sys.argv[1]) if len(sys.argv) > 1 else 10
    run(iters)
