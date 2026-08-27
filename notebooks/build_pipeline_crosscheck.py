import sys

sys.path.insert(0, "notebooks")
sys.path.insert(0, ".")
import duckdb
from dope_viz import (
    FONT_BODY,
    FONT_MONO,
    GRID_STRONG,
    INK,
    INK_DIM,
    INK_FAINT,
    MONITOR_BLUE,
    MONITOR_CYAN,
    MONITOR_GREEN,
    MONITOR_RED,
    ekg_waveform_path,
    glow_filter,
    header_block,
    save,
    svg_document,
)

con = duckdb.connect("data/processed/omop_demo.duckdb")

# The tables both implementations actually build — src/transform/ populates
# the full OMOP schema, dbt/models/marts/ covers this subset (see ADR 0002).
tables = ["person", "visit_occurrence", "condition_occurrence", "drug_exposure", "measurement"]

rows = []
for i, table in enumerate(tables):
    pandas_n = con.execute(f"select count(*) from cdm.{table}").fetchone()[0]
    dbt_n = con.execute(f"select count(*) from cdm_dbt.{table}").fetchone()[0]
    rows.append((table, pandas_n, dbt_n, pandas_n == dbt_n))

W, H = 1200, 780
defs = (
    glow_filter("pandas_glow", MONITOR_BLUE, 3)
    + glow_filter("dbt_glow", MONITOR_CYAN, 3)
    + glow_filter("match_glow", MONITOR_GREEN, 4)
    + glow_filter("mismatch_glow", MONITOR_RED, 4)
)

body = header_block(
    "PIPELINE CROSS-CHECK",
    "Two independent OMOP builds against the same warehouse, read back side by side — pandas (src/transform/) and dbt (dbt/models/marts/)",
    W,
)

# Legend
body += f'<circle cx="48" cy="162" r="6" fill="{MONITOR_BLUE}" filter="url(#pandas_glow)"/>'
body += f'<text x="62" y="167" font-family="{FONT_BODY}" font-size="13" fill="{INK_DIM}">pandas (cdm.*)</text>'
body += f'<circle cx="220" cy="162" r="6" fill="{MONITOR_CYAN}" filter="url(#dbt_glow)"/>'
body += f'<text x="234" y="167" font-family="{FONT_BODY}" font-size="13" fill="{INK_DIM}">dbt (cdm_dbt.*)</text>'
body += (
    f'<text x="{W-48}" y="167" font-family="{FONT_BODY}" font-size="12.5" fill="{INK_FAINT}" '
    f'text-anchor="end">identical trace, traced twice — agreement, not magnitude</text>'
)

row_y0 = 210
row_h = 100

for i, (table, pandas_n, dbt_n, is_match) in enumerate(rows):
    y = row_y0 + i * row_h + row_h / 2
    body += f'<text x="48" y="{y-6}" font-family="{FONT_MONO}" font-size="15" fill="{INK}">{table}</text>'
    body += f'<text x="48" y="{y+14}" font-family="{FONT_BODY}" font-size="11" fill="{INK_FAINT}">cdm.{table} · cdm_dbt.{table}</text>'

    # Two traces of the same waveform (same jitter seed), one nudged 2px
    # down — if the two pipelines agree, both colors peek out along the
    # same line instead of resolving into a single trace.
    trace_x0, trace_w = 340, 420
    wave = ekg_waveform_path(trace_x0, y, trace_w, 1, amplitude=1.0, jitter_seed=i * 7)
    body += f'<path d="{wave}" stroke="{MONITOR_BLUE}" stroke-width="2" fill="none" opacity="0.85" filter="url(#pandas_glow)"/>'
    wave2 = ekg_waveform_path(trace_x0, y + 2, trace_w, 1, amplitude=1.0, jitter_seed=i * 7)
    body += f'<path d="{wave2}" stroke="{MONITOR_CYAN}" stroke-width="2" fill="none" opacity="0.85" filter="url(#dbt_glow)"/>'

    body += (
        f'<text x="{trace_x0 + trace_w + 24}" y="{y-4}" font-family="{FONT_MONO}" font-size="16" '
        f'font-weight="bold" fill="{MONITOR_BLUE}" text-anchor="end">{pandas_n:,}</text>'
    )
    body += (
        f'<text x="{trace_x0 + trace_w + 24}" y="{y+18}" font-family="{FONT_MONO}" font-size="16" '
        f'font-weight="bold" fill="{MONITOR_CYAN}" text-anchor="end">{dbt_n:,}</text>'
    )

    badge_x = trace_x0 + trace_w + 140
    color, glow, label = (MONITOR_GREEN, "match_glow", "MATCH") if is_match else (MONITOR_RED, "mismatch_glow", "DIFFERS")
    body += f'<rect x="{badge_x}" y="{y-16}" width="108" height="32" rx="16" fill="none" stroke="{color}" stroke-width="1.5" filter="url(#{glow})"/>'
    body += f'<circle cx="{badge_x+20}" cy="{y}" r="4" fill="{color}" filter="url(#{glow})"/>'
    body += f'<text x="{badge_x+34}" y="{y+5}" font-family="{FONT_MONO}" font-size="13" fill="{color}" letter-spacing="1">{label}</text>'

    if i < len(rows) - 1:
        body += f'<line x1="48" y1="{row_y0 + (i+1) * row_h - 12}" x2="{W-48}" y2="{row_y0 + (i+1) * row_h - 12}" stroke="{GRID_STRONG}" stroke-width="1" opacity="0.5"/>'

n_match = sum(1 for r in rows if r[3])
body += (
    f'<text x="48" y="{H - 42}" font-family="{FONT_BODY}" font-size="12.5" fill="{INK_FAINT}">'
    f"{n_match} of {len(rows)} tables match exactly — the same warehouse, transformed twice by unrelated code paths,"
    "</text>"
)
body += (
    f'<text x="48" y="{H - 24}" font-family="{FONT_BODY}" font-size="12.5" fill="{INK_FAINT}">'
    "landing on the same row counts every time. See ADR 0002 for why dbt exists as a second build, not a shared writer."
    "</text>"
)

svg = svg_document(W, H, body, defs)
save(svg, "pipeline_crosscheck", W, H)
