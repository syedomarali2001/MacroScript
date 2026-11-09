"""MacroScript V7 — U.S. Macroeconomic Intelligence & Historical Research.

Place this file directly inside the V7 starter folder, alongside
fred_client.py, data_loader.py, features.py, and signals.py.
Run: streamlit run app.py

The Time Machine never reads future-recession labels from the research CSVs.
Historical month-end cache dates are exact; arbitrary dates query ALFRED.
Landing page performs no network requests; current data is loaded on demand.
"""
from __future__ import annotations

import calendar
import html
import math
import os
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from dotenv import load_dotenv

from data_loader import load_observations
from features import calculate_all_features, month_label, monthly_values
from fred_client import FredClient
from signals import RULES, is_warning


ROOT = Path(__file__).resolve().parent
DATASETS = ROOT / "research" / "datasets"
AUDIT = ROOT / "research" / "v6_final_audit"
load_dotenv(ROOT / ".env")
GITHUB_URL = "https://github.com/syedomarali2001/MacroScript"

st.set_page_config(
    page_title="MacroScript | Economic Intelligence",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

INDICATORS = {
    "unemployment": {
        "name": "Unemployment", "measure": "Unemployment rate",
        "field": "unemployment_rate_pct", "unit": "%", "fmt": "{:.2f}%",
        "reference": "unemployment_reference_month", "age": "unemployment_age_months",
        "sources": ("UNRATE",), "color": "#81A9FF", "group": "unemployment",
        "series": "UNRATE", "chart_unit": "%", "chart_title": "Unemployment rate",
        "detail": "The share of the labor force that is unemployed. This can react after the broader economy starts changing.",
    },
    "payrolls": {
        "name": "Employment", "measure": "Job growth (past year)",
        "field": "payroll_growth_12m_pct", "unit": "%", "fmt": "{:+.2f}%",
        "reference": "payrolls_reference_month", "age": "payrolls_age_months",
        "sources": ("PAYEMS",), "color": "#4DD9C1", "group": "payrolls",
        "series": "PAYEMS", "chart_unit": "%", "chart_title": "Job growth compared with a year earlier",
        "detail": "How much U.S. payroll employment has grown or declined over the previous 12 months.",
    },
    "industrial_production": {
        "name": "Production", "measure": "Industrial output (past year)",
        "field": "industrial_growth_12m_pct", "unit": "%", "fmt": "{:+.2f}%",
        "reference": "industrial_production_reference_month", "age": "industrial_production_age_months",
        "sources": ("INDPRO",), "color": "#C4A5FF", "group": "industrial_production",
        "series": "INDPRO", "chart_unit": "%", "chart_title": "Industrial output compared with a year earlier",
        "detail": "The percentage change in industrial production over the past year.",
    },
    "housing_permits": {
        "name": "Housing", "measure": "Building permits (past year)",
        "field": "permits_growth_12m_pct", "unit": "%", "fmt": "{:+.2f}%",
        "reference": "housing_permits_reference_month", "age": "housing_permits_age_months",
        "sources": ("PERMIT",), "color": "#FFC47B", "group": "housing_permits",
        "series": "PERMIT", "chart_unit": "%", "chart_title": "Building permits compared with a year earlier",
        "detail": "The yearly change in permits for new homes. Declining permits may signal slowing residential construction.",
    },
    "treasury_spread": {
        "name": "Yield curve", "measure": "Treasury interest-rate gap",
        "field": "treasury_spread_pp", "unit": "pp", "fmt": "{:+.2f} pp",
        "reference": "treasury_spread_reference_month", "age": "treasury_spread_age_months",
        "sources": ("GS10", "TB3MS"), "color": "#F38BA8", "group": "treasury_spread",
        "series": None, "chart_unit": "pp", "chart_title": "Long-term minus short-term Treasury rates",
        "detail": "The 10-year Treasury rate minus the 3-month Treasury bill rate, using monthly readings. A negative gap means short-term rates are higher.",
    },
}
DISPLAY_ORDER = ("unemployment", "payrolls", "industrial_production", "housing_permits", "treasury_spread")
FEATURE_COLUMNS = (
    "unemployment_rate_pct", "unemployment_change_3m_pp", "unemployment_sahm_pp",
    "payroll_growth_3m_pct", "payroll_growth_12m_pct",
    "industrial_growth_3m_pct", "industrial_growth_12m_pct",
    "permits_growth_3m_pct", "permits_growth_12m_pct",
    "treasury_spread_pp", "treasury_average_3m_pp", "treasury_inversion_months",
)
REFERENCE_COLUMNS = tuple(INDICATORS[k]["reference"] for k in DISPLAY_ORDER)
MONTHLY_CSV = DATASETS / "v5_pit_full_rows.csv"
REVISED_CSV = DATASETS / "v5_research_revised.csv"


THEMES = {
    "Light": dict(bg="#F5F7FB", side="#EBF1F8", panel="#FFFFFF", elevated="#EDF3FA", text="#17263A", muted="#465D76", faint="#506880", border="#CEDAE6", accent="#146BA3", on_accent="#FFFFFF", chart="#266DCC", good="#17785D", bad="#B34350", warn="#9F651B"),
    "Dark Navy": dict(bg="#0B1220", side="#0F1A2C", panel="#15233A", elevated="#1C304A", text="#F3F7FC", muted="#B5C5DC", faint="#89A0BD", border="#304461", accent="#6AD7C6", on_accent="#061B1C", chart="#8EAEFF", good="#70DDB9", bad="#F2A0A8", warn="#F4C18B"),
    "Ocean Blue": dict(bg="#081724", side="#0B2233", panel="#102B40", elevated="#173852", text="#EFF8FF", muted="#B4D1E2", faint="#84A8BD", border="#2B5268", accent="#69C7F4", on_accent="#08212D", chart="#74C4FF", good="#74DCC3", bad="#F3A1A6", warn="#F7C888"),
    "Forest Green": dict(bg="#0D1916", side="#11241F", panel="#172D26", elevated="#1D3A30", text="#F1FAF4", muted="#B8D2C4", faint="#89AA9A", border="#375648", accent="#8CE2B6", on_accent="#10251A", chart="#8FC5AD", good="#8CE2B6", bad="#EDA4A3", warn="#F2C994"),
    "Burgundy Red": dict(bg="#1A111A", side="#261622", panel="#301F2D", elevated="#40283A", text="#FFF3F7", muted="#DBC0D0", faint="#B497AD", border="#614257", accent="#F3A2B5", on_accent="#351020", chart="#F0ABC5", good="#99D9BA", bad="#F3A2B5", warn="#F5C18F"),
}


def palette():
    return THEMES.get(st.session_state.get("ms_theme", "Light"), THEMES["Light"])


def theme_css():
    c = palette()
    return """<style>
:root {color-scheme: %(scheme)s; --ms-bg: %(bg)s; --ms-side: %(side)s; --ms-panel: %(panel)s; --ms-elevated: %(elevated)s; --ms-text: %(text)s; --ms-muted: %(muted)s; --ms-faint: %(faint)s; --ms-border: %(border)s; --ms-accent: %(accent)s; --ms-on-accent: %(on_accent)s; --ms-good: %(good)s; --ms-bad: %(bad)s; --ms-warn: %(warn)s;}
[data-testid="stAppViewContainer"], [data-testid="stMain"] {background:var(--ms-bg);color:var(--ms-text);}
[data-testid="stSidebar"] {background:var(--ms-side);border-right:1px solid var(--ms-border);}
[data-testid="stHeader"] {background:transparent;}
.block-container {max-width:1460px;padding-top:2.2rem;padding-bottom:4rem;}
html, body, [data-testid="stAppViewContainer"] p, [data-testid="stAppViewContainer"] label {color:var(--ms-text);}
[data-testid="stSidebar"] p, [data-testid="stSidebar"] label {color:var(--ms-muted);}
h1,h2,h3 {color:var(--ms-text) !important;letter-spacing:-.04em;}
p {line-height:1.6;}
[data-testid="stSidebar"] .stButton button {justify-content:flex-start;text-align:left;font-size:1rem;font-weight:650;min-height:2.95rem;}
.stButton button, [data-testid="stDownloadButton"] button {border-radius:11px!important;padding:.55rem 1.1rem!important;font-weight:700!important;transition:none!important;}
.stButton button[kind="primary"], [data-testid="stDownloadButton"] button[kind="primary"] {background:var(--ms-accent)!important;color:var(--ms-on-accent)!important;border-color:var(--ms-accent)!important;}
.stButton button[kind="secondary"], [data-testid="stDownloadButton"] button[kind="secondary"] {background:var(--ms-panel)!important;color:var(--ms-text)!important;border-color:var(--ms-border)!important;}
[data-baseweb="select"]>div, [data-baseweb="input"]>div, [data-baseweb="base-input"] {background:var(--ms-panel)!important;color:var(--ms-text)!important;border:1px solid var(--ms-border)!important;}
[data-testid="stAlert"] {border-radius:12px;}
[data-testid="stPlotlyChart"] {border-radius:18px;overflow:hidden;}
[data-testid="stRadio"] label {font-size:.92rem;font-weight:600;}
[data-testid="stHorizontalBlock"] {gap:.9rem;}
[data-testid="stWidgetLabel"] p, [data-testid="stCaptionContainer"] p {color:var(--ms-muted)!important;}
/* Streamlit renders button labels as nested paragraphs. Set contrast on those too. */
.stButton button[kind="primary"] *, [data-testid="stDownloadButton"] button[kind="primary"] * {color:var(--ms-on-accent)!important;fill:var(--ms-on-accent)!important;}
.stButton button[kind="secondary"] *, [data-testid="stDownloadButton"] button[kind="secondary"] * {color:var(--ms-text)!important;fill:var(--ms-text)!important;}
.stButton button:focus-visible, [data-testid="stLinkButton"] a:focus-visible {outline:3px solid var(--ms-accent);outline-offset:3px;}
[data-testid="stLinkButton"] a, .stLinkButton a {background:var(--ms-panel)!important;color:var(--ms-text)!important;border:1px solid var(--ms-border)!important;border-radius:11px!important;min-height:2.75rem!important;font-weight:750!important;}
[data-testid="stLinkButton"] a *, .stLinkButton a * {color:var(--ms-text)!important;fill:var(--ms-text)!important;}
[data-baseweb="select"] span, [data-baseweb="select"] input, [data-baseweb="select"] svg,
[data-testid="stDateInput"] input, [data-testid="stDateInput"] svg {color:var(--ms-text)!important;fill:var(--ms-text)!important;}
[data-testid="stDateInput"] input {background:var(--ms-panel)!important;border-color:var(--ms-border)!important;}
[data-baseweb="popover"] [role="listbox"], [data-baseweb="popover"] [role="option"] {background:var(--ms-panel)!important;color:var(--ms-text)!important;}
[data-testid="stRadio"] label p {color:var(--ms-text)!important;}
/* Date input uses a floating calendar portal, not a child of the input field.
   Apply the active MacroScript palette to the field AND the calendar popup. */
[data-testid="stDateInputField"] {background:var(--ms-panel)!important;color:var(--ms-text)!important;border-color:var(--ms-border)!important;}
[data-testid="stDateInputField"] [role="spinbutton"],
[data-testid="stDateInputField"] [data-type="literal"] {color:var(--ms-text)!important;}
[data-testid="stDateInputField"] [data-focused] {background:var(--ms-accent)!important;color:var(--ms-on-accent)!important;}
[data-testid="stDateInputField"] button, [data-testid="stDateInputField"] button svg {color:var(--ms-text)!important;fill:currentColor!important;}
/* React Aria calendar (Streamlit 1.62+) and legacy BaseWeb calendar. */
[data-testid="stDateInputCalendar"], [data-baseweb="calendar"] {background:var(--ms-panel)!important;color:var(--ms-text)!important;border:1px solid var(--ms-border)!important;color-scheme:%(scheme)s!important;}
[data-testid="stDateInputCalendar"] header button,
[data-testid="stDateInputCalendar"] header button svg,
[data-testid="stDateInputCalendar"] [role="columnheader"],
[data-testid="stDateInputCalendar"] [role="gridcell"]:not([data-selected]):not([data-disabled]):not([data-outside-month]),
[data-baseweb="calendar"] button:not([aria-selected="true"]) {color:var(--ms-text)!important;}
[data-testid="stDateInputCalendar"] [data-outside-month],
[data-baseweb="calendar"] [aria-disabled="true"] {color:var(--ms-faint)!important;}
[data-testid="stDateInputCalendar"] [data-selected]:not([data-disabled]),
[data-baseweb="calendar"] [aria-selected="true"] {background:var(--ms-accent)!important;color:var(--ms-on-accent)!important;}
/* The month/year pickers are separate portals in newer Streamlit versions. */
.stDateInputHeaderPickerPopover, [data-testid="stDateInputHeaderPickerPopover"] {background:var(--ms-panel)!important;color:var(--ms-text)!important;border:1px solid var(--ms-border)!important;}
.stDateInputHeaderPickerPopover [role="option"],
[data-testid="stDateInputHeaderPickerPopover"] [role="option"] {color:var(--ms-text)!important;}

.ms-brand {font-size:1.43rem;font-weight:850;letter-spacing:-.045em;color:var(--ms-text);margin:0 0 .3rem;}
.ms-brand span {color:var(--ms-accent);}
.ms-tagline {font-size:.9rem;color:var(--ms-muted);line-height:1.55;}
.ms-eyebrow {font-size:.76rem;text-transform:uppercase;letter-spacing:.13em;font-weight:850;color:var(--ms-accent);margin-bottom:.72rem;}
.ms-hero {margin:.15rem 0 1.6rem;padding:0 0 1.1rem;border-bottom:1px solid var(--ms-border);}
.ms-title {font-size:clamp(2.45rem,4.4vw,4.2rem);font-weight:860;letter-spacing:-.055em;line-height:1.09;color:var(--ms-text);margin:0 0 .78rem;}
.ms-deck {font-size:1.07rem;line-height:1.65;color:var(--ms-muted);max-width:860px;}
.ms-section {font-size:1.5rem;font-weight:790;letter-spacing:-.035em;color:var(--ms-text);margin:1.45rem 0 .55rem;}
.ms-mini-title {font-size:.84rem;text-transform:uppercase;letter-spacing:.10em;font-weight:800;color:var(--ms-muted);}
.ms-mode-card {min-height:300px;border:1px solid var(--ms-border);background:var(--ms-panel);border-radius:20px;padding:1.75rem 1.8rem 1.45rem;margin-bottom:.6rem;}
.ms-mode-number {color:var(--ms-accent);font-size:.78rem;letter-spacing:.12em;text-transform:uppercase;font-weight:850;}
.ms-mode-symbol {font-size:2.35rem;margin:1.1rem 0 .8rem;}
.ms-mode-title {color:var(--ms-text);font-size:2.25rem;line-height:1.1;font-weight:825;letter-spacing:-.045em;margin-bottom:.7rem;}
.ms-mode-description {color:var(--ms-muted);font-size:1.06rem;line-height:1.65;min-height:3.4rem;}
.ms-mode-why {margin-top:1.1rem;padding-top:1rem;border-top:1px solid var(--ms-border);color:var(--ms-text);font-size:.94rem;line-height:1.55;}
.ms-research-card {background:var(--ms-panel);border:1px solid var(--ms-border);border-radius:18px;padding:1.55rem 1.8rem;margin:1.4rem 0 .6rem;display:grid;grid-template-columns:1fr 2fr;column-gap:2rem;align-items:center;}
.ms-research-card .ms-research-title {color:var(--ms-text);font-size:1.5rem;font-weight:820;letter-spacing:-.035em;}
.ms-research-card .ms-research-copy {color:var(--ms-muted);font-size:1rem;line-height:1.6;}
.ms-benchmark-head {display:grid;grid-template-columns:1.2fr 1.45fr 2.35fr;gap:1rem;padding:.75rem 1.1rem;font-size:.78rem;text-transform:uppercase;letter-spacing:.08em;font-weight:800;color:var(--ms-muted);}
.ms-benchmark {background:var(--ms-panel);border:1px solid var(--ms-border);border-radius:15px;overflow:hidden;margin:.4rem 0 .8rem;}
.ms-benchmark-row {display:grid;grid-template-columns:1.2fr 1.45fr 2.35fr;gap:1rem;padding:1rem 1.1rem;align-items:center;border-bottom:1px solid var(--ms-border);color:var(--ms-text);font-size:.95rem;line-height:1.55;}
.ms-benchmark-row:last-child {border-bottom:0;}
.ms-benchmark-name {font-weight:780;}
.ms-benchmark-value {font-weight:780;font-variant-numeric:tabular-nums;color:var(--ms-text);}
.ms-benchmark-hint {color:var(--ms-muted);font-size:.91rem;}
.ms-signal {display:inline-block;border:1px solid var(--ms-border);background:var(--ms-elevated);border-radius:7px;padding:.15rem .45rem;font-size:.8rem;font-weight:750;margin-top:.25rem;color:var(--ms-text);}
.ms-signal.weak {border-color:var(--ms-bad);}
.ms-signal.missing {border-color:var(--ms-warn);}
.ms-signal.ok {border-color:var(--ms-good);}

.ms-kpi {background:var(--ms-panel);border:1px solid var(--ms-border);border-radius:16px;padding:1.05rem 1.0rem 1rem;min-height:170px;margin-bottom:.35rem;}
.ms-kpi-top {color:var(--ms-muted);font-weight:750;font-size:.89rem;min-height:2rem;line-height:1.4;}
.ms-kpi-val {color:var(--ms-text);font-weight:820;font-size:clamp(1.45rem,2vw,2.2rem);letter-spacing:-.04em;margin:.38rem 0 .6rem;white-space:nowrap;}
.ms-kpi-bottom {color:var(--ms-faint);font-size:.87rem;}
.ms-note {background:var(--ms-panel);border:1px solid var(--ms-border);border-radius:16px;padding:1.3rem 1.45rem;color:var(--ms-text);font-size:1.03rem;line-height:1.7;margin:.8rem 0 1.25rem;}
.ms-note strong {color:var(--ms-text);}
.ms-detail {background:var(--ms-panel);border:1px solid var(--ms-border);border-radius:16px;padding:1.2rem 1.4rem;font-size:1.01rem;line-height:1.65;color:var(--ms-muted);margin:.45rem 0;}
.ms-detail strong {color:var(--ms-text);}
.ms-flag {display:inline-block;border:1px solid var(--ms-border);background:var(--ms-elevated);padding:.46rem .72rem;border-radius:9px;font-size:.86rem;color:var(--ms-text);margin:.18rem .34rem .24rem 0;}
.ms-flag.weak {border-color:var(--ms-bad);}
.ms-flag.ok {border-color:var(--ms-good);}
.ms-flag.missing {border-color:var(--ms-warn);}
.ms-finding {background:var(--ms-panel);border:1px solid var(--ms-border);border-radius:16px;padding:1.3rem 1.35rem;min-height:186px;}
.ms-finding strong {color:var(--ms-text);font-size:1.16rem;}
.ms-finding p {color:var(--ms-muted);font-size:.97rem;line-height:1.6;margin:.6rem 0 0;}
.ms-footnote {color:var(--ms-faint);font-size:.85rem;line-height:1.65;margin:.6rem 0 1rem;}
.ms-sidebar-foot {color:var(--ms-faint);font-size:.82rem;line-height:1.6;margin-top:1.4rem;}
@media(max-width:900px){.block-container{padding-top:1.4rem}.ms-title{font-size:2.45rem}.ms-mode-card{min-height:0}.ms-kpi{min-height:145px}.ms-kpi-val{white-space:normal}.ms-research-card{display:block}.ms-benchmark-head{display:none}.ms-benchmark-row{display:block}.ms-benchmark-row > div{margin-bottom:.3rem}}
</style>""" % dict(c, scheme="light" if st.session_state.get("ms_theme") == "Light" else "dark")


def safe_float(value):
    try:
        if value is None or isinstance(value, str) and not value.strip():
            return None
        value = float(value)
        return value if math.isfinite(value) else None
    except (ValueError, TypeError):
        return None


def text(value):
    return html.escape(str(value), quote=True)


def pretty_month(yyyymm):
    try:
        return datetime.strptime(str(yyyymm), "%Y-%m").strftime("%b %Y")
    except (TypeError, ValueError):
        return "Unavailable"


def month_end_str(yyyymm):
    year, mon = map(int, yyyymm.split("-"))
    return f"{yyyymm}-{calendar.monthrange(year, mon)[1]:02d}"


def months_ago(start: str | None, end: str):
    if not start:
        return None
    try:
        return (int(end[:4]) - int(start[:4])) * 12 + int(end[5:7]) - int(start[5:7])
    except (ValueError, TypeError):
        return None


def as_metric_value(value, spec):
    return spec["fmt"].format(value) if value is not None else "Unavailable"


@st.cache_data(show_spinner=False)
def read_research_csv(path: str):
    df = pd.read_csv(path)
    if "month" in df.columns:
        if df["month"].duplicated().any():
            raise ValueError(f"Duplicate months in {Path(path).name}")
        df = df.sort_values("month").reset_index(drop=True)
    return df


def cached_monthly():
    if not MONTHLY_CSV.is_file():
        raise FileNotFoundError(f"Missing {MONTHLY_CSV.relative_to(ROOT)}")
    df = read_research_csv(str(MONTHLY_CSV))
    if not {"month", "as_of", "data_mode", *FEATURE_COLUMNS, *REFERENCE_COLUMNS}.issubset(df):
        raise ValueError("Cached historical CSV lacks required economic columns")
    if not (df["data_mode"] == "time_machine").all():
        raise ValueError("Historical CSV contains non-Time-Machine rows")
    if any(month_end_str(m) != a for m, a in zip(df["month"], df["as_of"])):
        raise ValueError("Historical cache contains a mismatched as-of date")
    return df


def cached_revised():
    if not REVISED_CSV.is_file():
        raise FileNotFoundError(f"Missing {REVISED_CSV.relative_to(ROOT)}")
    df = read_research_csv(str(REVISED_CSV))
    if not {"month", "data_mode", *FEATURE_COLUMNS, *REFERENCE_COLUMNS}.issubset(df):
        raise ValueError("Revised CSV lacks required columns")
    if not (df["data_mode"] == "revised").all():
        raise ValueError("Revised CSV contains unexpected data modes")
    return df


def row_to_snapshot(row, mode: str):
    """Extract ONLY historical economic inputs, never future outcome labels."""
    output = {key: safe_float(row.get(key)) for key in FEATURE_COLUMNS}
    for key in REFERENCE_COLUMNS:
        value = row.get(key)
        output[key] = str(value) if pd.notna(value) and str(value).strip() else None
    output["as_of"] = str(row["as_of"])
    output["mode"] = mode
    output["quality"] = {}
    for name, spec in INDICATORS.items():
        statuses = [str(row.get(f"quality_{series}", "UNKNOWN")) for series in spec["sources"]]
        output["quality"][name] = "OK" if all(s == "OK" for s in statuses) else ", ".join(statuses)
    return output


def cached_snapshot(df, month: str):
    matched = df.loc[df["month"] == month]
    if len(matched) != 1:
        raise ValueError(f"No single cached snapshot for {month}")
    return row_to_snapshot(matched.iloc[0], "time_machine")


@st.cache_data(show_spinner=False, ttl=3600)
def api_bundle(mode: str, as_of: str, api_key: str):
    """Cached per-session FRED/ALFRED retrieval; never archives the API key."""
    client = FredClient(api_key)
    try:
        return load_observations(client, mode, as_of)
    finally:
        client.close()


def get_api_key():
    key = os.getenv("FRED_API_KEY", "").strip()
    if not key or key.lower().startswith("replace_"):
        return None
    return key


def snapshot_from_bundle(bundle):
    calculated = calculate_all_features(bundle["observations"], bundle["as_of"])
    snapshot = {"as_of": bundle["as_of"], "mode": bundle["mode"], "quality": {}}
    mapping = {
        "unemployment_rate_pct": ("unemployment", "rate_pct"),
        "unemployment_change_3m_pp": ("unemployment", "change_3m_pp"),
        "unemployment_sahm_pp": ("unemployment", "sahm_pp"),
        "payroll_growth_3m_pct": ("payrolls", "growth_3m_pct"),
        "payroll_growth_12m_pct": ("payrolls", "growth_12m_pct"),
        "industrial_growth_3m_pct": ("industrial_production", "growth_3m_pct"),
        "industrial_growth_12m_pct": ("industrial_production", "growth_12m_pct"),
        "permits_growth_3m_pct": ("housing_permits", "growth_3m_pct"),
        "permits_growth_12m_pct": ("housing_permits", "growth_12m_pct"),
        "treasury_spread_pp": ("treasury_spread", "spread_pp"),
        "treasury_average_3m_pp": ("treasury_spread", "average_3m_pp"),
        "treasury_inversion_months": ("treasury_spread", "inversion_months"),
    }
    for dest, (group, field) in mapping.items():
        snapshot[dest] = safe_float(calculated[group][field])
    for name, spec in INDICATORS.items():
        grp = calculated[spec["group"]]
        snapshot[spec["reference"]] = grp.get("reference_month")
        statuses = [bundle["quality"].get(s, {}).get("status", "NO") for s in spec["sources"]]
        snapshot["quality"][name] = "OK" if all(s == "OK" for s in statuses) else ", ".join(statuses)
    return snapshot


def is_usable(snapshot, key, field=None):
    """An old documented gap need not invalidate a later observed value.

    Each computed feature still requires its exact source months; a missing
    Sahm Rule stays unavailable even if the latest unemployment rate exists.
    """
    spec = INDICATORS[key]
    metric = field or spec["field"]
    quality = str(snapshot["quality"].get(key, "UNKNOWN"))
    return quality in ("OK", "KNOWN_GAP") and safe_float(snapshot.get(metric)) is not None


def kpi_cards(snapshot):
    columns = st.columns(5, gap="small")
    for col, key in zip(columns, DISPLAY_ORDER):
        spec = INDICATORS[key]
        raw_value = safe_float(snapshot.get(spec["field"]))
        value = raw_value if is_usable(snapshot, key) else None
        reference = snapshot.get(spec["reference"])
        # Dates remain visible because economic series are released on different schedules.
        status = pretty_month(reference) if value is not None else "Not available"
        with col:
            st.markdown(
                f'<div class="ms-kpi">'
                f'<div class="ms-kpi-top">{text(spec["measure"])}</div>'
                f'<div class="ms-kpi-val">{text(as_metric_value(value, spec))}</div>'
                f'<div class="ms-kpi-bottom">{text(status)}</div>'
                f'</div>', unsafe_allow_html=True,
            )


def clean_signals(snapshot):
    """Only usable contemporaneous economic inputs; no USREC or future targets."""
    signal = {}
    for key, field in (
        ("unemployment", "unemployment_sahm_pp"),
        ("payrolls", "payroll_growth_12m_pct"),
        ("industrial_production", "industrial_growth_12m_pct"),
        ("housing_permits", "permits_growth_12m_pct"),
        ("treasury_spread", "treasury_spread_pp"),
    ):
        signal[field] = safe_float(snapshot.get(field)) if is_usable(snapshot, key, field) else None
    return signal


def interpret(snapshot):
    signal = clean_signals(snapshot)
    flags = []
    narratives = []
    tests = (
        ("Yield curve", "treasury_spread_pp", lambda x: x < 0,
         "The monthly 10Y–3M spread is inverted.", "The monthly 10Y–3M spread is positive."),
        ("Housing", "permits_growth_12m_pct", lambda x: x < 0,
         "Housing permit issuance is lower than a year earlier.", "Housing permits are not below their year-earlier level."),
        ("Employment", "payroll_growth_12m_pct", lambda x: x < 0,
         "Nonfarm payroll employment has declined year over year.", "Payroll employment is not declining year over year."),
        ("Industry", "industrial_growth_12m_pct", lambda x: x < 0,
         "Industrial production is down from a year earlier.", "Industrial production is not down year over year."),
        ("Unemployment", "unemployment_sahm_pp", lambda x: x >= .5,
         "The calculated Sahm Rule unemployment deterioration threshold is met.",
         "The calculated Sahm Rule measure is below its 0.50 pp threshold."),
    )
    for title, field, rule, weak, other in tests:
        value = signal[field]
        if value is None:
            flags.append((title, "Unavailable", "The required value or source quality is unavailable."))
        elif rule(value):
            flags.append((title, "Deteriorating", weak))
            narratives.append(title.lower())
        else:
            flags.append((title, "No threshold breach", other))

    count = len(narratives)
    observed = sum(status != "Unavailable" for _, status, _ in flags)
    if observed < 3:
        summary = "Too few comparable, quality-checked indicators are available for a combined assessment."
    elif count >= 3:
        summary = ("Several monitored areas are showing deterioration: "
                   + ", ".join(narratives) + ". This is a descriptive cross-indicator signal, not a recession forecast.")
    elif count:
        summary = ("The picture is mixed: deterioration is visible in "
                   + ", ".join(narratives) + ", while other available indicators have not crossed their defined thresholds.")
    else:
        summary = "None of the available indicators has crossed these particular deterioration thresholds. This does not rule out economic weakness or future recession."

    candidate = next(rule for rule in RULES if rule.name == "Treasury < 0.5 AND Housing < 0")
    combined = is_warning(signal, candidate)
    return summary, flags, combined


def section_heading(title, subtitle=None):
    st.markdown(f'<div class="ms-section">{text(title)}</div>', unsafe_allow_html=True)
    if subtitle:
        st.caption(subtitle)


def unemployment_history_gap(snapshot):
    """Explain the verified 2025-10 gap only when it affects the Sahm window.

    The Sahm calculation needs the newest three-month average and the 12
    preceding three-month averages: 15 consecutive monthly observations.
    """
    reference = snapshot.get("unemployment_reference_month")
    if not reference:
        return False
    try:
        year, month = map(int, str(reference).split("-"))
    except (ValueError, TypeError):
        return False
    distance = (year - 2025) * 12 + month - 10
    return 0 <= distance <= 14 and snapshot["quality"].get("unemployment") == "KNOWN_GAP"


def benchmark_rows(snapshot):
    """Descriptive benchmarks match existing signal rules, not invented grades."""
    rows = []
    for key, name, field, threshold, why in (
        ("treasury_spread", "Yield curve", "treasury_spread_pp",
         "Warning when below 0 pp (inverted)",
         "Short-term interest rates exceed long-term rates. Inversions have preceded some recessions, but are not a prediction."),
        ("housing_permits", "Housing", "permits_growth_12m_pct",
         "Warning when below 0% year over year",
         "Fewer building permits than a year ago can signal cooling construction."),
        ("payrolls", "Jobs", "payroll_growth_12m_pct",
         "Warning when below 0% year over year",
         "Payroll employment has fallen over the year, a sign of labor-market weakness."),
        ("industrial_production", "Industry", "industrial_growth_12m_pct",
         "Warning when below 0% year over year",
         "Output has contracted compared with a year ago, indicating weaker industrial activity."),
        ("unemployment", "Unemployment trend (Sahm)", "unemployment_sahm_pp",
         "Warning at 0.50 pp or higher",
         "The unemployment rate's three-month average has risen sharply relative to the previous year's low."),
    ):
        value = safe_float(snapshot.get(field)) if is_usable(snapshot, key, field) else None
        display = (f"{value:+.2f} pp" if value is not None and key in ("treasury_spread", "unemployment")
                   else f"{value:+.2f}%" if value is not None else "Not available")
        if value is None:
            label, style = "Not enough data", "missing"
            if key == "unemployment":
                if unemployment_history_gap(snapshot):
                    why = ("The unemployment rate itself is available. The October 2025 household survey wasn't collected "
                           "during the federal shutdown, so the separate Sahm calculation lacks the monthly history it needs.")
                else:
                    why = ("The unemployment rate may still be available, but the full monthly history "
                           "needed for the Sahm measure is incomplete at this date.")
            else:
                why = "There is insufficient validated source data at this date. " + why
        elif (value >= .5 if key == "unemployment" else value < 0):
            label, style = "Warning threshold crossed", "weak"
        else:
            label, style = "No warning threshold crossed", "ok"
        rows.append({"name": name, "value": display, "label": label,
                     "style": style, "threshold": threshold, "why": why})
    return rows


def economic_insights(snapshot):
    """Plain-language interpretation plus visible, numeric, contextual benchmarks."""
    _, flags, _ = interpret(snapshot)
    weak = [description for _, status, description in flags if status == "Deteriorating"]
    steady = [name for name, status, _ in flags if status == "No threshold breach"]
    missing = [name for name, status, _ in flags if status == "Unavailable"]
    observed = len(flags) - len(missing)
    if observed < 3:
        narrative = "Not enough indicators are available for a complete picture."
    elif weak:
        narrative = " ".join(weak)
    else:
        narrative = "None of the available indicators crosses its defined warning threshold."
    if steady and weak:
        narrative += " Other available signals have not crossed their warning levels."
    if missing:
        if "Unemployment" in missing and is_usable(snapshot, "unemployment"):
            narrative += " The unemployment rate is available, but its separate Sahm warning cannot be calculated."
            missing.remove("Unemployment")
        if missing:
            narrative += " Unable to assess: " + ", ".join(missing) + "."
    st.markdown('<div class="ms-section">What the numbers suggest</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="ms-note">{text(narrative)}</div>', unsafe_allow_html=True)
    st.markdown('<div class="ms-section">How these readings compare with warning levels</div>', unsafe_allow_html=True)
    st.markdown('<div class="ms-footnote">The numbers below show the specific thresholds used for the labels above. They are not universal good or bad ranges.</div>', unsafe_allow_html=True)
    rows = benchmark_rows(snapshot)
    cells = ['<div class="ms-benchmark-head"><div>Indicator</div><div>Reading and status</div><div>Benchmark and why it matters</div></div>', '<div class="ms-benchmark">']
    for row in rows:
        cells.append(f'<div class="ms-benchmark-row">'
                     f'<div class="ms-benchmark-name">{text(row["name"])}</div>'
                     f'<div><div class="ms-benchmark-value">{text(row["value"])}</div>'
                     f'<span class="ms-signal {text(row["style"])}">{text(row["label"])}</span></div>'
                     f'<div class="ms-benchmark-hint"><strong>{text(row["threshold"])}</strong><div>{text(row["why"])}</div></div>'
                     f'</div>')
    cells.append('</div>')
    st.markdown(''.join(cells), unsafe_allow_html=True)
    st.markdown('<div class="ms-footnote">Thresholds flag specific types of deterioration. Crossing one does not mean a recession is certain, and staying below it does not mean the economy is safe.</div>', unsafe_allow_html=True)


def hero(label, title, description):
    st.markdown(
        f'<div class="ms-hero"><div class="ms-eyebrow">{text(label)}</div>'
        f'<div class="ms-title">{text(title)}</div>'
        f'<div class="ms-deck">{text(description)}</div></div>',
        unsafe_allow_html=True,
    )


def observation_chart_df(bundle, key, months=36):
    spec = INDICATORS[key]
    as_of = bundle["as_of"]
    obs = bundle["observations"]
    if key == "treasury_spread":
        long_rates = monthly_values(obs.get("GS10", []), as_of)
        short_rates = monthly_values(obs.get("TB3MS", []), as_of)
        values = {m: long_rates[m] - short_rates[m] for m in long_rates.keys() & short_rates.keys()}
    else:
        series = monthly_values(obs.get(spec["series"], []), as_of)
        if key == "unemployment":
            values = series
        else:
            values = {m: 100 * (val / series[m-12] - 1)
                      for m, val in series.items() if m-12 in series and series[m-12] > 0}
    if not values:
        return pd.DataFrame(columns=["date", "value"])
    end = max(values)
    result = []
    for m in range(end-months+1, end+1):
        val = values.get(m)
        result.append({"date": pd.Timestamp(month_label(m) + "-01"), "value": val})
    return pd.DataFrame(result)


def cached_chart_df(df, key, through_month, months=36):
    field = INDICATORS[key]["field"]
    subset = df.loc[df["month"] <= through_month, ["month", field]].tail(months).copy()
    if subset.empty:
        return pd.DataFrame(columns=["date", "value"])
    subset["date"] = pd.to_datetime(subset["month"] + "-01")
    subset["value"] = pd.to_numeric(subset[field], errors="coerce")
    return subset[["date", "value"]]


def plot_history(df, key, note=None):
    spec = INDICATORS[key]
    if df.empty or df["value"].notna().sum() == 0:
        st.info("No observations are available for this indicator and time period.")
        return
    c = palette()
    figure = go.Figure()
    figure.add_trace(go.Scatter(
        x=df["date"], y=df["value"], mode="lines",
        line={"color": c["chart"], "width": 3.2},
        hovertemplate=f"%{{x|%b %Y}}<br>%{{y:.2f}} {spec['chart_unit']}<extra></extra>",
        connectgaps=False,
    ))
    if key in ("treasury_spread", "payrolls", "industrial_production", "housing_permits"):
        figure.add_hline(y=0, line_color=c["faint"], line_dash="dot", line_width=1)
    figure.update_layout(
        template="none", height=410, margin=dict(l=5, r=14, t=16, b=8),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color=c["text"], size=14),
        xaxis=dict(showgrid=False, title=None, color=c["text"], tickfont=dict(color=c["text"], size=13)),
        yaxis=dict(showgrid=True, gridcolor=c["border"], title=dict(text=spec["chart_unit"], font=dict(color=c["text"])),
                   zeroline=False, color=c["text"], tickfont=dict(color=c["text"], size=13)),
        hoverlabel=dict(bgcolor=c["panel"], bordercolor=c["border"], font=dict(color=c["text"], size=14)),
        showlegend=False, hovermode="x unified",
    )
    st.plotly_chart(figure, width="stretch", config={"displayModeBar": False})
    if note:
        st.markdown(f'<div class="ms-footnote">{text(note)}</div>', unsafe_allow_html=True)


