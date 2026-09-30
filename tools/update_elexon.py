#!/usr/bin/env python3
"""Daily history from Elexon Insights (BMRS), for the curtailment tracker and station history.

For each of yesterday's half-hours (and up to a week back on the first run) it reads the same
three feeds the live map uses, then saves:

  data/curtail.json   per day: wind turned down (MWh), payments (GBP) and each wind farm's share
  data/stations.json  the last 14 days, hourly: each mapped station's notified output and
                      the part the grid operator paid it to turn down

Output is the station's physical notification (PN): the output it told the grid operator it
planned for the half-hour. Turn-down is the gap between that plan and the level in the grid
operator's accepted instructions (bid-offer acceptances). Payments use the unit's bid price.
Contains BMRS data (c) Elexon Limited.
"""
import json, re, sys, time, urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
CUR = ROOT / "data" / "curtail.json"
STA = ROOT / "data" / "stations.json"
ELX = "https://data.elexon.co.uk/bmrs/api/v1"
UK = ZoneInfo("Europe/London")
UNIT = 5  # MW per step in the packed station series
B64 = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
KEEP_SITES_DAYS, KEEP_TOTAL_DAYS, KEEP_STATION_DAYS = 120, 800, 14

def get(path, tries=3):
    for k in range(tries):
        try:
            req = urllib.request.Request(ELX + path, headers={"Accept": "application/json", "User-Agent": "uk-power-map/1.0"})
            with urllib.request.urlopen(req, timeout=60) as r:
                x = json.load(r)
            return x["data"] if isinstance(x, dict) and "data" in x else x
        except Exception:
            if k == tries - 1:
                raise
            time.sleep(2 + 3 * k)

def load(path, default):
    try:
        return json.loads(path.read_text())
    except Exception:
        return default

def site_table():
    """Read the curated sites and their BMU prefixes from the page source, so there is one list."""
    app = (ROOT / "src" / "app.html").read_text(encoding="utf-8")
    m = re.search(r"const BMU = (\{.*?\});", app, re.S)
    bmu = json.loads(re.sub(r"([{,]\s*)([A-Za-z0-9_]+):", r'\1"\2":', m.group(1).replace("'", '"')))
    sites = (ROOT / "src" / "sites.js").read_text(encoding="utf-8")
    types = dict(re.findall(r"\{id:'([^']+)'.*?\bt:'(\w+)'", sites))
    return {k: {"bmu": v, "t": types.get(k, "")} for k, v in bmu.items()}

bmu_id = lambda r: re.sub(r"^[TE]_", "", str(r.get("nationalGridBmUnit") or r.get("bmUnit") or r.get("bmUnitId") or "")).upper()
ts = lambda s: datetime.fromisoformat(str(s).replace("Z", "+00:00")).timestamp()

def level(recs, t, pick_latest_acceptance=False):
    """Level at time t from segments (timeFrom, timeTo, levelFrom, levelTo); None if nothing covers t."""
    cover = []
    for r in recs:
        try:
            a, b = ts(r["timeFrom"]), ts(r["timeTo"])
        except Exception:
            continue
        if a <= t <= b:
            cover.append((r, a, b))
    if not cover:
        return None
    if pick_latest_acceptance:  # a later acceptance replaces an earlier one
        cover.sort(key=lambda c: (c[0].get("acceptanceNumber") or 0, str(c[0].get("acceptanceTime") or "")))
    r, a, b = cover[-1]
    lf, lt = float(r["levelFrom"]), float(r["levelTo"])
    return lt if b <= a else lf + (lt - lf) * (t - a) / (b - a)

def half_hour(date, sp, start, table, prefixes):
    """Average MW notified and MW turned down, per BMU, for one settlement period."""
    q = f"settlementDate={date}&settlementPeriod={sp}"
    group = lambda rows: {k: v for k, v in _group(rows).items() if k.startswith(prefixes)}
    pn = group(get(f"/balancing/physical/all?dataset=PN&{q}"))
    acc = group(get(f"/balancing/acceptances/all?{q}"))
    samples = [start + 60 * (m + 0.5) for m in range(30)]
    out_pn, out_cut = {}, {}
    for u, recs in pn.items():
        lv = [level(recs, t) for t in samples]
        lv = [max(0.0, x) for x in lv if x is not None]
        if not lv:
            continue
        out_pn[u] = sum(lv) / len(lv)
        if u in acc:
            cut = []
            for t in samples:
                p, a = level(recs, t), level(acc[u], t, True)
                cut.append(max(0.0, p - a) if p is not None and a is not None else 0.0)
            c = sum(cut) / len(cut)
            if c > 0.5:
                out_cut[u] = c
    bid = {}
    if out_cut:
        for r in get(f"/balancing/bid-offer/all?{q}"):
            u, p = bmu_id(r), r.get("pairId")
            try:
                p = int(p); b = float(r["bid"])
            except Exception:
                continue
            if u in out_cut and p < 0 and (u not in bid or p > bid[u][0]):
                bid[u] = (p, b)
    return out_pn, out_cut, {u: max(0.0, -bid[u][1]) for u in bid}

