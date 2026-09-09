# -*- coding: utf-8 -*-
"""domena3-prod tile inventory — the Rewards-page source-of-truth walk.

Run AFTER owner login, via tunnel: python tools/d3_tile_inventory.py
Read-only: dumps every visible Rewards tile (content-desc/text/bounds/class),
clicks NOTHING. Output: artifacts/domena3-prod/ui/tile-inventory-*.json + log.

Purpose (user directive): the d3 daily flow must be driven by TILE STATE —
every stage exists only while its tile offers points; the driver must recognize
"tile needs nothing" and skip. This script harvests the raw tile universe the
flow-state machine will be built from.
"""
import json, os, re, sys, time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
from bing_mobile_flow import BingMobileFlow  # noqa: E402

SERIAL = "127.0.0.1:15555"
PROFILE = "domena3-prod"
SCROLLS = 12          # walk depth down the Rewards page
SETTLE = 2.2          # after each scroll

NODE = re.compile(
    r'<node[^>]*?'
    r'(?:content-desc="([^"]*)")?[^>]*?'
    r'text="([^"]*)"[^>]*?'
    r'resource-id="([^"]*)"[^>]*?'
    r'class="([^"]*)"[^>]*?'
    r'bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"', re.S)

def classify(desc, text):
    """Tile-type hypothesis per known d2 contracts — to VERIFY on d3."""
    blob = (desc or "") + " " + (text or "")
    if re.search(r"earn \d+ points", blob, re.I):
        return "earn-card"            # misc pool card (d2 §1: desc loses suffix when done)
    if "read to earn" in blob.lower():
        return "rte"                  # 'N out of M points earned' = active; no 'out of' = done
    if re.match(r"check ?in", blob, re.I) or "checked" == (text or "").lower():
        return "checkin"
    if re.search(r"total points|daily points", blob, re.I):
        return "balance"
    if re.search(r"quiz|puzzle|poll|this or that", blob, re.I):
        return "quiz-like"
    return None

def nodes(xml):
    out = []
    for m in NODE.finditer(xml):
        desc, text, rid, cls = m.group(1), m.group(2), m.group(3), m.group(4)
        x1, y1, x2, y2 = map(int, m.groups()[4:])
        if not desc and not text:
            continue
        kind = classify(desc, text)
        out.append({
            "type": kind, "desc": desc, "text": text, "rid": rid, "class": cls,
            "cx": (x1 + x2) // 2, "cy": (y1 + y2) // 2, "y1": y1,
        })
    return out

def main():
    flow = BingMobileFlow(SERIAL, debug=False, profile=PROFILE)
    flow.to_home()
    if not flow.open_rewards():
        raise SystemExit("rewards page did not open — login likely missing (wall?)")
    inventory, seen = [], set()
    for i in range(SCROLLS):
        xml = flow.d.dump_hierarchy()
        found = nodes(xml)
        new = [n for n in found if (n["desc"] or n["text"]) not in seen]
        for n in new:
            seen.add(n["desc"] or n["text"])
        inventory.extend(new)
        flow.shot(f"tile-walk-{i+1}")
        if i < SCROLLS - 1:
            flow.scroll_feed(0.4)
            time.sleep(SETTLE)
    tiles = [n for n in inventory if n["type"]]
    out = {
        "profile": PROFILE, "when": time.strftime("%Y-%m-%d %H:%M:%S"),
        "total_nodes": len(inventory), "typed_tiles": tiles,
        "balance": {t: n["text"] for t in ("balance",) for n in inventory if n["type"] == "balance"},
    }
    path = os.path.join(flow.ui_dir, "tile-inventory.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print(f"tiles: {len(tiles)} (total nodes {len(inventory)}) -> {path}")
    for t in tiles:
        print(f"  [{t['type']:8s}] {t['desc'] or t['text']}"[:110])

if __name__ == "__main__":
    main()
