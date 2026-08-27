import sys

sys.path.insert(0, "notebooks")
sys.path.insert(0, ".")
import pandas as pd
from dope_viz import (
    FONT_BODY,
    FONT_MONO,
    GRID,
    GRID_STRONG,
    INK_DIM,
    INK_FAINT,
    MONITOR_AMBER,
    MONITOR_CYAN,
    MONITOR_GREEN,
    MONITOR_RED,
    glow_filter,
    header_block,
    save,
    svg_document,
)
from sqlalchemy import text as sqltext

from src.analytics.cohort_builder import CohortBuilder
from src.analytics.predefined_cohorts import OPIOID_LADDER_TERMS, run_all

builder = CohortBuilder()
results = run_all(builder)
result = results["opioid_escalation"]

sample_ids = (
    result.members.sort_values(["highest_rung", "span_days"], ascending=[False, True])
    ["person_id"].head(14).tolist()
)
person_list = ",".join(str(p) for p in sample_ids)
drug_terms = "|".join(OPIOID_LADDER_TERMS)

with builder.engine.connect() as conn:
    events = pd.read_sql(sqltext(f"""
        SELECT de.person_id, c.concept_name AS drug_name,
               de.drug_exposure_start_date AS start_date, de.drug_exposure_end_date AS end_date
        FROM cdm.drug_exposure de
        JOIN cdm.concept c ON c.concept_id = de.drug_concept_id
        WHERE de.person_id IN ({person_list})
          AND regexp_matches(lower(c.concept_name), '{drug_terms}')
        ORDER BY de.person_id, de.drug_exposure_start_date
    """), conn)

events["start_date"] = pd.to_datetime(events["start_date"])
events["end_date"] = pd.to_datetime(events["end_date"])
patient_start = events.groupby("person_id")["start_date"].transform("min")
events["day_offset"] = (events["start_date"] - patient_start).dt.days
events["duration"] = (events["end_date"] - events["start_date"]).dt.days.clip(lower=1)
events["drug_lower"] = events["drug_name"].str.lower()

# Rung 0 (codeine) -> rung 3 (fentanyl): both spike amplitude and color ramp
# from cool/mild to hot/dangerous, so climbing the ladder reads as the trace
# getting taller and hotter, not just a color swap on an otherwise flat mark.
rung_order = [t.lower() for t in OPIOID_LADDER_TERMS]
rung_color = {rung_order[0]: MONITOR_CYAN, rung_order[1]: MONITOR_GREEN,
              rung_order[2]: MONITOR_AMBER, rung_order[3]: MONITOR_RED}
rung_amp = {rung_order[0]: 0.40, rung_order[1]: 0.60, rung_order[2]: 0.80, rung_order[3]: 1.00}


def _spike_path(x: float, y: float, height: float, width: float = 7) -> str:
    """A single QRS-style blip, not a full beat — one drug event, one spike."""
    return (
        f"M {x-width:.1f},{y:.1f} L {x-width*0.35:.1f},{y:.1f} "
        f"L {x-width*0.15:.1f},{y+height*0.22:.1f} L {x:.1f},{y-height:.1f} "
        f"L {x+width*0.15:.1f},{y+height*0.28:.1f} L {x+width*0.35:.1f},{y:.1f} "
        f"L {x+width:.1f},{y:.1f}"
    )


W, H = 1300, 900
defs = "".join(glow_filter(f"rung_glow_{r}", c, 3.5) for r, c in rung_color.items())

body = header_block(
    "OPIOID DOSE ESCALATION",
    "Sample patient telemetry, aligned to each patient's first opioid exposure — day 0, not the calendar",
    W,
)

# Legend — color is the only encoding for which rung, so it gets a proper key.
legend_y = 160
legend_x = 48
for i, rung in enumerate(rung_order):
    lx = legend_x + i * 230
    body += f'<circle cx="{lx}" cy="{legend_y}" r="5" fill="{rung_color[rung]}" filter="url(#rung_glow_{rung})"/>'
    body += (
        f'<text x="{lx+14}" y="{legend_y+4}" font-family="{FONT_BODY}" font-size="13" '
        f'fill="{INK_DIM}">{rung.capitalize()}</text>'
    )
body += (
    f'<text x="{W-48}" y="{legend_y+4}" font-family="{FONT_BODY}" font-size="12.5" fill="{INK_FAINT}" '
    f'text-anchor="end">spike height = potency · bar length = days on drug</text>'
)

row_y0 = 210
row_h = 42
trace_x0, trace_x1 = 250, W - 48
trace_w = trace_x1 - trace_x0
day_max = 190

# Day-axis gridlines behind every row, ticked every 30 days.
grid_top, grid_bottom = row_y0 - 14, row_y0 + len(sample_ids) * row_h - 4
for day in range(0, day_max + 1, 30):
    gx = trace_x0 + day / day_max * trace_w
    body += f'<line x1="{gx:.1f}" y1="{grid_top}" x2="{gx:.1f}" y2="{grid_bottom}" stroke="{GRID}" stroke-width="1"/>'
    body += (
        f'<text x="{gx:.1f}" y="{grid_bottom+22}" font-family="{FONT_MONO}" font-size="11" '
        f'fill="{INK_FAINT}" text-anchor="middle">{day}d</text>'
    )

for i, pid in enumerate(sample_ids):
    y = row_y0 + i * row_h + row_h / 2
    body += f'<text x="{trace_x0-16}" y="{y+4}" font-family="{FONT_MONO}" font-size="12.5" fill="{INK_DIM}" text-anchor="end">PT-{i+1:02d}</text>'
    body += f'<line x1="{trace_x0}" y1="{y:.1f}" x2="{trace_x1}" y2="{y:.1f}" stroke="{GRID_STRONG}" stroke-width="1"/>'

    sub = events[events["person_id"] == pid].sort_values("day_offset")
    for _, ev in sub.iterrows():
        rung = ev["drug_lower"]
        color = rung_color[rung]
        x0 = trace_x0 + ev["day_offset"] / day_max * trace_w
        x1 = trace_x0 + (ev["day_offset"] + ev["duration"]) / day_max * trace_w
        body += f'<line x1="{x0:.1f}" y1="{y:.1f}" x2="{x1:.1f}" y2="{y:.1f}" stroke="{color}" stroke-width="3" stroke-linecap="round" opacity="0.35"/>'
        height = 8 + 16 * rung_amp[rung]
        body += f'<path d="{_spike_path(x0, y, height)}" stroke="{color}" stroke-width="1.8" fill="none" filter="url(#rung_glow_{rung})"/>'

body += (
    f'<text x="48" y="{H - 42}" font-family="{FONT_BODY}" font-size="12.5" fill="{INK_FAINT}">'
    "The pattern is consistent across the sample — codeine, then hydrocodone, then oxycodone, then fentanyl,"
    "</text>"
)
body += (
    f'<text x="48" y="{H - 24}" font-family="{FONT_BODY}" font-size="12.5" fill="{INK_FAINT}">'
    "roughly 30–45 days apart, exactly the ladder scripts/demo_codes.py defines and the generator seeds."
    "</text>"
)

svg = svg_document(W, H, body, defs)
save(svg, "opioid_escalation_timeline", W, H)
