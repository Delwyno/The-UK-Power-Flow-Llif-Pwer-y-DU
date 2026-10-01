#!/usr/bin/env python3
"""Cost of switching wind off and turning gas on, by hour, from Elexon Insights (BMRS).

Modes
  (default)  the last few settlement days  -> data/costs.json        (daily refresh)
  --today    today so far                  -> data/today.json        (every 30 minutes; the workflow
                                                                      publishes it to the live-data branch)
  --probe    print what the feeds return, to diagnose a problem from the Actions log

How the figures are made (all from Elexon's own published calculations)
  * Indicative cashflows per BM unit per half hour: bids for wind units, offers for gas units.
  * Each unit-period's cashflow is scaled by the share of its accepted volume that was flagged as a
    system action (BOALF soFlag), so energy-balancing trades are left out and constraint management
    is what remains. If the flag cannot be matched for most volume, the figures use ALL actions and
    the file says so ("basis": "all").
  * Wind = BM units whose fuel type is WIND. Gas = CCGT and OCGT.
Indicative figures are published about 15 minutes after each half hour and may be revised later.
Contains BMRS data (c) Elexon Limited.
"""
import json, os, sys, time, urllib.request
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "costs.json"
FUEL = ROOT / "data" / "bmu_fuel.json"
ELX = os.environ.get("ELEXON_BASE", "https://data.elexon.co.uk/bmrs/api/v1")
UK = ZoneInfo("Europe/London")
WIND_TYPES, GAS_TYPES = {"WIND"}, {"CCGT", "OCGT"}
KEEP_HOURLY_DAYS, KEEP_DAYS = 45, 2000
MIN_MATCH = 0.6   # share of volume whose system flag must be found before the "system" basis is used

def get(path, tries=3):
    for k in range(tries):
        try:
            req = urllib.request.Request(ELX + path, headers={"Accept": "application/json", "User-Agent": "uk-power-map/1.0"})
            with urllib.request.urlopen(req, timeout=90) as r:
                return json.load(r)
        except Exception:
            if k == tries - 1:
                raise
            time.sleep(2 + 4 * k)

def rows(x):
    if isinstance(x, dict):
        x = x.get("data")
    return x if isinstance(x, list) else []

def num(v):
    try:
        return float(v)
    except Exception:
        return 0.0

def period_start(d, sp):
    """UTC start of a settlement period. Periods run in real time from UK midnight, so this holds on clock-change days."""
    y, m, dd = map(int, d.split("-"))
    return datetime(y, m, dd, tzinfo=UK).astimezone(timezone.utc) + timedelta(minutes=30 * (int(sp) - 1))

def hour_of(d, sp):
    return period_start(d, sp).astimezone(UK).hour

_FUEL = None
def bm_fuel():
    """Sets of wind and gas BM unit ids (both the Elexon and the National Grid forms), cached on disk."""
    global _FUEL
    if _FUEL is not None:
        return _FUEL
    try:
        wind, gas = set(), set()
        for r in rows(get("/reference/bmunits/all")):
            ft = str(r.get("fuelType") or "").upper()
            tgt = wind if ft in WIND_TYPES else gas if ft in GAS_TYPES else None
            if tgt is not None:
                tgt.update(i for i in (r.get("elexonBmUnit"), r.get("nationalGridBmUnit")) if i)
        if len(wind) < 30 or len(gas) < 20:
            raise ValueError(f"unexpectedly few units (wind {len(wind)}, gas {len(gas)}): the fuelType field may have changed")
        FUEL.write_text(json.dumps({"updated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ"), "wind": sorted(wind), "gas": sorted(gas)}, separators=(",", ":")))
        _FUEL = (wind, gas)
    except Exception as e:
        print("BM unit reference not updated -", e, file=sys.stderr)
        try:
            d = json.loads(FUEL.read_text()); _FUEL = (set(d["wind"]), set(d["gas"]))
        except Exception:
            _FUEL = (set(), set())
    return _FUEL

def so_flags(d):
    """acceptance number -> was it a system action? One call for the whole settlement date."""
    for path in (f"/datasets/BOALF/stream?from={d}&to={d}&settlementPeriodFrom=1&settlementPeriodTo=50",
                 f"/datasets/BOALF?from={d}&to={d}&settlementPeriodFrom=1&settlementPeriodTo=50"):
        try:
            flags = {}
            for r in rows(get(path)):
                n = r.get("acceptanceNumber")
                if n is not None:
                    flags[int(n)] = bool(r.get("soFlag"))
            if flags:
                return flags
        except Exception as e:
            print("acceptances not read -", e, file=sys.stderr)
    return {}

