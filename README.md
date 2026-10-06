# The UK Power Flow · Llif Pŵer y DU

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

**Switch-off prices.** Each tracked wind farm shows its support scheme (Renewables Obligation, a 2014 early Contract for Difference, or an auction CfD) and what it cost per MWh to switch off over the last 30 days. Stories compares the schemes and explains why older ones cost more. Schemes and sources are in `data/subsidy.json`.

**Replay the last 7 days.** From the Map or Stories tab, the map plays back the week hour by hour for every station that reports to Elexon: flows change, wind farms being turned down light up, and a label on the map shows the hour. Pause, scrub or tap the chart to jump.

**Grid queue** (in the Future tab). Every project with a contract to connect to the transmission grid, from NESO's TEC register, shown as circles at each connection site. Totals by technology and contracted year, the longest queues, each site's largest projects, and a Wales-only view.

**Wales in depth.** The Wales view shows progress against the Welsh Government's targets (70% of consumption from renewables by 2030, 100% by 2035), local ownership and heat pumps, recent wind in Wales, Welsh wind farms turned down, and what's queuing to connect in Wales.

**Checked against NESO.** The curtailment tracker compares its wind payments with NESO's official daily thermal constraint costs, with a note on why they differ.

**Hydrogen** (in the Future tab). The first funded hydrogen production projects (the 11 first-round winners), the proposed Project Union East Coast pipeline corridor and the hubs around them, each with its status, date checked and sources. Britain has no national hydrogen network yet, so this shows plans and progress, including projects that have been paused. It is curated by hand in `data/hydrogen.json`; the Wales view has its own hydrogen section. The tab also has an electrolyser what-if that replays each wind farm's real turn-down, and a ranking of where a 50 MW electrolyser would have been busiest.

**What it costs: wind off, gas on.** The **Curtailment** tab (Costs, Wind farms and Why it happens) shows today so far, with a running total by hour, the last seven days, and running totals for the month, last month and since tracking began, with a per-household illustration. Each period is compared with the same dates a year earlier. It adds up two things from Elexon's own indicative cashflows: payments to switch wind farms off, and payments to turn gas plants up, counting only system actions. The week's total is compared with NESO's published thermal constraint cost. A **gas split** shows how much of the gas turned up was a system action (the kind used to manage constraints such as wind) and how much was ordinary balancing of the market, for today, the last seven days, the year so far and day by day. Today's figure is refreshed about every 30 minutes by a scheduled job that publishes one small file to a separate `live-data` branch, so the history of `main` isn't cluttered.

**Data freshness.** Layers > Data freshness shows when each dataset last changed against how often it should, with a green, amber or red status. The daily refresh runs the same check (`tools/health.py`) and opens a GitHub issue labelled `data-health` if something has stopped updating, and closes it when all is well.

**Resizable side panel.** On a computer, drag the left edge of the side panel to make it wider, and everything inside it grows with it. Double-click the edge, or press Home when it has focus, to reset; the arrow keys adjust it. The width is remembered in the browser.

**Electricity demand.** The Map tab shows Great Britain's national demand live (Elexon's Initial National Demand Outturn, half-hourly, refreshed every few minutes while the page is open): the figure now, the peak so far today, the change against the same time yesterday, and a chart of today against yesterday. It is measured at the transmission grid, so it leaves out rooftop solar and other embedded generation; the methods page explains what that means. It needs the live feed, so it does not appear in the offline snapshot.

**Electricity supply.** Under the demand card, the Map tab shows live supply: the total in GW and how it splits between wind, gas, imports, nuclear, biomass, hydro and other, with a chart of the day so far against transmission demand. It comes from Elexon's instantaneous generation outturn (refreshed every five minutes), measured at the transmission grid, so like demand it leaves out solar and wind on local networks (the percentage mix at the top, from the Carbon Intensity API, includes estimates of them). Supply should match Transmission System Demand closely, and the card says by how much.

