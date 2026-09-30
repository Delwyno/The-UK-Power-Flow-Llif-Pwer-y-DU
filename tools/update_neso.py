#!/usr/bin/env python3
"""Connection queue and official constraint costs, from the NESO data portal.

  data/queue.json        the Transmission Entry Capacity (TEC) register, grouped by connection
                         site and placed on the map (loaded by the page when the queue opens)
  data/constraints.json  NESO's daily constraint costs and volumes, used to cross-check the
                         map's own curtailment tracker

Each part is independent: if one fails, the previous file is kept.
Contains data from the NESO Data Portal, NESO Open Data Licence.
"""
import json, re, statistics, sys, time, urllib.parse, urllib.request
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
API = "https://api.neso.energy/api/3/action"
TEC_DATASET, TEC_RESOURCE = "transmission-entry-capacity-tec-register", "17becbab-e3e8-473f-b303-3806f43a6a10"
CON_DATASET = "constraint-breakdown"

def get(action, **q):
    url = f"{API}/{action}?" + urllib.parse.urlencode(q)
    for k in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "uk-power-map/1.0", "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=90) as r:
                x = json.load(r)
            if not x.get("success"):
                raise IOError(x.get("error"))
            return x["result"]
        except Exception:
            if k == 2:
                raise
            time.sleep(3 + 5 * k)

def records(resource):
    out, off = [], 0
    while True:
        r = get("datastore_search", resource_id=resource, limit=10000, offset=off)
        out += r["records"]; off += len(r["records"])
        if not r["records"] or off >= r.get("total", off):
            return out

def field(row, *names):
    """Read a column by any of its names, ignoring case and spacing (NESO renames columns now and then)."""
    low = {re.sub(r"\W", "", k).lower(): v for k, v in row.items()}
    for n in names:
        v = low.get(re.sub(r"\W", "", n).lower())
        if v not in (None, ""):
            return v
    return None

def num(v):
    try:
        return float(str(v).replace(",", ""))
    except Exception:
        return 0.0

def when(v):
    """Contracted date as (year, 'YYYY-MM'); the register mixes dd/mm/yyyy and ISO dates."""
    s = str(v or "").strip()
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%d-%m-%Y"):
        try:
            d = datetime.strptime(s[:19] if "T" in s else s[:10], fmt)
            return d.year, d.strftime("%Y-%m")
        except Exception:
            pass
    return None, None

# ---------------------------------------------------------------- places
STOP = {"substation", "sub", "station", "kv", "gsp", "grid", "supply", "point", "main", "switching", "converter",
        "the", "new", "and", "tee", "hvdc", "cable", "sealing", "end", "generating", "power", "site", "supergrid"}

def norm(s):
    s = str(s).lower().replace("&", " and ").replace("'", "").replace("’", "")
    s = re.sub(r"\d+(\.\d+)?\s*/?\s*\d*\s*kv", " ", s); s = re.sub(r"\(.*?\)", " ", s); s = re.sub(r"[^a-z ]", " ", s)
    return " ".join(w for w in s.split() if w not in STOP)

def places():
    """Name index from the OpenStreetMap gazetteer, the mapped substations and power stations, and curated sites."""
    idx = {}
    def add(name, lat, lon, rank):
        k = norm(name)
        if k and lat and lon:
            cur = idx.get(k)
            if not cur or rank > cur[2]:
                idx[k] = (round(lat, 4), round(lon, 4), rank)
    for f, conv in [("gazetteer.json", lambda r: (r[0], r[1], r[2], 1 + r[3] / 1000)),
                    ("subs.json", lambda r: (r[0], r[2], r[3], 2 + r[1] / 1000)),
                    ("plants.json", lambda r: (r[0], r[2], r[3], 0.5))]:
        try:
            for r in json.loads((DATA / f).read_text()):
                add(*conv(r))
        except Exception:
            pass
    try:
        src = (ROOT / "src" / "sites.js").read_text(encoding="utf-8")
        for n, la, lo in re.findall(r"n:'([^']+)'[^\n]*?c:\[\s*(-?[\d.]+)\s*,\s*(-?[\d.]+)\s*\]", src):
            add(n, float(la), float(lo), 3)
    except Exception:
        pass
    return idx