def day_costs(d):
    """Hourly wind turn-down and gas turn-up for one UK settlement date."""
    wind, gas = bm_fuel()
    if not wind or not gas:
        raise ValueError("no wind or gas unit lists, so nothing can be attributed")
    flags = so_flags(d)
    parts = {}   # (kind, unit, sp) -> [cashflow, total volume, system volume]
    matched = seen = 0.0
    last_sp = 0
    for bo, units, kind in (("bid", wind, "w"), ("offer", gas, "g")):
        vol_t, vol_s = defaultdict(float), defaultdict(float)
        for r in rows(get(f"/balancing/settlement/acceptance/volumes/all/{bo}/{d}")):
            u, ng = r.get("bmUnit"), r.get("nationalGridBmUnit")
            if u not in units and ng not in units:
                continue
            v, k = abs(num(r.get("totalVolumeAccepted"))), (u or ng, int(r.get("settlementPeriod") or 0))
            vol_t[k] += v; seen += v
            aid = r.get("acceptanceId")
            if aid is not None and int(aid) in flags:
                matched += v
                if flags[int(aid)]:
                    vol_s[k] += v
        cash = {}
        for r in rows(get(f"/balancing/settlement/indicative/cashflows/all/{bo}/{d}")):
            sp = int(r.get("settlementPeriod") or 0)
            last_sp = max(last_sp, sp)
            u, ng = r.get("bmUnit"), r.get("nationalGridBmUnit")
            if u in units or ng in units:
                cash[(u or ng, sp)] = cash.get((u or ng, sp), 0.0) + num(r.get("totalCashflow"))
        for k, cf in cash.items():
            parts[(kind,) + k] = [cf, vol_t.get(k, 0.0), vol_s.get(k, 0.0)]
    ratio = matched / seen if seen > 0 else 0.0
    basis = "system" if ratio >= MIN_MATCH else "all"
    H = {s: [0.0] * 24 for s in ("wm", "wg", "gm", "gg")}
    for (kind, _unit, sp), (cf, vt, vs) in parts.items():
        if vt <= 0:
            continue
        share = (vs / vt) if basis == "system" else 1.0
        h = hour_of(d, sp)
        H[kind + "m"][h] += vt * share
        H[kind + "g"][h] += cf * share
    out = {"d": d, "basis": basis, "match": round(ratio, 2), "n": last_sp,
           "wm": [round(x, 1) for x in H["wm"]], "wg": [round(x) for x in H["wg"]],
           "gm": [round(x, 1) for x in H["gm"]], "gg": [round(x) for x in H["gg"]]}
    out["t"] = {k: round(sum(out[k]), 1 if k.endswith("m") else 0) for k in ("wm", "wg", "gm", "gg")}
    if last_sp:
        out["through"] = (period_start(d, last_sp) + timedelta(minutes=30)).astimezone(UK).strftime("%H:%M")
    return out

def load_existing():
    try:
        return {x["d"]: x for x in json.loads(OUT.read_text())["days"]}
    except Exception:
        return {}

def main():
    now = datetime.now(timezone.utc)
    today = now.astimezone(UK).strftime("%Y-%m-%d")
    if "--probe" in sys.argv:
        return probe(today)
    if "--today" in sys.argv:
        res = day_costs(today)
        res["updated"] = now.strftime("%Y-%m-%dT%H:%MZ")
        path = Path(sys.argv[sys.argv.index("--out") + 1]) if "--out" in sys.argv else ROOT / "data" / "today.json"
        path.write_text(json.dumps(res, separators=(",", ":")))
        print(f"today {today}: {res['n']} periods to {res.get('through','-')}, wind £{res['t']['wg']:,} gas £{res['t']['gg']:,} (basis {res['basis']}, flags matched {res['match']:.0%})")
        return
    existing = load_existing()
    n = int(os.environ.get("COST_DAYS", "14" if not existing else "8"))
    dates = [(now.astimezone(UK) - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(1, n + 1)]
    got = {}
    def one(d):
        try:
            return d, day_costs(d)
        except Exception as e:
            print(f"{d}: not updated - {e}", file=sys.stderr)
            return d, None
    with ThreadPoolExecutor(max_workers=3) as ex:
        for d, r in ex.map(one, dates):
            if r and r["n"] > 0:
                got[d] = r
    if not got:
        print("costs: nothing new, file left as it was", file=sys.stderr)
        return
    existing.update(got)
    days = sorted(existing.values(), key=lambda x: x["d"])[-KEEP_DAYS:]
    cut = (now.astimezone(UK) - timedelta(days=KEEP_HOURLY_DAYS)).strftime("%Y-%m-%d")
    for x in days:
        if x["d"] < cut:
            for k in ("wm", "wg", "gm", "gg"):
                x.pop(k, None)
    OUT.write_text(json.dumps({"updated": now.strftime("%Y-%m-%dT%H:%MZ"), "days": days}, separators=(",", ":")))
    last = days[-1]
    print(f"costs: {len(got)} days updated; latest {last['d']}: wind £{last['t']['wg']:,}, gas £{last['t']['gg']:,} (basis {last['basis']})")

def probe(today):
    """Diagnose the feeds for yesterday: what comes back, how well the flags match, what the totals are."""
    d = (datetime.now(UK) - timedelta(days=1)).strftime("%Y-%m-%d")
    print("probe for", d, "against", ELX)
    wind, gas = bm_fuel(); print(" BM units:", len(wind), "wind ids,", len(gas), "gas ids")
    fl = so_flags(d); print(" acceptances with flags:", len(fl), "| system-flagged:", sum(fl.values()))
    for bo in ("bid", "offer"):
        v = rows(get(f"/balancing/settlement/acceptance/volumes/all/{bo}/{d}")); c = rows(get(f"/balancing/settlement/indicative/cashflows/all/{bo}/{d}"))
        print(f" {bo}: {len(v)} volume rows, {len(c)} cashflow rows"); print("   volume row keys:", sorted(v[0]) if v else None); print("   cashflow row keys:", sorted(c[0]) if c else None)
        print("   sample acceptanceId:", [r.get("acceptanceId") for r in v[:3]], "| in flags:", [int(r.get("acceptanceId", -1)) in fl for r in v[:3]])
    r = day_costs(d); print(" result:", json.dumps({k: r[k] for k in ("basis", "match", "n", "t")}))

if __name__ == "__main__":
    main()
