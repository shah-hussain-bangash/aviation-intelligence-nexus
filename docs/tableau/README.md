# Tableau aviation dashboards

[Download the packaged Tableau workbook](Aviation_Intelligence_Nexus.twbx?raw=true).

Open the downloaded `.twbx` in Tableau Desktop. The data is embedded; no database connection is required. Built and checked in Tableau Desktop 2026.3. Press **F7** for presentation mode and use the bottom tabs to switch dashboards.

| Dashboard | Contents |
| --- | --- |
| 01 Executive Overview | Five KPIs, daily volume, monthly punctuality, carrier comparison and major origin airports |
| 02 Airline Benchmark | Flight volume, on-time rate, cancellation rate and mean arrival delay by reporting carrier |
| 03 Network and Trends | Weekday/month reliability, daily cancellations, airport punctuality and departure delay |

Month, Airline and Origin controls are shared across all dashboards. Origin supports all airports together or one of 15 selected major airports. The airport charts display those 15 origins. There are 16 editable worksheets.

## Data and definitions

The package represents **2,835,101 historical US domestic reporting-carrier flights**, 1 January–31 May 2025, imported from the official Bureau of Transportation Statistics archives into this project's local database. It contains **1,154,864 daily carrier/origin/destination aggregates**, not individual flight records. All source flights contribute to the additive counts. It contains no local database, account records, credentials, live airline data or model predictions.

- **Scheduled flights:** all source flight records.
- **On-time rate:** arrival delay less than 15 minutes, divided by completed non-diverted flights with observed arrival delay.
- **Delayed arrivals:** arrival delay of 15 minutes or more in the same completed-flight population.
- **Cancellation rate:** cancellations divided by all scheduled flight records.
- **Mean arrival delay:** signed arrival-delay sum divided by completed flights with observed arrival delay. Early arrivals remain negative.
- **Mean departure delay:** signed departure-delay sum divided by records with observed departure delay.

Rates use the filtered sums, preserving weighted results. Carriers have different network and schedule mixes; these descriptive comparisons do not establish causal performance or operational suitability. The monthly weekday matrix uses darker shading for higher on-time rates.

See [the project's data audit](../DATA_QUALITY_LINEAGE.md) and [the machine-readable workbook manifest](manifest.json).

## Verification

All three pages were opened and visually reviewed in Tableau. Shared controls were checked against independent read-only database queries:

| Selection | Flights | Delayed arrivals |
| --- | ---: | ---: |
| All records | 2,835,101 | 571,908 |
| January | 539,747 | 98,130 |
| January / Delta Air Lines | 76,306 | 14,302 |
| January / Delta / ATL origin | 17,468 | 3,821 |

Full-period KPIs: **79.5% on time**, **1.48% cancelled**, **6.2 minutes mean arrival delay**. These are historical descriptive measures, not forecasts. Package integrity and aggregate totals were rechecked before publication.

The original workbook's Tableau licensing/author metadata is preserved. This repository upload does not grant additional Tableau usage or sharing rights.
