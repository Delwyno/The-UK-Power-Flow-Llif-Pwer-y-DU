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

The cards are drawn from HTML with a headless browser (Playwright). On GitHub's runners Chrome is already installed;
elsewhere run `playwright install chromium` once.
Contains BMRS data (c) Elexon Limited. Contains NESO Carbon Intensity API data.
"""
import html
import json
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


def gwh(mwh):
    g = mwh / 1000
    return f"{g:.1f}" if g < 100 else f"{g:.0f}"


def date_label(date, lang):
    d = datetime.strptime(date, "%Y-%m-%d")
    if lang == "cy":
        return f"{CY_DAYS[d.weekday()]} {d.day} {CY_MONTHS[d.month - 1]}"
    return f"{EN_DAYS[d.weekday()]} {d.day} {EN_MONTHS[d.month - 1]}"


def date_short(date, lang):
    d = datetime.strptime(date, "%Y-%m-%d")
    if lang == "cy":
        return f"{CY_DAYS[d.weekday()].replace('Dydd ', '')} {d.day} {CY_MONTHS[d.month - 1][:3]}"
    return f"{EN_DAYS[d.weekday()][:3]} {d.day} {EN_MONTHS[d.month - 1][:3]}"


# ---------------------------------------------------------------- card
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
.foot{display:flex;justify-content:space-between;align-items:flex-end;gap:20px;color:#5a6b71}
.foot .url{font-weight:700;color:#1b282e;white-space:nowrap}

.land #card{width:1200px;height:675px;padding:28px 36px 22px}
.land .head{margin-bottom:16px}
.land .brand{font-size:30px;line-height:1.05}.land .brand small{font-size:17px;margin-top:3px}
.land .when{font-size:26px;line-height:1.1}.land .when span{font-size:17px}
.land .grid{display:grid;grid-template-columns:430px 1fr;gap:16px;flex:1;min-height:0}
.land .tiles{display:grid;grid-template-rows:1.25fr 1fr 1fr;gap:12px;min-height:0}
.land .tile{padding:12px 18px 10px 26px;display:flex;flex-direction:column;justify-content:center}
.land .tile h3{font-size:14px;margin-bottom:4px}
.land .tile .big{font-size:54px}.land .tile .big small{font-size:20px}
.land .tile p{font-size:17px;line-height:1.2;margin-top:4px}
.land .tile p.fine{font-size:14px;margin-top:2px}
.land .right{display:grid;grid-template-rows:1fr auto;gap:12px;min-height:0}
.land .panel{padding:14px 18px 12px}
.land .panel h3{font-size:14px;margin-bottom:6px}
.land .legend{margin-top:10px;gap:4px 16px;font-size:17px}.land .legend b{width:13px;height:13px;margin-right:6px}
.land .mixbar{height:36px}.land .mixbar i{font-size:16px;line-height:36px}
.land .foot{margin-top:12px;font-size:13px;line-height:1.25}.land .foot .url{font-size:17px}

.port #card{width:1080px;height:1350px;padding:44px 56px 34px}
.port .head{margin-bottom:22px}
.port .brand{font-size:44px;line-height:1.05}.port .brand small{font-size:24px;margin-top:5px}
.port .when{font-size:34px;line-height:1.1}.port .when span{font-size:24px}
.port .grid{display:flex;flex-direction:column;gap:16px;flex:1;min-height:0}
.port .tiles{display:flex;flex-direction:column;gap:14px}
.port .tile{padding:16px 26px 14px 38px}
.port .tile h3{font-size:19px;margin-bottom:4px}
.port .tile .big{font-size:70px}.port .tile .big small{font-size:28px}
.port .tile p{font-size:25px;line-height:1.2;margin-top:6px}
.port .tile p.fine{font-size:20px;margin-top:3px}
.port .right{display:flex;flex-direction:column;gap:14px}
.port .panel{padding:16px 24px 16px}
.port .panel h3{font-size:19px;margin-bottom:6px}
.port .legend{margin-top:12px;gap:4px 20px;font-size:22px}.port .legend b{width:16px;height:16px;margin-right:8px}
.port .mixbar{height:46px}.port .mixbar i{font-size:21px;line-height:46px}
.port .foot{margin-top:auto;padding-top:14px;font-size:17px;line-height:1.3;flex-direction:column;align-items:flex-start;gap:8px}.port .foot .url{font-size:26px}
"""


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
    cw, ch = (646, 282) if land else (912, 215)
    body = (
        f'<div class="head"><div class="brand cond">THE UK POWER FLOW<small>LLIF PŴER Y DU</small></div>'
        f'<div class="when cond">{esc(date_label(data["date"], lang))}<span>{esc(T["kicker"])}</span></div></div>'
        f'<div class="grid"><div class="tiles" style="grid-template-rows:repeat({len(tiles)},1fr)">{"".join(tiles)}</div>'
        f'<div class="right"><div class="panel"><h3 class="cond">{esc(T["chart_h"])}</h3>{chart_svg(k["series"], cw, ch, lang)}</div>'
        f'<div class="panel"><h3 class="cond">{esc(T["mix_h"])}</h3>{mix_html(k["mix"], T)}</div></div></div>'
        f'<div class="foot"><span>{esc(T["src"])}</span><span class="url">{esc(T["map"])}: {SITE}</span></div>'
    )
    return (f'<!doctype html><html lang="{lang}"><head><meta charset="utf-8"><title>card</title>'
            f'<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
            f'<link href="https://fonts.googleapis.com/css2?family=Barlow:wght@400;500;600;700&family=Barlow+Semi+Condensed:wght@500;600;700&display=swap" rel="stylesheet">'
            f'<style>{fonts_css}{CSS}</style></head><body class="{fmt[:4]}"><div id="card">{body}</div></body></html>')