**Open data.** Twelve CSV files, refreshed daily at stable addresses under `data/open/`, with an index describing each (`data/open/index.json`). Linked from "How this map works" and the Layers panel.

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
data/costs.json        daily and hourly wind turn-down and gas turn-up costs (loads when needed)
data/bmu_fuel.json    which BM units are wind and which are gas (from Elexon; cached)
data/health.json      data freshness report, written by tools/health.py
data/hydrogen.json    hydrogen projects and pipeline, curated by hand with sources and status dates
data/subsidy.json     support scheme for each tracked wind farm, with sources (edit by hand)
data/queue.json       the connection queue by connection site (loads when needed)
data/constraints.json NESO's daily constraint costs, for the cross-check (loads when needed)
data/gazetteer.json   named substations and power stations from OpenStreetMap, for placing queue sites
data/open/            open data: CSV files and index.json
tools/build.py        assembles index.html from src/ and data/
tools/update_snapshot.py   refreshes the offline snapshot, forecast accuracy, weekly digest and Wales figures (daily)
tools/update_elexon.py     refreshes the curtailment tracker and station history from Elexon (daily)
tools/update_history.py    refreshes carbon history, records and the simulator data from NESO (daily)
tools/update_osm.py        refreshes grid, substations, smaller sites and routes from OpenStreetMap (monthly)
tools/update_neso.py       refreshes the connection queue and official constraint costs from the NESO data portal (daily)
tools/export_open.py       writes the open data CSVs (daily)
tools/daily_card.py        draws yesterday's shareable cards and post text, in English and Welsh (daily)
tools/requirements.txt
```

## Keeping the data fresh automatically

The GitHub Action runs on its own:

| When | What it refreshes | Script |
|---|---|---|
| Every day, 05:15 UTC | The offline snapshot: national, Welsh and regional mix, today's carbon intensity, import factors. Also saves today's 24-hour forecast, scores earlier ones, and adds last week's digest once the week is over | `update_snapshot.py` |
| Every day | Yesterday's curtailment and each station's output, read half-hour by half-hour from Elexon (the first run fills in the last week) | `update_elexon.py` |
| Every day | Carbon history since 2009, records and milestones, and the simulator's hourly year (NESO historic generation mix) | `update_history.py` |
| Every day | Wind turn-down and gas turn-up costs, by hour, for the last 8 days (14 on the first run), plus 20 earlier days filled in back to 1 January 2025 | `update_costs.py` |
| Every day | A data freshness check, and a GitHub issue if something has stopped updating | `health.py` |
| Every 10 minutes | Checks whether Elexon has published a new half hour, and if so recalculates today's running total and publishes it to the `live-data` branch (separate workflow, `live-costs.yml`) | `update_costs.py --today --prev` |
| Every day | The connection queue (TEC register) and NESO's daily constraint costs; then the open data CSVs | `update_neso.py`, `export_open.py` |
| 2nd of each month | All of the above, plus lines, substations, smaller sites, wind farm areas, routes and cross-checks (OpenStreetMap UK extract) | `update_osm.py` |

After refreshing, it rebuilds `index.html` and commits only if something changed. Each step works independently: if one source is down, the previous data is kept and the rest still updates.

GitHub pauses scheduled workflows in repositories with no activity for 60 days. The daily commits normally prevent this, but if the map stops updating, check the Actions tab.

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
| Wind and gas costs | Elexon Insights: indicative cashflows, acceptance volumes, acceptances (BOALF) and BM unit reference data |
| Households (for the per-household figure) | ONS, Families and households in the UK: 2024 (28.6 million) |
| Connection queue by site | NESO TEC register (NESO Open Data Licence); locations from OpenStreetMap |
| Official constraint costs | NESO constraint breakdown (NESO Open Data Licence) |
| Welsh targets and progress | Welsh Government, Energy Generation and Energy Use in Wales (2026) |
| Wind farm support schemes | LCCC Contracts for Difference register; Ofgem; developer announcements (see `data/subsidy.json`) |

The open data in `data/open/` is shared under CC BY 4.0, except the connection queue file, which is ODbL because it includes OpenStreetMap-derived locations. See **Licence and credit** below. The original sources' terms also apply.

The map carries the required credits in its bottom corner. Check each provider's current terms before any commercial use.

## Methods and caveats

- **Routes show the typical direction of flow.** Electricity joins a shared pool once it's on the grid, so a route shows where power usually goes, not a fixed destination.
- **Per-station live output is reported, not metered.** Where a station reports to Elexon, the figure is its physical notification: the output it told the grid operator it planned to produce that half-hour. Turn-down instructions are shown separately as curtailment.
- **Some live output figures are estimates.** Where a station doesn't report to Elexon, its output is its capacity multiplied by how hard that technology is running nationally. The site panel says which method was used.
- **Two carbon measures are used.** The history uses NESO's generation-based figures. The live figures estimate electricity consumed, including imports. They usually differ by 10 to 30 gCO₂/kWh.
- **Future dates are targets.** They are developer or government targets and often slip. The 2030 and 2035 carbon points are targets, not forecasts.
- **Northern Ireland** runs a separate grid shared with Ireland.
- **OpenStreetMap is community-mapped.** Some entries are out of date.
- **The connection queue is a list of contracts, not a forecast.** Many queued projects are never built, NESO notes some capacity is repeated across rows (repeats are counted once), and connections reform is re-ordering the queue. Sites the map can't place from their names are counted but not drawn.
- **Switch-off prices are averages.** Payments divided by energy turned down over 30 days; wind farms turned down by less than 200 MWh are left out.

## Accessibility

- **Keyboard:** everything works from the keyboard. You can tab to sites, the search results and the table rows.
- **Motion:** reduced-motion settings turn off the animated flows.
- **Themes:** light and dark mode are supported.
- **Language:** fully bilingual, and your choice is remembered.
- **Table view:** a text alternative to the map for screen-reader users.

## Brand files

The icon, favicons and link-preview image are in the top-level folder: `logo.svg` (the mark, scalable), `icon-512.png` (for social profile pictures; it survives the round crop), `icon-192.png`, `apple-touch-icon.png`, `favicon.svg`, `favicon-32.png`, `favicon.ico`, and `social.png` (1200 × 630, the image shown when the link is shared). The mark is Britain's outline with the 400 kV grid, and a line from a wind farm in the north to a socket in the south-east: source to socket. Typeface: Barlow Semi Condensed and Barlow.

If a platform still shows an old preview after you update `social.png`, ask it to refresh: LinkedIn Post Inspector, Facebook Sharing Debugger, or add `?v=3` to the image address in `src/app.html`.

## Daily card

`tools/daily_card.py` makes a shareable card for the whole of yesterday: wind turned down and what it cost, gas turned up for grid constraints (with gas for any reason alongside, so a £0 reads in context), average carbon intensity with the cleanest and dirtiest half hours, a half-hourly carbon chart coloured on the map's own scale, and the day's generation mix. It writes four images (landscape 1200×675 and portrait 1080×1350, each in English and Welsh, drawn at 2×) and a ready-to-post text for each language with alt text for the image. Nothing is posted automatically.

The latest card is always at `https://raw.githubusercontent.com/delwyno/The-UK-Power-Flow-Llif-Pwer-y-DU/daily-card/card-en-landscape.png` (also `-portrait`, `card-cy-…`, `post-en.txt`, `post-cy.txt`, `card-data.json`)

