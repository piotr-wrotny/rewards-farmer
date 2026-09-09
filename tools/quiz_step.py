"""One quiz step on the CURRENT screen (no navigation): dump -> if pattern arg given,
tap the first clickable node matching it -> dump screen after. Read questions from
AFTER lines, answer with the next call.

Usage: python tools/quiz_step.py <serial> <profile> [answer-pattern]
"""
import os
import re
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
import uiautomator2 as u2  # noqa: E402
from bing_mobile_flow import log, profile_dirs  # noqa: E402
from rewards_full_crawl import nodes  # noqa: E402

B = re.compile(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]")


def show(d, ui, tag):
    xml = d.dump_hierarchy()
    with open(os.path.join(ui, f"quiz-{tag}.xml"), "w", encoding="utf-8") as fh:
        fh.write(xml)
    for n in nodes(xml):
        dd = (n["desc"] or n["text"])[:140].replace("\n", " ")
        log(f"AFTER|{dd}|click={n['clickable']}|{n['bounds']}")
    return xml


def main():
    serial, profile = sys.argv[1], sys.argv[2]
    pattern = sys.argv[3] if len(sys.argv) > 3 else None
    _, ui = profile_dirs(profile)
    d = u2.connect(serial)
    d.implicitly_wait(5)
    if not pattern:
        show(d, ui, "view")
        return 0
    xml = d.dump_hierarchy()
    rx = re.compile(pattern, re.IGNORECASE)
    for n in nodes(xml):
        if n["clickable"] == "true" and rx.search(n["desc"] or n["text"]):
            m = B.search(n["bounds"])
            if not m:
                continue
            x1, y1, x2, y2 = map(int, m.groups())
            if x2 <= x1:
                continue
            log(f"TAP {(n['desc'] or n['text'])[:80]} @ {(x1+x2)//2},{(y1+y2)//2}")
            d.click((x1 + x2) // 2, (y1 + y2) // 2)
            time.sleep(5)
            show(d, ui, "after-tap")
            return 0
    log("STEP-RESULT no-matching-clickable")
    show(d, ui, "nomatch")
    return 2


if __name__ == "__main__":
    sys.exit(main())
