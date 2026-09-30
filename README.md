# UK power, source to socket

An interactive, bilingual (English and Welsh) map of Britain's electricity system. It shows where power is generated, the grid it travels along, where it is used, what flows in and out through interconnectors, and what is coming next.

The map is a single self-contained web page (`index.html`). The `src/`, `data/` and `tools/` folders are what `index.html` is built from, plus the scripts that keep its data fresh.

## What it shows

**Map tab**
- **Major sites.** Around 90 power stations, interconnectors and grid links, each with capacity, status and dates. Each has a route showing where its electricity typically goes, drawn along real 400 kV and 275 kV pylon lines.
- **Smaller generators.** About 2,600 more from OpenStreetMap appear when you zoom in, including about 270 in Wales.
- **Year slider (2026–2040).** Planned projects such as Wylfa, Hinkley Point C and Sizewell C switch on, and older nuclear stations close.
- **Grid infrastructure layer.** Lines coloured by voltage, about 400 substations and offshore wind farm areas. Tapping a substation shows which mapped power stations route through it.
- **Wales view.** Welsh capacity, the latest Welsh generation mix, and the links out of Wales.
- **Postcode check** (hosted version only). Local carbon intensity, the cleanest time in the next 24 hours, and the nearest sites.
- **Sources and checks.** Every site shows its sources, with a badge showing whether its capacity has been cross-checked against OpenStreetMap.

**Carbon intensity tab**
- Right now, today's average and this year so far.
- A half-hourly chart: the last 24 hours and the next 48.
- History since 2009 with the Clean Power 2030 pathway, plus the carbon intensity of imports by country.

**Stories tab**
- Where electricity is cleanest right now, with the 14 regions shaded on the map.
- Hours at the 2030 clean power level.
- Wind that can't get south (live curtailment).
- The grid connection queue.
- Clean hours are cheap hours (carbon against wholesale price).

**Why now.** The Map and Carbon tabs explain whether carbon intensity is higher or lower than typical for the month and time of day, and which sources are driving the difference. "Typical" comes from the last two years of NESO's historic generation mix.

**Curtailment.** Wind farms being turned down show the megawatts, the estimated payment (from Elexon bid prices) and the extra CO₂ from replacing that power with gas. A scenario block in Stories estimates how much of today's curtailed Scottish wind Eastern Green Link 1 and 2 could carry south.

**Plan tab.** "When to run it" finds the cleanest time to run a flexible load (EV charging, a kiln, a cold store) in any region over the next 48 hours, shows the CO₂ saved compared with starting now, and can add the best window to a calendar.

**Future tab.** Two views, switched at the top. **2030 simulator:** a simulator that replays every hour of 2024's real weather and demand with the capacities you choose (offshore and onshore wind, solar, nuclear, batteries, long-duration storage, interconnectors, new low-carbon plant and demand growth). It shows whether the system meets the Clean Power 2030 goal of 95% clean generation, how much gas it still needs, the longest gas-heavy spell and how much wind and solar would be turned down. Green bands on the sliders show the government's 2030 plan, and a model check compares the replayed base year with what actually happened.

**Weekly digest.** The top of Stories summarises the last Monday-to-Sunday week in plain English, with records and a shareable image. Earlier weeks are one tap away.

**Forecast accuracy.** The Carbon tab shows how well NESO's 24-hour forecasts matched reality over the last 30 days, including how often the forecast's cleanest window really was the cleanest.

**How this map works.** One page, in both languages, explains every calculation, estimate and source. It opens from Layers, the Map tab and "How this is calculated" links throughout.

**Curtailment tracker.** Stories shows how much wind was turned down over the last 30 days, what it cost and the extra CO₂, with the wind farms turned down most. The live curtailment box on the Map tab names each wind farm being turned down right now, grouped by region, with a link to each.

**Station history.** Each mapped power station's panel shows its output over the last week, hour by hour, with any turn-down shaded, plus how often it was turned down in the last 30 days.

**Records and milestones.** Stories lists Britain's all-time records (lowest carbon half-hour, cleanest day, longest spell at 50 g or below, highest wind and solar shares) and milestones from the last 30 days. They all come from one dataset, so a record is never an artefact of comparing two measures. Wales has its own row from NESO's regional estimates.

**Share this view.** The share button copies a link that reopens the map exactly as you see it: tab, site or region, year, Wales view, simulator settings or digest week. Link previews on LinkedIn and messaging apps show `social.png`.

**Downloads.** On the published map, every chart's enlarged view has **Download data (CSV)**, and the table downloads as filtered.

**Compare years** (also in the Future tab): pick two years to see capacity by technology side by side, what's new and what closes. You can also highlight the changes on the map: a green ring means new and a red dashed ring means closed.

**Also:**
- One search box for sites, substations, smaller generators, places, regions and postcodes.
- A **Layers** panel.
- A sortable, filterable **Table** of every site.
- Hover previews on desktop.
- A draggable information panel on phones.
- A short first-visit guide, which you can reopen from Layers.

## Folder layout

Everything sits at the top level of the repository:

```
index.html            the built map: this is what GitHub Pages serves
README.md
.nojekyll             tells GitHub Pages to serve files as they are
.github/workflows/refresh-power-map.yml   automatic data refresh
src/app.html          page template: layout, styles, code, text in both languages
src/sites.js          curated sites, interconnectors and grid links (edit these by hand)
social.png            the picture shown when the link is shared
data/*.json           datasets (generated by the tools); most are embedded in index.html
data/plants.json, data/subs.json   smaller generators and substations (load just after the map appears)
data/sim.json         one year of hourly data for the 2030 simulator (loads when the simulator opens)
data/accuracy.json    forecast accuracy record (grows daily)
data/digest.json      weekly digests (one added each week)
data/daily.json       daily Wales figures from NESO's regional estimates
data/curtail.json     daily curtailment totals and each wind farm's share (loads when needed)
data/stations.json    each mapped station's hourly output for the last 14 days (loads when needed)
tools/build.py        assembles index.html from src/ and data/
tools/update_snapshot.py   refreshes the offline snapshot, forecast accuracy, weekly digest and Wales figures (daily)
tools/update_elexon.py     refreshes the curtailment tracker and station history from Elexon (daily)
tools/update_history.py    refreshes carbon history, records and the simulator data from NESO (daily)
tools/update_osm.py        refreshes grid, substations, smaller sites and routes from OpenStreetMap (monthly)
tools/requirements.txt
```

## Keeping the data fresh automatically

The GitHub Action runs on its own:

| When | What it refreshes | Script |
|---|---|---|
| Every day, 05:15 UTC | The offline snapshot: national, Welsh and regional mix, today's carbon intensity, import factors. Also saves today's 24-hour forecast, scores earlier ones, and adds last week's digest once the week is over | `update_snapshot.py` |
| Every day | Yesterday's curtailment and each station's output, read half-hour by half-hour from Elexon (the first run fills in the last week) | `update_elexon.py` |
| Every day | Carbon history since 2009, records and milestones, and the simulator's hourly year (NESO historic generation mix) | `update_history.py` |
| 2nd of each month | All of the above, plus lines, substations, smaller sites, wind farm areas, routes and cross-checks (OpenStreetMap UK extract) | `update_osm.py` |

After refreshing, it rebuilds `index.html` and commits only if something changed. Each step works independently: if one source is down, the previous data is kept and the rest still updates.

GitHub pauses scheduled workflows in repositories with no activity for 60 days. The daily commits normally prevent this, but if the map stops updating, check the Actions tab.

**Running it by hand** (Python 3.10+, Node.js; `osmium-tool` recommended for the OpenStreetMap step):

```bash
pip install -r tools/requirements.txt
python tools/update_snapshot.py
python tools/update_elexon.py
python tools/update_history.py              # or: --csv df_fuel_ckan.csv
python tools/update_osm.py                  # or: --pbf united-kingdom-latest.osm.pbf
python tools/build.py                       # or: --inline for one self-contained file
```

**Editing sites.** Change `src/sites.js`, then run `update_osm.py` (to rebuild routes and cross-checks) and `build.py`.

## Live data and snapshot mode

The simulator's data (`data/sim.json`, about 120 KB) is kept out of `index.html` so the map opens quickly. The page fetches it only when someone opens the 2030 tab, so the simulator works on the hosted version only (or build with `python tools/build.py --inline-sim` to embed it).

The page always contains an embedded snapshot, so it works anywhere, including offline and inside sandboxed previews. When it is hosted on its own web address, it also fetches live data every five minutes. Each feed is independent: if one fails, the map uses the snapshot for that part.

To see which feeds are working, tap the status pill at the top left of the map, or scroll to **Data sources** at the bottom of the Map tab.

| Feed | Source |
|---|---|
| GB, Welsh and regional mix; carbon intensity; import factors | NESO Carbon Intensity API |
| Output per power station (`/balancing/physical/all`, PN) | Elexon Insights |
| Balancing actions for curtailment (`/balancing/acceptances/all`) | Elexon Insights |
| Generation by fuel and interconnector flows (`/generation/outturn/current`) | Elexon Insights |
| Wholesale prices (market index) | Elexon Insights |
| Postcode lookup | postcodes.io |

All feeds were confirmed working on the live site on 29 September 2026.

## Data sources and licences

| Data | Source |
|---|---|
| Major sites: capacities, dates, notes | Compiled from public announcements; checked September 2026 |
| Lines, substations, smaller generators, wind farm areas | © OpenStreetMap contributors, via Geofabrik (Open Database Licence) |
| Historic generation mix and carbon intensity | NESO Data Portal |
| Region boundaries (GSP regions grouped into 14 regions) | NESO Data Portal |
| Live mix, regional and import carbon | NESO Carbon Intensity API |
| Output, flows, balancing, prices | Elexon Insights (BMRS): contains BMRS data © Elexon Limited |
| Connection queue figures | NESO; Knight Frank; Curvature Energy |

The map carries the required credits in its bottom corner. Check each provider's current terms before any commercial use.

## Methods and caveats

- **Routes show the typical direction of flow.** Electricity joins a shared pool once it's on the grid, so a route shows where power usually goes, not a fixed destination.
- **Per-station live output is reported, not metered.** Where a station reports to Elexon, the figure is its physical notification: the output it told the grid operator it planned to produce that half-hour. Turn-down instructions are shown separately as curtailment.
- **Some live output figures are estimates.** Where Elexon metering isn't available, a site's output is its capacity multiplied by how hard that technology is running nationally. The site panel says which method was used.
- **Two carbon measures are used.** The history uses NESO's generation-based figures. The live figures estimate electricity consumed, including imports. They usually differ by 10 to 30 gCO₂/kWh.
- **Future dates are targets.** They are developer or government targets and often slip. The 2030 and 2035 carbon points are targets, not forecasts.
- **Northern Ireland** runs a separate grid shared with Ireland.
- **OpenStreetMap is community-mapped.** Some entries are out of date.

## Accessibility

- **Keyboard:** everything works from the keyboard. You can tab to sites, the search results and the table rows.
- **Motion:** reduced-motion settings turn off the animated flows.
- **Themes:** light and dark mode are supported.
- **Language:** fully bilingual, and your choice is remembered.
- **Table view:** a text alternative to the map for screen-reader users.
