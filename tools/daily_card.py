#!/usr/bin/env python3
"""Daily card: yesterday on Britain's grid, as ready-to-post images and text in English and Welsh.

What it makes (in --out, default ./daily-card)
  card-en-landscape.png  card-en-portrait.png   1200x675 and 1080x1350 (drawn at 2x, so crisp)
  card-cy-landscape.png  card-cy-portrait.png   the same in Welsh
  post-en.txt  post-cy.txt                      the words to post with it, plus alt text for the image
  card-data.json                                the figures behind the card

Where the figures come from
  * Wind turned down and gas turned up: the same Elexon Insights (BMRS) calculation the map's running totals use
    (tools/update_costs.py, day_costs), for the whole of yesterday.
  * Carbon intensity every half hour, and the generation mix: NESO Carbon Intensity API (GB, all of yesterday).
Yesterday is used, not today, because it is complete and Elexon's indicative figures have settled.

  python3 tools/daily_card.py [--date YYYY-MM-DD] [--out DIR]
  python3 tools/daily_card.py --week [--date LAST-DAY-OF-THE-WEEK] [--out DIR]    # the 7 days ending that day (default: yesterday)

The week card makes card-week-{en,cy}-{landscape,portrait}.png, post-week-{en,cy}.txt and week-data.json.
The logo is read from logo.svg at the top of the repository; the card is drawn without it if the file is missing.

The cards are drawn from HTML with a headless browser (Playwright). On GitHub's runners Chrome is already installed;
elsewhere run `playwright install chromium` once.
Contains BMRS data (c) Elexon Limited. Contains NESO Carbon Intensity API data.
"""
import html
import json
import math
import os
import statistics
import sys
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent))
import update_costs as uc

ROOT = Path(__file__).resolve().parent.parent
CI_BASE = os.environ.get("CI_BASE", "https://api.carbonintensity.org.uk")
SITE = "delwyno.github.io/The-UK-Power-Flow-Llif-Pwer-y-DU"
UK = ZoneInfo("Europe/London")
KWH_HOME_DAY = 2700 / 365          # a typical household, Ofgem's 2,700 kWh a year
ZERO = ["wind", "solar", "nuclear", "hydro"]

IDX_COL = {"very low": "#2fa84f", "low": "#8bbf3a", "moderate": "#e0a800", "high": "#e8772e", "very high": "#d6333a"}
FUEL_COL = {"wind": "#0f8b8d", "solar": "#d9a100", "nuclear": "#7a4fd1", "gas": "#d2692a",
            "biomass": "#9a7b2c", "hydro": "#2f6fd0", "imports": "#c23b77", "other": "#607482"}
FUELS = ["wind", "solar", "nuclear", "gas", "biomass", "hydro", "imports", "other"]

CY_MONTHS = ["Ionawr", "Chwefror", "Mawrth", "Ebrill", "Mai", "Mehefin", "Gorffennaf", "Awst", "Medi", "Hydref", "Tachwedd", "Rhagfyr"]
CY_DAYS = ["Dydd Llun", "Dydd Mawrth", "Dydd Mercher", "Dydd Iau", "Dydd Gwener", "Dydd Sadwrn", "Dydd Sul"]
EN_MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
EN_DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

TXT = {
    "en": {
        "kicker": "Yesterday on the grid",
        "wind_h": "Wind turned down", "wind_sub": "{g} paid to wind farms", "wind_net": "Net {n} after {b} paid back",
        "gas_h": "Gas turned up for grid constraints", "gas_h_all": "Gas turned up (all actions)",
        "gas_sub": "{m} GWh turned up", "gas_none": "No gas turned up for grid constraints", "gas_any": "For any reason, including balancing the market: {a}",
        "co2_h": "Average carbon intensity", "unit": "gCO₂/kWh", "range": "Cleanest {t1} ({v1}) · Dirtiest {t2} ({v2})",
        "chart_h": "Carbon intensity, every half hour", "mix_h": "Where Britain's electricity came from",
        "idx": {"very low": "very low", "low": "low", "moderate": "moderate", "high": "high", "very high": "very high"},
        "fuel": {"wind": "Wind", "solar": "Solar", "nuclear": "Nuclear", "gas": "Gas", "biomass": "Biomass", "hydro": "Hydro", "imports": "Imports", "other": "Other"},
        "src": "Data: NESO Carbon Intensity API · Elexon Insights (BMRS). Contains BMRS data © Elexon Limited. Cost figures are indicative.",
        "map": "Live map",
        "m": "million", "bn": "billion",
        "src_homes": " Homes: a typical household, 2,700 kWh a year (Ofgem).",
        "sd_h": "Transmission grid supply and demand (GW), carbon underneath", "k_dem": "Demand", "k_carbon": "Carbon: clean to dirty", "carbon_lbl": "Carbon", "wk_clean": "Cleanest", "wk_dirty": "Dirtiest",
        "reg_h": "Carbon by region", "reg_hw": "Carbon by region, week average",
        "fc_h": "{d}, forecast", "fc_big": "Cleanest {a}–{b}", "fc_sub": "About {v} gCO₂/kWh. Dirtiest {c}–{e}.",
        "dem_lo": "Lowest", "dem_pk": "Peak",
        "rec_h": "Records", "rec_none": "No records this week",
        "rec_ci_year": "cleanest day of {y} so far", "rec_ci_month": "cleanest day this month",
        "rec_wind_year": "windiest day of {y} so far · {p}% wind", "rec_solar_year": "sunniest day of {y} so far · {p}% solar",
        "rec_busy": "busiest day, {v} GW peak", "rec_quiet": "quietest day, {v} GW lowest",
        "src_tx": " Supply and demand are for the transmission grid only: rooftop solar and small local generators are not included.",
        "wk_chart_h2": "The week, day by day", "k_bars": "Carbon (gCO₂/kWh)", "k_down": "Wind turned down (GWh)", "k_peak": "Peak demand (GW)",
        "zero_big": "{p}%", "zero_sub": "from wind, solar, nuclear and hydro",
        "vs_c": "{p}% cleaner", "vs_d": "{p}% dirtier", "vs_s": "About the same",
        "vs_sub_d": "than the previous 7 days", "vs_sub_w": "than the week before", "vs_sub_sd": "as the previous 7 days", "vs_sub_sw": "as the week before",
        "homes_big": "{h} homes", "homes_sub_d": "could have run for a day on the wind turned down", "homes_sub_w": "could have run for a week on the wind turned down",
        "wk_kicker": "Last week on the grid", "days7": "7 days",
        "wk_wind_h": "Wind turned down, 7 days", "wk_gas_h": "Gas turned up for grid constraints, 7 days", "wk_gas_h_all": "Gas turned up (all actions), 7 days",
        "wk_gas_sub": "{m} GWh turned up", "wk_co2_h": "Average carbon intensity, 7 days",
        "wk_range": "Cleanest {d1} ({v1}) · Dirtiest {d2} ({v2})", "wk_partial": "Cost figures for {n} of 7 days",
        "wk_chart_h": "Carbon intensity by day (bars) · wind turned down, GWh (green-blue)", "wk_mix_h": "Where Britain's electricity came from, 7 days",
        "wk_days": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"], "wk_gwh": "GWh down",
    },
    "cy": {
        "kicker": "Ddoe ar y grid",
        "wind_h": "Gwynt wedi’i droi i lawr", "wind_sub": "{g} wedi’i dalu i ffermydd gwynt", "wind_net": "Net {n} ar ôl i {b} gael ei dalu’n ôl",
        "gas_h": "Nwy wedi’i droi i fyny oherwydd cyfyngiadau’r grid", "gas_h_all": "Nwy wedi’i droi i fyny (pob gweithred)",
        "gas_sub": "{m} GWh wedi’i droi i fyny", "gas_none": "Dim nwy wedi’i droi i fyny oherwydd cyfyngiadau’r grid", "gas_any": "Am unrhyw reswm, gan gynnwys cydbwyso’r farchnad: {a}",
        "co2_h": "Dwysedd carbon cyfartalog", "unit": "gCO₂/kWh", "range": "Glanaf {t1} ({v1}) · Mwyaf budr {t2} ({v2})",
        "chart_h": "Dwysedd carbon, bob hanner awr", "mix_h": "O ble y daeth trydan Prydain",
        "idx": {"very low": "isel iawn", "low": "isel", "moderate": "cymedrol", "high": "uchel", "very high": "uchel iawn"},
        "fuel": {"wind": "Gwynt", "solar": "Solar", "nuclear": "Niwclear", "gas": "Nwy", "biomass": "Biomas", "hydro": "Dŵr", "imports": "Mewnforion", "other": "Arall"},
        "src": "Data: API Dwysedd Carbon NESO · Elexon Insights (BMRS). Yn cynnwys data BMRS © Elexon Limited. Ffigurau dangosol yw’r costau.",
        "map": "Map byw",
        "m": "miliwn", "bn": "biliwn",
        "src_homes": " Cartrefi: aelwyd nodweddiadol, 2,700 kWh y flwyddyn (Ofgem).",
        "sd_h": "Cyflenwad a galw ar y grid trawsyrru (GW), carbon oddi tano", "k_dem": "Galw", "k_carbon": "Carbon: glân i fudr", "carbon_lbl": "Carbon", "wk_clean": "Glanaf", "wk_dirty": "Mwyaf budr",
        "reg_h": "Carbon yn ôl rhanbarth", "reg_hw": "Carbon yn ôl rhanbarth, cyfartaledd yr wythnos",
        "fc_h": "{d}, rhagolwg", "fc_big": "Glanaf {a}–{b}", "fc_sub": "Tua {v} gCO₂/kWh. Mwyaf budr {c}–{e}.",
        "dem_lo": "Isaf", "dem_pk": "Uchaf",
        "rec_h": "Recordiau", "rec_none": "Dim recordiau’r wythnos hon",
        "rec_ci_year": "diwrnod glanaf {y} hyd yma", "rec_ci_month": "diwrnod glanaf y mis",
        "rec_wind_year": "diwrnod gwyntaf {y} hyd yma · {p}% o wynt", "rec_solar_year": "diwrnod heulaf {y} hyd yma · {p}% o solar",
        "rec_busy": "y diwrnod prysuraf, brig o {v} GW", "rec_quiet": "y diwrnod tawelaf, isaf {v} GW",
        "src_tx": " Mae’r cyflenwad a’r galw ar gyfer y grid trawsyrru yn unig: nid yw solar to a chynhyrchwyr lleol bach wedi’u cynnwys.",
        "wk_chart_h2": "Yr wythnos, diwrnod wrth ddiwrnod", "k_bars": "Carbon (gCO₂/kWh)", "k_down": "Gwynt wedi’i droi i lawr (GWh)", "k_peak": "Galw brig (GW)",
        "zero_big": "{p}%", "zero_sub": "o wynt, solar, niwclear a dŵr",
        "vs_c": "{p}% yn lanach", "vs_d": "{p}% yn fwy budr", "vs_s": "Tua’r un peth",
        "vs_sub_d": "na’r 7 diwrnod blaenorol", "vs_sub_w": "na’r wythnos gynt", "vs_sub_sd": "â’r 7 diwrnod blaenorol", "vs_sub_sw": "â’r wythnos gynt",
        "homes_big": "{h} o gartrefi", "homes_sub_d": "y gallai’r gwynt a droddwyd i lawr fod wedi’u pweru am ddiwrnod", "homes_sub_w": "y gallai’r gwynt a droddwyd i lawr fod wedi’u pweru am wythnos",
        "wk_kicker": "Yr wythnos ddiwethaf ar y grid", "days7": "7 diwrnod",
        "wk_wind_h": "Gwynt wedi’i droi i lawr, 7 diwrnod", "wk_gas_h": "Nwy wedi’i droi i fyny oherwydd cyfyngiadau’r grid, 7 diwrnod", "wk_gas_h_all": "Nwy wedi’i droi i fyny (pob gweithred), 7 diwrnod",
        "wk_gas_sub": "{m} GWh wedi’i droi i fyny", "wk_co2_h": "Dwysedd carbon cyfartalog, 7 diwrnod",
        "wk_range": "Glanaf {d1} ({v1}) · Mwyaf budr {d2} ({v2})", "wk_partial": "Ffigurau cost ar gyfer {n} o 7 diwrnod",
        "wk_chart_h": "Dwysedd carbon fesul diwrnod (bariau) · gwynt wedi’i droi i lawr, GWh (gwyrddlas)", "wk_mix_h": "O ble y daeth trydan Prydain, 7 diwrnod",
        "wk_days": ["Llun", "Maw", "Mer", "Iau", "Gwe", "Sad", "Sul"], "wk_gwh": "GWh i lawr",
    },
}


