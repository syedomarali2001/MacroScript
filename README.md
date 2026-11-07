# MacroScript

**U.S. Macroeconomic Intelligence & Historical Research**  
*A Python / Streamlit application for investigating current and historically available U.S. economic data.*

![MacroScript homepage](assets/home.png)

## Why MacroScript?

Economic indicators are published on different schedules and can be revised after release. A retrospective chart built from today's revised data may show information that no analyst could have known at the time. MacroScript offers an explicit distinction between **today's record** and **historical information vintages**.

## What you can do

| Mode | Purpose |
| --- | --- |
| **Today's Economy** | Request the latest available FRED observations, calculate trends, check source freshness, and review transparent indicator-level interpretations. |
| **Time Machine** | Choose a past date and query ALFRED to reconstruct the observations available by that information cutoff. An optional, locally archived set of monthly snapshots covers September 1999–December 2024. |
| **Indicator Explorer** | Explore unemployment, payroll growth, industrial production, housing permits, and the monthly 10-year minus 3-month Treasury spread. |
| **Research Lab** | Review recession-warning research, chronological model comparisons, calibration checks, limitations, and the decision **not** to deploy unreliable forecasts. |

![MacroScript historical Time Machine](assets/time-machine.png)

### Economic indicators

- Unemployment rate and a calculated Sahm-style change in unemployment
- Nonfarm payroll employment: three- and twelve-month growth
- Industrial production: three- and twelve-month growth
- Housing building permits: three- and twelve-month growth
- Monthly Treasury spread based on `GS10 − TB3MS` (not identical to the daily `T10Y3M` series)

The application's interpretations are descriptive rules, **not recession probabilities, financial advice, or a guarantee of future economic conditions**.

## Run locally

You need **Python 3.10 or newer** and a personal [FRED API key](https://fred.stlouisfed.org/docs/api/api_key.html).

```powershell
# In PowerShell, from the folder containing the repository:
git clone https://github.com/syedomarali2001/MacroScript.git
cd MacroScript

# Install dependencies (a virtual environment is recommended):
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt

# Create your local, private settings file:
Copy-Item .env.example .env
# Edit .env and replace the placeholder with your own FRED_API_KEY.

# Launch the dashboard:
.\.venv\Scripts\python.exe -m streamlit run app.py
```

Streamlit typically serves the application at **http://localhost:8501**. Stop the server using `Ctrl+C` in the terminal.

If you already have the project locally, you can run `python -m streamlit run app.py` from the V7 directory instead of cloning.

## Data availability and reproducibility

**A public clone intentionally excludes locally cached historical source datasets** under `research/datasets/` pending confirmation of source-specific redistribution terms. This means:

- **Today's Economy** works with your FRED API key.
- **Time Machine → Custom ALFRED date** works with your FRED API key, for dates/series with available historical vintages.
- **Time Machine → Archived month-end snapshot** requires `research/datasets/v5_pit_full_rows.csv` from the original local research archive.
- Same-period revised-data comparisons require `research/datasets/v5_research_revised.csv`.
- Research summary reports in `research/v6_final_audit/` are included, but reproducing every historical model fit requires the separate original V5/V6 research artifacts and code, not shipped with this streamlined app.

These two source datasets are **not generated automatically by the GitHub release**. The archived mode is therefore a demonstration of a locally available data product, not a turnkey feature of a fresh public clone. The custom ALFRED mode is the reproducible public alternative.

The source data and reference-period dates should not be confused with intraday publication timestamps. Historical features contain only date-level information, and some vintages may be unavailable.

## Research conclusion

The V5/V6 experiments compared simple economic warning rules and recession-risk models using revised and historical-vintage inputs, chronological evaluation, and calibration/robustness checks. Some specifications beat simple historical benchmarks in retrospective tests; **performance did not establish robust, deployable recession probabilities**. The later evaluation set contained only two independent recession onsets, was revisited during research, and produced substantial false warnings in some periods.

See [`research/MacroScript_V6_Overview.txt`](research/MacroScript_V6_Overview.txt) for the full research summary. The dashboard intentionally separates retrospective recession outcomes from information displayed as historically available.

## Project structure

```text
app.py                    Streamlit interface
config.py                 Original indicator catalog
fred_client.py            FRED API client
history.py                ALFRED historical-vintage retrieval
features.py               Economic feature calculations
data_loader.py            Present, Time Machine, and revised-data loaders
data_quality.py           Missing-data and freshness checks
signals.py                Transparent, exploratory warning rules
research/                 Overview documents and selected evaluation reports
research/datasets/        Optional local historical datasets (excluded from Git)
tests/                    Automated checks
assets/                   Application screenshots
```

Run the included tests:

```powershell
python -m unittest discover -s tests -p "test_*.py" -v
```

## Data sources and credit

Economic observations are obtained through [FRED](https://fred.stlouisfed.org/) and historical vintages through [ALFRED](https://alfred.stlouisfed.org/), services of the Federal Reserve Bank of St. Louis. Underlying data sources include the U.S. Bureau of Labor Statistics, U.S. Census Bureau, U.S. Department of Housing and Urban Development, and the Board of Governors of the Federal Reserve System.

Relevant series: [UNRATE](https://fred.stlouisfed.org/series/UNRATE), [PAYEMS](https://fred.stlouisfed.org/series/PAYEMS), [INDPRO](https://fred.stlouisfed.org/series/INDPRO), [PERMIT](https://fred.stlouisfed.org/series/PERMIT), [GS10](https://fred.stlouisfed.org/series/GS10), [TB3MS](https://fred.stlouisfed.org/series/TB3MS).

Data use is subject to the [FRED API terms](https://fred.stlouisfed.org/docs/api/terms_of_use.html), and any rights held by originating data providers. This project is independent and is **not affiliated with or endorsed by the Federal Reserve Bank of St. Louis**.

## Security

Create a private `.env` from `.env.example`. **Never commit `.env`, API keys, `.streamlit/secrets.toml`, or local cache files.** The public `.gitignore` excludes these by default. If a secret has ever been published, revoke/rotate it—removing a file from a later commit does not erase Git history.

## Status

**V7 is the completed research-oriented dashboard.** Models from V6 are archived for methodological transparency rather than used to issue live recession predictions.