def detail_table(snapshot):
    rows = []
    for key in DISPLAY_ORDER:
        spec = INDICATORS[key]
        val = safe_float(snapshot.get(spec["field"]))
        reference = snapshot.get(spec["reference"])
        age = months_ago(reference, snapshot["as_of"])
        rows.append({
            "Indicator": spec["measure"],
            "Value": as_metric_value(val, spec),
            "Reference period": pretty_month(reference),
            "Age (months)": age,
            "Quality": snapshot["quality"].get(key, "UNKNOWN"),
            "FRED IDs": ", ".join(spec["sources"]),
        })
    df = pd.DataFrame(rows)
    st.dataframe(df, hide_index=True, width="stretch")
    st.download_button("Export economic snapshot CSV", data=df.to_csv(index=False).encode("utf-8"),
                       file_name=f"macroscript_{snapshot['mode']}_{snapshot['as_of']}.csv", mime="text/csv")


def load_selected_api(mode, as_of):
    key = get_api_key()
    if not key:
        st.warning("FRED_API_KEY is missing or still a placeholder in V7/.env. You can still use the cached Time Machine and Research Lab.")
        return None
    with st.spinner("Retrieving and validating FRED / ALFRED observations..."):
        try:
            bundle = api_bundle(mode, as_of, key)
            if bundle.get("errors"):
                st.warning(f"{len(bundle['errors'])} of 6 sources could not be retrieved. Unavailable data will not be filled in.")
            return bundle
        except Exception as exc:
            st.error(f"Economic data retrieval failed: {type(exc).__name__}: {exc}")
            return None


