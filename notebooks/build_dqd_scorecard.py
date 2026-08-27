import sys

sys.path.insert(0, "notebooks")
sys.path.insert(0, ".")
from dope_viz import (
    BG_PANEL,
    FONT_BODY,
    FONT_MONO,
    GRID_STRONG,
    INK,
    INK_DIM,
    INK_FAINT,
    MONITOR_AMBER,
    MONITOR_GREEN,
    MONITOR_RED,
    ekg_waveform_path,
    glow_filter,
    header_block,
    save,
    svg_document,
)

from src.quality.dqd_checks import DQDChecker

checker = DQDChecker()
checker.run_all()
df = checker.summary_dataframe()

pivot = df.pivot_table(index="table", columns="category", values="metric", aggfunc="mean")
category_order = ["completeness", "conformance", "plausibility", "temporal"]
table_order = ["person", "visit_occurrence", "condition_occurrence", "drug_exposure"]
pivot = pivot.reindex(index=table_order, columns=category_order)

W, H = 1200, 900
defs = "".join(glow_filter(f"cell_glow_{i}", c, 4) for i, c in enumerate([MONITOR_GREEN, MONITOR_AMBER, MONITOR_RED]))


def status_color(pct):
    if pct is None:
        return None
    if pct >= 0.95:
        return MONITOR_GREEN, 0
    if pct >= 0.80:
        return MONITOR_AMBER, 1
    return MONITOR_RED, 2


body = header_block(
    "DATA QUALITY SCORECARD",
    "OHDSI-style DQD checks against the loaded warehouse — mean pass rate by table and category",
    W,
)

grid_x, grid_y = 260, 190
cell_w, cell_h = 220, 120
gap = 16

# Column headers
for j, cat in enumerate(category_order):
    cx = grid_x + j * (cell_w + gap) + cell_w / 2
    body += f'<text x="{cx}" y="{grid_y - 20}" font-family="{FONT_BODY}" font-size="14" letter-spacing="1.5" fill="{INK_DIM}" text-anchor="middle" font-weight="bold">{cat.upper()}</text>'

for i, table in enumerate(table_order):
    ry = grid_y + i * (cell_h + gap)
    # Row label
    body += f'<text x="{grid_x - 24}" y="{ry + cell_h / 2 + 5}" font-family="{FONT_MONO}" font-size="14" fill="{INK}" text-anchor="end">{table}</text>'

    for j, cat in enumerate(category_order):
        cx = grid_x + j * (cell_w + gap)
        val = pivot.iloc[i, j]

        body += f'<rect x="{cx}" y="{ry}" width="{cell_w}" height="{cell_h}" rx="6" fill="{BG_PANEL}" stroke="{GRID_STRONG}" stroke-width="1"/>'

        if val != val:  # NaN — no checks defined for this combo
            body += f'<text x="{cx + cell_w/2}" y="{ry + cell_h/2 + 5}" font-family="{FONT_MONO}" font-size="13" fill="{INK_FAINT}" text-anchor="middle">— n/a —</text>'
            continue

        color, severity = status_color(val)
        pct = val * 100

        # A little pulse trace across the top of the card — flatter/lower
        # amplitude signals a worse reading, same encoding as the other
        # charts in this set, not just a color swap.
        amp = 0.4 + 0.6 * val
        wave = ekg_waveform_path(cx + 14, ry + 34, cell_w - 28, 2, amplitude=amp, jitter_seed=i * 10 + j)
        body += f'<path d="{wave}" stroke="{color}" stroke-width="1.8" fill="none" opacity="0.85" filter="url(#cell_glow_{severity})"/>'

        body += f'<text x="{cx + 16}" y="{ry + cell_h - 24}" font-family="{FONT_MONO}" font-size="30" font-weight="bold" fill="{INK}">{pct:.0f}<tspan font-size="16" fill="{INK_DIM}">%</tspan></text>'

        # Status dot
        body += f'<circle cx="{cx + cell_w - 18}" cy="{ry + cell_h - 32}" r="5" fill="{color}" filter="url(#cell_glow_{severity})"/>'

body += (
    f'<text x="48" y="{H - 68}" font-family="{FONT_BODY}" font-size="12.5" fill="{INK_FAINT}">'
    "condition_occurrence / completeness reads below 100% on purpose — condition_end_date is checked against"
    "</text>"
)
body += (
    f'<text x="48" y="{H - 48}" font-family="{FONT_BODY}" font-size="12.5" fill="{INK_FAINT}">'
    "a 30% threshold, not 99%, since most conditions in a real population are chronic or still active."
    "</text>"
)
body += f'<text x="48" y="{H - 22}" font-family="{FONT_MONO}" font-size="11.5" fill="{INK_FAINT}">src/quality/dqd_checks.py</text>'

svg = svg_document(W, H, body, defs)
save(svg, "dqd_scorecard_heatmap", W, H)