* **Sources:** the wind and gas figures use the same Elexon calculation as the running totals (`tools/update_costs.py`); carbon intensity and the mix come from the NESO Carbon Intensity API. Yesterday is used because it is complete and Elexon's indicative figures have settled. If Elexon's costs cannot be fetched the card is still made, with carbon and the mix only, and the run shows a warning.
* **Headline wind figure:** what NESO paid wind farms, as on the map. When some farms paid money back by bidding to be turned down, the card adds a "net" line.
* **Fonts and browser:** the cards are drawn from HTML with Playwright, using the Chrome already on GitHub's runners and Barlow from Google Fonts, the same typefaces as the map. To run it elsewhere: `pip install playwright`, `playwright install chromium`, then `python3 tools/daily_card.py`.
* **Checking the layout:** the script warns if any card overflows, which would only happen with unusually long text.
* **Attribution:** every card carries the Elexon and NESO data credit.

## Licence and credit

Created by **Daniel Elwyn Thomas**.

**Open data** (the CSV files in `data/open/`): shared under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). You can copy, share, adapt and use them, including commercially, if you give credit. The exception is `connection-queue-by-site.csv`, which includes locations derived from OpenStreetMap and is shared under the [Open Database Licence (ODbL)](https://opendatacommons.org/licenses/odbl/1-0/) instead.

**How to credit it:**

> Data: The UK Power Flow (Daniel Elwyn Thomas), CC BY 4.0. https://delwyno.github.io/The-UK-Power-Flow-Llif-Pwer-y-DU/

The licence covers the compilation (the daily tracking, matching and calculations), not the original data, which comes from NESO, Elexon and OpenStreetMap and carries their terms (see Data sources and licences). It is provided without warranty. `data/open/README.md` and `data/open/index.json` repeat this, with the exact credit line for each file.

The licence for the code (everything outside `data/`) has not been chosen yet.
