"""Atomic Rewards-tab action: find node by content-desc pattern (scrolling down to
it if needed), tap its REAL bounds from the SAME dump, dump+print the result screen.

Usage: python tools/rewards_act.py <serial> <profile> <desc-pattern> [--no-scroll]
Observation-first: after tap prints focus + every text/desc node of new screen.
"""
import os
import re
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
from bing_mobile_flow import BingMobileFlow, log  # noqa: E402
from rewards_full_crawl import nodes  # noqa: E402

B = re.compile(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]")


def main():
    serial, profile, pattern = sys.argv[1], sys.argv[2], sys.argv[3]
    no_scroll = "--no-scroll" in sys.argv
    f = BingMobileFlow(serial, debug=False, profile=profile)
    f.ensure_home()
    if not f.open_rewards():
        log("WARNING: rewards focus unexpected")
    f.swipe(0.5, 0.75, 0.5, 0.45, "settle")
    time.sleep(2)

    rx = re.compile(pattern, re.IGNORECASE)
    target = None
    max_scroll = 1 if no_scroll else 10
    for i in range(max_scroll):
        xml = f.d.dump_hierarchy()
        for n in nodes(xml):
            if rx.search(n["desc"] or n["text"]):
                m = B.search(n["bounds"])
                if m and int(m.group(3)) > int(m.group(1)):  # real bounds
                    target = tuple(int(g) for g in m.groups())
                    log(f"FOUND step {i}: {(n['desc'] or n['text'])[:100]} {n['bounds']} clickable={n['clickable']}")
                    break
        if target:
            break
        f.swipe(0.5, 0.78, 0.5, 0.28, "seek")
        time.sleep(2)
    if not target:
        log("ACT-RESULT not-found (or zero bounds on every viewport)")
        return 2

    x1, y1, x2, y2 = target
    f.d.click((x1 + x2) // 2, (y1 + y2) // 2)
    time.sleep(8)
    name = f.shot(f"act-{pattern[:20]}")
    xml = f.d.dump_hierarchy()
    with open(os.path.join(f.ui_dir, name + "-after.xml"), "w", encoding="utf-8") as fh:
        fh.write(xml)
    log(f"FOCUS {f.focus()}")
    for n in nodes(xml):
        d = (n["desc"] or n["text"])[:130].replace("\n", " ")
        log(f"AFTER|{d}|click={n['clickable']}|{n['bounds']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
