#!/usr/bin/env python3
"""Rebuild the OpenStreetMap-derived data and the power routes.

Outputs (in data/):
  gridlines.json   400/275/220 kV and HVDC lines, simplified for display
  subs.json        substations of 220 kV and above
  windareas.json   offshore wind farm outlines
  plants.json      smaller generators not in src/sites.js
  routes.json      each curated site's route along the real grid
  xchk.json        curated capacities cross-checked against OpenStreetMap

Usage:
  python tools/update_osm.py                    # downloads the UK extract from Geofabrik (~2.3 GB)
  python tools/update_osm.py --pbf uk.osm.pbf   # uses a local extract
  python tools/update_osm.py --out /tmp/test    # writes somewhere other than data/

Needs: pyosmium, shapely, numpy, scipy, and Node.js (to read src/sites.js).
"""
import argparse, json, math, os, re, subprocess, sys, tempfile, time, urllib.request
from pathlib import Path
import numpy as np
import osmium
from scipy.spatial import cKDTree
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import dijkstra
from shapely.geometry import LineString, Point, Polygon, shape
from shapely.ops import unary_union

ROOT = Path(__file__).resolve().parent.parent
PBF_URL = "https://download.geofabrik.de/europe/united-kingdom-latest.osm.pbf"
R = 6371.0

# ---------------------------------------------------------------- helpers
def volts(v): return [int(x) for x in re.findall(r"\d{5,7}", v or "")]
def hav(a, b):
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 2 * R * math.asin(math.sqrt(h))
def xyz(lat, lon):
    la, lo = math.radians(lat), math.radians(lon)
    return (math.cos(la) * math.cos(lo), math.cos(la) * math.sin(lo), math.sin(la))
def centroid(pts): return [sum(a for a, b in pts) / len(pts), sum(b for a, b in pts) / len(pts)]
def mw(t):
    m = re.match(r"\s*([\d.]+)\s*(GW|MW|kW|W)?", t.get("plant:output:electricity", ""), re.I)
    if not m: return None
    try: x = float(m.group(1))
    except ValueError: return None
    return x * {"gw": 1000, "mw": 1, "kw": .001, "w": 1e-6}[(m.group(2) or "W").lower()]
SRC = {"solar": "so", "wind": "nw", "hydro": "hy", "battery": "bat", "gas": "gas", "diesel": "gas", "oil": "gas",
       "oil;gas": "gas", "biogas": "bio", "biomass": "bio", "waste": "bio", "landfill_gas": "bio", "biomass;gas": "bio",
       "biomass;waste": "bio", "waste;biomass": "bio", "biofuel": "bio", "nuclear": "nu", "tidal": "ti"}
STOP = {"wind", "farm", "offshore", "onshore", "power", "station", "the", "energy", "park", "extension", "solar",
        "hydro", "plant", "scheme", "b", "c", "1", "&"}
def key(n):
    w = [x for x in re.split(r"[^a-z0-9]+", (n or "").lower()) if x and x not in STOP]
    return w[0] if w else ""
grp = lambda t: {"ow": "w", "nw": "w"}.get(t, t)

def load_sites():
    js = (ROOT / "src" / "sites.js").read_text() + "\nconsole.log(JSON.stringify({P,SITES,LINKS,GRID}));"
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as f: f.write(js)
    out = subprocess.run(["node", f.name], capture_output=True, text=True, check=True).stdout
    os.unlink(f.name)
    return json.loads(out)

