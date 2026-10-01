# The UK Power Flow: open data

By Daniel Elwyn Thomas. Refreshed daily. Every file is described, with its columns, in `index.json`.

## Licence

- Most files: **CC BY 4.0** (https://creativecommons.org/licenses/by/4.0/). You can copy, share, adapt and use them, including commercially, if you give credit.
- `connection-queue-by-site.csv`: **ODbL 1.0** (https://opendatacommons.org/licenses/odbl/1-0/), because it includes locations derived from OpenStreetMap.

## How to credit

> Data: The UK Power Flow (Daniel Elwyn Thomas), CC BY 4.0. https://delwyno.github.io/UK-Energy-Generation-Map/

For the queue file:

> Data: The UK Power Flow (Daniel Elwyn Thomas), ODbL 1.0. Contains information from OpenStreetMap contributors. https://delwyno.github.io/UK-Energy-Generation-Map/

## Original sources

The numbers come from NESO (NESO Open Data Licence), Elexon (Contains BMRS data © Elexon Limited copyright and database right) and OpenStreetMap contributors (ODbL).
Their terms also apply. This licence covers the compilation (the daily tracking, matching and calculations), not the original data.
Provided without warranty: please check anything important against the original sources.

## Files

- `curtailment-daily.csv` (CC BY 4.0): Wind turned down, daily
- `curtailment-by-windfarm.csv` (CC BY 4.0): Wind turned down, by wind farm and day
- `station-output-hourly.csv` (CC BY 4.0): Station output, hourly (last 14 days)
- `carbon-daily.csv` (CC BY 4.0): Carbon intensity, daily
- `weekly-digest.csv` (CC BY 4.0): Weekly summary
- `forecast-accuracy.csv` (CC BY 4.0): Forecast accuracy
- `records.csv` (CC BY 4.0): Britain's electricity records
- `connection-queue-by-site.csv` (ODbL 1.0): Connection queue, by connection site
- `hydrogen-projects.csv` (CC BY 4.0): Hydrogen projects and pipeline, with status
- `official-constraint-costs.csv` (CC BY 4.0): Official constraint costs, with the map's tracked wind payments