# ---------------------------------------------------------------- data
def get_json(url, tries=3):
    for k in range(tries):
        try:
            req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "uk-power-map/1.0"})
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.load(r)
        except Exception:
            if k == tries - 1:
                raise
            time.sleep(2 + 3 * k)


def utc_window(date):
    y, m, d = map(int, date.split("-"))
    a = datetime(y, m, d, tzinfo=UK).astimezone(timezone.utc)
    b = datetime(y, m, d, tzinfo=UK) + timedelta(days=1)
    b = datetime(b.year, b.month, b.day, tzinfo=UK).astimezone(timezone.utc)
    return a, b


def ci_index(g):
    return "very low" if g < 60 else "low" if g < 120 else "moderate" if g < 180 else "high" if g < 240 else "very high"


def uk_hm(iso):
    return datetime.strptime(iso, "%Y-%m-%dT%H:%MZ").replace(tzinfo=timezone.utc).astimezone(UK).strftime("%H:%M")


def carbon_and_mix(date):
    a, b = utc_window(date)
    f, t = a.strftime("%Y-%m-%dT%H:%MZ"), b.strftime("%Y-%m-%dT%H:%MZ")
    inten = get_json(f"{CI_BASE}/intensity/{f}/{t}").get("data") or []
    series = []
    for p in inten:
        i = p.get("intensity") or {}
        v = i.get("actual") if i.get("actual") is not None else i.get("forecast")
        if v is not None and p.get("from"):
            series.append({"from": p["from"], "v": float(v)})
    if len(series) < 20:
        raise ValueError(f"only {len(series)} carbon intensity periods for {date}")
    avg = statistics.fmean(x["v"] for x in series)
    lo, hi = min(series, key=lambda x: x["v"]), max(series, key=lambda x: x["v"])
    mixrows = get_json(f"{CI_BASE}/generation/{f}/{t}").get("data") or []
    acc = {k: [] for k in FUELS}
    for p in mixrows:
        cur = {k: 0.0 for k in FUELS}
        for g in p.get("generationmix") or []:
            k = str(g.get("fuel", "")).lower()
            k = k if k in cur else "other"          # coal and anything unlisted go in "other"
            cur[k] += float(g.get("perc") or 0)
        for k in FUELS:
            acc[k].append(cur[k])
    if len(mixrows) < 20:
        raise ValueError(f"only {len(mixrows)} generation periods for {date}")
    mix = {k: statistics.fmean(v) for k, v in acc.items()}
    return {"series": series, "avg": avg, "lo": {"t": uk_hm(lo["from"]), "v": lo["v"]}, "hi": {"t": uk_hm(hi["from"]), "v": hi["v"]}, "mix": mix}


def add_days(date, n):
    return (datetime.strptime(date, "%Y-%m-%d") + timedelta(days=n)).strftime("%Y-%m-%d")


def period_avg(first, last):
    """Average carbon intensity over whole UK days first..last, or None."""
    try:
        a, _ = utc_window(first)
        _, b = utc_window(last)
        rows = get_json(f"{CI_BASE}/intensity/{a.strftime('%Y-%m-%dT%H:%MZ')}/{b.strftime('%Y-%m-%dT%H:%MZ')}").get("data") or []
        vals = []
        for p in rows:
            i = p.get("intensity") or {}
            v = i.get("actual") if i.get("actual") is not None else i.get("forecast")
            if v is not None:
                vals.append(float(v))
        return statistics.fmean(vals) if len(vals) > 0.8 * 48 * ((datetime.strptime(last, "%Y-%m-%d") - datetime.strptime(first, "%Y-%m-%d")).days + 1) else None
    except Exception as e:
        print("comparison period not available -", e, file=sys.stderr)
        return None



REGIONS = [(1, "North Scotland", "Gogledd yr Alban"), (2, "South Scotland", "De’r Alban"), (3, "North West England", "Gogledd-orllewin Lloegr"),
           (4, "North East England", "Gogledd-ddwyrain Lloegr"), (5, "Yorkshire", "Swydd Efrog"), (6, "North Wales & Merseyside", "Gogledd Cymru a Glannau Merswy"),
           (7, "South Wales", "De Cymru"), (8, "West Midlands", "Gorllewin Canolbarth Lloegr"), (9, "East Midlands", "Dwyrain Canolbarth Lloegr"),
           (10, "East England", "Dwyrain Lloegr"), (11, "South West England", "De-orllewin Lloegr"), (12, "South England", "De Lloegr"),
           (13, "London", "Llundain"), (14, "South East England", "De-ddwyrain Lloegr")]
FUEL_GROUP = {"WIND": "wind", "CCGT": "gas", "OCGT": "gas", "NUCLEAR": "nuclear", "BIOMASS": "biomass", "NPSHYD": "hydro", "PS": "hydro",
              "COAL": "other", "OIL": "other", "OTHER": "other"}
STACK = ["nuclear", "biomass", "hydro", "wind", "other", "gas", "imports"]      # bottom to top, as on the map's supply card


def fuel_group(f):
    f = str(f or "").upper()
    return "imports" if f.startswith("INT") else FUEL_GROUP.get(f, "other")


def uk_hours(iso, day):
    """Hours since UK midnight of `day` for an ISO time."""
    t = datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(UK)
    m = datetime.strptime(day, "%Y-%m-%d").replace(tzinfo=UK)
    return (t - m).total_seconds() / 3600


def hm(h):
    h = max(0, h)
    return f"{int(h):02d}:{int(round((h % 1) * 60)):02d}" if round((h % 1) * 60) < 60 else f"{int(h) + 1:02d}:00"


def elexon_range(first, last):
    """Transmission supply by fuel group (MW) and transmission demand (MW) for UK days first..last, or None."""
    try:
        a, _ = utc_window(first)
        _, b = utc_window(last)
        sj = get_json(f"{uc.ELX}/generation/outturn/summary?startTime={a.strftime('%Y-%m-%dT%H:%M:%SZ')}&endTime={b.strftime('%Y-%m-%dT%H:%M:%SZ')}&includeNegativeGeneration=false&format=json")
        rows = sj if isinstance(sj, list) else (sj or {}).get("data") or []
        sup = []
        for r in rows:
            if not (r and r.get("startTime") and isinstance(r.get("data"), list)):
                continue
            g = {k: 0.0 for k in STACK}
            for it in r["data"]:
                v = float(it.get("generation") or 0)
                if v > 0:
                    g[fuel_group(it.get("fuelType"))] += v
            if sum(g.values()) > 1000:
                sup.append({"st": r["startTime"], "g": g})
        sup.sort(key=lambda x: x["st"])
        dj = get_json(f"{uc.ELX}/demand/outturn?settlementDateFrom={first}&settlementDateTo={last}&format=json")
        drows = dj if isinstance(dj, list) else (dj or {}).get("data") or []
        dem = []
        for r in drows:
            if not (r and r.get("startTime")):
                continue
            v = r.get("initialTransmissionSystemDemandOutturn")
            v = r.get("initialDemandOutturn") if v is None else v
            if v is not None:
                dem.append({"st": r["startTime"], "w": float(v)})
        dem.sort(key=lambda x: x["st"])
        n_days = (datetime.strptime(last, "%Y-%m-%d") - datetime.strptime(first, "%Y-%m-%d")).days + 1
        if len(sup) < 40 * n_days or len(dem) < 40 * n_days:
            raise ValueError(f"only {len(sup)} supply and {len(dem)} demand periods")
        return {"sup": sup, "dem": dem}
    except Exception as e:
        print("supply and demand not available -", e, file=sys.stderr)
        return None


def day_view(elx, day):
    """The part of an elexon_range for one UK day, with x in hours."""
    a, b = utc_window(day)
    ia, ib = a.strftime("%Y-%m-%dT%H:%M"), b.strftime("%Y-%m-%dT%H:%M")
    sup = [dict(r, x=uk_hours(r["st"], day)) for r in elx["sup"] if ia <= r["st"][:16] < ib]
    dem = [dict(r, x=uk_hours(r["st"], day)) for r in elx["dem"] if ia <= r["st"][:16] < ib]
    return {"sup": sup, "dem": dem} if len(sup) >= 40 and len(dem) >= 40 else None


def demand_extremes(dem):
    lo, hi = min(dem, key=lambda r: r["w"]), max(dem, key=lambda r: r["w"])
    return lo, hi


def stack_shares(sup):
    tot = {k: sum(r["g"][k] for r in sup) for k in STACK}
    t = sum(tot.values()) or 1
    return {k: v / t * 100 for k, v in tot.items()}