def navigate(page):
    st.session_state["page"] = page
    st.rerun()


def landing():
    """No network calls on the home screen."""
    hero("UNDERSTAND THE U.S. ECONOMY", "One economy. Two ways to explore it.",
         "See what is happening today, or travel to the past and see what people actually knew at the time.")
    left, right = st.columns(2, gap="large")
    with left:
        st.markdown("""<div class="ms-mode-card">
            <div class="ms-mode-number">01 / The present</div>
            <div class="ms-mode-symbol">◉</div>
            <div class="ms-mode-title">Today's Economy</div>
            <div class="ms-mode-description">Five key readings, clear explanations, and easy-to-explore charts.</div>
            <div class="ms-mode-why"><strong>Choose this to:</strong> Understand the latest picture without sorting through raw economic data.</div>
        </div>""", unsafe_allow_html=True)
        if st.button("Explore today's economy", type="primary", width="stretch", key="home_today"):
            navigate("Today")
    with right:
        st.markdown("""<div class="ms-mode-card">
            <div class="ms-mode-number">02 / The past</div>
            <div class="ms-mode-symbol">◷</div>
            <div class="ms-mode-title">Time Machine</div>
            <div class="ms-mode-description">Pick a historical date. Explore the economy using only information available then.</div>
            <div class="ms-mode-why"><strong>Choose this to:</strong> See why the past often looks different after later data releases and revisions.</div>
        </div>""", unsafe_allow_html=True)
        if st.button("Explore the past", type="primary", width="stretch", key="home_history"):
            navigate("Time Machine")
    st.markdown('''<div class="ms-research-card">
        <div><div class="ms-mode-number">Behind the numbers</div><div class="ms-research-title">Research findings</div></div>
        <div class="ms-research-copy">Can these indicators predict a recession? Explore what our historical tests found, what failed, and why we don't publish a probability forecast.</div>
    </div>''', unsafe_allow_html=True)
    if st.button("Explore the research findings", width="stretch", key="home_research"):
        navigate("Research")
    st.markdown('<div class="ms-footnote">Economic data: FRED and ALFRED. Research and education, not a recession forecast.</div>', unsafe_allow_html=True)


