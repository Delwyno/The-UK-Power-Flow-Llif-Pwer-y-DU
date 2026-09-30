#!/usr/bin/env python3
"""Daily refresh from the NESO Carbon Intensity API.

data/snapshot.json  what the page shows when it can't reach live feeds
data/accuracy.json  forecast tracker: stores today's 24-hour forecast, then scores
                    earlier forecasts against what actually happened
data/digest.json    weekly grid digest: one summary per Monday-to-Sunday week
data/daily.json     one line of extremes per day, for records and milestones

Each part is updated independently; if one call fails, the previous data is kept.
"""
import json, sys, urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import mean
from zoneinfo import ZoneInfo

API = "https://api.carbonintensity.org.uk"
OUT = Path(__file__).resolve().parent.parent / "data" / "snapshot.json"
ACC = OUT.parent / "accuracy.json"
DIG = OUT.parent / "digest.json"
DAY = OUT.parent / "daily.json"
DIGEST_VERSION = 2  # bump to rebuild stored weeks after a fix to week_summary

def val(r):
    """Measured intensity, or the forecast when the measurement is missing (NESO reports gaps as 0 or null)."""
    i = r["intensity"]; a = i.get("actual")
    return a if a not in (None, 0) else i.get("forecast")

def in_range(rows, t0, t1):
    """NESO range queries also return the half-hour ending at the start time, so drop it."""
    return [r for r in rows if t0 <= parse(r["from"][:16] + "Z") < t1]
UK = ZoneInfo("Europe/London")
iso = lambda dt: dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%MZ")
parse = lambda s: datetime.strptime(s.replace("Z", ""), "%Y-%m-%dT%H:%M").replace(tzinfo=timezone.utc)
def load(path, default):
    try:
        return json.loads(path.read_text())
    except Exception:
        return default