def regional_avg(first, last):
    """{region id: average forecast carbon intensity} over UK days first..last."""
    try:
        a, _ = utc_window(first)
        _, b = utc_window(last)
        rows = get_json(f"{CI_BASE}/regional/intensity/{a.strftime('%Y-%m-%dT%H:%MZ')}/{b.strftime('%Y-%m-%dT%H:%MZ')}").get("data") or []
        acc = {}
        for p in rows:
            for r in p.get("regions") or []:
                v = (r.get("intensity") or {}).get("forecast")
                if v is not None and 1 <= int(r.get("regionid", 0)) <= 14:
                    acc.setdefault(int(r["regionid"]), []).append(float(v))
        out = {k: statistics.fmean(v) for k, v in acc.items() if len(v) >= 40}
        return out if len(out) >= 12 else None
    except Exception as e:
        print("regional carbon not available -", e, file=sys.stderr)
        return None


def region_rows(avg):
    """[(region id, value, kind)] cleanest, dirtiest, then the two Welsh regions, without repeats."""
    if not avg:
        return []
    lo, hi = min(avg, key=avg.get), max(avg, key=avg.get)
    out = []
    for rid in (lo, hi, 6, 7):
        if rid in avg and rid not in [x[0] for x in out]:
            out.append((rid, avg[rid]))
    return out


def forecast_for(day):
    """Cleanest 4-hour and dirtiest 2.5-hour windows from NESO's forecast for a UK day, plus the half-hour series; None if unavailable."""
    try:
        a, b = utc_window(day)
        rows = get_json(f"{CI_BASE}/intensity/{a.strftime('%Y-%m-%dT%H:%MZ')}/{b.strftime('%Y-%m-%dT%H:%MZ')}").get("data") or []
        ser = []
        for p in rows:
            i = p.get("intensity") or {}
            v = i.get("forecast") if i.get("forecast") is not None else i.get("actual")
            if v is not None and p.get("from"):
                ser.append({"x": uk_hours(p["from"], day), "v": float(v)})
        if len(ser) < 44:
            return None
        def best(n, sign):
            cands = [(statistics.fmean(x["v"] for x in ser[i:i + n]), i) for i in range(len(ser) - n + 1)]
            v, i = (min if sign > 0 else max)(cands)
            return v, ser[i]["x"], ser[i + n - 1]["x"] + .5
        cv, ca, cb = best(8, 1)
        dv, da, db = best(5, -1)
        return {"day": day, "series": ser, "clean": {"v": cv, "a": hm(ca), "b": hm(cb)}, "dirty": {"v": dv, "a": hm(da), "b": hm(db)}}
    except Exception as e:
        print("forecast not available -", e, file=sys.stderr)
        return None


def history(end):
    """Daily carbon intensity, wind and solar share for each UK day of the year up to `end`: {date: {ci, wind, solar}}; None on any failure."""
    try:
        year = end[:4]
        first = f"{year}-01-01"
        out = {}
        d = first
        while d <= end:
            e = min(add_days(d, 13), end)
            a, _ = utc_window(d)
            _, b = utc_window(e)
            f, t = a.strftime("%Y-%m-%dT%H:%MZ"), b.strftime("%Y-%m-%dT%H:%MZ")
            ci = {}
            for p in get_json(f"{CI_BASE}/intensity/{f}/{t}").get("data") or []:
                i = p.get("intensity") or {}
                v = i.get("actual") if i.get("actual") is not None else i.get("forecast")
                if v is not None and p.get("from"):
                    day = datetime.strptime(p["from"], "%Y-%m-%dT%H:%MZ").replace(tzinfo=timezone.utc).astimezone(UK).strftime("%Y-%m-%d")
                    ci.setdefault(day, []).append(float(v))
            gm = {}
            for p in get_json(f"{CI_BASE}/generation/{f}/{t}").get("data") or []:
                day = datetime.strptime(p["from"], "%Y-%m-%dT%H:%MZ").replace(tzinfo=timezone.utc).astimezone(UK).strftime("%Y-%m-%d")
                m = {str(g.get("fuel", "")).lower(): float(g.get("perc") or 0) for g in p.get("generationmix") or []}
                gm.setdefault(day, []).append((m.get("wind", 0.0), m.get("solar", 0.0)))
            for day, v in ci.items():
                if len(v) >= 40 and len(gm.get(day, [])) >= 40:
                    out[day] = {"ci": statistics.fmean(v), "wind": statistics.fmean(x[0] for x in gm[day]), "solar": statistics.fmean(x[1] for x in gm[day])}
            d = add_days(e, 1)
        return out if len(out) >= 21 else None
    except Exception as e:
        print("history for records not available -", e, file=sys.stderr)
        return None


def records_for(day, hist, end):
    """Records this day holds so far this year / this month, strongest first: [(kind, value)]."""
    if not hist or day not in hist:
        return []
    ys = {d: v for d, v in hist.items() if d <= end}
    ms = {d: v for d, v in ys.items() if d[:7] == end[:7]}
    me = hist[day]
    out = []
    if me["wind"] >= max(v["wind"] for v in ys.values()) - 1e-9:
        out.append(("rec_wind_year", round(me["wind"])))
    if me["ci"] <= min(v["ci"] for v in ys.values()) + 1e-9:
        out.append(("rec_ci_year", None))
    elif len(ms) >= 7 and day[:7] == end[:7] and me["ci"] <= min(v["ci"] for v in ms.values()) + 1e-9:
        out.append(("rec_ci_month", None))
    if me["solar"] >= 5 and me["solar"] >= max(v["solar"] for v in ys.values()) - 1e-9:
        out.append(("rec_solar_year", round(me["solar"])))
    return out


def rec_text(kind, val, lang, year):
    return TXT[lang][kind].format(y=year, p=val)


def costs(date, fn=None):
    """Wind and gas figures for the day, or None when Elexon cannot give them (the card then leaves that part out)."""
    try:
        r = (fn or uc.day_costs)(date)
        t = r["t"]
        if r.get("n", 0) < 1:
            return None
        wp = t["wp"] if "wp" in t else max(0.0, t["wg"])
        wr = t.get("wr", 0.0)
        return {"wind_mwh": t["wm"], "paid": wp, "back": wr, "net": wp - wr, "gas_sys": t["gg"], "gas_mwh": t["gm"],
                "gas_all": t.get("ga", t["gg"]), "basis": r.get("basis", "system"), "periods": r.get("n", 0)}
    except Exception as e:
        print("costs not available -", e, file=sys.stderr)
        return None


# ---------------------------------------------------------------- formatting
def gbp(v):
    if v < 0:
        return "−" + gbp(-v)
    if v >= 1e9:
        return f"£{v / 1e9:.2f}bn"
    if v >= 1e6:
        return f"£{v / 1e6:.1f}m"
    if v >= 1e5:
        return f"£{v / 1e3:.0f}k"
    if v >= 1e3:
        return f"£{v / 1e3:.1f}k"
    return f"£{v:.0f}"


def gbp_words(v, lang):
    if v < 0:
        return "−" + gbp_words(-v, lang)
    w = TXT[lang]
    if v >= 1e9:
        return f"£{v / 1e9:.2f} {w['bn']}"
    if v >= 1e6:
        return f"£{v / 1e6:.1f} {w['m']}"
    if v >= 1000:
        return f"£{round(v / 100) * 100:,.0f}"
    return f"£{v:.0f}"


def round2(n):
    """Two significant figures, for 'about' numbers."""
    if n <= 0:
        return 0
    m = 10 ** (len(str(int(n))) - 2)
    return int(round(n / m) * m) if m >= 1 else int(round(n))


def homes_text(mwh, days, lang):
    h = round2(mwh * 1000 / KWH_HOME_DAY / days)
    w = TXT[lang]
    if h >= 1e6:
        return f"{h / 1e6:.1f} {w['m']}"
    return f"{h:,}"


def zero_share(mix):
    return round(sum(mix[k] for k in ZERO))


def vs_stat(avg, prev, lang, week):
    """(big, sub) for the comparison with the previous period, or None."""
    if not prev:
        return None
    T = TXT[lang]
    d = (avg - prev) / prev * 100
    if abs(d) < 3:
        return T["vs_s"], T["vs_sub_sw" if week else "vs_sub_sd"]
    return T["vs_c" if d < 0 else "vs_d"].format(p=round(abs(d))), T["vs_sub_w" if week else "vs_sub_d"]


def gwh(mwh):
    g = mwh / 1000
    return f"{g:.1f}" if g < 100 else f"{g:.0f}"


def date_label(date, lang):
    d = datetime.strptime(date, "%Y-%m-%d")
    if lang == "cy":
        return f"{CY_DAYS[d.weekday()]} {d.day} {CY_MONTHS[d.month - 1]}"
    return f"{EN_DAYS[d.weekday()]} {d.day} {EN_MONTHS[d.month - 1]}"


def wd_short(date, lang):
    return TXT[lang]["wk_days"][datetime.strptime(date, "%Y-%m-%d").weekday()]


def date_short(date, lang):
    d = datetime.strptime(date, "%Y-%m-%d")
    if lang == "cy":
        return f"{CY_DAYS[d.weekday()].replace('Dydd ', '')} {d.day} {CY_MONTHS[d.month - 1][:3]}"
    return f"{EN_DAYS[d.weekday()][:3]} {d.day} {EN_MONTHS[d.month - 1][:3]}"


# ---------------------------------------------------------------- card
def logo_uri():
    import base64
    f = Path(os.environ.get("CARD_LOGO") or ROOT / "logo.svg")
    try:
        return "data:image/svg+xml;base64," + base64.b64encode(f.read_bytes()).decode()
    except Exception:
        return ""


def head_html(lang, date_html, kicker):
    u = logo_uri()
    img = f'<img class="logo" alt="" src="{u}">' if u else ""
    return (f'<div class="head"><div class="brandwrap">{img}<div class="brand cond">THE UK POWER FLOW<small>LLIF PŴER Y DU</small></div></div>'
            f'<div class="when cond">{date_html}<span>{html.escape(kicker)}</span></div></div>')


def stats_html(items):
    return f'<div class="stats" style="--n:{len(items)}">' + "".join(
        it if isinstance(it, str) else f'<div class="stat"><b class="cond">{html.escape(it[0])}</b><span>{html.escape(it[1])}</span></div>' for it in items) + "</div>"