def indicator_journey(snapshot, chart_data, history_note=None, suffix="today"):
    """One integrated visible chart for each mode, not a separate indicator page."""
    st.markdown('<div class="ms-section">Explore an indicator</div>', unsafe_allow_html=True)
    st.markdown('<div class="ms-footnote">Choose what you want to understand. The chart and explanation update together.</div>', unsafe_allow_html=True)
    short = {"unemployment":"Unemployment", "payrolls":"Jobs", "industrial_production":"Industry", "housing_permits":"Housing", "treasury_spread":"Yield curve"}
    selection_key = f"{suffix}_metric"
    st.session_state.setdefault(selection_key, DISPLAY_ORDER[0])
    choices = st.columns(5, gap="small")
    for col, option in zip(choices, DISPLAY_ORDER):
        with col:
            if st.button(short[option], key=f"{suffix}_choose_{option}",
                         type="primary" if st.session_state[selection_key] == option else "secondary",
                         width="stretch"):
                st.session_state[selection_key] = option
                st.rerun()
    selected = st.session_state[selection_key]
    spec = INDICATORS[selected]
    status = next((entry for entry in interpret(snapshot)[1] if entry[0] == {
        "unemployment":"Unemployment", "payrolls":"Employment", "industrial_production":"Industry",
        "housing_permits":"Housing", "treasury_spread":"Yield curve"}[selected]), None)
    a, b = st.columns([2.7, 1], gap="large")
    with a:
        st.markdown(f'<div class="ms-section">{text(spec["chart_title"])}</div>', unsafe_allow_html=True)
    with b:
        lookback_key = f"{suffix}_years"
        st.session_state.setdefault(lookback_key, 60)
        time_cols = st.columns(3, gap="small")
        for col, period, label in zip(time_cols, (12, 36, 60), ("1Y", "3Y", "5Y")):
            with col:
                if st.button(label, key=f"{suffix}_period_{period}",
                             type="primary" if st.session_state[lookback_key] == period else "secondary",
                             width="stretch"):
                    st.session_state[lookback_key] = period
                    st.rerun()
        lookback = st.session_state[lookback_key]
    plot_history(chart_data(selected, lookback), selected, history_note)
    value = as_metric_value(safe_float(snapshot.get(spec["field"])) if is_usable(snapshot, selected) else None, spec)
    ref = pretty_month(snapshot.get(spec["reference"]))
    status_detail = status[2] if status else ""
    if selected == "unemployment" and is_usable(snapshot, selected) and not is_usable(snapshot, selected, "unemployment_sahm_pp"):
        status_detail = ("This unemployment rate is available, but the separate Sahm trend warning cannot be calculated. "
                         + ("October 2025 survey data were not collected during the federal shutdown." if unemployment_history_gap(snapshot)
                            else "It needs a longer uninterrupted history."))
    elif snapshot["quality"].get(selected) == "KNOWN_GAP":
        status_detail += " Some earlier observations are missing, so certain trend measures are incomplete."
    elif not is_usable(snapshot, selected):
        status_detail += " This reading could not be validated with the available source data."
    st.markdown(f'<div class="ms-detail"><strong>{text(spec["measure"])}: {text(value)}</strong> · {text(ref)}'
                f'<div style="margin-top:.42rem">{text(spec["detail"])} {text(status_detail)}</div></div>',
                unsafe_allow_html=True)


