
"""V5: Recession-warning threshold research.

Uses today's revised economic data for descriptive comparisons.
This is NOT a point-in-time backtest or a trained forecasting model.
"""

import csv
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from statistics import mean


def month_number(month):
    if not isinstance(month, str) or len(month) != 7 or month[4] != "-":
        raise ValueError(f"Expected YYYY-MM: {month!r}")
    parsed = date.fromisoformat(month + "-01")
    return parsed.year * 12 + parsed.month - 1


def month_name(index):
    year, offset = divmod(index, 12)
    return f"{year:04d}-{offset + 1:02d}"


@dataclass(frozen=True)
class Rule:
    name: str
    checks: tuple
    logic: str = "AND"


RULES = (
    Rule(
        "Treasury spread < 0",
        (("treasury_spread_pp", "<", 0),),
    ),
    Rule(
        "Treasury spread < 0.5",
        (("treasury_spread_pp", "<", 0.5),),
    ),
    Rule(
        "Housing YoY < 0",
        (("permits_growth_12m_pct", "<", 0),),
    ),
    Rule(
        "Housing YoY <= -10",
        (("permits_growth_12m_pct", "<=", -10),),
    ),
    Rule(
        "Payroll growth < 1",
        (("payroll_growth_12m_pct", "<", 1),),
    ),
    Rule(
        "Industrial growth < 0",
        (("industrial_growth_12m_pct", "<", 0),),
    ),
    Rule(
        "Sahm >= 0.5",
        (("unemployment_sahm_pp", ">=", 0.5),),
    ),
    Rule(
        "Treasury < 0 AND Housing < 0",
        (
            ("treasury_spread_pp", "<", 0),
            ("permits_growth_12m_pct", "<", 0),
        ),
    ),
    Rule(
        "Treasury < 0.5 AND Housing < 0",
        (
            ("treasury_spread_pp", "<", 0.5),
            ("permits_growth_12m_pct", "<", 0),
        ),
    ),
    Rule(
        "Treasury < 0 AND Housing <= -10",
        (
            ("treasury_spread_pp", "<", 0),
            ("permits_growth_12m_pct", "<=", -10),
        ),
    ),
    Rule(
        "Treasury < 0 OR Housing < 0",
        (
            ("treasury_spread_pp", "<", 0),
            ("permits_growth_12m_pct", "<", 0),
        ),
        "OR",
    ),
)


def load_csv(path):
    """Load research data and convert relevant fields to usable types."""
    with Path(path).open(newline="", encoding="utf-8-sig") as f:
        raw = list(csv.DictReader(f))

    if not raw:
        raise ValueError("Research CSV is empty")

    required = {
        "month",
        "in_recession",
        "recession_next_12m",
        *(column for rule in RULES for column, _, _ in rule.checks),
    }

    missing = required - set(raw[0])
    if missing:
        raise ValueError(f"Missing columns: {sorted(missing)}")

    rows = []

    for item in raw:
        month = item["month"]
        month_number(month)

        recession = item["in_recession"].strip().lower()
        if recession not in ("true", "false", ""):
            raise ValueError(f"Invalid recession label: {month}")

        target = item["recession_next_12m"].strip()
        if target not in ("0", "1", ""):
            raise ValueError(f"Invalid target: {month}")

        row = {
            "month": month,
            "in_recession": {
                "true": True,
                "false": False,
                "": None,
            }[recession],
            "recession_next_12m": int(target) if target else None,
            "data_mode": item.get("data_mode", ""),
        }

        feature_fields = required - {
            "month", "in_recession", "recession_next_12m"
        }

        for field in feature_fields:
            value = item[field].strip()
            row[field] = float(value) if value else None

        rows.append(row)

    rows.sort(key=lambda r: r["month"])

    if len(set(r["month"] for r in rows)) != len(rows):
        raise ValueError("Duplicate month in research CSV")

    return rows


def is_warning(row, rule):
    """Evaluate a warning; missing inputs mean UNKNOWN, not False."""
    results = []

    for column, op, threshold in rule.checks:
        value = row.get(column)

        if value is None:
            return None

        if op == "<":
            results.append(value < threshold)
        elif op == "<=":
            results.append(value <= threshold)
        elif op == ">=":
            results.append(value >= threshold)
        else:
            raise ValueError(f"Unsupported operator: {op}")

    if rule.logic == "AND":
        return all(results)

    if rule.logic == "OR":
        return any(results)

    raise ValueError(f"Unknown combination logic: {rule.logic}")


def onset_months(rows):
    """Identify actual 0-to-1 recession transitions."""
    mapping = {r["month"]: r for r in rows}
    events = []

    for row in rows:
        if row["in_recession"] is not True:
            continue

        previous_month = month_name(
            month_number(row["month"]) - 1
        )
        previous = mapping.get(previous_month)

        if previous and previous["in_recession"] is False:
            events.append(row["month"])

    return sorted(events)


