"""Full Rewards-tab crawl: open Rewards, scroll to bottom in steps, collect EVERY
node (text/content-desc/bounds/clickable) at each viewport, dedupe by desc.

Read-only observation: taps NOTHING (except navigation to Rewards).
Output: artifacts/<profile>/ui/crawl-<ts>.json + per-step XML. Run on server via hub.
"""
import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
from bing_mobile_flow import BingMobileFlow, log  # noqa: E402


def nodes(xml):
    """All <node> attrs with text or content-desc, plus clickable/bounds."""
    out = []
    for m in re.finditer(r"<node\b([^>]*)/?>", xml):
        a = m.group(1)

        def g(k, _a=a):
            mm = re.search(k + r'="([^"]*)"', _a)
            return mm.group(1) if mm else ""

        text, desc = g("text"), g("content-desc")
        if not (text or desc):
            continue
        out.append({"text": text, "desc": desc, "bounds": g("bounds"),
                    "clickable": g("clickable"), "resource-id": g("resource-id"),
                    "class": g("class")})
    return out


def main():
    serial = sys.argv[1] if len(sys.argv) > 1 else "127.0.0.1:5555"
    profile = sys.argv[2] if len(sys.argv) > 2 else "domena3-prod"
    steps = int(sys.argv[3]) if len(sys.argv) > 3 else 14

    f = BingMobileFlow(serial, debug=False, profile=profile)
    f.ensure_home()
    if not f.open_rewards():
        log("WARNING: rewards focus unexpected")
    # settle the lazy WebView, then settle wait
    f.swipe(0.5, 0.75, 0.5, 0.45, "settle")
    time.sleep(2)

    seen = {}
    order = []
    prev_keys = None
    for i in range(steps):
        xml = f.d.dump_hierarchy()
        step_nodes = nodes(xml)
        keys = set()
        for n in step_nodes:
            key = (n["desc"] or n["text"])[:160]
            keys.add(key)
            if key not in seen:
                n["_step"] = i
                seen[key] = n
                order.append(key)
        with open(os.path.join(f.ui_dir, f"crawl-step-{i:02d}.xml"), "w", encoding="utf-8") as fh:
            fh.write(xml)
        if keys == prev_keys:
            log(f"step {i}: viewport unchanged — bottom reached")
            break
        prev_keys = keys
        f.swipe(0.5, 0.78, 0.5, 0.28, "crawl")
        time.sleep(2.0)

    ts = time.strftime("%Y%m%d-%H%M%S")
    out = os.path.join(f.ui_dir, f"crawl-{ts}.json")
    with open(out, "w", encoding="utf-8") as fh:
        json.dump({"profile": profile, "steps": steps,
                   "entries": [seen[k] for k in order]}, fh, ensure_ascii=False, indent=1)
    log(f"CRAWL-DONE unique={len(order)} -> {out}")
    for k in order:
        n = seen[k]
        d = (n["desc"] or n["text"])[:120].replace("\n", " ")
        log(f"ENT|{d}|click={n['clickable']}|{n['bounds']}")


if __name__ == "__main__":
    main()
