#!/usr/bin/env python3
"""Assemble index.html from src/app.html, src/sites.js and data/*.json.

Everything is embedded so the page works as a single file, offline or hosted,
except data/sim.json (the 2030 simulator's year of hourly data), which the page
fetches only when someone opens the simulator. Pass --inline-sim to embed it too.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PARTS = {
    "__DATA__": "src/sites.js",
    "__GEO__": "data/geo.json",
    "__PYL__": "data/gridlines.json",
    "__ROUTES__": "data/routes.json",
    "__PLANTS__": "data/plants.json",
    "__SUBS__": "data/subs.json",
    "__WINDA__": "data/windareas.json",
    "__XCHK__": "data/xchk.json",
    "__REGGEO__": "data/regions.json",
    "__SNAPSHOT__": "data/snapshot.json",
    "__HISTORY__": "data/history.json",
    "__ACC__": "data/accuracy.json",
    "__DIGEST__": "data/digest.json",
}

def main():
    html = (ROOT / "src" / "app.html").read_text(encoding="utf-8")
    for key, path in PARTS.items():
        if key not in html:
            raise SystemExit(f"placeholder {key} missing from src/app.html")
        html = html.replace(key, (ROOT / path).read_text(encoding="utf-8").strip())
    sim = "null"
    if "--inline-sim" in sys.argv and (ROOT / "data" / "sim.json").exists():
        sim = (ROOT / "data" / "sim.json").read_text(encoding="utf-8").strip() or "null"
    html = html.replace("__SIMINLINE__", sim)
    out = ROOT / "index.html"
    out.write_text(html, encoding="utf-8")
    print(f"index.html: {out.stat().st_size/1024:.0f} KB")

if __name__ == "__main__":
    main()