def week_chart_svg(days, w, h, T, cols=False):
    """One big bar a day for carbon intensity (map colours), with the cleanest and dirtiest day marked."""
    n = len(days)
    zt, zb = 44, h - 28
    zh = zb - zt
    slot = w / n
    mx = max(d["ci"] for d in days)
    lo, hi = min(days, key=lambda d: d["ci"]), max(days, key=lambda d: d["ci"])
    fs = 17 if cols else 20
    s = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}" role="img">',
         f'<line x1="0" x2="{w}" y1="{zb}" y2="{zb}" stroke="#d6dee1"/>']
    for i, d in enumerate(days):
        cx = i * slot + slot / 2
        bh = max(2.0, d["ci"] / mx * zh * .86)
        c = IDX_COL[ci_index(d["ci"])]
        s.append(f'<rect x="{cx - slot * .31:.1f}" y="{zb - bh:.1f}" width="{slot * .62:.1f}" height="{bh:.1f}" rx="5" fill="{c}"/>')
        s.append(f'<text x="{cx:.1f}" y="{zb - bh - 7:.1f}" text-anchor="middle" font-size="{fs + 2}" font-weight="700" fill="#1b282e">{round(d["ci"])}</text>')
        s.append(f'<text x="{cx:.1f}" y="{h - 6}" text-anchor="middle" font-size="{fs - 3}" font-weight="600" fill="#5a6b71">{html.escape(d["wd"])}</text>')
        tag = T["wk_clean"] if d is lo else T["wk_dirty"] if d is hi else None
        if tag and lo is not hi:
            col = "#2f8f3d" if d is lo else "#c0282f"
            s.append(f'<text x="{cx:.1f}" y="{zb - bh - 7 - fs - 6:.1f}" text-anchor="middle" font-size="{fs - 5}" font-weight="700" letter-spacing=".05em" fill="{col}">{html.escape(tag.upper())}</text>')
    s.append("</svg>")
    return "".join(s)


def chart_svg(series, w, h, lang):
    """A bar for every half hour, coloured on the same scale as the map."""
    ml, mr, mt, mb = 40, 6, 8, 26
    mx = max(200.0, max(x["v"] for x in series) * 1.08)
    top = 100 * -(-mx // 100)
    n = len(series)
    iw, ih = w - ml - mr, h - mt - mb
    bw = iw / n
    y = lambda v: mt + ih - v / top * ih
    s = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}" role="img">']
    for g in range(0, int(top) + 1, 100):
        s.append(f'<line x1="{ml}" x2="{w - mr}" y1="{y(g):.1f}" y2="{y(g):.1f}" stroke="#d6dee1" stroke-width="1"/>')
        s.append(f'<text x="{ml - 8}" y="{y(g) + 5:.1f}" text-anchor="end" font-size="14" fill="#5a6b71">{g}</text>')
    for i, p in enumerate(series):
        c = IDX_COL[ci_index(p["v"])]
        s.append(f'<rect x="{ml + i * bw + 1:.1f}" y="{y(p["v"]):.1f}" width="{max(1, bw - 2):.1f}" height="{y(0) - y(p["v"]):.1f}" rx="2" fill="{c}"/>')
    for hh in (0, 6, 12, 18, 24):
        x = ml + iw * hh / 24
        s.append(f'<text x="{x:.1f}" y="{h - 6}" text-anchor="{"start" if hh == 0 else "end" if hh == 24 else "middle"}" font-size="14" fill="#5a6b71">{hh:02d}:00</text>')
    s.append("</svg>")
    return "".join(s)


def mix_html(mix, T):
    parts = [(k, mix[k]) for k in FUELS if mix[k] >= 0.5]
    tot = sum(v for _, v in parts) or 1
    bar = "".join(f'<i style="width:{v / tot * 100:.2f}%;background:{FUEL_COL[k]}">{round(v)}%</i>' if v >= 6 else f'<i style="width:{v / tot * 100:.2f}%;background:{FUEL_COL[k]}"></i>' for k, v in parts)
    leg = "".join(f'<span><b style="background:{FUEL_COL[k]}"></b>{T["fuel"][k]} {round(v)}%</span>' for k, v in sorted(parts, key=lambda kv: -kv[1]))
    return f'<div class="mixbar">{bar}</div><div class="legend">{leg}</div>'


CSS = """
*{box-sizing:border-box;margin:0;padding:0}
html,body{background:#fff}
#card{position:relative;overflow:hidden;background:#e9f0f0;color:#1b282e;font-family:"Barlow",system-ui,"Segoe UI",Roboto,Arial,sans-serif;display:flex;flex-direction:column}
.cond{font-family:"Barlow Semi Condensed","Arial Narrow",sans-serif}
.head{display:flex;justify-content:space-between;align-items:flex-end;gap:16px}
.brandwrap{display:flex;align-items:center}
.logo{display:block;flex:none}
.brand{font-weight:700;letter-spacing:.01em}
.brand small{display:block;font-weight:500;color:#5a6b71;letter-spacing:.02em}
.when{text-align:right;font-weight:600}
.when span{display:block;color:#5a6b71;font-weight:500}
.tile{background:#fff;border-radius:16px;position:relative;overflow:hidden}
.tile:before{content:"";position:absolute;left:0;top:0;bottom:0;width:8px;background:var(--c)}
.tile h3{font-weight:600;text-transform:uppercase;letter-spacing:.05em;color:#5a6b71}
.tile .big{font-weight:700;line-height:1;letter-spacing:-.01em}
.tile .big small{font-weight:500;color:#5a6b71;margin-left:.3em}
.tile p{color:#1b282e}
.tile p.fine{color:#5a6b71}
.dot{display:inline-block;border-radius:50%;margin-right:.35em;vertical-align:middle}
.panel{background:#fff;border-radius:16px}
.panel h3{font-weight:600;text-transform:uppercase;letter-spacing:.05em;color:#5a6b71}
.mixbar{display:flex;border-radius:10px;overflow:hidden;background:#d6dee1}
.mixbar i{display:block;color:#fff;font-style:normal;font-weight:600;text-align:center;white-space:nowrap}
.legend{display:flex;flex-wrap:wrap}
.legend span{display:inline-flex;align-items:center;font-weight:500}
.legend b{display:inline-block;border-radius:3px}
.stats{display:grid;grid-template-columns:repeat(var(--n),1fr)}
.stat{background:#fff;border-radius:16px}
.stat b{display:block;font-weight:700;line-height:1.05;color:#1b282e}
.stat span{display:block;color:#5a6b71;font-weight:500;line-height:1.2}
.foot{display:flex;justify-content:space-between;align-items:flex-end;gap:20px;color:#5a6b71}
.foot .url{font-weight:700;color:#1b282e;white-space:nowrap}

.land #card{width:1200px;height:675px;padding:28px 36px 22px}
.land .head{margin-bottom:16px}
.land .brand{font-size:30px;line-height:1.05}.land .brand small{font-size:17px;margin-top:3px}
.land .when{font-size:26px;line-height:1.1}.land .when span{font-size:17px}
.badge{display:inline-flex;align-items:center;gap:8px;background:#fff7d6;border:1.5px solid #e0a800;color:#6b4e00;border-radius:999px;font-weight:700;white-space:nowrap}
.badge svg{flex:none}
.land .badge{font-size:16px;padding:5px 14px 5px 10px}.port .badge{font-size:22px;padding:7px 18px 7px 12px}
.land .mid{display:flex;align-items:center;justify-content:center;flex:1}
.port .badgerow{display:flex;justify-content:center;margin:-4px 0 12px}
.two{display:grid;grid-auto-flow:column;grid-auto-columns:1fr;gap:10px}
.rlist div{display:flex;align-items:center;justify-content:space-between;white-space:nowrap;gap:12px}
.rlist div span{display:inline-flex;align-items:center;overflow:hidden;text-overflow:ellipsis}
.rlist i{display:inline-block;border-radius:50%;margin-right:8px;flex:none}
.rlist b{font-weight:700}
.rlist svg{flex:none;margin-right:8px}
.land .rlist{font-size:14px;line-height:1.38}.land .rlist i{width:10px;height:10px}
.port .rlist{font-size:19px;line-height:1.4}.port .rlist i{width:13px;height:13px}
.tom .big{font-weight:700;line-height:1}
.land .tom .big{font-size:26px}.port .tom .big{font-size:34px}
.tom p{color:#5a6b71;font-weight:500}.land .tom p{font-size:14px;margin-top:3px}.port .tom p{font-size:19px;margin-top:4px}
.ribbon{display:flex;border-radius:5px;overflow:hidden}.ribbon i{flex:1;display:block}
.land .ribbon{height:12px;margin-top:6px}.port .ribbon{height:16px;margin-top:8px}
.rtimes{display:flex;justify-content:space-between;color:#5a6b71;font-weight:500}.land .rtimes{font-size:12px;margin-top:2px}.port .rtimes{font-size:16px;margin-top:3px}
.leg2{display:flex;flex-wrap:wrap;color:#1b282e;font-weight:500}.land .leg2{font-size:14px;gap:2px 12px;margin-top:6px}.port .leg2{font-size:19px;gap:2px 16px;margin-top:8px}
.leg2 span{display:inline-flex;align-items:center}.leg2 b{display:inline-block;border-radius:3px;margin-right:5px}.land .leg2 b{width:11px;height:11px}.port .leg2 b{width:15px;height:15px}
.leg2 u{display:inline-block;width:22px;border-top:4px dashed #1b282e;margin-right:6px}
.stat.dem{display:flex;justify-content:space-between;align-items:flex-end;gap:12px}
.stat.dem .r{text-align:right}
.stat.dem small{display:block;color:#5a6b71;font-weight:600;text-transform:uppercase;letter-spacing:.05em}
.land .stat.dem small{font-size:11px}.port .stat.dem small{font-size:14px}
.stat.dem b{margin-top:1px}
.land .right.flex{display:flex;flex-direction:column;gap:10px}.land .right.flex>.panel:first-child{flex:1}
.port .stats.c2{grid-template-columns:1fr 1fr}.port .stats.c3{grid-template-columns:1.25fr 1fr 1fr}.port .stats.c3 .stat b{font-size:27px}.port .stats.c3 .stat span{font-size:16px}
.port .tiles{display:grid;grid-template-columns:repeat(var(--n,3),1fr);gap:10px}
.port .tile .big{font-size:46px}.port .tile .big small{font-size:20px}.port .tile p{font-size:18px}.port .tile p.fine{font-size:14px}.port .tile h3{font-size:15px}
.land .logo{width:54px;height:54px;border-radius:13px;margin-right:14px}
.land .grid{display:grid;grid-template-columns:430px 1fr;gap:16px;flex:1;min-height:0}
.land .tiles{display:grid;grid-template-rows:1.25fr 1fr 1fr;gap:12px;min-height:0}
.land .tile{padding:12px 18px 10px 26px;display:flex;flex-direction:column;justify-content:center}
.land .tile h3{font-size:14px;margin-bottom:4px}
.land .tile .big{font-size:54px}.land .tile .big small{font-size:20px}
.land .tile p{font-size:17px;line-height:1.2;margin-top:4px}
.land .tile p.fine{font-size:14px;margin-top:2px}
.land .right{display:grid;grid-template-rows:1fr auto auto;gap:10px;min-height:0}
.land .stats{gap:10px}.land .stat{padding:8px 14px 8px}.land .stat b{font-size:25px}.land .stat span{font-size:14px;margin-top:2px}
.land .panel{padding:14px 18px 12px}
.land .panel h3{font-size:14px;margin-bottom:6px}
.land .legend{margin-top:10px;gap:4px 16px;font-size:17px}.land .legend b{width:13px;height:13px;margin-right:6px}
.land .mixbar{height:36px}.land .mixbar i{font-size:16px;line-height:36px}
.land .foot{margin-top:12px;font-size:13px;line-height:1.25}.land .foot .url{font-size:17px}

.port #card{width:1080px;height:1350px;padding:44px 56px 34px}
.port .logo{width:78px;height:78px;border-radius:18px;margin-right:20px}
.port .head{margin-bottom:16px}
.port .brand{font-size:44px;line-height:1.05}.port .brand small{font-size:24px;margin-top:5px}
.port .when{font-size:34px;line-height:1.1}.port .when span{font-size:24px}
.port .grid{display:flex;flex-direction:column;gap:12px;flex:1;min-height:0}
.port .tiles{display:flex;flex-direction:column;gap:10px}
.port .tile{padding:8px 24px 8px 36px}
.port .tile h3{font-size:18px;margin-bottom:2px}
.port .tile .big{font-size:50px;line-height:1.05}.port .tile .big small{font-size:24px}
.port .tile p{font-size:21px;line-height:1.15;margin-top:2px}
.port .tile p.fine{font-size:17px;margin-top:1px}
.port .right{display:flex;flex-direction:column;gap:14px}
.port .stats{gap:10px}.port .stat{padding:10px 14px 10px}.port .stat b{font-size:29px}.port .stat span{font-size:17px;margin-top:2px}
.port .panel{padding:12px 22px 12px}
.port .panel h3{font-size:18px;margin-bottom:4px}
.port .legend{margin-top:8px;gap:2px 18px;font-size:20px}.port .legend b{width:16px;height:16px;margin-right:8px}
.port .mixbar{height:40px}.port .mixbar i{font-size:19px;line-height:40px}
.port .foot{margin-top:auto;padding-top:14px;font-size:17px;line-height:1.3;flex-direction:column;align-items:flex-start;gap:8px}.port .foot .url{font-size:26px}
.port .tiles{display:grid;grid-template-columns:repeat(var(--n,3),1fr);grid-template-rows:auto!important;gap:12px}
.port .tile{padding:14px 14px 12px 24px}.port .tile h3{font-size:15px;line-height:1.2;margin-bottom:6px}
.port .tile .big{font-size:46px}.port .tile .big small{font-size:20px;margin-left:.2em}
.port .tile p{font-size:19px;line-height:1.2;margin-top:6px}.port .tile p.fine{font-size:15px;margin-top:4px}
"""



