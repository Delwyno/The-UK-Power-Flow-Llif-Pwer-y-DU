#!/usr/bin/env python3
"""Rebuild data/history.json from NESO's historic generation mix CSV.

Usage:
  python tools/update_history.py                 # downloads the latest CSV from NESO
  python tools/update_history.py --csv file.csv  # uses a local copy
"""
import argparse, io, json, sys, urllib.request
from pathlib import Path
import pandas as pd

URL = ("https://api.neso.energy/dataset/88313ae5-94e4-4ddc-a790-593554d8c6b9/"
       "resource/f93d1835-75bc-43e5-84ad-12472b180a98/download/df_fuel_ckan.csv")
OUT = Path(__file__).resolve().parent.parent / "data" / "history.json"

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", help="local CSV instead of downloading")
    a = ap.parse_args()
    if a.csv:
        df = pd.read_csv(a.csv, parse_dates=["DATETIME"])
    else:
        req = urllib.request.Request(URL, headers={"User-Agent": "uk-power-map/1.0"})
        with urllib.request.urlopen(req, timeout=300) as r:
            df = pd.read_csv(io.BytesIO(r.read()), parse_dates=["DATETIME"])
    df = df.dropna(subset=["CARBON_INTENSITY"])
    if len(df) < 100000:
        sys.exit("CSV looks too short; not overwriting history.json")
    dt = df["DATETIME"]  # UTC half-hour starts
    yr = df.groupby(dt.dt.year)["CARBON_INTENSITY"].mean().round().astype(int)
    mon = df.groupby([dt.dt.year, dt.dt.month])["CARBON_INTENSITY"].mean().round().astype(int)
    clean = df[df["CARBON_INTENSITY"] <= 50].groupby(dt.dt.year).size() / 2
    last = dt.max()
    lo = df.loc[df["CARBON_INTENSITY"].idxmin()]
    out = {
        "source": "NESO historic generation mix (df_fuel_ckan.csv)",
        "yr": {int(k): int(v) for k, v in yr.items()},
        "ytd": {"y": int(last.year), "v": int(yr[last.year]), "to": last.strftime("%Y-%m-%d")},
        "mon": [[int(y), int(m), int(v)] for (y, m), v in mon.items()],
        "clean": {int(y): int(clean.get(y, 0)) for y in range(2018, int(last.year) + 1)},
        "record": {"v": int(round(lo["CARBON_INTENSITY"])), "t": lo["DATETIME"].strftime("%Y-%m-%dT%H:%MZ")},
    }
    OUT.write_text(json.dumps(out, separators=(",", ":")))
    print(f"history.json: {len(out['yr'])} years, latest {out['ytd']}, record {out['record']}")

if __name__ == "__main__":
    main()