def locate(site, idx):
    k = norm(site)
    if not k:
        return None
    if k in idx:
        return idx[k]
    hits = [v for kk, v in idx.items() if kk.startswith(k + " ") or k.startswith(kk + " ")]
    if hits:
        return max(hits, key=lambda v: v[2])
    return None

def wales_test():
    """Point-in-polygon test against the Wales outline in data/geo.json. The outline is simplified,
    so a point just off the Welsh coast (within about 5 km) also counts, unless it lies in England."""
    try:
        g = json.loads((DATA / "geo.json").read_text())
        shapes = {}
        for f in g["features"]:
            n = f["properties"].get("n")
            if n in ("Wales", "England"):
                geo = f["geometry"]
                shapes.setdefault(n, []).extend(geo["coordinates"] if geo["type"] == "MultiPolygon" else [geo["coordinates"]])
        assert "Wales" in shapes
    except Exception:
        return lambda lat, lon: False
    def inside(polys, lat, lon):
        for poly in polys:
            ring, hit = poly[0], False
            for (x1, y1), (x2, y2) in zip(ring, ring[1:] + ring[:1]):
                if (y1 > lat) != (y2 > lat) and lon < (x2 - x1) * (lat - y1) / (y2 - y1) + x1:
                    hit = not hit
            if hit:
                return True
        return False
    W, E = shapes["Wales"], shapes.get("England", [])
    def test(lat, lon):
        if inside(W, lat, lon):
            return True
        if inside(E, lat, lon):
            return False
        return any(inside(W, lat + a, lon + b) for a, b in ((.045, 0), (-.045, 0), (0, .07), (0, -.07)))
    return test

# ---------------------------------------------------------------- the queue
def kind(plant):
    """Map the register's plant type onto the map's technology codes (the first listed type wins)."""
    p = str(plant or "").lower()
    for part in re.split(r"[;,/]| and ", p) or [p]:
        part = part.strip()
        if not part:
            continue
        if "wind" in part:
            return "ow" if "offshore" in part else "nw"
        if "pv" in part or "solar" in part: return "so"
        if "pump" in part: return "hy"
        if "storage" in part or "batter" in part: return "bat"
        if "nuclear" in part: return "nu"
        if "interconnector" in part: return "ic"
        if any(w in part for w in ("ccgt", "ocgt", "gas", "reciprocat", "chp")): return "gas"
        if "hydro" in part: return "hy"
        if "biomass" in part or "waste" in part: return "bio"
        if "tidal" in part or "wave" in part: return "ti"
        if "demand" in part: return "dem"
    return "oth"

STATUS = [("built", "B"), ("construct", "C"), ("commission", "C"), ("approved", "A"), ("awaiting", "W"), ("scoping", "S")]
def status(s):
    s = str(s or "").lower()
    return next((c for k, c in STATUS if k in s), "")

