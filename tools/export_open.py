#!/usr/bin/env python3
"""Publish the map's own datasets as CSV files in data/open/, with an index.

Runs after the other refresh scripts. Every file has a stable address on the published site,
for example https://delwyno.github.io/UK-Energy-Generation-Map/data/open/curtailment-daily.csv
"""
import csv, io, json, re
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA, OUT = ROOT / "data", ROOT / "data" / "open"
SITE = "https://delwyno.github.io/UK-Energy-Generation-Map/"
B64 = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
ELX = "Contains BMRS data © Elexon Limited copyright and database right"
NESO = "NESO Open Data Licence"
NAME, AUTHOR = "The UK Power Flow", "Daniel Elwyn Thomas"
CC = "CC BY 4.0"
ODBL = "ODbL 1.0"
CREDIT = f"Data: {NAME} ({AUTHOR}), {CC}. {SITE}"
CREDIT_ODBL = f"Data: {NAME} ({AUTHOR}), {ODBL}. Contains information from OpenStreetMap contributors. {SITE}"

def load(name, default=None):
    try:
        return json.loads((DATA / name).read_text(encoding="utf-8"))
    except Exception:
        return default

def unpack(s, unit):
    return [((B64.index(s[i]) << 6) | B64.index(s[i + 1])) * unit for i in range(0, len(s), 2)]

def names():
    src = (ROOT / "src" / "sites.js").read_text(encoding="utf-8")
    return dict(re.findall(r"\{id:'([^']+)'[^\n]*?n:'([^']+)'", src))

def write(fname, head, rows):
    buf = io.StringIO(); w = csv.writer(buf, lineterminator="\n"); w.writerow(head); w.writerows(rows)
    (OUT / fname).write_text(buf.getvalue(), encoding="utf-8")
    return len(rows)

