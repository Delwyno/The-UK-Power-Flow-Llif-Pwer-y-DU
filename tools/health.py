#!/usr/bin/env python3
"""How fresh is each dataset? Writes data/health.json, which the app shows under Layers > Data freshness.

A dataset counts as "updated" when its content changes (not when its file is touched), so this works
the same in a fresh checkout. data/health.json remembers when each content hash was first seen.
Status: ok (within its expected interval), late (up to twice the interval), stale (beyond that).
With --issue-file PATH it also writes a short report when anything is stale, for the workflow to turn
into a GitHub issue; the file is removed when everything is healthy.
"""
import hashlib, json, os, sys, urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
OUT = DATA / "health.json"
REPO = os.environ.get("GITHUB_REPOSITORY", "delwyno/UK-Energy-Generation-Map")
LIVE_URL = f"https://raw.githubusercontent.com/{REPO}/live-data/today.json"
# key, English label, Welsh label, files, hours between expected updates
ITEMS = [
    ("snapshot", "Live snapshot (offline copy)", "Ciplun byw (copi all-lein)", ["snapshot.json"], 30),
    ("curtail", "Wind turn-down tracker", "Traciwr troi gwynt i lawr", ["curtail.json"], 36),
    ("stations", "Station history", "Hanes gorsafoedd", ["stations.json"], 36),
    ("costs", "Wind and gas costs", "Costau gwynt a nwy", ["costs.json"], 36),
    ("digest", "Weekly digest", "Crynodeb wythnosol", ["digest.json"], 8 * 24),
    ("accuracy", "Forecast accuracy", "Cywirdeb y rhagolygon", ["accuracy.json"], 36),
    ("daily", "Daily carbon and Wales figures", "Ffigurau carbon a Chymru dyddiol", ["daily.json"], 36),
    ("history", "Carbon history and records", "Hanes carbon a recordiau", ["history.json"], 36),
    ("sim", "2030 simulator data", "Data’r efelychydd 2030", ["sim.json"], 48),
    ("queue", "Connection queue", "Ciw cysylltu", ["queue.json"], 36),
    ("constraints", "NESO constraint costs", "Costau cyfyngiadau NESO", ["constraints.json"], 10 * 24),
    ("osm", "Grid, substations and routes (OpenStreetMap)", "Grid, is-orsafoedd a llwybrau (OpenStreetMap)", ["gridlines.json", "subs.json", "plants.json", "windareas.json", "routes.json"], 45 * 24),
    ("open", "Open data files", "Ffeiliau data agored", ["open/index.json"], 36),
]
LIVE = ("live", "Live running totals (every 30 minutes)", "Cyfansymiau byw (bob 30 munud)", None, 3)

def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ")

def parse(s):
    return datetime.strptime(s, "%Y-%m-%dT%H:%MZ").replace(tzinfo=timezone.utc)

def digest(files):
    h, found = hashlib.sha1(), 0
    for f in files:
        p = DATA / f
        if p.exists():
            h.update(p.read_bytes()); found += 1
        else:
            h.update(b"missing:" + f.encode())
    return ("missing" if found == 0 else h.hexdigest()), found

def status(age_h, limit):
    return "ok" if age_h <= limit else "late" if age_h <= 2 * limit else "stale"

def main():
    now = datetime.now(timezone.utc)
    try:
        seen = json.loads(OUT.read_text()).get("seen", {})
    except Exception:
        seen = {}
    items, new_seen = [], {}
    for key, en, cy, files, limit in ITEMS:
        sha, found = digest(files)
        prev = seen.get(key)
        changed = prev["changed"] if prev and prev["sha"] == sha else now_iso()
        new_seen[key] = {"sha": sha, "changed": changed}
        age = (now - parse(changed)).total_seconds() / 3600
        items.append({"key": key, "label": {"en": en, "cy": cy}, "changed": changed, "limit_h": limit, "status": status(age, limit), "missing": found == 0})
    # live running totals: read from the live-data branch (not part of this checkout)
    key, en, cy, _, limit = LIVE
    try:
        with urllib.request.urlopen(urllib.request.Request(LIVE_URL, headers={"User-Agent": "uk-power-map/1.0"}), timeout=30) as r:
            upd = json.load(r)["updated"]
        age = (now - parse(upd)).total_seconds() / 3600
        items.append({"key": key, "label": {"en": en, "cy": cy}, "changed": upd, "limit_h": limit, "status": status(age, limit), "missing": False})
    except Exception:
        items.append({"key": key, "label": {"en": en, "cy": cy}, "changed": None, "limit_h": limit, "status": "waiting", "missing": True})
    bad = [i for i in items if i["status"] == "stale"]
    doc = {"updated": now_iso(), "overall": "stale" if bad else "late" if any(i["status"] == "late" for i in items) else "ok", "items": items, "seen": new_seen}
    OUT.write_text(json.dumps(doc, separators=(",", ":"), ensure_ascii=False))
    print("data health:", doc["overall"], "|", ", ".join(f"{i['key']}={i['status']}" for i in items))
    if "--issue-file" in sys.argv:
        path = Path(sys.argv[sys.argv.index("--issue-file") + 1])
        if bad:
            lines = ["These datasets have not updated for more than twice their expected interval:", ""]
            for i in bad:
                age = (now - parse(i["changed"])).total_seconds() / 3600 if i["changed"] else 0
                lines.append(f"- **{i['label']['en']}** (`{i['key']}`): last changed {i['changed']}, about {age:.0f} h ago, expected every {i['limit_h']} h")
            lines += ["", "Open the latest **Refresh UK power map data** run under Actions and look for a red or skipped step.",
                      "Most steps are allowed to fail without stopping the rest, so a stale dataset is often the only sign.",
                      "This issue is updated automatically and closes itself when everything is current again."]
            path.write_text("\n".join(lines) + "\n")
        elif path.exists():
            path.unlink()

if __name__ == "__main__":
    main()