def update_queue():
    try:
        pk = get("package_show", id=TEC_DATASET)
        res = next((r["id"] for r in pk["resources"] if r.get("datastore_active") and "csv" in str(r.get("format", "")).lower()), TEC_RESOURCE)
    except Exception:
        res = TEC_RESOURCE
    rows = records(res)
    if len(rows) < 100:
        raise ValueError(f"only {len(rows)} rows")
    idx, in_wales = places(), wales_test()
    seen, sites, connected, unmatched = set(), {}, {}, {}
    today = date.today().strftime("%Y-%m")
    for r in rows:
        site = (field(r, "Connection Site") or "").strip()
        name = (field(r, "Project Name") or "").strip()
        pid = field(r, "Project ID") or f"{name}|{site}"
        stage = str(field(r, "Stage") or "")
        inc, conn = num(field(r, "MW Increase / Decrease", "MW Increase/Decrease")), num(field(r, "MW Connected"))
        st = status(field(r, "Project Status"))
        y, ym = when(field(r, "MW Effective From"))
        code = kind(field(r, "Plant Type"))
        if not site:
            continue
        if conn > 0:
            connected[(site, pid)] = max(connected.get((site, pid), 0), conn)
        if inc <= 0 or st == "B":
            continue
        key = (pid, stage, round(inc, 1), ym)
        if key in seen:  # the register repeats some capacity across stages and technologies
            continue
        seen.add(key)
        s = sites.setdefault(site, {"q": 0.0, "n": 0, "types": {}, "years": [], "st": {}, "p": [], "host": field(r, "HOST TO") or "", "late": 0.0})
        s["q"] += inc; s["n"] += 1; s["types"][code] = s["types"].get(code, 0) + inc
        s["st"][st] = s["st"].get(st, 0) + inc
        if y: s["years"] += [y]
        if ym and ym < today: s["late"] += inc
        s["p"].append([name[:60], round(inc), code, ym or "", st])
    for (site, _), mw in connected.items():
        if site in sites: sites[site]["conn"] = sites[site].get("conn", 0) + mw
    out, tot_types, tot_years, tot_st = [], {}, {}, {}
    for site, s in sorted(sites.items(), key=lambda kv: -kv[1]["q"]):
        loc = locate(site, idx)
        if not loc:
            unmatched[site] = round(s["q"])
        lat, lon = (loc[0], loc[1]) if loc else (None, None)
        yrs = sorted(s["years"])
        out.append([site[:60], lat, lon, s["host"], round(s["q"]), round(s.get("conn", 0)), s["n"],
                    {k: round(v) for k, v in sorted(s["types"].items(), key=lambda kv: -kv[1])},
                    yrs[0] if yrs else None, int(statistics.median(yrs)) if yrs else None,
                    1 if loc and in_wales(lat, lon) else 0,
                    sorted(s["p"], key=lambda p: -p[1])[:10], round(s["late"])])
        for k, v in s["types"].items(): tot_types[k] = tot_types.get(k, 0) + v
        for k, v in s["st"].items(): tot_st[k] = tot_st.get(k, 0) + v
        for p in s["p"]:
            yb = p[3][:4] if p[3] else "?"
            tot_years[yb] = tot_years.get(yb, 0) + p[1]
    q = sum(x[4] for x in out)
    doc = {"updated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ"), "rows": len(rows),
           "tot": {"q": round(q), "n": sum(x[6] for x in out), "sites": len(out), "types": {k: round(v) for k, v in tot_types.items()},
                   "years": {k: round(v) for k, v in sorted(tot_years.items())}, "st": {k: round(v) for k, v in tot_st.items()},
                   "late": round(sum(x[12] for x in out)), "unplaced": round(sum(unmatched.values()))},
           "sites": out}
    (DATA / "queue.json").write_text(json.dumps(doc, separators=(",", ":"), ensure_ascii=False))
    print(f"queue: {len(rows)} register rows, {doc['tot']['n']} queued projects, {q/1000:.0f} GW at {len(out)} sites; "
          f"{len(unmatched)} sites ({doc['tot']['unplaced']/1000:.1f} GW) not placed on the map")
    if unmatched:
        print("  not placed:", "; ".join(f"{k} ({v} MW)" for k, v in sorted(unmatched.items(), key=lambda kv: -kv[1])[:25]))

# ---------------------------------------------------------------- official constraint costs
def fy(d):
    y = d.year if d.month >= 4 else d.year - 1
    return f"{y}-{y + 1}"

def update_constraints():
    pk = get("package_show", id=CON_DATASET)
    today = date.today(); want = {fy(today), fy(date(today.year - 1, today.month, 1))}
    res = [r for r in pk["resources"] if r.get("datastore_active") and any(w in str(r.get("name", "")) for w in want)]
    if not res:
        raise ValueError("no constraint breakdown resource for " + ", ".join(sorted(want)))
    days = {}
    for r in res:
        for row in records(r["id"]):
            d = str(field(row, "Date") or "")[:10]
            if not re.match(r"\d{4}-\d{2}-\d{2}", d):
                continue
            costs = [num(field(row, c)) for c in ("Reducing largest loss cost", "Increasing system inertia cost", "Voltage constraints cost", "Thermal constraints cost")]
            days[d] = [d, round(num(field(row, "Thermal constraints cost"))), round(num(field(row, "Thermal constraints volume"))), round(sum(costs))]
    rows = sorted(days.values())[-400:]
    if not rows:
        raise ValueError("no rows")
    (DATA / "constraints.json").write_text(json.dumps({"updated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ"),
        "cols": ["date", "thermal_cost_gbp", "thermal_volume_mwh", "all_constraints_cost_gbp"], "days": rows}, separators=(",", ":")))
    print(f"constraints: {len(rows)} days, latest {rows[-1][0]}")

def main():
    for name, fn in [("queue", update_queue), ("constraints", update_constraints)]:
        try:
            fn()
        except Exception as e:
            print(name, "not updated -", e, file=sys.stderr)

if __name__ == "__main__":
    main()
