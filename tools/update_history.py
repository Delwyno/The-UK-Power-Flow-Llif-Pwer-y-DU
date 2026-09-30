#!/usr/bin/env python3
"""Rebuild data/history.json and data/sim.json from NESO's historic generation mix CSV.

history.json  annual, monthly and typical carbon intensity (embedded in the page)
sim.json      one base year of hourly demand and output, for the 2030 simulator
              (loaded by the page only when the simulator is opened)

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
SIM = OUT.parent / "sim.json"

# Installed GB capacity (GW) in each base year the simulator can replay. The page scales
# each hour's output by (chosen capacity / base capacity), so these must describe the
# fleet that produced that year's output. Source for 2024: DESNZ Clean Power 2030 Action
# Plan, connections reform annex, Table 1 (renewables Q2 2024; nuclear 2023; batteries
# Q4 2024; interconnectors 2024). Add a year here to let the simulator replay it.
BASE_CAP = {
    2024: {"off": 14.8, "on": 14.2, "solar": 16.6, "nuclear": 5.9, "bat": 4.55, "ldes": 2.9, "ic": 9.8,
           "src": "DESNZ, Clean Power 2030 Action Plan: connections reform annex, Table 1"},
}
SIM_UNIT = 50  # MW per step in the packed series
B64 = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"

def pack(series):
    """Two characters per hour: value in 50 MW steps, 0-4095."""
    out = []
    for v in series:
        n = int(round(max(0.0, float(v)) / SIM_UNIT)) if v == v else 0
        n = min(n, 4095)
        out.append(B64[n >> 6] + B64[n & 63])
    return "".join(out)

def records(df, days_back=30):
    """All-time records, and milestones reached in the last days_back days.

    Uses NESO's historic generation mix only (generation-based carbon intensity), so a
    'record' is never an artefact of comparing two different measures."""
    s = df.sort_values("DATETIME").reset_index(drop=True)
    stamp = lambda t: t.strftime("%Y-%m-%dT%H:%MZ")
    s["wind"] = s["WIND_perc"] + (s["WIND_EMB_perc"] if "WIND_EMB_perc" in s else 0)
    s["solar"] = s["SOLAR_perc"]; s["ci"] = s["CARBON_INTENSITY"]
    s["day"] = s["DATETIME"].dt.tz_localize("UTC").dt.tz_convert("Europe/London").dt.date
    g = s.groupby("day")
    D = pd.DataFrame({"n": g.size(), "mean": g["ci"].mean(), "min": g["ci"].min(), "wmax": g["wind"].max(), "smax": g["solar"].max(),
                      "min_t": s.loc[g["ci"].idxmin(), "DATETIME"].values, "w_t": s.loc[g["wind"].idxmax(), "DATETIME"].values,
                      "s_t": s.loc[g["solar"].idxmax(), "DATETIME"].values})
    for c in ["min_t", "w_t", "s_t"]:
        D[c] = pd.to_datetime(D[c])
    full = D[D["n"] >= 46]
    # spells at or below 50 g, across day boundaries
    flag = (s["ci"] <= 50).to_numpy(); runs = []; start = None
    for i, f in enumerate(flag):
        if f and start is None: start = i
        if (not f or i == len(flag) - 1) and start is not None:
            end = i if f else i - 1; runs.append((end - start + 1, start, end)); start = None
    best_run = max(runs) if runs else None
    lo = full["mean"].idxmin()
    rec = {"from": str(D.index.min()), "to": str(D.index.max()),
           "low": [round(float(D["min"].min())), stamp(D.loc[D["min"].idxmin(), "min_t"])],
           "day": [int(round(full.loc[lo, "mean"])), str(lo)],
           "wind": [round(float(D["wmax"].max()), 1), stamp(D.loc[D["wmax"].idxmax(), "w_t"])],
           "solar": [round(float(D["smax"].max()), 1), stamp(D.loc[D["smax"].idxmax(), "s_t"])]}
    if best_run:
        rec["run50"] = [best_run[0] / 2, stamp(s.loc[best_run[1], "DATETIME"])]
    ms = []
    recent = [d for d in D.index if d > D.index.max() - pd.Timedelta(days=days_back)]
    for d in recent:
        prior, x = D[D.index < d], D.loc[d]
        if not len(prior):
            continue
        if x["min"] < prior["min"].min():
            ms.append({"d": str(d), "k": "low", "v": round(float(x["min"]))})
        if x["wmax"] > prior["wmax"].max():
            ms.append({"d": str(d), "k": "wind", "v": round(float(x["wmax"]), 1)})
        if x["smax"] > prior["smax"].max():
            ms.append({"d": str(d), "k": "solar", "v": round(float(x["smax"]), 1)})
        if x["n"] >= 46:
            pf = prior[prior["n"] >= 46]; cleaner = pf[pf["mean"] <= x["mean"]]
            v = int(round(x["mean"]))
            if not len(cleaner):
                ms.append({"d": str(d), "k": "day_ever", "v": v})
            elif (d - cleaner.index.max()).days >= 30:
                ms.append({"d": str(d), "k": "day", "v": v, "s": str(cleaner.index.max())})
    for length, a, b in runs:
        d = s.loc[b, "day"]
        if d in recent and length >= 8 and length > max([r[0] for r in runs if r[2] < a] or [0]):
            ms.append({"d": str(d), "k": "run", "v": length / 2})
    return rec, sorted(ms, key=lambda m: m["d"])

def build_sim(df):
    need = ["WIND", "SOLAR", "NUCLEAR", "GAS"]
    if any(c not in df for c in need):
        print("sim.json: CSV lacks", [c for c in need if c not in df], "- not updated", file=sys.stderr)
        return
    d = df.set_index("DATETIME").sort_index()
    years = sorted(y for y in BASE_CAP if ((d.index.year == y).sum() >= 17000))
    if not years:
        print("sim.json: no complete base year in the CSV - not updated", file=sys.stderr)
        return
    y = years[-1]
    d = d[d.index.year == y]
    col = lambda c: d[c].clip(lower=0).fillna(0) if c in d else pd.Series(0.0, index=d.index)
    parts = {
        "gas": col("GAS") + col("COAL"),
        "nuclear": col("NUCLEAR"),
        "wind": col("WIND") + col("WIND_EMB"),
        "solar": col("SOLAR"),
        "bio": col("BIOMASS"),
        "hydro": col("HYDRO"),
        "other": col("OTHER"),
        "imports": col("IMPORTS"),
        "storage": col("STORAGE"),
    }
    demand = sum(parts.values())
    h = lambda s: s.resample("1h").mean().interpolate(limit=4).fillna(0)
    H = {k: h(v) for k, v in parts.items()}
    D = h(demand)
    ci = h(d["CARBON_INTENSITY"])
    twh = lambda s: round(float(s.sum()) / 1e6, 1)
    dom = sum(H[k] for k in ["gas", "nuclear", "wind", "solar", "bio", "hydro", "other"])
    clean = H["nuclear"] + H["wind"] + H["solar"] + H["bio"] + H["hydro"]
    daily = ci.resample("1D").mean().round().astype(int).tolist()
    out = {
        "year": y, "from": D.index[0].strftime("%Y-%m-%dT%H:%MZ"), "hours": len(D), "unit": SIM_UNIT,
        "cap": BASE_CAP[y],
        "s": {"d": pack(D), "w": pack(H["wind"]), "so": pack(H["solar"]), "n": pack(H["nuclear"]),
              "b": pack(H["bio"]), "hy": pack(H["hydro"]), "ot": pack(H["other"]), "im": pack(H["imports"])},
        "act": {"ci": int(round(float(ci.mean()))), "demand": twh(D), "gas": twh(H["gas"]), "imports": twh(H["imports"]),
                "wind": twh(H["wind"]), "solar": twh(H["solar"]), "nuclear": twh(H["nuclear"]),
                "clean_share": round(float(clean.sum() / dom.sum()) * 100, 1),
                "h50": int((ci <= 50).sum())},
        "daily": daily,
    }
    SIM.write_text(json.dumps(out, separators=(",", ":")))
    print(f"sim.json: base year {y}, {len(D)} hours, {SIM.stat().st_size/1024:.0f} KB, actual mean {out['act']['ci']} g")


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
    # typical conditions for each month and half-hour (UK local time), from the last 24 months
    recent = df[dt >= last - pd.Timedelta(days=730)].copy()
    loc = recent["DATETIME"].dt.tz_localize("UTC").dt.tz_convert("Europe/London")
    recent["m"] = loc.dt.month; recent["s"] = loc.dt.hour * 2 + loc.dt.minute // 30
    recent["wind_all"] = recent["WIND_perc"] + recent.get("WIND_EMB_perc", 0)
    cols = {"ci": "CARBON_INTENSITY", "wind": "wind_all", "solar": "SOLAR_perc", "gas": "GAS_perc",
            "nuclear": "NUCLEAR_perc", "imports": "IMPORTS_perc", "biomass": "BIOMASS_perc"}
    g = recent.groupby(["m", "s"])
    typ = {}
    for m in range(1, 13):
        typ[m] = {}
        for k, c in cols.items():
            ser = g[c].mean()
            typ[m][k] = [round(float(ser.get((m, s), float("nan"))), 1 if k != "ci" else 0) for s in range(48)]
        q = g["CARBON_INTENSITY"]
        typ[m]["p10"] = [round(float(q.quantile(.1).get((m, s), float("nan")))) for s in range(48)]
        typ[m]["p90"] = [round(float(q.quantile(.9).get((m, s), float("nan")))) for s in range(48)]
    out["typ"] = typ
    # records and milestones, all from this one dataset so every comparison uses the same measure
    try:
        out["rec"], out["ms"] = records(df)
    except Exception as e:
        print("history: records not updated -", e, file=sys.stderr)
    out["typ_from"] = (last - pd.Timedelta(days=730)).strftime("%Y-%m-%d")
    OUT.write_text(json.dumps(out, separators=(",", ":")).replace("NaN", "null"))
    print(f"history.json: {len(out['yr'])} years, latest {out['ytd']}, record {out['record']}")
    try:
        build_sim(df)
    except Exception as e:  # the simulator data is optional; never block the history refresh
        print("sim.json: not updated -", e, file=sys.stderr)

if __name__ == "__main__":
    main()