def download_snapshot(snapshot, key="today"):
    rows = []
    for metric in DISPLAY_ORDER:
        spec = INDICATORS[metric]
        rows.append({"Indicator": spec["measure"], "Value": as_metric_value(safe_float(snapshot.get(spec["field"])), spec),
                     "Reference month": pretty_month(snapshot.get(spec["reference"])),
                     "Source": ", ".join(spec["sources"]), "Data quality": snapshot["quality"].get(metric, "UNKNOWN")})
    data = pd.DataFrame(rows).to_csv(index=False).encode("utf-8")
    st.download_button("Download readings (CSV)", data=data,
                       file_name=f"macroscript_{key}_{snapshot['as_of']}.csv", mime="text/csv")


def today_view():
    hero("THE CURRENT PICTURE", "Today's U.S. economy",
         "A clear look at five economic indicators, what they mean, and how they have changed.")
    if not get_api_key():
        st.warning("Add your FRED API key to the local .env file to view current readings. The Time Machine's saved dates work offline.")
        return
    _, refresh_col = st.columns([5, 1.6])
    with refresh_col:
        if st.button("↻ Refresh data", width="stretch", key="refresh_today"):
            api_bundle.clear()
            st.rerun()
    bundle = load_selected_api("present", date.today().isoformat())
    if bundle is None:
        return
    snapshot = snapshot_from_bundle(bundle)
    st.markdown(f'<div class="ms-mini-title">Latest readings · checked {text(snapshot["as_of"])}</div>', unsafe_allow_html=True)
    st.markdown('<div class="ms-footnote">Each reading shows its own reference month because economic data is released on different dates.</div>', unsafe_allow_html=True)
    kpi_cards(snapshot)
    economic_insights(snapshot)
    indicator_journey(snapshot, lambda k, months: observation_chart_df(bundle, k, months),
                      "FRED data can be revised after it is first published.", suffix="today")
    st.markdown('<div class="ms-footnote">Source: Federal Reserve Economic Data (FRED). All numbers describe observed economic conditions; they do not predict recessions.</div>', unsafe_allow_html=True)
    download_snapshot(snapshot)