def main():
    OUT.mkdir(exist_ok=True)
    N, SUB = names(), (load("subsidy.json", {}) or {}).get("farms", {})
    index = []
    def add(fname, title, desc, source, head, rows, licence=CC):
        n = write(fname, head, rows)
        index.append({"file": fname, "url": SITE + "data/open/" + fname, "title": title, "description": desc, "rows": n, "columns": head, "source": source,
                      "licence": licence, "credit": CREDIT_ODBL if licence == ODBL else CREDIT})

    cur = load("curtail.json", {"days": []})
    add("curtailment-daily.csv", "Wind turned down, daily",
        "Energy the tracked wind farms were paid to turn down each day (UK days), the payments, and the CO2 if the lost power were replaced by gas at 394 g/kWh.",
        ELX, ["date", "turned_down_mwh", "payments_gbp", "co2_if_replaced_by_gas_tonnes"],
        [[d["d"], d["mwh"], d["gbp"], round(d["mwh"] * 0.394)] for d in cur["days"]])
    rows = []
    for d in cur["days"]:
        for k, (mwh, gbp) in (d.get("s") or {}).items():
            f = SUB.get(k, {})
            rows.append([d["d"], N.get(k, k), k, f.get("s", ""), mwh, gbp, round(gbp / mwh, 2) if mwh else ""])
    add("curtailment-by-windfarm.csv", "Wind turned down, by wind farm and day",
        "Each tracked wind farm's daily turn-down, payments and switch-off price, with its support scheme (ro = Renewables Obligation, ic = 2014 investment contract, cfd = auction Contract for Difference, part = CfD on part of the capacity).",
        ELX, ["date", "wind_farm", "site_id", "scheme", "turned_down_mwh", "payments_gbp", "gbp_per_mwh"], rows)

    sta = load("stations.json", {"days": [], "unit": 5})
    rows = []
    for d in sta["days"]:
        t0 = datetime.strptime(d["from"], "%Y-%m-%dT%H:%MZ").replace(tzinfo=timezone.utc)
        for k, (pn, cu) in d["s"].items():
            a, b = unpack(pn, sta["unit"]), unpack(cu, sta["unit"])
            for i in range(d["h"]):
                rows.append([(t0 + timedelta(hours=i)).strftime("%Y-%m-%dT%H:%MZ"), N.get(k, k), k, a[i], b[i]])
    rows.sort()
    add("station-output-hourly.csv", "Station output, hourly (last 14 days)",
        "Hourly average of each mapped station's physical notification (the output it planned) and the part the grid operator paid it to turn down, in MW, 5 MW resolution.",
        ELX, ["hour_start_utc", "station", "site_id", "notified_mw", "turned_down_mw"], rows)

    day = load("daily.json", {"days": []})
    add("carbon-daily.csv", "Carbon intensity, daily",
        "Daily average and lowest carbon intensity (gCO2/kWh, measured where available), hours at or below 50 g, the highest wind and solar shares, and Wales's average wind share.",
        NESO + " (Carbon Intensity API)", ["date", "average_gco2_kwh", "lowest_gco2_kwh", "lowest_at_utc", "hours_at_or_below_50g", "longest_spell_at_or_below_50g_hours",
         "max_wind_share_pct", "max_solar_share_pct", "wales_avg_wind_share_pct", "wales_hours_wind_above_80pct"],
        [[d["d"], d.get("ci"), d["min"][0], d["min"][1], d.get("h50"), d.get("run50"), (d.get("wind") or [None])[0], (d.get("solar") or [None])[0],
          (d.get("wales") or {}).get("wind"), (d.get("wales") or {}).get("h80")] for d in day["days"]])

    dig = load("digest.json", {"weeks": []})
    add("weekly-digest.csv", "Weekly summary",
        "One row per Monday-to-Sunday week (UK time): average and extreme carbon intensity, hours at or below 50 g and average generation shares.",
        NESO + " (Carbon Intensity API)", ["week_start", "average_gco2_kwh", "lowest_gco2_kwh", "highest_gco2_kwh", "hours_at_or_below_50g", "wind_pct", "solar_pct", "gas_pct", "nuclear_pct", "imports_pct", "wales_average_gco2_kwh"],
        [[w["start"], w["ci"], w["min"][0], w["max"][0], w["h50"]] + [(w.get("mix") or {}).get(f) for f in ("wind", "solar", "gas", "nuclear", "imports")] + [(w.get("reg") or {}).get("17")] for w in dig["weeks"]])

    acc = load("accuracy.json", {"days": []})
    add("forecast-accuracy.csv", "Forecast accuracy",
        "How NESO's 24-hour national carbon intensity forecast, saved each morning, compared with the measured figures: mean absolute error, bias, share within 20 g, and how far the forecast's cleanest 3-hour window was from the true cleanest.",
        NESO + " (Carbon Intensity API)", ["date", "mean_abs_error_g", "bias_g", "within_20g_pct", "cleanest_3h_window_gap_g", "half_hours"],
        [[d["d"], d["mae"], d["bias"], d["w20"], d["gap"], d["n"]] for d in acc["days"]])

    his = load("history.json", {})
    rec = his.get("rec") or {}
    add("records.csv", "Britain's electricity records",
        "All-time records from NESO's historic generation mix (generation-based carbon intensity), since 2009.",
        NESO + " (historic generation mix)", ["record", "value", "unit", "when"],
        [[k, v[0], u, v[1]] for k, u in (("low", "gCO2/kWh"), ("day", "gCO2/kWh, daily average"), ("wind", "% of generation"), ("solar", "% of generation"), ("run50", "hours at or below 50 g")) if (v := rec.get(k))])

    q = load("queue.json")
    if q:
        add("connection-queue-by-site.csv", "Connection queue, by connection site",
            "Capacity with a contract to connect at each transmission connection site (NESO TEC register), repeated rows counted once, with location where the map could place it.",
            NESO + " (TEC register); locations derived from OpenStreetMap, © OpenStreetMap contributors, ODbL", ["connection_site", "latitude", "longitude", "network_owner", "queued_mw", "connected_mw", "projects", "earliest_year", "typical_year", "in_wales", "mw_past_contracted_date", "mw_by_technology"],
            [[s[0], s[1], s[2], s[3], s[4], s[5], s[6], s[8], s[9], s[10], s[12], ";".join(f"{k}:{v}" for k, v in s[7].items())] for s in q["sites"]],
            licence=ODBL)

    hy = load("hydrogen.json")
    if hy:
        add("hydrogen-projects.csv", "Hydrogen projects and pipeline, with status",
            "Hand-curated: the 11 first-round electrolytic hydrogen projects, proposed hubs and the Project Union East Coast pipeline corridor, with status at the date shown. Positions are approximate (town or cluster level).",
            "DESNZ HAR1 list (Open Government Licence v3.0) and the trade and company sources cited in data/hydrogen.json",
            ["name", "type", "status", "capacity_mw", "developer", "region", "latitude_approx", "longitude_approx", "status_as_of", "first_round_project"],
            [[s["n"], s["k"], s["st"], s["mw"] if s["mw"] is not None else "", s["dev"], s["reg"]["en"], s["lat"], s["lon"], s["asof"], "yes" if s.get("har1") else ""] for s in hy["sites"]])

    cst = load("costs.json")
    if cst and cst.get("days"):
        add("costs-daily.csv", "Wind turn-down and gas turn-up costs, daily",
            "System actions in the Balancing Mechanism: payments to wind units to switch off (bids) and to gas units (CCGT, OCGT) to turn up (offers), from Elexon's indicative cashflows. basis=system counts only actions flagged as system actions; basis=all counts every action. Indicative: Elexon may revise.",
            ELX, ["date", "wind_mwh_turned_down", "wind_gbp", "gas_mwh_turned_up", "gas_gbp", "total_gbp", "basis"],
            [[x["d"], x["t"]["wm"], x["t"]["wg"], x["t"]["gm"], x["t"]["gg"], x["t"]["wg"] + x["t"]["gg"], x.get("basis", "")] for x in cst["days"]])
        hr = []
        for x in cst["days"]:
            if "wg" in x:
                for h in range(24):
                    hr.append([x["d"], f"{h:02d}:00", x["wm"][h], x["wg"][h], x["gm"][h], x["gg"][h], x.get("basis", "")])
        add("costs-hourly.csv", "Wind turn-down and gas turn-up costs, hourly (last 45 days)",
            "As costs-daily.csv, by UK local hour. On clock-change days the repeated hour is added together.",
            ELX, ["date", "hour_uk", "wind_mwh_turned_down", "wind_gbp", "gas_mwh_turned_up", "gas_gbp", "basis"], hr)

    con = load("constraints.json")
    if con:
        ours = {d["d"]: d for d in cur["days"]}
        add("official-constraint-costs.csv", "Official constraint costs, with the map's tracked wind payments",
            "NESO's daily constraint costs, alongside the payments to the wind farms this map tracks on the same day. They are not meant to match: NESO's thermal cost includes turning other generators up.",
            NESO + " (constraint breakdown); " + ELX, ["date", "neso_thermal_cost_gbp", "neso_thermal_volume_mwh", "neso_all_constraints_cost_gbp", "tracked_wind_payments_gbp", "tracked_wind_turned_down_mwh"],
            [r + [ours[r[0]]["gbp"] if r[0] in ours else "", ours[r[0]]["mwh"] if r[0] in ours else ""] for r in con["days"]])

    doc = {"title": f"{NAME}: open data", "author": AUTHOR, "site": SITE, "updated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ"),
           "licence": {"default": CC, "default_url": "https://creativecommons.org/licenses/by/4.0/",
                       "exceptions": "connection-queue-by-site.csv is shared under ODbL 1.0 (https://opendatacommons.org/licenses/odbl/1-0/) because it includes locations derived from OpenStreetMap.",
                       "original_sources": "The underlying data comes from NESO (NESO Open Data Licence), Elexon (" + ELX + ") and OpenStreetMap contributors (ODbL). Their terms also apply. The licence here covers the compilation, not the original data. Provided without warranty."},
           "cite": CREDIT, "datasets": index}
    (OUT / "index.json").write_text(json.dumps(doc, indent=1, ensure_ascii=False), encoding="utf-8")
    (OUT / "README.md").write_text(f"""# {NAME}: open data

By {AUTHOR}. Refreshed daily. Every file is described, with its columns, in `index.json`.

## Licence

- Most files: **{CC}** (https://creativecommons.org/licenses/by/4.0/). You can copy, share, adapt and use them, including commercially, if you give credit.
- `connection-queue-by-site.csv`: **{ODBL}** (https://opendatacommons.org/licenses/odbl/1-0/), because it includes locations derived from OpenStreetMap.

## How to credit

> {CREDIT}

For the queue file:

> {CREDIT_ODBL}

## Original sources

The numbers come from NESO (NESO Open Data Licence), Elexon ({ELX}) and OpenStreetMap contributors (ODbL).
Their terms also apply. This licence covers the compilation (the daily tracking, matching and calculations), not the original data.
Provided without warranty: please check anything important against the original sources.

## Files

""" + "\n".join(f"- `{d['file']}` ({d['licence']}): {d['title']}" for d in index) + "\n", encoding="utf-8")
    print("open data:", ", ".join(f"{d['file']} ({d['rows']})" for d in index))

if __name__ == "__main__":
    main()
