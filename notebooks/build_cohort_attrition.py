import sys

sys.path.insert(0, "notebooks")
sys.path.insert(0, ".")
from dope_viz import (
    FONT_BODY,
    FONT_MONO,
    GRID,
    INK,
    INK_DIM,
    INK_FAINT,
    MONITOR_AMBER,
    MONITOR_GREEN,
    MONITOR_VIOLET,
    flatline_decay_path,
    glow_filter,
    header_block,
    save,
    svg_document,
)

from src.analytics.cohort_builder import CohortBuilder
from src.analytics.predefined_cohorts import run_all

builder = CohortBuilder()
results = run_all(builder)

titles = {
    "diabetes_complications": ("DIABETES", "CARDIOVASCULAR EVENT"),
    "opioid_escalation": ("OPIOID DOSE ESCALATION", None),
    "polypharmacy_elderly": ("POLYPHARMACY (65+)", None),
}
colors = {
    "diabetes_complications": MONITOR_GREEN,
    "opioid_escalation": MONITOR_AMBER,
    "polypharmacy_elderly": MONITOR_VIOLET,
}


def _shorten(label, max_len=48):
    return label if len(label) <= max_len else label[: max_len - 1] + "…"


W, H = 1300, 850
defs = "".join(glow_filter(f"trace_glow_{i}", c, 5) for i, c in enumerate(colors.values()))

body = header_block(
    "COHORT ATTRITION",
    "Each inclusion criterion as one heartbeat — amplitude tracks the surviving population, not a decoration",
    W,
)

row_h = 190
row_y0 = 190

for row_i, (name, result) in enumerate(results.items()):
    attrition = result.attrition
    counts = [s["count"] for s in attrition]
    max_count = counts[0]
    decay = [c / max_count for c in counts]
    color = colors[name]
    y = row_y0 + row_i * row_h + 70

    left, right = titles[name]
    title_y = y - 45
    if right is None:
        body += f'<text x="48" y="{title_y}" font-family="{FONT_BODY}" font-size="15" letter-spacing="1.5" fill="{color}" font-weight="bold">{left}</text>'
    else:
        # Two segments joined by a hand-drawn chevron instead of a Unicode
        # arrow glyph — cairosvg's font fallback doesn't reliably carry
        # U+2192, so the connector is real geometry, same as every other
        # mark in this system.
        left_w = 12.2 * len(left)  # bold 15px caps, letter-spacing 1.5 — measured empirically
        body += (
            f'<text x="48" y="{title_y}" font-family="{FONT_BODY}" font-size="15" '
            f'letter-spacing="1.5" fill="{color}" font-weight="bold" '
            f'textLength="{left_w:.0f}" lengthAdjust="spacingAndGlyphs">{left}</text>'
        )
        arrow_x = 48 + left_w + 16
        body += (
            f'<path d="M {arrow_x:.1f},{title_y - 9} L {arrow_x + 9:.1f},{title_y - 4.5} '
            f'L {arrow_x:.1f},{title_y}" stroke="{color}" stroke-width="2" fill="none" '
            f'stroke-linecap="round" stroke-linejoin="round"/>'
        )
        right_x = arrow_x + 22
        body += (
            f'<text x="{right_x:.1f}" y="{title_y}" font-family="{FONT_BODY}" font-size="15" '
            f'letter-spacing="1.5" fill="{color}" font-weight="bold">{right}</text>'
        )
    body += f'<text x="{W - 48}" y="{title_y}" font-family="{FONT_MONO}" font-size="14" fill="{INK_DIM}" text-anchor="end">{result.total_count:,} / {max_count:,} FINAL</text>'

    trace_x0, trace_w = 48, W - 96
    path = flatline_decay_path(trace_x0, y, trace_w, len(attrition), decay)
    body += f'<path d="{path}" stroke="{color}" stroke-width="2.5" fill="none" filter="url(#trace_glow_{row_i})"/>'

    # Step markers + labels beneath each beat
    beat_w = trace_w / len(attrition)
    for i, step in enumerate(attrition):
        bx = trace_x0 + i * beat_w + beat_w * 0.32
        pct = 100 * step["count"] / max_count
        body += f'<circle cx="{bx:.1f}" cy="{y - 40 * decay[i]:.1f}" r="3.5" fill="{color}"/>'
        body += f'<text x="{bx:.1f}" y="{y + 34}" font-family="{FONT_MONO}" font-size="12" fill="{INK}" text-anchor="middle">{step["count"]:,}</text>'
        body += f'<text x="{bx:.1f}" y="{y + 50}" font-family="{FONT_MONO}" font-size="10.5" fill="{INK_DIM}" text-anchor="middle">{pct:.0f}%</text>'
        body += f'<text x="{bx:.1f}" y="{y + 70}" font-family="{FONT_BODY}" font-size="10.5" fill="{INK_FAINT}" text-anchor="middle">{_shorten(step["step"])}</text>'

    if row_i < len(results) - 1:
        body += f'<line x1="48" y1="{row_y0 + (row_i+1) * row_h - 10}" x2="{W-48}" y2="{row_y0 + (row_i+1) * row_h - 10}" stroke="{GRID}" stroke-width="1"/>'

body += f'<text x="48" y="{H - 22}" font-family="{FONT_MONO}" font-size="11.5" fill="{INK_FAINT}">src/analytics/cohort_builder.py · src/analytics/predefined_cohorts.py</text>'

svg = svg_document(W, H, body, defs)
save(svg, "cohort_attrition_waterfalls", W, H)