def cap(t):
    return t[:1].upper() + t[1:]


def wd_full(date, lang):
    d = datetime.strptime(date, "%Y-%m-%d")
    return (CY_DAYS if lang == "cy" else EN_DAYS)[d.weekday()]


STAR = '<svg width="{n}" height="{n}" viewBox="0 0 24 24" fill="#e0a800" aria-hidden="true"><path d="M12 2l3 6.5 7 .8-5.2 4.8 1.5 7L12 17.3 5.7 21l1.5-7L2 9.3l7-.8z"/></svg>'


def supply_svg(view, ci_series, day, w, h, T):
    """Generation by fuel (stacked), demand (dashed line) and a carbon-intensity ribbon underneath, all against UK clock time."""
    sup, dem = view["sup"], view["dem"]
    ml, mr, mt, mb, rb = 40, 6, 22, 22, 16
    tot = [sum(r["g"].values()) for r in sup]
    top = 10 * -(-max(max(tot), max(d["w"] for d in dem)) / 1000 * 1.06 // 10)
    iw, ih = w - ml - mr, h - mt - mb - rb - 8
    X = lambda x: ml + iw * x / 24
    Y = lambda gw: mt + ih - gw / top * ih
    s = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}" role="img">']
    for g in range(0, int(top) + 1, 10):
        s.append(f'<line x1="{ml}" x2="{w - mr}" y1="{Y(g):.1f}" y2="{Y(g):.1f}" stroke="#d6dee1"/>'
                 f'<text x="{ml - 8}" y="{Y(g) + 5:.1f}" text-anchor="end" font-size="14" fill="#5a6b71">{g}</text>')
    hrs = {}
    for r in sup:
        hrs.setdefault(int(r["x"] + 1e-6), {"g": [], "w": []})["g"].append(r["g"])
    for d in dem:
        hrs.setdefault(int(d["x"] + 1e-6), {"g": [], "w": []})["w"].append(d["w"])
    slot = iw / 24
    bw = slot * .78
    for hh in sorted(h_ for h_ in hrs if 0 <= h_ < 24):
        gs = hrs[hh]["g"]
        if not gs:
            continue
        x0 = X(hh) + (slot - bw) / 2
        base = 0.0
        for k in STACK:
            v = sum(g[k] for g in gs) / len(gs) / 1000
            if v <= 0:
                continue
            s.append(f'<rect x="{x0:.1f}" y="{Y(base + v):.1f}" width="{bw:.1f}" height="{max(0.0, Y(base) - Y(base + v)):.1f}" fill="{FUEL_COL[k]}"/>')
            base += v
    pts = " ".join(f"{X(d['x'] + .25):.1f},{Y(d['w'] / 1000):.1f}" for d in dem)
    s.append(f'<polyline points="{pts}" fill="none" stroke="#fff" stroke-width="8" stroke-linejoin="round" stroke-linecap="round"/>'
             f'<polyline points="{pts}" fill="none" stroke="#1b282e" stroke-width="3.5" stroke-dasharray="8 5" stroke-linejoin="round"/>')
    for pick, name, dy in ((max, T["dem_pk"], -14), (min, T["dem_lo"], -16)):
        d = pick(dem, key=lambda q: q["w"])
        px, py = X(d["x"] + .25), Y(d["w"] / 1000)
        anchor = "start" if px < ml + iw * .18 else "end" if px > ml + iw * .82 else "middle"
        s.append(f'<circle cx="{px:.1f}" cy="{py:.1f}" r="5.5" fill="#fff" stroke="#1b282e" stroke-width="3"/>'
                 f'<text x="{px:.1f}" y="{py + dy:.1f}" text-anchor="{anchor}" font-size="15" font-weight="700" fill="#1b282e" stroke="#fff" stroke-width="4" paint-order="stroke" stroke-linejoin="round">{html.escape(name)} {d["w"] / 1000:.1f} GW</text>')
    ry = mt + ih + 8
    for c in ci_series:
        x = uk_hours(c["from"], day)
        s.append(f'<rect x="{X(x):.1f}" y="{ry}" width="{iw / 48 + .4:.1f}" height="{rb}" fill="{IDX_COL[ci_index(c["v"])]}"/>')
    s.append(f'<text x="0" y="{ry + rb - 3}" text-anchor="start" font-size="11" font-weight="600" fill="#5a6b71">{html.escape(T["carbon_lbl"])}</text>')
    for hh in (0, 6, 12, 18, 24):
        s.append(f'<text x="{X(hh):.1f}" y="{h - 4}" text-anchor="{"start" if hh == 0 else "end" if hh == 24 else "middle"}" font-size="14" fill="#5a6b71">{hh:02d}:00</text>')
    s.append("</svg>")
    return "".join(s)


def supply_legend(shares, T):
    parts = [(k, shares[k]) for k in sorted(STACK, key=lambda k: -shares[k]) if shares[k] >= 0.5]
    leg = "".join(f'<span><b style="background:{FUEL_COL[k]}"></b>{html.escape(T["fuel"][k])} {round(v)}%</span>' for k, v in parts)
    return (f'<div class="leg2">{leg}<span><u></u>{html.escape(T["k_dem"])}</span>'
            f'<span><b style="background:linear-gradient(90deg,#2fa84f,#e0a800,#d6333a);height:7px;width:22px"></b>{html.escape(T["k_carbon"])}</span></div>')


def dem_stat(T, lo, hi):
    """lo/hi: (GW, when) -> the lowest on the left and the peak on the right."""
    return (f'<div class="stat dem"><div><small>{html.escape(T["dem_lo"])}</small><b class="cond">{lo[0]:.1f} GW</b><span>{html.escape(lo[1])}</span></div>'
            f'<div class="r"><small>{html.escape(T["dem_pk"])}</small><b class="cond">{hi[0]:.1f} GW</b><span>{html.escape(hi[1])}</span></div></div>')


def region_panel(rows, lang, week):
    if not rows:
        return ""
    T = TXT[lang]
    names = {r[0]: r[2 if lang == "cy" else 1] for r in REGIONS}
    items = "".join(f'<div><span><i style="background:{IDX_COL[ci_index(v)]}"></i>{html.escape(names[rid])}</span><b>{round(v)}</b></div>' for rid, v in rows)
    return f'<div class="panel"><h3 class="cond">{html.escape(T["reg_hw" if week else "reg_h"])}</h3><div class="rlist">{items}</div></div>'


def forecast_panel(fc, lang, fmt):
    if not fc:
        return ""
    T = TXT[lang]
    n = 48
    cells = [None] * n
    for x in fc["series"]:
        i = min(n - 1, max(0, int(round(x["x"] * 2))))
        cells[i] = x["v"]
    ribbon = "".join(f'<i style="background:{IDX_COL[ci_index(v)] if v is not None else "#d6dee1"}"></i>' for v in cells)
    return (f'<div class="panel tom"><h3 class="cond">{html.escape(T["fc_h"].format(d=wd_full(fc["day"], lang)))}</h3>'
            f'<div class="big cond">{html.escape(T["fc_big"].format(a=fc["clean"]["a"], b=fc["clean"]["b"]))}</div>'
            f'<p>{html.escape(T["fc_sub"].format(v=round(fc["clean"]["v"]), c=fc["dirty"]["a"], e=fc["dirty"]["b"]))}</p>'
            f'<div class="ribbon">{ribbon}</div><div class="rtimes"><span>00:00</span><span>06:00</span><span>12:00</span><span>18:00</span><span>24:00</span></div></div>')


def records_panel(lines, lang):
    T = TXT[lang]
    if lines:
        body = "".join(f'<div><span>{STAR.format(n=16)}{html.escape(t)}</span></div>' for t in lines[:3])
    else:
        body = f'<div><span style="color:#5a6b71">{html.escape(T["rec_none"])}</span></div>'
    return f'<div class="panel"><h3 class="cond">{html.escape(T["rec_h"])}</h3><div class="rlist">{body}</div></div>'


