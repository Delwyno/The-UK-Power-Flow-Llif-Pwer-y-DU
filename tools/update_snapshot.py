#!/usr/bin/env python3
"""Refresh data/snapshot.json from the NESO Carbon Intensity API.

This is the data the page shows when it can't reach live feeds (for example
inside a sandboxed preview). Each part is updated independently; if one call
fails, the previous value is kept.
"""
import json, sys, urllib.request
from datetime import datetime, timezone
from pathlib import Path

API = "https://api.carbonintensity.org.uk"
OUT = Path(__file__).resolve().parent.parent / "data" / "snapshot.json"

def get(path):
    req = urllib.request.Request(API + path, headers={"Accept": "application/json", "User-Agent": "uk-power-map/1.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)

def mix(gm):
    m = {f["fuel"]: float(f["perc"]) for f in gm}
    return {k: m.get(k, 0) for k in ["wind", "solar", "nuclear", "gas", "biomass", "hydro", "imports", "coal", "other"]}

def main():
    snap = json.loads(OUT.read_text())
    ok = 0
    parts = {
        "nat": lambda: (lambda d: {"from": d["from"], "mix": mix(d["generationmix"]), "demandGW": snap["nat"].get("demandGW", 30)})(
            (lambda x: x[0] if isinstance(x, list) else x)(get("/generation")["data"])),
        "wales": lambda: (lambda d: {"from": d["from"], "mix": mix(d["generationmix"]), "ci": d["intensity"]["forecast"], "idx": d["intensity"]["index"]})(
            get("/regional/wales")["data"][0]["data"][0]),
        "region": lambda: (lambda d: {"from": d["from"], "v": {str(r["regionid"]): r["intensity"]["forecast"] for r in d["regions"] if r["regionid"] <= 14}})(
            get("/regional")["data"][0]),
        "day": lambda: (lambda rows: {"from": rows[0]["from"], "v": [[r["intensity"]["forecast"], r["intensity"]["actual"]] for r in rows]})(
            get("/intensity/date")["data"]),
        "factors": lambda: (lambda f: {"France": f["French Imports"], "the Netherlands": f["Dutch Imports"], "Ireland": f["Irish Imports"]})(
            get("/intensity/factors")["data"][0]),
    }
    for k, fn in parts.items():
        try:
            snap[k] = fn(); ok += 1; print("updated", k)
        except Exception as e:
            print("kept previous", k, "-", e, file=sys.stderr)
    if ok:
        snap["updated"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ")
        OUT.write_text(json.dumps(snap, indent=1))
    print(f"{ok}/{len(parts)} parts updated")

if __name__ == "__main__":
    main()