def _group(rows):
    g = {}
    for r in rows or []:
        u = bmu_id(r)
        if u:
            g.setdefault(u, []).append(r)
    return g

def day_periods(day):
    """Settlement periods for a UK day: 46, 48 or 50 half-hours, starting at local midnight."""
    start = datetime(day.year, day.month, day.day, tzinfo=UK).astimezone(timezone.utc)
    end = datetime.combine(day + timedelta(days=1), datetime.min.time(), tzinfo=UK).astimezone(timezone.utc)
    n = int((end - start).total_seconds() // 1800)
    return start, [(sp, start.timestamp() + 1800 * (sp - 1)) for sp in range(1, n + 1)]

def pack(vals):
    return "".join(B64[min(4095, max(0, int(round(v / UNIT)))) >> 6] + B64[min(4095, max(0, int(round(v / UNIT)))) & 63] for v in vals)

def do_day(day, table):
    date = day.strftime("%Y-%m-%d")
    start, periods = day_periods(day)
    prefixes = tuple(p for s in table.values() for p in s["bmu"])
    with ThreadPoolExecutor(max_workers=6) as ex:
        res = list(ex.map(lambda x: half_hour(date, x[0], x[1], table, prefixes), periods))
    site = lambda u: next((k for k, s in table.items() if any(u.startswith(p) for p in s["bmu"])), None)
    n = len(periods); hours = (n + 1) // 2
    pn = {}; cu = {}; money = {}
    for i, (p, c, price) in enumerate(res):
        for u, mw in p.items():
            k = site(u)
            if k: pn.setdefault(k, [0.0] * n)[i] += mw
        for u, mw in c.items():
            k = site(u)
            if not k or table[k]["t"] not in ("ow", "nw"):
                continue  # the tracker covers wind farms, like the live map
            cu.setdefault(k, [0.0] * n)[i] += mw
            money[k] = money.get(k, 0.0) + mw * 0.5 * price.get(u, 0.0)
    hourly = lambda a: [sum(a[j:j + 2]) / len(a[j:j + 2]) for j in range(0, n, 2)]
    stations = {k: [pack(hourly(v)), pack(hourly(cu.get(k, [0.0] * n)))] for k, v in pn.items() if max(v) > 1}
    sites = {k: [round(sum(v) * 0.5), round(money.get(k, 0.0))] for k, v in cu.items() if sum(v) * 0.5 >= 1}
    total = {"d": date, "mwh": sum(s[0] for s in sites.values()), "gbp": sum(s[1] for s in sites.values()), "s": sites}
    return total, {"d": date, "from": start.strftime("%Y-%m-%dT%H:%MZ"), "h": hours, "s": stations}

def main():
    table = site_table()
    cur = load(CUR, {"since": None, "days": []})
    sta = load(STA, {"unit": UNIT, "days": []})
    have = {d["d"] for d in cur["days"]}
    today = datetime.now(UK).date()
    back = 7 if len(cur["days"]) < 3 else 2
    for k in range(1, back + 1):
        day = today - timedelta(days=k)
        if day.strftime("%Y-%m-%d") in have:
            continue
        try:
            t0 = time.time(); total, st = do_day(day, table)
            cur["days"].append(total); sta["days"].append(st)
            print(f"elexon: {total['d']} turned down {total['mwh']:,} MWh, paid £{total['gbp']:,}, {len(st['s'])} stations ({time.time()-t0:.0f} s)")
        except Exception as e:
            print("elexon: skipped", day, "-", e, file=sys.stderr)
    cur["days"] = sorted(cur["days"], key=lambda d: d["d"])[-KEEP_TOTAL_DAYS:]
    for d in cur["days"][:-KEEP_SITES_DAYS]:
        d.pop("s", None)
    cur["since"] = cur["days"][0]["d"] if cur["days"] else None
    sta["days"] = sorted(sta["days"], key=lambda d: d["d"])[-KEEP_STATION_DAYS:]
    CUR.write_text(json.dumps(cur, separators=(",", ":")))
    STA.write_text(json.dumps(sta, separators=(",", ":")))

if __name__ == "__main__":
    main()
