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
    def add(fname, title, desc, source, head, rows):
        n = write(fname, head, rows)
        index.append({"file": fname, "url": SITE + "data/open/" + fname, "title": title, "description": desc, "rows": n, "columns": head, "source": source})

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
            NESO + " (TEC register); locations © OpenStreetMap contributors, ODbL", ["connection_site", "latitude", "longitude", "network_owner", "queued_mw", "connected_mw", "projects", "earliest_year", "typical_year", "in_wales", "mw_past_contracted_date", "mw_by_technology"],
            [[s[0], s[1], s[2], s[3], s[4], s[5], s[6], s[8], s[9], s[10], s[12], ";".join(f"{k}:{v}" for k, v in s[7].items())] for s in q["sites"]])

    con = load("constraints.json")
    if con:
        ours = {d["d"]: d for d in cur["days"]}
        add("official-constraint-costs.csv", "Official constraint costs, with the map's tracked wind payments",
            "NESO's daily constraint costs, alongside the payments to the wind farms this map tracks on the same day. They are not meant to match: NESO's thermal cost includes turning other generators up.",
            NESO + " (constraint breakdown); " + ELX, ["date", "neso_thermal_cost_gbp", "neso_thermal_volume_mwh", "neso_all_constraints_cost_gbp", "tracked_wind_payments_gbp", "tracked_wind_turned_down_mwh"],
            [r + [ours[r[0]]["gbp"] if r[0] in ours else "", ours[r[0]]["mwh"] if r[0] in ours else ""] for r in con["days"]])

    doc = {"title": "UK power, source to socket: open data", "site": SITE, "updated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ"),
           "licence": "CC BY 4.0 for this compilation. The original sources' terms also apply: NESO Open Data Licence; Elexon BMRS (" + ELX + "); OpenStreetMap (ODbL).",
           "cite": "UK power, source to socket. " + SITE, "datasets": index}
    (OUT / "index.json").write_text(json.dumps(doc, indent=1, ensure_ascii=False), encoding="utf-8")
    print("open data:", ", ".join(f"{d['file']} ({d['rows']})" for d in index))

if __name__ == "__main__":
    main()