def page(lang, fmt, body, fonts_css):
    return (f'<!doctype html><html lang="{lang}"><head><meta charset="utf-8"><title>card</title>'
            f'<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
            f'<link href="https://fonts.googleapis.com/css2?family=Barlow:wght@400;500;600;700&family=Barlow+Semi+Condensed:wght@500;600;700&display=swap" rel="stylesheet">'
            f'<style>{fonts_css}{CSS}</style></head><body class="{fmt[:4]}"><div id="card">{body}</div></body></html>')


def layout(lang, fmt, date_html, kicker, badge, tiles, right_panels, boxes, stats, src):
    """Shared card layout. right_panels: the main chart panel(s); boxes: small panels in a row under it; stats: list of (big, sub) or raw html."""
    land = fmt == "landscape"
    n = len(tiles)
    head = head_html(lang, date_html, kicker)
    if badge:
        b = f'<span class="badge cond">{STAR.format(n=20)}{html.escape(badge)}</span>'
        head = head.replace('<div class="when', f'<div class="mid">{b}</div><div class="when', 1) if land else head + f'<div class="badgerow">{b}</div>'
    boxes = [x for x in boxes if x]
    two = f'<div class="two">{"".join(boxes)}</div>' if boxes else ""
    c2 = " c2" if (not land and len(stats) == 4) else " c3" if (not land and len(stats) == 3) else ""
    st = stats_html(stats).replace('class="stats"', f'class="stats{c2}"', 1)
    right = f'<div class="right flex">{"".join(right_panels)}{two}{st}</div>' if land else f'<div class="right">{"".join(right_panels)}{two}{st}</div>'
    return (head + f'<div class="grid"><div class="tiles" style="--n:{n};grid-template-rows:repeat({n},1fr)">{"".join(tiles)}</div>{right}</div>'
            f'<div class="foot"><span>{html.escape(src)}</span><span class="url">{html.escape(TXT[lang]["map"])}: {SITE}</span></div>')


def render_html(data, lang, fmt, fonts_css=""):
    T = TXT[lang]
    c, k = data["costs"], data["carbon"]
    esc = html.escape
    idx = ci_index(k["avg"])
    land = fmt == "landscape"
    tiles = []
    if c:
        net_line = ""
        if c["back"] > 0:
            net_line = f'<p class="fine">{esc(T["wind_net"].format(n=gbp(c["net"]), b=gbp(c["back"])))}</p>'
        tiles.append(f'<div class="tile" style="--c:{FUEL_COL["wind"]}"><h3 class="cond">{esc(T["wind_h"])}</h3>'
                     f'<div class="big cond">{gwh(c["wind_mwh"])}<small>GWh</small></div>'
                     f'<p>{esc(T["wind_sub"].format(g=gbp(c["paid"])))}</p>{net_line}</div>')
        gh = T["gas_h"] if c["basis"] == "system" else T["gas_h_all"]
        tiles.append(f'<div class="tile" style="--c:{FUEL_COL["gas"]}"><h3 class="cond">{esc(gh)}</h3>'
                     f'<div class="big cond">{gbp(c["gas_sys"])}</div>'
                     f'<p>{esc(T["gas_none"] if (c["gas_mwh"] < 0.05 and c["basis"] == "system") else T["gas_sub"].format(m=gwh(c["gas_mwh"])))}</p>'
                     f'<p class="fine">{esc(T["gas_any"].format(a=gbp(c["gas_all"])))}</p></div>')
    tiles.append(f'<div class="tile" style="--c:{IDX_COL[idx]}"><h3 class="cond">{esc(T["co2_h"])}</h3>'
                 f'<div class="big cond">{round(k["avg"])}<small>{T["unit"]}</small></div>'
                 f'<p><span class="dot" style="background:{IDX_COL[idx]};width:.62em;height:.62em"></span>{esc(T["idx"][idx])}</p>'
                 f'<p class="fine">{esc(T["range"].format(t1=k["lo"]["t"], v1=round(k["lo"]["v"]), t2=k["hi"]["t"], v2=round(k["hi"]["v"])))}</p></div>')
    elx, dem, year = data.get("elx"), data.get("dem"), data["date"][:4]
    zero = (T["zero_big"].format(p=zero_share(k["mix"])), T["zero_sub"])
    vs = vs_stat(k["avg"], data.get("prev_avg"), lang, False)
    homes = (T["homes_big"].format(h=homes_text(c["wind_mwh"], 1, lang)), T["homes_sub_d"]) if c and c["wind_mwh"] > 0 else None
    badge = cap(rec_text(*data["records"][0], lang, year)) if data.get("records") else None
    boxes = [region_panel(data.get("regions"), lang, False), forecast_panel(data.get("forecast"), lang, fmt)]
    stats = []
    if elx and dem:
        stats.append(dem_stat(T, dem["lo"], dem["hi"]))
    stats.append(zero)
    if vs:
        stats.append(vs)
    show_homes = homes and not (elx and dem)
    if show_homes:
        stats.append(homes)
    if elx:
        cw, ch = (660, 178 if any(boxes) else 250) if land else (912, 470 if any(boxes) else 520)
        panels = [f'<div class="panel"><h3 class="cond">{esc(T["sd_h"])}</h3>{supply_svg(elx, k["series"], data["date"], cw, ch, T)}{supply_legend(stack_shares(elx["sup"]), T)}</div>']
    else:
        cw, ch = (646, 125) if land else (912, 135)
        if land:
            boxes = []
        panels = [f'<div class="panel"><h3 class="cond">{esc(T["chart_h"])}</h3>{chart_svg(k["series"], cw, ch, lang)}</div>',
                  f'<div class="panel"><h3 class="cond">{esc(T["mix_h"])}</h3>{mix_html(k["mix"], T)}</div>']
    src = T["src"] + (T["src_tx"] if elx else "") + (T["src_homes"] if show_homes else "")
    return page(lang, fmt, layout(lang, fmt, esc(date_label(data["date"], lang)), T["kicker"], badge, tiles, panels, boxes, stats, src), fonts_css)


# ---------------------------------------------------------------- words

def extra_lines(d, lang, week):
    T = TXT[lang]
    L = []
    dem = d.get("dem")
    if dem:
        lo, hi = dem["lo"], dem["hi"]
        lw = f"{wd_short(lo[2], lang)} {lo[3]}" if week else lo[1]
        hw = f"{wd_short(hi[2], lang)} {hi[3]}" if week else hi[1]
        L.append(f"Demand on the transmission grid: lowest {lo[0]:.1f} GW ({lw}), peak {hi[0]:.1f} GW ({hw})." if lang == "en"
                 else f"Galw ar y grid trawsyrru: isaf {lo[0]:.1f} GW ({lw}), uchaf {hi[0]:.1f} GW ({hw}).")
    rows = d.get("regions")
    if rows:
        names = {r[0]: r[2 if lang == "cy" else 1] for r in REGIONS}
        lo, hi = min(rows, key=lambda r: r[1]), max(rows, key=lambda r: r[1])
        L.append(f"Cleanest region: {names[lo[0]]} ({round(lo[1])}). Dirtiest: {names[hi[0]]} ({round(hi[1])})." if lang == "en"
                 else f"Rhanbarth glanaf: {names[lo[0]]} ({round(lo[1])}). Mwyaf budr: {names[hi[0]]} ({round(hi[1])}).")
    fc = d.get("forecast")
    if fc and not week:
        L.append(f"{wd_full(fc['day'], 'en')} forecast: cleanest {fc['clean']['a']}–{fc['clean']['b']} (about {round(fc['clean']['v'])} gCO₂/kWh)." if lang == "en"
                 else f"Rhagolwg {wd_full(fc['day'], 'cy')}: glanaf {fc['clean']['a']}–{fc['clean']['b']} (tua {round(fc['clean']['v'])} gCO₂/kWh).")
    year = (d.get("last") or d.get("date") or "")[:4]
    if week:
        for day, kd, val in (d.get("records") or [])[:3]:
            L.append(f"★ {wd_short(day, lang)}: {rec_text(kd, val, lang, year)}")
    else:
        for kd, val in (d.get("records") or [])[:2]:
            L.append(f"★ {cap(rec_text(kd, val, lang, year))}")
    return L


def post_text(data, lang):
    T = TXT[lang]
    c, k = data["costs"], data["carbon"]
    idx = T["idx"][ci_index(k["avg"])]
    mix = k["mix"]
    url = f"https://{SITE}/"
    L = []
    if lang == "cy":
        L.append(f"Ddoe ar y grid ({date_short(data['date'], 'cy')})")
        if c:
            L.append(f"Gwynt wedi’i droi i lawr: {gwh(c['wind_mwh'])} GWh, {gbp_words(c['paid'], 'cy')} wedi’i dalu i ffermydd gwynt")
            if c["back"] > 0:
                L.append(f"(net {gbp_words(c['net'], 'cy')} ar ôl i {gbp_words(c['back'], 'cy')} gael ei dalu’n ôl)")
            L.append(f"Nwy wedi’i droi i fyny oherwydd cyfyngiadau’r grid: {gbp_words(c['gas_sys'], 'cy')}" if c["basis"] == "system"
                     else f"Nwy wedi’i droi i fyny (pob gweithred): {gbp_words(c['gas_sys'], 'cy')}")
        L.append(f"Carbon cyfartalog: {round(k['avg'])} gCO₂/kWh ({idx}). Glanaf: {k['lo']['t']} ({round(k['lo']['v'])}), mwyaf budr: {k['hi']['t']} ({round(k['hi']['v'])})")
        L.append(f"Gwynt a gynhyrchodd {round(mix['wind'])}% o drydan Prydain, nwy {round(mix['gas'])}%. {zero_share(mix)}% o wynt, solar, niwclear a dŵr.")
        vs = vs_stat(k["avg"], data.get("prev_avg"), "cy", False)
        if vs:
            L.append(f"{vs[0]} {vs[1]}.")
        if c and c["wind_mwh"] > 0:
            L.append(f"Digon i bweru tua {homes_text(c['wind_mwh'], 1, 'cy')} o gartrefi am ddiwrnod: dyna’r gwynt a droddwyd i lawr.")
        L.extend(extra_lines(data, "cy", False))
        L.append(f"Map byw: {url}")
        L.append("Data: NESO, Elexon BMRS")
        alt = (f"Cerdyn yn dangos {date_label(data['date'], 'cy')} ar grid trydan Prydain: " +
               (f"{gwh(c['wind_mwh'])} GWh o wynt wedi’i droi i lawr, " if c else "") +
               f"dwysedd carbon cyfartalog o {round(k['avg'])} gCO₂/kWh, siart bob hanner awr a chymysgedd cynhyrchu: gwynt {round(mix['wind'])}%, nwy {round(mix['gas'])}%.")
    else:
        L.append(f"Yesterday on the grid ({date_short(data['date'], 'en')})")
        if c:
            L.append(f"Wind turned down: {gwh(c['wind_mwh'])} GWh, {gbp_words(c['paid'], 'en')} paid to wind farms")
            if c["back"] > 0:
                L.append(f"(net {gbp_words(c['net'], 'en')} after {gbp_words(c['back'], 'en')} paid back)")
            L.append(f"Gas turned up for grid constraints: {gbp_words(c['gas_sys'], 'en')}" if c["basis"] == "system"
                     else f"Gas turned up (all actions): {gbp_words(c['gas_sys'], 'en')}")
        L.append(f"Average carbon: {round(k['avg'])} gCO₂/kWh ({idx}). Cleanest {k['lo']['t']} ({round(k['lo']['v'])}), dirtiest {k['hi']['t']} ({round(k['hi']['v'])})")
        L.append(f"Wind made {round(mix['wind'])}% of Britain’s electricity, gas {round(mix['gas'])}%. {zero_share(mix)}% came from wind, solar, nuclear and hydro.")
        vs = vs_stat(k["avg"], data.get("prev_avg"), "en", False)
        if vs:
            L.append(f"{vs[0]} {vs[1]}.")
        if c and c["wind_mwh"] > 0:
            L.append(f"The wind turned down was enough to power about {homes_text(c['wind_mwh'], 1, 'en')} homes for a day.")
        L.extend(extra_lines(data, "en", False))
        L.append(f"Live map: {url}")
        L.append("Data: NESO, Elexon BMRS")
        alt = (f"Card showing {date_label(data['date'], 'en')} on Britain’s electricity grid: " +
               (f"{gwh(c['wind_mwh'])} GWh of wind turned down, " if c else "") +
               f"average carbon intensity {round(k['avg'])} gCO₂/kWh, a half-hourly chart, and the generation mix: wind {round(mix['wind'])}%, gas {round(mix['gas'])}%.")
    return "\n".join(L) + ("\n\nAlt text for the image:\n" if lang == "en" else "\n\nTestun amgen ar gyfer y ddelwedd:\n") + alt + "\n"