def revised_comparison_records(snapshot):
    """Match the original and revised features by their economic reference month."""
    if snapshot["as_of"][:7] > "2024-12":
        return []
    try:
        revised = cached_revised().set_index("month", drop=False)
    except (OSError, ValueError):
        return []
    rows = []
    for key in DISPLAY_ORDER:
        spec = INDICATORS[key]
        reference = snapshot.get(spec["reference"])
        original = safe_float(snapshot.get(spec["field"]))
        if not reference or reference not in revised.index or original is None:
            continue
        revised_row = revised.loc[reference]
        if str(revised_row[spec["reference"]]) != reference:
            continue
        present = safe_float(revised_row[spec["field"]])
        if present is None:
            continue
        rows.append((key, original, present, reference))
    return rows


def revised_comparison(snapshot):
    rows = revised_comparison_records(snapshot)
    if not rows:
        st.caption("A matching revised-data comparison is not available for this date.")
        return
    st.markdown('<div class="ms-section">How later revisions changed the record</div>', unsafe_allow_html=True)
    st.markdown('<div class="ms-footnote">Each pair refers to the same economic month, so we do not confuse revisions with newly published months.</div>', unsafe_allow_html=True)
    columns = st.columns(min(3, len(rows)), gap="small")
    for idx, (key, original, revised, reference) in enumerate(rows):
        spec = INDICATORS[key]
        with columns[idx % len(columns)]:
            st.markdown(f'<div class="ms-detail"><div class="ms-mini-title">{text(spec["name"])}</div>'
                        f'<div style="margin-top:.55rem"><strong>Then:</strong> {text(as_metric_value(original, spec))}</div>'
                        f'<div><strong>Later:</strong> {text(as_metric_value(revised, spec))}</div>'
                        f'<div class="ms-footnote">Same reference: {text(pretty_month(reference))}</div></div>',
                        unsafe_allow_html=True)
    st.markdown('<div class="ms-footnote">These later values come from the saved revised research archive through December 2024, not a current live revision query.</div>', unsafe_allow_html=True)