def get(path):
    req = urllib.request.Request(API + path, headers={"Accept": "application/json", "User-Agent": "uk-power-map/1.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)

def mix(gm):
    m = {f["fuel"]: float(f["perc"]) for f in gm}
    return {k: m.get(k, 0) for k in ["wind", "solar", "nuclear", "gas", "biomass", "hydro", "imports", "coal", "other"]}

# ---------------------------------------------------------------- forecast tracker
WIN = 6  # a 3-hour window, the length the Plan tab most often looks for

def score(f, a):
    """Compare one day's forecast f with actuals a (lists of half-hourly gCO2/kWh)."""
    pairs = [(x, y) for x, y in zip(f, a) if x is not None and y is not None]
    if len(pairs) < 40:
        return None
    err = [x - y for x, y in pairs]
    ff = [x for x, _ in pairs]; aa = [y for _, y in pairs]
    wins = range(len(pairs) - WIN + 1)
    best_f = min(wins, key=lambda i: mean(ff[i:i + WIN]))
    best_a = min(wins, key=lambda i: mean(aa[i:i + WIN]))
    gap = mean(aa[best_f:best_f + WIN]) - mean(aa[best_a:best_a + WIN])
    return {"mae": round(mean(abs(e) for e in err), 1), "bias": round(mean(err), 1),
            "w20": round(sum(abs(e) <= 20 for e in err) / len(err) * 100),
            "gap": round(gap, 1), "n": len(pairs)}

def update_accuracy(now):
    acc = load(ACC, {"since": None, "fc": {}, "days": []})
    changed = False
    # 1. store the forecast issued now for the next 24 hours
    start = now.replace(minute=0 if now.minute < 30 else 30, second=0, microsecond=0)
    key = start.strftime("%Y-%m-%d")
    if key not in acc["fc"] and not any(d["d"] == key for d in acc["days"]):
        rows = get(f"/intensity/{iso(start)}/fw24h")["data"]
        f = [r["intensity"]["forecast"] for r in rows][:48]
        if len(f) >= 40:
            acc["fc"][key] = {"from": rows[0]["from"][:16] + "Z", "f": f}
            acc["since"] = acc["since"] or key
            changed = True
            print("accuracy: stored forecast", key)
    # 2. score stored forecasts whose 24 hours are over
    for k in sorted(list(acc["fc"])):
        fc = acc["fc"][k]; t0 = parse(fc["from"]); t1 = t0 + timedelta(hours=24)
        if t1 > now - timedelta(minutes=10):
            continue
        rows = get(f"/intensity/{iso(t0)}/{iso(t1)}")["data"]
        rows = in_range(rows, t0, t1)
        a = [(r["intensity"]["actual"] or None) for r in rows][:len(fc["f"])]
        s = score(fc["f"], a)
        if s:
            acc["days"].append({"d": k, **s})
            print("accuracy: scored", k, s)
        del acc["fc"][k]; changed = True
    for k in list(acc["fc"]):  # never keep more than a few pending forecasts
        if parse(acc["fc"][k]["from"]) < now - timedelta(days=4):
            del acc["fc"][k]; changed = True
    acc["days"] = sorted(acc["days"], key=lambda d: d["d"])[-120:]
    if changed:
        ACC.write_text(json.dumps(acc, separators=(",", ":")))
    return changed

# ---------------------------------------------------------------- weekly digest
FUELS = ["wind", "solar", "nuclear", "gas", "biomass", "hydro", "imports", "coal", "other"]

def week_summary(start_uk):
    """Summarise the Monday-to-Sunday week starting at start_uk (UK midnight)."""
    t0 = start_uk.astimezone(timezone.utc); t1 = (start_uk + timedelta(days=7)).astimezone(timezone.utc)
    rng = f"{iso(t0)}/{iso(t1)}"
    rows = in_range(get(f"/intensity/{rng}")["data"], t0, t1)
    pts = [(parse(r["from"][:16] + "Z"), val(r)) for r in rows if val(r) is not None]
    if len(pts) < 300:
        raise ValueError(f"only {len(pts)} half-hours")
    vals = [v for _, v in pts]
    days = {}
    for t, v in pts:
        days.setdefault(t.astimezone(UK).strftime("%Y-%m-%d"), []).append(v)
    lo = min(pts, key=lambda p: p[1]); hi = max(pts, key=lambda p: p[1])
    out = {"start": start_uk.strftime("%Y-%m-%d"), "ci": round(mean(vals)), "min": [lo[1], iso(lo[0])], "max": [hi[1], iso(hi[0])],
           "h50": sum(v <= 50 for v in vals) / 2, "days": [[d, round(mean(v))] for d, v in sorted(days.items())], "n": len(vals)}
    try:
        gen = in_range(get(f"/generation/{rng}")["data"], t0, t1)
        mix = {f: [] for f in FUELS}; pk = {"wind": [0, None], "solar": [0, None]}
        for g in gen:
            m = {x["fuel"]: float(x["perc"]) for x in g["generationmix"]}
            for f in FUELS:
                mix[f].append(m.get(f, 0.0))
            for f in pk:
                if m.get(f, 0) > pk[f][0]:
                    pk[f] = [round(m.get(f, 0)), g["from"][:16] + "Z"]
        if len(mix["wind"]) > 200:
            out["mix"] = {f: round(mean(v), 1) for f, v in mix.items()}
            out["pk"] = pk
    except Exception as e:
        print("digest: no generation mix -", e, file=sys.stderr)
    try:
        reg = in_range(get(f"/regional/intensity/{rng}")["data"], t0, t1)
        acc = {}
        for r in reg:
            for x in r["regions"]:
                v = x["intensity"]["forecast"]
                if v is not None:
                    acc.setdefault(str(x["regionid"]), []).append(v)
        out["reg"] = {k: round(mean(v)) for k, v in acc.items() if len(v) > 200}
    except Exception as e:
        print("digest: no regional data -", e, file=sys.stderr)
    return out

def update_digest(now):
    dig = load(DIG, {"weeks": []})
    if dig.get("v") != DIGEST_VERSION:
        dig = {"v": DIGEST_VERSION, "weeks": []}
    have = {w["start"] for w in dig["weeks"]}
    uk = now.astimezone(UK)
    monday = (uk - timedelta(days=uk.weekday())).replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=None)
    changed = False
    # the most recent complete week, plus up to seven earlier ones on the first run
    for back in range(1, 9 if len(dig["weeks"]) < 4 else 2):
        start = (monday - timedelta(days=7 * back)).replace(tzinfo=UK)
        if start.strftime("%Y-%m-%d") in have:
            continue
        try:
            dig["weeks"].append(week_summary(start)); changed = True
            print("digest: added week", start.strftime("%Y-%m-%d"))
        except Exception as e:
            print("digest: skipped", start.strftime("%Y-%m-%d"), "-", e, file=sys.stderr)
    dig["weeks"] = sorted(dig["weeks"], key=lambda w: w["start"])[-104:]
    if changed:
        DIG.write_text(json.dumps(dig, separators=(",", ":")))
    return changed

# ---------------------------------------------------------------- daily extremes (records and milestones)
def longest_run(flags):
    best = run = 0
    for f in flags:
        run = run + 1 if f else 0; best = max(best, run)
    return best

def day_summary(day_uk):
    t0 = day_uk.astimezone(timezone.utc); t1 = (day_uk + timedelta(days=1)).astimezone(timezone.utc)
    rng = f"{iso(t0)}/{iso(t1)}"
    rows = in_range(get(f"/intensity/{rng}")["data"], t0, t1)
    pts = [(r["from"][:16] + "Z", val(r)) for r in rows if val(r) is not None]
    if len(pts) < 40:
        raise ValueError(f"only {len(pts)} half-hours")
    v = [x for _, x in pts]; lo = min(pts, key=lambda p: p[1])
    out = {"d": day_uk.strftime("%Y-%m-%d"), "ci": round(mean(v)), "min": [lo[1], lo[0]],
           "h50": sum(x <= 50 for x in v) / 2, "run50": longest_run([x <= 50 for x in v]) / 2}
    try:
        gen = in_range(get(f"/generation/{rng}")["data"], t0, t1)
        best = {"wind": [0, None], "solar": [0, None]}
        for g in gen:
            m = {x["fuel"]: float(x["perc"]) for x in g["generationmix"]}
            for f in best:
                if m.get(f, 0) > best[f][0]:
                    best[f] = [round(m.get(f, 0), 1), g["from"][:16] + "Z"]
        out["wind"] = best["wind"]; out["solar"] = best["solar"]
    except Exception as e:
        print("daily: no mix -", e, file=sys.stderr)
    try:
        reg = in_range(get(f"/regional/intensity/{rng}")["data"], t0, t1)
        w = []
        for r in reg:
            x = next((x for x in r["regions"] if x["regionid"] == 17), None)
            if x and x.get("generationmix"):
                w.append({m["fuel"]: float(m["perc"]) for m in x["generationmix"]})
        if len(w) > 40:
            ws = [m.get("wind", 0) for m in w]
            out["wales"] = {"wind": round(mean(ws), 1), "h80": sum(s >= 80 for s in ws) / 2, "max": round(max(ws), 1)}
    except Exception as e:
        print("daily: no Wales mix -", e, file=sys.stderr)
    return out

def update_daily(now):
    day = load(DAY, {"days": []})
    have = {d["d"] for d in day["days"]}
    today = now.astimezone(UK).replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=None)
    back = 60 if len(day["days"]) < 7 else 3   # backfill two months on the first run
    changed = False
    for k in range(1, back + 1):
        d = (today - timedelta(days=k)).replace(tzinfo=UK)
        if d.strftime("%Y-%m-%d") in have:
            continue
        try:
            day["days"].append(day_summary(d)); changed = True
        except Exception as e:
            print("daily: skipped", d.strftime("%Y-%m-%d"), "-", e, file=sys.stderr)
    day["days"] = sorted(day["days"], key=lambda x: x["d"])[-800:]
    if changed:
        DAY.write_text(json.dumps(day, separators=(",", ":")))

def main():
    now = datetime.now(timezone.utc)
    for name, fn in [("accuracy", update_accuracy), ("digest", update_digest), ("daily", update_daily)]:
        try:
            fn(now)
        except Exception as e:
            print(name, "not updated -", e, file=sys.stderr)
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