# ---------------------------------------------------------------- week
def week_end(date):
    """The Sunday on or before this date, so every week card runs Monday to Sunday."""
    d = datetime.strptime(date, "%Y-%m-%d")
    return (d - timedelta(days=(d.weekday() + 1) % 7)).strftime("%Y-%m-%d")


def week_data(last, costs_fn=None):
    last = week_end(last)
    first = add_days(last, -6)
    a, _ = utc_window(first)
    _, b = utc_window(last)
    f, t = a.strftime("%Y-%m-%dT%H:%MZ"), b.strftime("%Y-%m-%dT%H:%MZ")
    rows = get_json(f"{CI_BASE}/intensity/{f}/{t}").get("data") or []
    per = {}
    for p in rows:
        i = p.get("intensity") or {}
        v = i.get("actual") if i.get("actual") is not None else i.get("forecast")
        if v is None or not p.get("from"):
            continue
        d = datetime.strptime(p["from"], "%Y-%m-%dT%H:%MZ").replace(tzinfo=timezone.utc).astimezone(UK).strftime("%Y-%m-%d")
        per.setdefault(d, []).append(float(v))
    dates = [add_days(first, i) for i in range(7)]
    if sum(len(per.get(d, [])) >= 40 for d in dates) < 5:
        raise ValueError("fewer than 5 complete days of carbon intensity for the week")
    days = []
    for d in dates:
        v = per.get(d) or []
        c = costs(d, costs_fn)
        days.append({"date": d, "wd": wd_short(d, "en"), "ci": statistics.fmean(v) if v else None, "costs": c, "wind_mwh": c["wind_mwh"] if c else None})
    have = [x for x in days if x["ci"] is not None]
    avg = statistics.fmean(x["ci"] for x in have)
    lo, hi = min(have, key=lambda x: x["ci"]), max(have, key=lambda x: x["ci"])
    mixrows = get_json(f"{CI_BASE}/generation/{f}/{t}").get("data") or []
    acc = {k: [] for k in FUELS}
    for p in mixrows:
        cur = {k: 0.0 for k in FUELS}
        for g in p.get("generationmix") or []:
            k = str(g.get("fuel", "")).lower()
            k = k if k in cur else "other"
            cur[k] += float(g.get("perc") or 0)
        for k in FUELS:
            acc[k].append(cur[k])
    if len(mixrows) < 200:
        raise ValueError(f"only {len(mixrows)} generation periods for the week")
    mix = {k: statistics.fmean(v) for k, v in acc.items()}
    cs = [x["costs"] for x in days if x["costs"]]
    tot = None
    if cs:
        tot = {"wind_mwh": sum(c["wind_mwh"] for c in cs), "paid": sum(c["paid"] for c in cs), "back": sum(c["back"] for c in cs),
               "gas_sys": sum(c["gas_sys"] for c in cs), "gas_mwh": sum(c["gas_mwh"] for c in cs), "gas_all": sum(c["gas_all"] for c in cs),
               "basis": "system" if all(c["basis"] == "system" for c in cs) else "all", "n": len(cs)}
        tot["net"] = tot["paid"] - tot["back"]
    elx = elexon_range(first, last)
    dem = None
    if elx:
        lows, highs = [], []
        for d in days:
            v = day_view(elx, d["date"])
            if v:
                l, h = demand_extremes(v["dem"])
                d["peak"] = h["w"] / 1000
                lows.append((l["w"] / 1000, f"{wd_short(d['date'], 'en')} {hm(l['x'])}", d["date"], hm(l["x"])))
                highs.append((h["w"] / 1000, f"{wd_short(d['date'], 'en')} {hm(h['x'])}", d["date"], hm(h["x"])))
        if lows and highs:
            dem = {"lo": min(lows), "hi": max(highs)}
    hist = history(last)
    order = ["rec_wind_year", "rec_ci_year", "rec_solar_year", "rec_ci_month"]
    recs = sorted([(d["date"], kd, val) for d in days for kd, val in records_for(d["date"], hist, last)], key=lambda r: order.index(r[1]))
    return {"first": first, "last": last, "days": days, "avg": avg, "lo": lo, "hi": hi, "mix": mix, "costs": tot,
            "prev_avg": period_avg(add_days(first, -7), add_days(first, -1)), "elx": bool(elx), "dem": dem, "records": recs,
            "regions": region_rows(regional_avg(first, last))}


def week_label(w, lang):
    return f"{date_short(w['first'], lang)} – {date_short(w['last'], lang)}"


def render_week_html(w, lang, fmt, fonts_css=""):
    T = TXT[lang]
    c = w["costs"]
    esc = html.escape
    idx = ci_index(w["avg"])
    land = fmt == "landscape"
    days = [dict(d, wd=wd_short(d["date"], lang)) for d in w["days"] if d["ci"] is not None]
    tiles = []
    if c:
        fine = []
        if c["back"] > 0:
            fine.append(T["wind_net"].format(n=gbp(c["net"]), b=gbp(c["back"])))
        if c["n"] < 7:
            fine.append(T["wk_partial"].format(n=c["n"]))
        tiles.append(f'<div class="tile" style="--c:{FUEL_COL["wind"]}"><h3 class="cond">{esc(T["wk_wind_h"])}</h3>'
                     f'<div class="big cond">{gwh(c["wind_mwh"])}<small>GWh</small></div>'
                     f'<p>{esc(T["wind_sub"].format(g=gbp(c["paid"])))}</p>' + "".join(f'<p class="fine">{esc(x)}</p>' for x in fine) + '</div>')
        gh = T["wk_gas_h"] if c["basis"] == "system" else T["wk_gas_h_all"]
        tiles.append(f'<div class="tile" style="--c:{FUEL_COL["gas"]}"><h3 class="cond">{esc(gh)}</h3>'
                     f'<div class="big cond">{gbp(c["gas_sys"])}</div>'
                     f'<p>{esc(T["gas_none"] if (c["gas_mwh"] < 0.05 and c["basis"] == "system") else T["wk_gas_sub"].format(m=gwh(c["gas_mwh"])))}</p>'
                     f'<p class="fine">{esc(T["gas_any"].format(a=gbp(c["gas_all"])))}</p></div>')
    lo, hi = w["lo"], w["hi"]
    tiles.append(f'<div class="tile" style="--c:{IDX_COL[idx]}"><h3 class="cond">{esc(T["wk_co2_h"])}</h3>'
                 f'<div class="big cond">{round(w["avg"])}<small>{T["unit"]}</small></div>'
                 f'<p><span class="dot" style="background:{IDX_COL[idx]};width:.62em;height:.62em"></span>{esc(T["idx"][idx])}</p>'
                 f'<p class="fine">{esc(T["wk_range"].format(d1=wd_short(lo["date"], lang), v1=round(lo["ci"]), d2=wd_short(hi["date"], lang), v2=round(hi["ci"])))}</p></div>')
    dem = w.get("dem")
    zero = (T["zero_big"].format(p=zero_share(w["mix"])), T["zero_sub"])
    vs = vs_stat(w["avg"], w.get("prev_avg"), lang, True)
    homes = (T["homes_big"].format(h=homes_text(c["wind_mwh"], 7, lang)), T["homes_sub_w"]) if c and c["wind_mwh"] > 0 else None
    year = w["last"][:4]
    recs = w.get("records") or []
    badge = (cap(rec_text(recs[0][1], recs[0][2], lang, year)) + " · " + wd_full(recs[0][0], lang)) if recs else None
    lines = [f"{wd_short(d, lang)}: {rec_text(kd, val, lang, year)}" for d, kd, val in recs]
    pk = [d for d in w["days"] if d.get("peak") is not None]
    if pk and len(lines) < 3:
        b_ = max(pk, key=lambda d: d["peak"])
        lines.append(f"{wd_short(b_['date'], lang)}: {T['rec_busy'].format(v=f'{b_[chr(112)+chr(101)+chr(97)+chr(107)]:.1f}')}")
    boxes = [region_panel(w.get("regions"), lang, True), records_panel(lines, lang)]
    stats = []
    if dem:
        stats.append(dem_stat(T, (dem["lo"][0], f"{wd_short(dem['lo'][2], lang)} {dem['lo'][3]}"), (dem["hi"][0], f"{wd_short(dem['hi'][2], lang)} {dem['hi'][3]}")))
    stats.append(zero)
    if vs:
        stats.append(vs)
    show_homes = homes and not dem
    if show_homes:
        stats.append(homes)
    cw, ch = (660, 180) if land else (912, 470)
    keys = f'<div class="leg2"><span><b style="background:linear-gradient(90deg,#2fa84f,#e0a800,#d6333a);width:22px;height:9px"></b>{esc(T["k_bars"])}</span></div>'
    panels = [f'<div class="panel"><h3 class="cond">{esc(T["wk_chart_h2"])}</h3>{week_chart_svg(days, cw, ch, T, cols=land)}{keys}</div>']
    src = T["src"] + (T["src_tx"] if dem else "") + (T["src_homes"] if show_homes else "")
    return page(lang, fmt, layout(lang, fmt, esc(week_label(w, lang)), T["wk_kicker"], badge, tiles, panels, boxes, stats, src), fonts_css)