def evaluate(rows, rule, event_months=None, horizon=12):
    """Evaluate a warning against recession events and monthly targets."""
    if horizon != 12:
        raise ValueError("Only the 12-month horizon is supported here")

    rows = sorted(rows, key=lambda r: r["month"])

    if event_months is None:
        event_months = onset_months(rows)

    event_months = sorted(set(event_months))

    eligible = [
        (row, is_warning(row, rule))
        for row in rows
        if row["in_recession"] is False
        and row["recession_next_12m"] in (0, 1)
    ]

    valid = [(r, s) for r, s in eligible if s is not None]

    positives = [
        (r, s) for r, s in valid
        if r["recession_next_12m"] == 1
    ]
    negatives = [
        (r, s) for r, s in valid
        if r["recession_next_12m"] == 0
    ]

    true_warning_months = sum(s for _, s in positives)
    false_warning_months = sum(s for _, s in negatives)

    lead_times = []
    covered_events = 0

    for event in event_months:
        event_index = month_number(event)

        preceding = [
            (row, warning)
            for row, warning in valid
            if row["recession_next_12m"] == 1
            and 1 <= event_index - month_number(row["month"]) <= horizon
        ]

        if not preceding:
            continue

        covered_events += 1

        warnings = [
            event_index - month_number(row["month"])
            for row, signal in preceding
            if signal
        ]

        if warnings:
            lead_times.append(max(warnings))

    # Group consecutive monthly warnings into spells.
    # A spell that never overlaps a pre-recession target is a false alarm.
    false_spells = 0
    spell_active = False
    spell_has_positive = False
    previous_month = None

    def finish_spell():
        return int(spell_active and not spell_has_positive)

    for row, warning in eligible:
        current = month_number(row["month"])

        if warning is True:
            if (
                not spell_active
                or previous_month is None
                or current != previous_month + 1
            ):
                false_spells += finish_spell()
                spell_active = True
                spell_has_positive = False

            if row["recession_next_12m"] == 1:
                spell_has_positive = True

            previous_month = current
        else:
            false_spells += finish_spell()
            spell_active = False
            spell_has_positive = False
            previous_month = None

    false_spells += finish_spell()

    total_warnings = true_warning_months + false_warning_months

    return {
        "rule": rule.name,
        "sample_months": len(rows),
        "eligible_months": len(eligible),
        "evaluated_months": len(valid),
        "coverage_pct": (
            100 * len(valid) / len(eligible) if eligible else None
        ),
        "events": len(event_months),
        "events_with_coverage": covered_events,
        "events_detected": len(lead_times),
        "mean_first_lead_months": (
            mean(lead_times) if lead_times else None
        ),
        "positive_warning_months": true_warning_months,
        "positive_evaluated_months": len(positives),
        "false_alarm_months": false_warning_months,
        "negative_evaluated_months": len(negatives),
        "false_alarm_pct": (
            100 * false_warning_months / len(negatives)
            if negatives else None
        ),
        "alert_precision_pct": (
            100 * true_warning_months / total_warnings
            if total_warnings else None
        ),
        "false_alarm_spells": false_spells,
    }


def event_details(rows, rule, event_months=None, horizon=12):
    """Record the first warning for each individual recession."""
    if horizon != 12:
        raise ValueError("Only the 12-month horizon is supported here")

    if event_months is None:
        event_months = onset_months(rows)

    records = []

    for event in sorted(set(event_months)):
        event_index = month_number(event)

        preceding = [
            (row, is_warning(row, rule))
            for row in rows
            if row["in_recession"] is False
            and row["recession_next_12m"] == 1
            and 1 <= event_index - month_number(row["month"]) <= horizon
        ]

        available = [
            (row, signal)
            for row, signal in preceding
            if signal is not None
        ]

        warnings = [
            row["month"]
            for row, signal in available
            if signal
        ]

        first = min(warnings) if warnings else None

        records.append({
            "rule": rule.name,
            "recession_start": event,
            "months_with_data": len(available),
            "detected": first is not None,
            "first_warning_month": first,
            "lead_months": (
                event_index - month_number(first)
                if first else None
            ),
        })

    return records


def format_number(value, suffix=""):
    if value is None:
        return "n/a"
    return f"{value:.1f}{suffix}"


def print_table(name, rows):
    print(f"\n=== {name} ===")
    print(
        f"{'Rule':40} {'Events':9} {'FPR':8} "
        f"{'Lead':8} {'Cover':9} {'FA spells':9}"
    )
    print("-" * 88)

    results = []

    for rule in RULES:
        result = evaluate(rows, rule)
        result["period"] = name
        results.append(result)

        print(
            f"{rule.name:40} "
            f"{result['events_detected']}/{result['events']:<7} "
            f"{format_number(result['false_alarm_pct'], '%'):8} "
            f"{format_number(result['mean_first_lead_months'], 'm'):8} "
            f"{format_number(result['coverage_pct'], '%'):9} "
            f"{result['false_alarm_spells']:>5}"
        )

    return results


def save_comparison(rows, path):
    if not rows:
        raise ValueError("No results to save")

    with Path(path).open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main():
    rows = load_csv("v5_research_revised.csv")

    earlier = [
        row for row in rows if row["month"] <= "1999-12"
    ]
    later = [
        row for row in rows if row["month"] >= "2000-01"
    ]

    print("Revised historical data only. NOT a real-time backtest.")
    print("Thresholds are fixed for this exploratory comparison.")

    full_results = print_table(
        "FULL SAMPLE: 1962-2024", rows
    )
    earlier_results = print_table(
        "EARLIER SAMPLE: 1962-1999", earlier
    )
    later_results = print_table(
        "LATER SAMPLE: 2000-2024 (stability only)", later
    )

    save_comparison(
        full_results + earlier_results + later_results,
        "v5_signal_comparison.csv",
    )

    details = [
        item
        for rule in RULES
        for item in event_details(rows, rule)
    ]

    save_comparison(
        details, "v5_signal_event_details.csv"
    )

    print("\nSaved: v5_signal_comparison.csv")
    print("Saved: v5_signal_event_details.csv")
    print(
        "WARNING: Revised data, overlapping forecast windows "
        "and few independent recessions limit these findings."
    )


if __name__ == "__main__":
    main()