def time_machine():
    hero("TRAVEL BACK IN TIME", "What did the economy look like then?",
         "Choose a date to see what economic data was actually available at that time, without looking ahead.")
    try:
        archive = cached_monthly() if MONTHLY_CSV.is_file() else None
    except (OSError, ValueError):
        archive = None
    a, b = st.columns([1.2, 2.4], gap="large")
    with a:
        selected = st.date_input("Choose a historical date", value=date(2007, 11, 30),
                                 min_value=date(1959, 1, 1), max_value=date.today(),
                                 key="tm_date")
    with b:
        st.markdown('<div class="ms-detail"><strong>Why historical dates matter</strong><div style="margin-top:.28rem">Economic figures are published gradually and can be revised. Looking at today’s numbers may misrepresent what people knew then.</div></div>', unsafe_allow_html=True)
    requested = selected.isoformat()
    month = requested[:7]
    last_day = calendar.monthrange(selected.year, selected.month)[1]
    archived_months = set(archive["month"].astype(str)) if archive is not None else set()
    is_archived = selected.day == last_day and month in archived_months
    bundle = None
    if is_archived:
        snapshot = cached_snapshot(archive, month)
        st.markdown(f'<div class="ms-mini-title">As known on {text(requested)} · Saved historical snapshot</div>', unsafe_allow_html=True)
    else:
        if not get_api_key():
            st.info("That date needs a historical data request. Add a FRED API key, or select a saved month-end date from 1999–2024.")
            return
        if st.button("View this date", type="primary", key="load_tm"):
            st.session_state["tm_loaded_date"] = requested
        if st.session_state.get("tm_loaded_date") != requested:
            st.markdown('<div class="ms-footnote">Select “View this date” to retrieve its historical data from ALFRED.</div>', unsafe_allow_html=True)
            return
        bundle = load_selected_api("time_machine", requested)
        if bundle is None:
            return
        snapshot = snapshot_from_bundle(bundle)
        st.markdown(f'<div class="ms-mini-title">Information available on {text(requested)} · Historical data</div>', unsafe_allow_html=True)
    st.markdown('<div class="ms-section">The economy at that date</div>', unsafe_allow_html=True)
    kpi_cards(snapshot)
    economic_insights(snapshot)
    if bundle is not None:
        chart = lambda k, months: observation_chart_df(bundle, k, months)
        note = "Chart values come from the ALFRED vintage available at this selected date."
    else:
        chart = lambda k, months: cached_chart_df(archive, k, snapshot["as_of"][:7], months)
        note = "Each point is what the archive recorded at that month-end, not one fixed-vintage series."
    indicator_journey(snapshot, chart, note, suffix="history")
    if snapshot["as_of"][:7] <= "2024-12":
        if st.toggle("Compare with figures published later", value=False, key="tm_revisions"):
            revised_comparison(snapshot)
    download_snapshot(snapshot, key="historical")
    st.markdown('<div class="ms-footnote">Historical observations do not include future outcome labels. Some sources or calculated measures may be missing at a selected cutoff.</div>', unsafe_allow_html=True)