def week_post_text(w, lang):
    T = TXT[lang]
    c, mix = w["costs"], w["mix"]
    idx = T["idx"][ci_index(w["avg"])]
    url = f"https://{SITE}/"
    lo, hi = w["lo"], w["hi"]
    vs = vs_stat(w["avg"], w.get("prev_avg"), lang, True)
    L = []
    if lang == "cy":
        L.append(f"Yr wythnos ddiwethaf ar y grid ({week_label(w, 'cy')})")
        if c:
            L.append(f"Gwynt wedi’i droi i lawr: {gwh(c['wind_mwh'])} GWh, {gbp_words(c['paid'], 'cy')} wedi’i dalu i ffermydd gwynt")
            if c["back"] > 0:
                L.append(f"(net {gbp_words(c['net'], 'cy')} ar ôl i {gbp_words(c['back'], 'cy')} gael ei dalu’n ôl)")
            L.append(f"Nwy wedi’i droi i fyny oherwydd cyfyngiadau’r grid: {gbp_words(c['gas_sys'], 'cy')}" if c["basis"] == "system"
                     else f"Nwy wedi’i droi i fyny (pob gweithred): {gbp_words(c['gas_sys'], 'cy')}")
            if c["n"] < 7:
                L.append(f"(ffigurau cost ar gyfer {c['n']} o 7 diwrnod)")
        L.append(f"Carbon cyfartalog: {round(w['avg'])} gCO₂/kWh ({idx}). Glanaf: {wd_short(lo['date'], 'cy')} ({round(lo['ci'])}), mwyaf budr: {wd_short(hi['date'], 'cy')} ({round(hi['ci'])})")
        if vs:
            L.append(f"{vs[0]} {vs[1]}.")
        L.append(f"Gwynt a gynhyrchodd {round(mix['wind'])}% o drydan Prydain, nwy {round(mix['gas'])}%.")
        if c and c["wind_mwh"] > 0:
            L.append(f"Digon i bweru tua {homes_text(c['wind_mwh'], 7, 'cy')} o gartrefi am wythnos: dyna’r gwynt a droddwyd i lawr.")
        L.extend(extra_lines(w, "cy", True))
        L.append(f"Map byw: {url}")
        L.append("Data: NESO, Elexon BMRS")
        alt = (f"Cerdyn yn dangos yr wythnos {week_label(w, 'cy')} ar grid trydan Prydain: " +
               (f"{gwh(c['wind_mwh'])} GWh o wynt wedi’i droi i lawr, " if c else "") +
               f"dwysedd carbon cyfartalog o {round(w['avg'])} gCO₂/kWh, siart fesul diwrnod a chymysgedd cynhyrchu: gwynt {round(mix['wind'])}%, nwy {round(mix['gas'])}%.")
    else:
        L.append(f"Last week on the grid ({week_label(w, 'en')})")
        if c:
            L.append(f"Wind turned down: {gwh(c['wind_mwh'])} GWh, {gbp_words(c['paid'], 'en')} paid to wind farms")
            if c["back"] > 0:
                L.append(f"(net {gbp_words(c['net'], 'en')} after {gbp_words(c['back'], 'en')} paid back)")
            L.append(f"Gas turned up for grid constraints: {gbp_words(c['gas_sys'], 'en')}" if c["basis"] == "system"
                     else f"Gas turned up (all actions): {gbp_words(c['gas_sys'], 'en')}")
            if c["n"] < 7:
                L.append(f"(cost figures for {c['n']} of 7 days)")
        L.append(f"Average carbon: {round(w['avg'])} gCO₂/kWh ({idx}). Cleanest {wd_short(lo['date'], 'en')} ({round(lo['ci'])}), dirtiest {wd_short(hi['date'], 'en')} ({round(hi['ci'])})")
        if vs:
            L.append(f"{vs[0]} {vs[1]}.")
        L.append(f"Wind made {round(mix['wind'])}% of Britain’s electricity, gas {round(mix['gas'])}%.")
        if c and c["wind_mwh"] > 0:
            L.append(f"The wind turned down was enough to power about {homes_text(c['wind_mwh'], 7, 'en')} homes for a week.")
        L.extend(extra_lines(w, "en", True))
        L.append(f"Live map: {url}")
        L.append("Data: NESO, Elexon BMRS")
        alt = (f"Card showing the week {week_label(w, 'en')} on Britain’s electricity grid: " +
               (f"{gwh(c['wind_mwh'])} GWh of wind turned down, " if c else "") +
               f"average carbon intensity {round(w['avg'])} gCO₂/kWh, a chart for each day, and the generation mix: wind {round(mix['wind'])}%, gas {round(mix['gas'])}%.")
    return "\n".join(L) + ("\n\nAlt text for the image:\n" if lang == "en" else "\n\nTestun amgen ar gyfer y ddelwedd:\n") + alt + "\n"


def build_week(last, out, costs_fn=None, fonts_css=""):
    out.mkdir(parents=True, exist_ok=True)
    w = week_data(last, costs_fn)
    pages = []
    for lang in ("en", "cy"):
        for fmt, (pw, ph) in (("landscape", (1200, 675)), ("portrait", (1080, 1350))):
            pages.append((f"card-week-{lang}-{fmt}.png", render_week_html(w, lang, fmt, fonts_css), pw, ph))
        (out / f"post-week-{lang}.txt").write_text(week_post_text(w, lang), encoding="utf-8")
    screenshot(pages, out)
    summary = {"first": w["first"], "last": w["last"], "generated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ"),
               "avg_ci": round(w["avg"], 1), "prev_avg": None if w["prev_avg"] is None else round(w["prev_avg"], 1),
               "mix": {k: round(v, 1) for k, v in w["mix"].items()},
               "days": [{"date": d["date"], "ci": None if d["ci"] is None else round(d["ci"], 1), "wind_mwh": d["wind_mwh"]} for d in w["days"]],
               "costs": w["costs"], "demand_gw": w["dem"], "regions": w["regions"], "records": w["records"]}
    (out / "week-data.json").write_text(json.dumps(summary, indent=1, ensure_ascii=False), encoding="utf-8")
    return w


# ---------------------------------------------------------------- run
def screenshot(pages, out):
    """pages: [(filename, html, width, height)] -> PNG files, drawn at 2x."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        try:
            b = p.chromium.launch(channel="chrome")       # GitHub's runners have Chrome installed
        except Exception:
            b = p.chromium.launch()
        for name, doc, w, h in pages:
            pg = b.new_page(viewport={"width": w, "height": h}, device_scale_factor=2)
            pg.set_content(doc, wait_until="networkidle")
            pg.evaluate("document.fonts.ready.then(()=>true)")
            pg.wait_for_timeout(300)
            over = pg.evaluate("(()=>{const c=document.querySelector('#card');let o=Math.max(c.scrollHeight-c.clientHeight, c.scrollWidth-c.clientWidth);const f=document.querySelector('.foot'),g=document.querySelector('.grid');if(f&&g){let b=0;g.querySelectorAll('*').forEach(e=>{b=Math.max(b,e.getBoundingClientRect().bottom)});o=Math.max(o,Math.round(b-f.getBoundingClientRect().top))}return o})()")
            if over > 2:
                print(f"WARNING: {name} overflows its card by {over}px: check the layout before posting", file=sys.stderr)
            pg.locator("#card").screenshot(path=str(out / name))
            pg.close()
        b.close()


def build(date, out, costs_fn=None, fonts_css=""):
    out.mkdir(parents=True, exist_ok=True)
    data = {"date": date, "carbon": carbon_and_mix(date), "costs": costs(date, costs_fn),
            "prev_avg": period_avg(add_days(date, -7), add_days(date, -1))}
    xr = elexon_range(date, date)
    data["elx"] = day_view(xr, date) if xr else None
    data["dem"] = None
    if data["elx"]:
        lo, hi = demand_extremes(data["elx"]["dem"])
        data["dem"] = {"lo": (lo["w"] / 1000, hm(lo["x"])), "hi": (hi["w"] / 1000, hm(hi["x"]))}
    data["regions"] = region_rows(regional_avg(date, date))
    data["forecast"] = forecast_for(add_days(date, 1))
    data["records"] = records_for(date, history(date), date)
    pages = []
    for lang in ("en", "cy"):
        for fmt, (w, h) in (("landscape", (1200, 675)), ("portrait", (1080, 1350))):
            pages.append((f"card-{lang}-{fmt}.png", render_html(data, lang, fmt, fonts_css), w, h))
        (out / f"post-{lang}.txt").write_text(post_text(data, lang), encoding="utf-8")
    screenshot(pages, out)
    summary = {"date": date, "generated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ"),
               "avg_ci": round(data["carbon"]["avg"], 1), "mix": {k: round(v, 1) for k, v in data["carbon"]["mix"].items()},
               "prev_avg": None if data["prev_avg"] is None else round(data["prev_avg"], 1), "costs": data["costs"],
               "demand_gw": data["dem"], "regions": data["regions"],
               "forecast": None if not data["forecast"] else {k_: v_ for k_, v_ in data["forecast"].items() if k_ != "series"},
               "records": data["records"]}
    (out / "card-data.json").write_text(json.dumps(summary, indent=1, ensure_ascii=False), encoding="utf-8")
    return data


def arg(name, default):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default


def main():
    date = arg("--date", (datetime.now(UK) - timedelta(days=1)).strftime("%Y-%m-%d"))
    out = Path(arg("--out", ROOT / "daily-card"))
    if "--week" in sys.argv:
        w = build_week(date, out)
        c = w["costs"]
        print(f"week card {w['first']} to {w['last']}: carbon {w['avg']:.0f} gCO2/kWh" + (f", wind turned down {c['wind_mwh']:.0f} MWh over {c['n']} days" if c else ", costs not available"))
        print("written to", out)
        return
    d = build(date, out)
    c = d["costs"]
    print(f"card for {date}: carbon {d['carbon']['avg']:.0f} gCO2/kWh" + (f", wind turned down {c['wind_mwh']:.0f} MWh, paid £{c['paid']:,.0f}, gas (system) £{c['gas_sys']:,.0f}" if c else ", costs not available"))
    print("written to", out)


if __name__ == "__main__":
    main()