# ---------------------------------------------------------------- words
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
        L.append(f"Gwynt a gynhyrchodd {round(mix['wind'])}% o drydan Prydain, nwy {round(mix['gas'])}%.")
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
        L.append(f"Wind made {round(mix['wind'])}% of Britain’s electricity, gas {round(mix['gas'])}%.")
        L.append(f"Live map: {url}")
        L.append("Data: NESO, Elexon BMRS")
        alt = (f"Card showing {date_label(data['date'], 'en')} on Britain’s electricity grid: " +
               (f"{gwh(c['wind_mwh'])} GWh of wind turned down, " if c else "") +
               f"average carbon intensity {round(k['avg'])} gCO₂/kWh, a half-hourly chart, and the generation mix: wind {round(mix['wind'])}%, gas {round(mix['gas'])}%.")
    return "\n".join(L) + ("\n\nAlt text for the image:\n" if lang == "en" else "\n\nTestun amgen ar gyfer y ddelwedd:\n") + alt + "\n"


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
            over = pg.evaluate("(()=>{const c=document.querySelector('#card');return Math.max(c.scrollHeight-c.clientHeight, c.scrollWidth-c.clientWidth)})()")
            if over > 2:
                print(f"WARNING: {name} overflows its card by {over}px: check the layout before posting", file=sys.stderr)
            pg.locator("#card").screenshot(path=str(out / name))
            pg.close()
        b.close()


def build(date, out, costs_fn=None, fonts_css=""):
    out.mkdir(parents=True, exist_ok=True)
    data = {"date": date, "carbon": carbon_and_mix(date), "costs": costs(date, costs_fn)}
    pages = []
    for lang in ("en", "cy"):
        for fmt, (w, h) in (("landscape", (1200, 675)), ("portrait", (1080, 1350))):
            pages.append((f"card-{lang}-{fmt}.png", render_html(data, lang, fmt, fonts_css), w, h))
        (out / f"post-{lang}.txt").write_text(post_text(data, lang), encoding="utf-8")
    screenshot(pages, out)
    summary = {"date": date, "generated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ"),
               "avg_ci": round(data["carbon"]["avg"], 1), "mix": {k: round(v, 1) for k, v in data["carbon"]["mix"].items()},
               "costs": data["costs"]}
    (out / "card-data.json").write_text(json.dumps(summary, indent=1, ensure_ascii=False), encoding="utf-8")
    return data


def arg(name, default):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default


def main():
    date = arg("--date", (datetime.now(UK) - timedelta(days=1)).strftime("%Y-%m-%d"))
    out = Path(arg("--out", ROOT / "daily-card"))
    d = build(date, out)
    c = d["costs"]
    print(f"card for {date}: carbon {d['carbon']['avg']:.0f} gCO2/kWh" + (f", wind turned down {c['wind_mwh']:.0f} MWh, paid £{c['paid']:,.0f}, gas (system) £{c['gas_sys']:,.0f}" if c else ", costs not available"))
    print("written to", out)


if __name__ == "__main__":
    main()