def research_lab():
    hero("BEHIND THE RESEARCH", "What our recession research taught us",
         "We tested whether economic indicators could provide reliable recession warnings. The evidence did not justify publishing a live prediction.")
    cards = st.columns(3, gap="medium")
    findings = (
        ("Promising in hindsight", "Some models trained on revised history beat a simple baseline in retrospective comparisons."),
        ("Not reliable enough", "When we trained with information available closer to each historical date, performance deteriorated."),
        ("False alarms matter", "Some models warned repeatedly during non-recession periods. A convincing chart alone is not a dependable early-warning system."),
    )
    for col, (heading, detail) in zip(cards, findings):
        with col:
            st.markdown(f'<div class="ms-finding"><strong>{text(heading)}</strong><p>{text(detail)}</p></div>', unsafe_allow_html=True)
    path = AUDIT / "v6_final_origin_scores.csv"
    if not path.is_file():
        st.info("The archived research results are unavailable in this copy.")
        return
    audit = read_research_csv(str(path))
    matched = audit.loc[(audit["stage"] == "PIT origin-vintage, matched for origin_rf7") & (audit["horizon"] == 12)]
    labels = {"historical_base": "Historical baseline",
              "rf7_rates_walk": "Model trained on revised data",
              "origin_rf7": "Model trained on historical data"}
    scores = []
    for method, label in labels.items():
        record = matched.loc[matched["method"] == method]
        if len(record) == 1:
            scores.append((label, float(record.iloc[0]["brier"])))
    if len(scores) == 3:
        section_heading("A promising result didn't hold up")
        st.markdown('<div class="ms-footnote">Illustration: 12-month recession research, matched 2005–2024 historical-input evaluation. Brier score measures forecast error; lower is better.</div>', unsafe_allow_html=True)
        c = palette()
        bars = go.Figure(go.Bar(
            x=[v for _,v in scores], y=[name for name,_ in scores], orientation="h",
            marker_color=[c["faint"], c["good"], c["bad"]],
            text=[f"{value:.3f}" for _,value in scores], textposition="outside",
            textfont=dict(color=c["text"], size=14),
            hovertemplate="Brier score: %{x:.4f}<extra></extra>"))
        bars.update_layout(template="none", height=330, margin=dict(l=230,r=85,t=18,b=65),
                           paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                           font=dict(color=c["text"],size=14),
                           xaxis=dict(showgrid=True,gridcolor=c["border"],rangemode="tozero",
                                      color=c["text"],tickfont=dict(color=c["text"],size=13),
                                      title=dict(text="Brier score (lower is better)",font=dict(color=c["text"],size=14))),
                           yaxis=dict(autorange="reversed",showgrid=False,automargin=True,
                                      color=c["text"],tickfont=dict(color=c["text"],size=14)),
                           hoverlabel=dict(bgcolor=c["panel"],bordercolor=c["border"],font=dict(color=c["text"])),
                           showlegend=False)
        st.plotly_chart(bars, width="stretch", config={"displayModeBar":False})
        st.markdown('<div class="ms-note"><strong>The important insight:</strong> The revised-trained seven-indicator model looked stronger, but the historical-origin-trained version scored worse than the basic baseline. This is why we do not publish a recession probability.</div>', unsafe_allow_html=True)
    st.markdown('<div class="ms-section">What this means</div>', unsafe_allow_html=True)
    st.markdown('<div class="ms-detail">The main dashboard still helps explain unemployment, jobs, production, housing, and interest rates. It does <strong>not</strong> claim that five economic indicators can reliably predict the next recession.</div>',unsafe_allow_html=True)
    st.markdown('<div class="ms-footnote">Research limitations: the evaluation period was examined repeatedly, recession events were few, and historical-origin training used a shorter sample. This comparison does not isolate the effect of vintage revisions alone.</div>',unsafe_allow_html=True)
    with st.container():
        report = ROOT / "research" / "MacroScript_V6_Overview.txt"
        if report.is_file():
            st.download_button("Download full technical research", report.read_bytes(),
                               file_name=report.name, mime="text/plain")


def sidebar():
    with st.sidebar:
        st.markdown('<div class="ms-brand">Macro<span>Script</span></div>', unsafe_allow_html=True)
        st.markdown('<div class="ms-tagline">Explore the U.S. economy, past and present.</div>', unsafe_allow_html=True)
        st.divider()
        for page, title in (
            ("Start", "Home"),
            ("Today", "Today's Economy"),
            ("Time Machine", "Time Machine"),
            ("Research", "Research findings"),
        ):
            if st.button(title, width="stretch",
                         type="primary" if st.session_state["page"] == page else "secondary",
                         key=f"nav_{page}"):
                navigate(page)
        st.divider()
        st.selectbox("Appearance", list(THEMES), key="ms_theme")
        st.link_button("View source on GitHub", GITHUB_URL, width="stretch")
        st.markdown('<div class="ms-sidebar-foot">Data from FRED / ALFRED.<div style="margin-top:.45rem">Research and education, not investment advice or a validated recession forecast.</div></div>',
                    unsafe_allow_html=True)
    return st.session_state["page"]


def main():
    st.session_state.setdefault("page", "Start")
    st.session_state.setdefault("ms_theme", "Light")
    st.markdown(theme_css(), unsafe_allow_html=True)
    page = sidebar()
    if page == "Start":
        landing()
    elif page == "Today":
        today_view()
    elif page == "Time Machine":
        time_machine()
    else:
        research_lab()


if __name__ == "__main__":
    main()