# ---------------------------------------------------------------- extraction
def extract(pbf, work, index="flex_mem"):
    t0 = time.time()
    lines, subs, plants, wind = [], [], [], []
    rel_plant, rel_nodes, rel_wind = {}, {}, {}
    for o in osmium.FileProcessor(pbf, osmium.osm.RELATION).with_filter(osmium.filter.KeyFilter("power")):
        t = o.tags
        if t.get("power") != "plant": continue
        i = len(plants); plants.append({"id": "r%d" % o.id, "tags": dict(t), "pts": []})
        if "wind" in t.get("plant:source", ""):
            j = len(wind); wind.append({"n": t.get("name"), "rings": []})
        else: j = None
        for m in o.members:
            if m.type == "w":
                rel_plant[m.ref] = i
                if j is not None and m.role in ("outer", ""): rel_wind[m.ref] = j
            elif m.type == "n": rel_nodes[m.ref] = i
    print(f"  relations: {len(plants)} plants ({time.time()-t0:.0f}s)", flush=True)
    idx = os.path.join(work, "nodes.idx")
    imap = (lambda: osmium.index.create_map(index)) if index == "flex_mem" else (lambda: osmium.index.create_map("sparse_file_array," + idx))
    need = set(rel_plant)
    fp = osmium.FileProcessor(pbf).with_locations(imap()) \
        .with_filter(osmium.filter.KeyFilter("power"))
    for o in fp:
        t = o.tags; p = t.get("power")
        if o.is_node():
            ll = (o.location.lat, o.location.lon)
            if o.id in rel_nodes: plants[rel_nodes[o.id]]["pts"].append(ll)
            if p == "plant": plants.append({"id": "n%d" % o.id, "tags": dict(t), "c": list(ll)})
            elif p == "substation":
                v = volts(t.get("voltage"))
                if v and max(v) >= 220000:
                    subs.append({"n": t.get("name"), "v": max(v), "c": list(ll), "id": "n%d" % o.id, "op": t.get("operator")})
        elif o.is_way():
            try: pts = [(n.lat, n.lon) for n in o.nodes if n.location.valid()]
            except Exception: continue
            if not pts: continue
            v = volts(t.get("voltage"))
            if p in ("line", "cable") and v and max(v) >= 220000:
                lines.append({"v": max(v), "pts": pts, "dc": t.get("frequency") == "0" or max(v) in (320000, 450000, 515000, 525000, 600000)})
            elif p == "substation" and v and max(v) >= 220000:
                subs.append({"n": t.get("name"), "v": max(v), "c": centroid(pts), "id": "w%d" % o.id, "op": t.get("operator")})
            elif p == "plant":
                plants.append({"id": "w%d" % o.id, "tags": dict(t), "c": centroid(pts)})
                if "wind" in t.get("plant:source", "") and pts[0] == pts[-1]: wind.append({"n": t.get("name"), "rings": [pts]})
            if o.id in need:
                plants[rel_plant[o.id]]["pts"].extend(pts[::max(1, len(pts) // 8)])
                if o.id in rel_wind: wind[rel_wind[o.id]]["rings"].append(pts)
                need.discard(o.id)
    print(f"  main pass: {len(lines)} lines, {len(subs)} substations ({time.time()-t0:.0f}s)", flush=True)
    if need:  # untagged member ways of plant relations
        fp3 = osmium.FileProcessor(pbf, osmium.osm.NODE | osmium.osm.WAY) \
            .with_locations(imap()) \
            .with_filter(osmium.filter.EntityFilter(osmium.osm.WAY)).with_filter(osmium.filter.IdFilter(need))
        for o in fp3:
            try: pts = [(n.lat, n.lon) for n in o.nodes if n.location.valid()]
            except Exception: continue
            plants[rel_plant[o.id]]["pts"].extend(pts[::max(1, len(pts) // 8)])
            if o.id in rel_wind: wind[rel_wind[o.id]]["rings"].append(pts)
    if os.path.exists(idx): os.remove(idx)
    print(f"  extraction done ({time.time()-t0:.0f}s)", flush=True)
    return lines, subs, plants, wind

# ---------------------------------------------------------------- outputs
def build(lines, subs, plants, wind, D, out):
    GEO = json.loads((ROOT / "data" / "geo.json").read_text())
    land = unary_union([shape(f["geometry"]) for f in GEO["features"] if f["properties"]["uk"]])
    wales = [shape(f["geometry"]) for f in GEO["features"] if f["properties"]["n"] == "Wales"][0].buffer(0.03)
    P = D["P"]
    dump = lambda name, obj: (out / name).write_text(json.dumps(obj, separators=(",", ":"), ensure_ascii=False))

    # display lines by class
    def cls(l):
        if l["dc"] and l["v"] != 400000: return "dc"
        if l["v"] >= 400000: return "400" if not l["dc"] else "dc"
        return "275" if l["v"] >= 275000 else "220"
    disp = {}
    for c in ["400", "275", "220", "dc"]:
        ls = [LineString([(p[1], p[0]) for p in l["pts"]]) for l in lines if cls(l) == c and len(l["pts"]) > 1]
        if not ls: disp[c] = []; continue
        u = unary_union(ls).simplify(0.0015)
        disp[c] = [[[round(y, 3), round(x, 3)] for x, y in g.coords] for g in getattr(u, "geoms", [u]) if g.length > 0.003]
    dump("gridlines.json", disp)

    # substations (deduplicated)
    so = []
    for s in sorted(subs, key=lambda s: -s["v"]):
        c = s["c"]
        if any(abs(c[0] - o[2]) < 0.004 and abs(c[1] - o[3]) < 0.006 for o in so): continue
        so.append([(s["n"] or "")[:50], s["v"] // 1000, round(c[0], 4), round(c[1], 4), (s["op"] or "")[:40], s["id"]])
    dump("subs.json", so)

    # offshore wind areas
    W = []
    for w in wind:
        polys = []
        for r in w["rings"]:
            if len(r) >= 4:
                try:
                    pg = Polygon([(b, a) for a, b in r]).buffer(0)
                    if not pg.is_empty: polys.append(pg)
                except Exception: pass
        if not polys: continue
        u = unary_union(polys)
        if land.contains(u.centroid) or u.area < 0.001: continue
        u = u.simplify(0.003)
        rings = [[[round(y, 3), round(x, 3)] for x, y in g.exterior.coords] for g in getattr(u, "geoms", [u]) if g.area > 0.0002]
        if rings: W.append([(w["n"] or "")[:50], rings, ""])
    dump("windareas.json", W)

    # routing graph from 400/275 kV AC lines
    nodes, coords, E, ends = {}, [], [], []
    def nid(p):
        k = (round(p[0], 5), round(p[1], 5))
        if k not in nodes: nodes[k] = len(coords); coords.append(k)
        return nodes[k]
    for l in lines:
        if l["v"] not in (400000, 275000) or l["dc"]: continue
        ids = [nid(p) for p in l["pts"]]
        for a, b in zip(ids, ids[1:]):
            if a != b: E.append((a, b, hav(coords[a], coords[b])))
        ends += [ids[0], ids[-1]]
    C = np.array([xyz(*c) for c in coords]); tree = cKDTree(C)
    for e in set(ends):
        for j in tree.query_ball_point(C[e], 1.2 / R):
            if j != e: E.append((e, j, hav(coords[e], coords[j]) + 0.2))
    n = len(coords)
    G = coo_matrix(([w for *_, w in E] * 2, ([a for a, b, w in E] + [b for a, b, w in E], [b for a, b, w in E] + [a for a, b, w in E])), shape=(n, n)).tocsr()
    cache = {}
    def nearest(p, maxkm=14):
        d, i = tree.query(xyz(*p)); return i if d * R <= maxkm else None
    def path(a, b):
        ia, ib = nearest(a), nearest(b)
        if ia is None or ib is None or ia == ib: return None
        if ia not in cache: cache[ia] = dijkstra(G, indices=ia, return_predecessors=True)
        dist, pred = cache[ia]
        if not np.isfinite(dist[ib]) or dist[ib] > 2.2 * hav(a, b) + 25: return None
        seq, k = [], ib
        while k != ia and k >= 0: seq.append(coords[k]); k = pred[k]
        seq.append(coords[ia]); seq.reverse()
        return [list(a)] + [list(p) for p in seq] + [list(b)]
    def simp(pts, tol=0.004):
        if len(pts) < 3: return pts
        return [[round(y, 3), round(x, 3)] for x, y in LineString([(p[1], p[0]) for p in pts]).simplify(tol).coords]
    pc = lambda k: k if isinstance(k, list) else [P[k][1], P[k][2]]
    def route(pts, first_straight=False, sea=()):
        res = []
        for i in range(len(pts) - 1):
            a, b = pts[i], pts[i + 1]
            seg = None if (i == 0 and first_straight) or i in sea else path(pc(a), pc(b))
            seg = simp(seg) if seg else [pc(a), pc(b)]
            res += seg if not res else seg[1:]
        return res
    ROUTES = {}
    for s in D["SITES"]:
        main = [s["c"]] + s["r"] + [s["h"]]
        rr = {"m": route(main, s["t"] in ("ow", "ti"), set(range(len(main))) if s.get("local") else ())}
        if s.get("sur"): rr["s"] = route([s["h"]] + s["sur"])
        ROUTES[s["id"] + "|" + s["t"]] = rr
    for l in D["LINKS"]:
        via = l.get("via", [])
        if l["dir"] == "export":
            pts = [l["h"], l["g"]] + via[::-1] + [l["a"], l["fh"]]; sea = set(range(1, len(pts) - 1))
        else:
            pts = [l["a"]] + via + [l["g"], l["h"]]; sea = set(range(0, len(pts) - 2))
        ROUTES[l["id"] + "|ic"] = {"m": route(pts, sea=sea)}
    dump("routes.json", ROUTES)

    # smaller plants, excluding curated sites
    cur = [(s["t"], s["c"], key(s["n"])) for s in D["SITES"]]
    pl = []
    def ptc(p): return p.get("c") or (centroid(p["pts"]) if p.get("pts") else None)
    for p in plants:
        t = p["tags"]; typ = SRC.get(t.get("plant:source", ""))
        c = ptc(p)
        if not typ or not c: continue
        m = mw(t); pt = Point(c[1], c[0]); inw = wales.contains(pt)
        if typ == "nw" and not land.contains(pt): typ = "ow"
        if (m is None or m < 1) and not inw: continue
        if m is not None and m < 0.5: continue
        nm = t.get("name") or t.get("name:en") or ""
        if any(grp(ct) == grp(typ) and hav(c, cc) < (9 if typ == "ow" else 3.5) for ct, cc, cn in cur): continue
        if key(nm) and any(key(nm) == cn and hav(c, cc) < 60 for ct, cc, cn in cur): continue
        pl.append([nm[:60], typ, round(c[0], 4), round(c[1], 4), round(m, 1) if m else None, 1 if inw else 0,
                   t.get("operator", "")[:40], t.get("name:cy", "")[:60], p["id"]])
    dump("plants.json", pl)

    # cross-check curated capacities against OSM (name match only)
    X = {}
    for s in D["SITES"]:
        if s["on"] > 2026: continue
        best = None
        for p in plants:
            t = p["tags"]; typ = SRC.get(t.get("plant:source", "")); c = ptc(p)
            if not typ or not c: continue
            if typ == "nw" and not land.contains(Point(c[1], c[0])): typ = "ow"
            if grp(typ) != grp(s["t"]): continue
            d = hav(c, s["c"])
            if not (key(t.get("name", "")) and key(t.get("name", "")) == key(s["n"]) and d < 60): continue
            m = mw(t)
            if not m or not (0.33 < m / s["mw"] < 3): continue
            if best is None or d < best[0]: best = (d, p["id"], t.get("name", ""), m)
        if best: X[s["id"]] = [best[1], round(best[3], 1), best[2][:60]]
    dump("xchk.json", X)
    print(f"  wrote {len(disp['400'])+len(disp['275'])} line groups, {len(so)} substations, {len(W)} wind areas, "
          f"{len(pl)} smaller sites, {len(ROUTES)} routes, {len(X)} cross-checks", flush=True)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pbf", help="local .osm.pbf instead of downloading")
    ap.add_argument("--out", default=str(ROOT / "data"))
    a = ap.parse_args()
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    work = tempfile.mkdtemp()
    pbf = a.pbf
    if not pbf:
        pbf = os.path.join(work, "uk.osm.pbf")
        print("downloading", PBF_URL, flush=True)
        urllib.request.urlretrieve(PBF_URL, pbf)
    D = load_sites()
    # Pre-filter to power features with osmium-tool (keeps referenced nodes), so the
    # node-location index fits in memory. Falls back to a disk index without it.
    small, index = pbf, "sparse_file_array"
    try:
        small = os.path.join(work, "power.osm.pbf")
        subprocess.run(["osmium", "tags-filter", pbf, "nwr/power=line,cable,substation,plant,generator",
                        "-o", small, "--overwrite"], check=True)
        index = "flex_mem"
        print("  pre-filtered with osmium-tool", flush=True)
    except (FileNotFoundError, subprocess.CalledProcessError):
        small = pbf
        print("  osmium-tool not found; using a disk index (needs ~8 GB free)", flush=True)
    lines, subs, plants, wind = extract(small, work, index)
    if len(lines) < 1000 and not a.pbf:
        sys.exit("Too few power lines found; not overwriting data")
    build(lines, subs, plants, wind, D, out)

if __name__ == "__main__":
    main()
