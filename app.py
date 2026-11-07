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
        "detail": "Share of the labor force unemployed. Changes often lag turning points.",
    },
    "payrolls": {
        "name": "Employment", "measure": "Payroll growth, 12m",
        "field": "payroll_growth_12m_pct", "unit": "%", "fmt": "{:+.2f}%",
        "reference": "payrolls_reference_month", "age": "payrolls_age_months",
        "sources": ("PAYEMS",), "color": "#4DD9C1", "group": "payrolls",
        "series": "PAYEMS", "chart_unit": "%", "chart_title": "Payroll employment · 12m growth",
        "detail": "Year-over-year growth in nonfarm payroll employment.",
    },
    "industrial_production": {
        "name": "Production", "measure": "Industrial growth, 12m",
        "field": "industrial_growth_12m_pct", "unit": "%", "fmt": "{:+.2f}%",
        "reference": "industrial_production_reference_month", "age": "industrial_production_age_months",
        "sources": ("INDPRO",), "color": "#C4A5FF", "group": "industrial_production",
        "series": "INDPRO", "chart_unit": "%", "chart_title": "Industrial production · 12m growth",
        "detail": "Year-over-year growth in the industrial production index.",
    },
    "housing_permits": {
        "name": "Housing", "measure": "Building permits, 12m",
        "field": "permits_growth_12m_pct", "unit": "%", "fmt": "{:+.2f}%",
        "reference": "housing_permits_reference_month", "age": "housing_permits_age_months",
        "sources": ("PERMIT",), "color": "#FFC47B", "group": "housing_permits",
        "series": "PERMIT", "chart_unit": "%", "chart_title": "Housing permits · 12m growth",
        "detail": "Year-over-year change in residential building permits (seasonally adjusted annual rate).",
    },
    "treasury_spread": {
        "name": "Yield curve", "measure": "10Y minus 3M spread",
        "field": "treasury_spread_pp", "unit": "pp", "fmt": "{:+.2f} pp",
        "reference": "treasury_spread_reference_month", "age": "treasury_spread_age_months",
        "sources": ("GS10", "TB3MS"), "color": "#F38BA8", "group": "treasury_spread",
        "series": None, "chart_unit": "pp", "chart_title": "Monthly 10Y–3M Treasury spread",
        "detail": "GS10 − TB3MS, matching monthly yield observations. This is not the daily T10Y3M series.",
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


CSS = """
<style>
:root {color-scheme: dark;}
[data-testid="stAppViewContainer"] {background:#0B1120;color:#E6ECF7;}
[data-testid="stSidebar"] {background:#0E172A;border-right:1px solid #24324A;}
[data-testid="stHeader"] {background:transparent;}
[data-testid="stToolbar"] {right:1rem;}
.block-container {max-width:1330px;padding-top:2.1rem;padding-bottom:3rem;}
h1,h2,h3 {letter-spacing:-.035em;}
h1 {color:#F4F7FF !important;}
p,span,label {line-height:1.5;}
.ms-brand {font-size:1.25rem;font-weight:850;letter-spacing:-.04em;color:#F0F5FF;margin-bottom:.18rem;}
.ms-brand span {color:#67DCCA;}
.ms-subtle {color:#94A6C0;font-size:.82rem;}
.ms-hero {padding:1.2rem 0 1.5rem;border-bottom:1px solid #25324A;margin-bottom:1.4rem;}
.ms-eyebrow {color:#64E0C4;text-transform:uppercase;letter-spacing:.19em;font-size:.71rem;font-weight:800;margin-bottom:.48rem;}
.ms-title {font-size:clamp(2rem,3.3vw,3.2rem);color:#F5F7FB;font-weight:850;letter-spacing:-.055em;line-height:1.13;margin:0 0 .6rem;}
.ms-deck {color:#AAB9D0;font-size:.99rem;max-width:850px;line-height:1.65;}
.ms-kpi {border:1px solid #2C3A54;background:linear-gradient(153deg,#17253B,#101B2E);border-radius:14px;padding:.95rem 1rem .9rem;min-height:137px;margin-bottom:.35rem;}
.ms-kpi-top {font-size:.73rem;text-transform:uppercase;letter-spacing:.1em;color:#A6B8D1;font-weight:750;}
.ms-kpi-val {font-size:1.6rem;font-weight:830;color:#F4F7FC;letter-spacing:-.045em;margin:.54rem 0 .34rem;white-space:nowrap;}
.ms-kpi-bottom {font-size:.76rem;color:#A1B0C9;}
.ms-section {font-size:1.17rem;letter-spacing:-.03em;font-weight:750;color:#EEF4FF;margin:1.2rem 0 .6rem;}
.ms-note {padding:1rem 1.15rem;background:#132137;border:1px solid #2B4160;border-radius:14px;color:#C2CFE3;line-height:1.65;margin:.8rem 0 1.1rem;}
.ms-note strong {color:#EAF0FF;}
.ms-pill {border-radius:30px;padding:.17rem .58rem;border:1px solid #375071;color:#BACBE2;font-size:.72rem;font-weight:680;}
.ms-result {padding:1.03rem 1.15rem;background:#131F34;border:1px solid #2E3E55;border-radius:13px;margin-bottom:.55rem;}
.ms-result-label {font-size:.85rem;font-weight:750;color:#EDF3FF;}
.ms-result-desc {font-size:.80rem;color:#ACBDD5;margin-top:.36rem;line-height:1.55;}
.ms-footer {color:#7F92AF;font-size:.76rem;margin-top:1.4rem;border-top:1px solid #26334B;padding-top:1rem;}
.ms-mode-card {border:1px solid #2C3C55;background:linear-gradient(150deg,#182940,#101B2C);border-radius:18px;padding:1.4rem;min-height:205px;margin:.25rem 0 .5rem;}
.ms-mode-icon {font-size:1.65rem;margin-bottom:.55rem;}
.ms-mode-title {font-size:1.32rem;color:#F2F6FF;font-weight:770;letter-spacing:-.035em;margin:.2rem 0 .45rem;}
.ms-mode-description {font-size:.91rem;color:#B0C0D6;line-height:1.65;}
.ms-step-title {font-size:.73rem;color:#66DAC4;font-weight:780;text-transform:uppercase;letter-spacing:.12em;}
.ms-small-note {font-size:.83rem;color:#A9BAD2;line-height:1.65;margin:.3rem 0 .8rem;}
[data-testid="stSidebar"] .stButton button {text-align:left;justify-content:flex-start;}
[data-testid="stAppViewContainer"] .stButton button {border-radius:10px;}

[data-testid="stMetricValue"] {color:#F4F7FF;}
[data-testid="stDataFrame"], [data-testid="stPlotlyChart"] {border-radius:14px;overflow:hidden;}
[data-testid="stAlert"] {border-radius:12px;}
</style>
"""


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
        value = safe_float(snapshot.get(spec["field"]))
        reference = snapshot.get(spec["reference"])
        quality = snapshot["quality"].get(key, "UNKNOWN")
        if value is None:
            status = "Not available"
        elif quality == "KNOWN_GAP":
            status = "Prior gap in history"
        elif is_usable(snapshot, key):
            status = "Source OK"
        else:
            status = "Check data quality"
        with col:
            st.markdown(
                f'<div class="ms-kpi">'
                f'<div class="ms-kpi-top">{text(spec["measure"])}</div>'
                f'<div class="ms-kpi-val">{text(as_metric_value(value, spec))}</div>'
                f'<div class="ms-kpi-bottom">{text(pretty_month(reference))} · {text(status)}</div>'
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


def economic_insights(snapshot):
    """One visible takeaway; details are opt-in."""
    summary, flags, combined = interpret(snapshot)
    section_heading("Economic picture", "Transparent indicator thresholds, not a recession probability.")
    st.markdown(
        f'<div class="ms-note"><strong>At this information cutoff</strong><div style="margin-top:.32rem">{text(summary)}</div></div>',
        unsafe_allow_html=True,
    )
    weak = [(title, status, desc) for title, status, desc in flags if status == "Deteriorating"]
    unknown = [(title, status, desc) for title, status, desc in flags if status == "Unavailable"]
    if weak:
        st.caption("Deteriorating under defined thresholds: " + ", ".join(t for t, _, _ in weak) + ".")
    if unknown:
        st.caption("Incomplete assessment: " + ", ".join(t for t, _, _ in unknown) + " requires additional data.")
    with st.expander("See how the five indicators contributed"):
        for name, status, description in flags:
            st.markdown(f"**{name} — {status}**  \n{description}")
        st.divider()
        if combined is True:
            st.info("The exploratory V5 Treasury + housing rule is active. It generated false warnings historically and is not a validated recession forecast.")
        elif combined is False:
            st.caption("The exploratory V5 Treasury + housing rule is not active. That does not rule out a recession.")
        else:
            st.caption("The exploratory V5 combined rule cannot be assessed from the available data.")


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
        st.info("No usable historical chart observations for this indicator and date.")
        return
    figure = go.Figure()
    figure.add_trace(go.Scatter(
        x=df["date"], y=df["value"], mode="lines",
        line={"color": spec["color"], "width": 2.8},
        fill="tozeroy" if key != "unemployment" else None,
        fillcolor="rgba(85,125,180,0.07)",
        hovertemplate=f"%{{x|%b %Y}}<br>%{{y:.2f}} {spec['chart_unit']}<extra></extra>",
        connectgaps=False,
    ))
    if key == "treasury_spread":
        figure.add_hline(y=0, line_color="#687B99", line_dash="dot", line_width=1)
    figure.update_layout(
        template="plotly_dark", height=345,
        margin=dict(l=5,r=14,t=10,b=5),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#B8C5DA",size=12),
        xaxis=dict(showgrid=False, title=None),
        yaxis=dict(showgrid=True, gridcolor="#233249", title=spec["chart_unit"], zeroline=False),
        showlegend=False, hovermode="x unified",
    )
    st.plotly_chart(figure, width="stretch", config={"displayModeBar": False})
    if note:
        st.caption(note)


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
    """A two-path home page, deliberately free of network requests."""
    hero(
        "MACROSCRIPT · ECONOMIC RESEARCH",
        "Understand the economy. Now or then.",
        "Explore up-to-date U.S. economic indicators, or travel back to see what data was actually available to decision-makers at a past date.",
    )
    left, right = st.columns(2, gap="large")
    with left:
        st.markdown("""<div class="ms-mode-card">
          <div class="ms-step-title">Mode 01 · Current conditions</div>
          <div class="ms-mode-icon">📡</div>
          <div class="ms-mode-title">Today's Economy</div>
          <div class="ms-mode-description">Request the latest readings from FRED, see the five core indicators and a concise interpretation. Each series shows its own observation month.</div>
        </div>""", unsafe_allow_html=True)
        if st.button("View today's economy", type="primary", width="stretch", key="home_today"):
            navigate("Today")
    with right:
        st.markdown("""<div class="ms-mode-card">
          <div class="ms-step-title">Mode 02 · Historical perspective</div>
          <div class="ms-mode-icon">🕰️</div>
          <div class="ms-mode-title">Time Machine</div>
          <div class="ms-mode-description">Choose a date and inspect historical ALFRED observations—before later releases and revisions changed the historical picture.</div>
        </div>""", unsafe_allow_html=True)
        if st.button("Explore a historical date", width="stretch", key="home_history"):
            navigate("Time Machine")
    st.markdown('<div class="ms-section">Why look backward?</div>', unsafe_allow_html=True)
    st.markdown("""<div class="ms-note">
    <strong>What we know today is not always what was known then.</strong>
    Employment, production, and other economic figures are released on different schedules and may be revised.
    A historical analysis using only today's revised data can accidentally give the past information it did not have.
    MacroScript lets you compare those perspectives—without presenting unvalidated recession predictions.
    </div>""", unsafe_allow_html=True)
    st.caption("Built with FRED / ALFRED data. Advanced indicator tools and V5–V6 forecasting research are available in the sidebar.")


def today_view():
    hero(
        "MODE 01 · FRED API",
        "Today's U.S. economy.",
        "See the latest published readings and a brief, rule-based interpretation. Observations have different release schedules and reference months.",
    )
    if not get_api_key():
        st.warning("Add FRED_API_KEY to V7/.env to retrieve live observations. Historical month-end snapshots remain available offline in Time Machine.")
        return
    if st.button("↻  Request latest FRED readings" if not st.session_state.get("today_loaded") else "↻  Refresh latest readings", 
                 type="primary", key="fetch_today"):
        if st.session_state.get("today_loaded"):
            api_bundle.clear()
        st.session_state["today_loaded"] = True
        st.rerun()
    if not st.session_state.get("today_loaded"):
        st.markdown('<div class="ms-note"><strong>Ready when you are.</strong> This page makes no API call until you request one. The five economic series are checked for missing values and historical-data gaps.</div>', unsafe_allow_html=True)
        return
    bundle = load_selected_api("present", date.today().isoformat())
    if bundle is None:
        return
    snapshot = snapshot_from_bundle(bundle)
    st.caption(f"Information cutoff: {snapshot['as_of']} · FRED data (cached for up to one hour unless refreshed) · Each card identifies its own observation month")
    kpi_cards(snapshot)
    economic_insights(snapshot)
    with st.expander("Explore an indicator's trend"):
        a, b = st.columns([2, 1], gap="large")
        with a:
            selected = st.selectbox("Indicator", options=DISPLAY_ORDER,
                                    format_func=lambda x: INDICATORS[x]["measure"], key="overview_metric")
        with b:
            lookback = st.selectbox("Chart history", [12,24,36,60], index=2,
                                    format_func=lambda n: f"Last {n} months", key="overview_history")
        plot_history(observation_chart_df(bundle, selected, lookback), selected)
        st.caption(INDICATORS[selected]["detail"])
    with st.expander("Data sources, freshness and export"):
        detail_table(snapshot)


def vintage_comparison(snapshot):
    """Match the *reference month* before reporting differences, not the decision month."""
    if snapshot["as_of"][:7] > "2024-12":
        st.caption("The archived revised research dataset ends in December 2024. No revised comparison is available for this date.")
        return
    try:
        revised = cached_revised().set_index("month", drop=False)
    except (OSError, ValueError) as exc:
        st.warning(f"Revised comparison unavailable: {exc}")
        return
    records = []
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
        records.append({
            "Indicator": spec["measure"],
            "Matching reference": pretty_month(reference),
            "At historical cutoff": round(original,3),
            "Revised research archive": round(present,3),
            "Difference (revised − original)": round(present - original,3),
            "Units": spec["unit"],
        })
    if records:
        st.dataframe(pd.DataFrame(records), hide_index=True, width="stretch")
    else:
        st.info("No features can be aligned to the same reference month in the archived research dataset.")
    st.caption("Reference-period alignment prevents mistaken comparisons with data that had not yet been published. The right-hand column is a saved revised research extract, not a live 2026 revision query. Derived growth measures can change because their underlying history was revised.")


def time_machine():
    hero(
        "MODE 02 · ALFRED TIME MACHINE",
        "What was known on that date?",
        "Recreate a historical economic information set, instead of looking backward with figures that may have been published or revised afterward.",
    )
    st.markdown('<div class="ms-small-note"><strong>Why it matters:</strong> Later data releases and revisions can make the past look clearer than it did to policymakers, analysts, and investors at the time.</div>', unsafe_allow_html=True)
    historical_modes = ["Custom ALFRED date"]
    if MONTHLY_CSV.is_file():
        historical_modes.insert(0, "Archived month-end snapshot")
    else:
        st.info("The optional offline month-end archive is not included in this public copy. "
                "Choose a custom date to retrieve an ALFRED vintage with your FRED API key.")
    mode = st.radio("Choose a historical source", historical_modes,
                    horizontal=True, key="tm_source")
    df = None
    bundle = None
    if mode == "Archived month-end snapshot":
        try:
            df = cached_monthly()
        except (OSError, ValueError) as exc:
            st.error(f"Cannot read historical snapshot archive: {exc}")
            return
        available = list(reversed(df["month"].astype(str).tolist()))
        default = "2007-11" if "2007-11" in available else available[0]
        if st.session_state.get("selected_historical_month") not in available:
            st.session_state["selected_historical_month"] = default
        chosen = st.selectbox(
            "Historical month", available, key="selected_historical_month", format_func=lambda m: datetime.strptime(m, "%Y-%m").strftime("%B %Y"),
        )
        snapshot = cached_snapshot(df, chosen)
        st.caption(f"As known on {snapshot['as_of']} · Saved ALFRED-derived month-end snapshot · Offline archive: 1999–2024")
    else:
        chosen_date = st.date_input(
            "Historical information cutoff", value=date(2007, 11, 30),
            min_value=date(1959, 1, 1), max_value=date.today(), key="tm_custom_day",
        )
        st.caption("This mode queries ALFRED for the chosen day. Its historical vintages may not exist for all indicators; intraday release timing is not reconstructed.")
        if st.button("Retrieve this historical date", type="primary", key="fetch_custom_history"):
            st.session_state["tm_custom_loaded"] = chosen_date.isoformat()
        if st.session_state.get("tm_custom_loaded") != chosen_date.isoformat():
            st.info("Choose a date and select **Retrieve this historical date** to make an ALFRED request.")
            return
        bundle = load_selected_api("time_machine", chosen_date.isoformat())
        if bundle is None:
            return
        snapshot = snapshot_from_bundle(bundle)
        st.caption(f"ALFRED vintage information cutoff: {snapshot['as_of']} · Date-level reconstruction")
    section_heading("Information available at the cutoff")
    kpi_cards(snapshot)
    economic_insights(snapshot)
    with st.expander("How does today's revised record compare?"):
        st.markdown("The comparison uses the **same observation reference month** wherever possible. Differences can reflect revisions to the source data, including the components of derived growth rates.")
        vintage_comparison(snapshot)
    with st.expander("Explore a historical indicator trend"):
        a, b = st.columns([2, 1], gap="large")
        with a:
            selected = st.selectbox("Indicator", DISPLAY_ORDER,
                                    format_func=lambda x: INDICATORS[x]["measure"], key="tm_metric")
        with b:
            lookback = st.selectbox("History", [12,24,36,60], index=2,
                                     format_func=lambda n: f"Last {n} months", key="tm_months")
        if bundle is not None:
            plot_history(observation_chart_df(bundle, selected, lookback), selected,
                         "All points belong to the ALFRED vintage at the selected cutoff; graph dates identify economic reference periods, not release times.")
        else:
            plot_history(cached_chart_df(df, selected, snapshot["as_of"][:7], lookback), selected,
                         "Each point represents a separate month-end information set, not a single fixed-vintage history. Reference months may differ.")
    with st.expander("Underlying sources, freshness and export"):
        detail_table(snapshot)


def indicator_explorer():
    hero("INDICATOR EXPLORER", "One signal at a time.",
         "Examine the definition, data lineage, and trend of each major economic measure without collapsing them into one opaque score.")
    sources = ["Live FRED"]
    if MONTHLY_CSV.is_file():
        sources.append("Archived month-end snapshots")
    source = st.radio("Data source", sources, horizontal=True)
    bundle = None
    df = None
    if source == "Live FRED":
        bundle = load_selected_api("present", date.today().isoformat())
        if bundle is None:
            return
        snapshot = snapshot_from_bundle(bundle)
    else:
        try:
            df = cached_monthly()
        except (OSError, ValueError) as exc:
            st.error(str(exc))
            return
        selected_month = st.selectbox("Latest snapshot month", list(reversed(df["month"].astype(str).tolist())),
                                      format_func=pretty_month, key="explorer_month")
        snapshot = cached_snapshot(df, selected_month)
    selector = st.selectbox("Economic series", DISPLAY_ORDER,
                            format_func=lambda x: INDICATORS[x]["name"], key="exp_indicator")
    spec = INDICATORS[selector]
    value = safe_float(snapshot.get(spec["field"]))
    st.metric(label=spec["measure"], value=as_metric_value(value, spec))
    st.caption(f"Reference: {pretty_month(snapshot.get(spec['reference']))} · FRED IDs: {', '.join(spec['sources'])} · Quality: {snapshot['quality'][selector]}")
    st.markdown(f'<div class="ms-note">{text(spec["detail"])}</div>', unsafe_allow_html=True)
    duration = st.select_slider("Chart period (months)", options=[12,24,36,60,120], value=60)
    if bundle is not None:
        data = observation_chart_df(bundle, selector, duration)
    else:
        data = cached_chart_df(df, selector, snapshot["as_of"][:7], duration)
    plot_history(data, selector,
                 "Historical cached points use their own monthly information cutoffs." if bundle is None else "Live FRED data may include revisions to older reference periods.")
    with st.expander("Feature methodology"):
        if selector == "unemployment":
            st.write("The Sahm Rule feature compares the latest three-month unemployment-rate average with the lowest three-month average from the preceding 12 months. A 0.50 percentage-point difference triggers the descriptive threshold.")
        elif selector == "treasury_spread":
            st.write("Monthly GS10 yield minus monthly TB3MS yield, measured in percentage points. Both yields must have the same reference month. The monthly spread is distinct from the daily T10Y3M series.")
        else:
            st.write("Twelve-month percentage growth = 100 × (latest level / level exactly twelve calendar months earlier − 1). Missing calendar months are not interpolated.")
        st.write("A historical information cutoff does not imply every reference-period observation had been released. All current-vs-historical interpretations preserve the source and vintage distinction.")


def research_lab():
    hero("RESEARCH ARCHIVE · V5–V6", "What the forecasting research found.",
         "Reproducible recession-warning experiments, chronological model evaluation, and a documented decision not to deploy unvalidated recession probabilities.")
    st.markdown('<div class="ms-note"><strong>Research conclusion.</strong> Some interest-rate-augmented models performed better than simple historical benchmarks in retrospective tests. But the improvement was not robust to the shorter origin-vintage training experiment, the most recent period showed excessive warnings, and the evaluation had no untouched future holdout. No live recession probability is published here.</div>', unsafe_allow_html=True)
    scores_path = AUDIT / "v6_final_regime_scores.csv"
    origin_path = AUDIT / "v6_final_origin_scores.csv"
    if not scores_path.is_file() or not origin_path.is_file():
        st.warning("V6 research summary CSVs not found; ensure you extracted the complete V7 starter.")
        return
    regular = read_research_csv(str(scores_path))
    origin = read_research_csv(str(origin_path))
    horizon = st.selectbox("Evaluation horizon", [3,6,12], index=2, format_func=lambda n: f"Next {n} months")
    named = {
        "historical_base": "Historical base rate",
        "v5_housing_rule": "V5 housing + Treasury rule",
        "rf5_walk": "5-indicator RF (revised-trained)",
        "rf7_rates_walk": "7-indicator RF (revised-trained)",
        "rf8_all_walk": "8-indicator RF (revised-trained)",
    }
    sample = regular.loc[(regular["stage"] == "2005-2024 PIT") &
                         (regular["horizon"] == horizon) &
                         regular["method"].isin(named)].copy()
    sample["Model"] = sample["method"].map(named)
    sample = sample.rename(columns={"brier":"Brier ↓", "log_loss":"Log loss ↓", "auc":"ROC AUC"})
    section_heading("Matched PIT-input evaluation · 2005–2024",
                    "The models in this table were trained on revised history. This is a historical-input sensitivity analysis, not a fully real-time-trained test.")
    st.dataframe(sample[["Model", "Brier ↓", "Log loss ↓", "ROC AUC", "months"]].rename(columns={"months":"Months"}),
                 hide_index=True, width="stretch",
                 column_config={"Brier ↓":st.column_config.NumberColumn(format="%.4f"),
                                "Log loss ↓":st.column_config.NumberColumn(format="%.4f"),
                                "ROC AUC":st.column_config.NumberColumn(format="%.3f")})
    origin_models = ["historical_base", "origin_rf5", "origin_rf7", "origin_rf8"]
    values=[]
    for method in origin_models:
        chosen=origin.loc[(origin["horizon"] == horizon) & (origin["method"] == method)]
        if len(chosen):
            values.append({"Model": {
                "historical_base": "Historical base rate", "origin_rf5": "5-indicator RF (origin-vintage)",
                "origin_rf7": "7-indicator RF (origin-vintage)",
                "origin_rf8": "8-indicator RF (origin-vintage)"}[method],
                "Brier ↓": float(chosen.iloc[0]["brier"]), "Months": int(chosen.iloc[0]["months"])})
    section_heading("Historical-origin training investigation",
                    "Shorter 1999-onward training history and historical-vintage inputs; it cannot isolate the effects of revisions from the smaller training sample.")
    st.dataframe(pd.DataFrame(values), hide_index=True, width="stretch",
                 column_config={"Brier ↓":st.column_config.NumberColumn(format="%.4f")})
    with st.expander("Methodological limitations", expanded=False):
        st.markdown("""
- The 2005–2024 period was repeatedly inspected; it is **not an untouched holdout**.
- Twelve-month labels overlap, and the evaluation contains only two independent recession onsets in the later period.
- Revised-history training is not the same as historical-vintage training.
- The final 30-month label delay is a conservative proxy, **not** an exact NBER announcement calendar.
- Models produced many false-warning months in some regimes, especially 2022–2024.
- Research outcomes (`USREC` and future recession labels) are **never** passed to the live or historical dashboard as predictors.
""")
    report = ROOT / "research" / "MacroScript_V6_Overview.txt"
    if report.is_file():
        st.download_button("Download full V6 research overview", report.read_bytes(),
                           file_name=report.name, mime="text/plain")
    report5 = ROOT / "research" / "MacroScript_V5_Overview.txt"
    if report5.is_file():
        st.download_button("Download V5 warning research overview", report5.read_bytes(),
                           file_name=report5.name, mime="text/plain")


def sidebar():
    with st.sidebar:
        st.markdown('<div class="ms-brand">Macro<span>Script</span> <span style="font-weight:450;font-size:.72rem;color:#90A3C0">V7</span></div>',
                    unsafe_allow_html=True)
        st.caption("U.S. Economic Intelligence & Historical Research")
        st.divider()
        if "page" not in st.session_state:
            st.session_state["page"] = "Start"
        for page, title in (
            ("Start", "⌂  Start here"),
            ("Today", "◉  Today's economy"),
            ("Time Machine", "◷  Time Machine"),
        ):
            if st.button(title, width="stretch", type="primary" if st.session_state["page"] == page else "secondary", key=f"nav_{page}"):
                navigate(page)
        with st.expander("Advanced tools", expanded=st.session_state["page"] in ("Indicator Explorer", "Research Lab")):
            for page, title in (("Indicator Explorer", "Indicator Explorer"), ("Research Lab", "V5–V6 Research Lab")):
                if st.button(title, width="stretch", type="primary" if st.session_state["page"] == page else "secondary", key=f"nav_{page}"):
                    navigate(page)
        st.divider()
        if get_api_key():
            st.caption("● FRED API key configured")
        else:
            st.caption("○ No API key · cached history works offline")
        st.markdown('<div class="ms-footer">Historical research, not investment advice or a reliable recession forecasting system.</div>',
                    unsafe_allow_html=True)
    return st.session_state["page"]


def main():
    st.markdown(CSS, unsafe_allow_html=True)
    page = sidebar()
    if page == "Start":
        landing()
    elif page == "Today":
        today_view()
    elif page == "Time Machine":
        time_machine()
    elif page == "Indicator Explorer":
        indicator_explorer()
    else:
        research_lab()


if __name__ == "__main__":
    main()
