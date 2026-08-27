import sys
sys.path.insert(0, "notebooks")
sys.path.insert(0, ".")
import duckdb
from dope_viz import (
    FONT_BODY, FONT_MONO, INK, INK_DIM, INK_FAINT, MONITOR_CYAN, MONITOR_GREEN,
    MONITOR_RED, MONITOR_VIOLET, gauge_arc, glow_filter, header_block, save, svg_document,
)

con = duckdb.connect("data/processed/omop_demo.duckdb")

domains = [
    ("CONDITION", "condition_occurrence", "condition_concept_id", MONITOR_GREEN),
    ("DRUG", "drug_exposure", "drug_concept_id", MONITOR_CYAN),
    ("MEASUREMENT", "measurement", "measurement_concept_id", MONITOR_VIOLET),
]

rows = []
for label, table, col, color in domains:
    total = con.execute(f"select count(*) from cdm.{table}").fetchone()[0]
    unmapped = con.execute(f"select count(*) from cdm.{table} where {col} = 0").fetchone()[0]
    mapped = total - unmapped
    rows.append((label, mapped, total, color))

W, H = 1100, 560
defs = "".join(glow_filter(f"glow_{i}", c, 5) for i, (_, _, _, c) in enumerate(rows))

body = header_block(
    "VOCABULARY MAPPING COVERAGE",
    "Source codes resolved to standard OMOP concepts, by clinical domain — demo vocabulary seed",
    W,
)

gauge_y = 330
gauge_r = 130
centers = [230, 550, 870]

for i, (label, mapped, total, color) in enumerate(rows):
    cx = centers[i]
    frac = mapped / total
    pct = 100 * frac

    # Track is the "unmapped" zone, in red so a small gap still reads as a
    # gap at a glance instead of disappearing into the dark background —
    # the filled reading draws on top of it.
    body += f'<path d="{gauge_arc(cx, gauge_y, gauge_r, 1.0)}" stroke="{MONITOR_RED}" stroke-width="14" fill="none" stroke-linecap="round" opacity="0.45"/>'
    body += f'<path d="{gauge_arc(cx, gauge_y, gauge_r, frac)}" stroke="{color}" stroke-width="14" fill="none" stroke-linecap="round" filter="url(#glow_{i})"/>'

    # Center readout — monospace, monitor-digital style
    body += f'<text x="{cx - 14}" y="{gauge_y - 6}" font-family="{FONT_MONO}" font-size="46" font-weight="bold" fill="{INK}" text-anchor="middle">{pct:.1f}<tspan font-size="24" dx="2" fill="{INK_DIM}">%</tspan></text>'
    body += f'<text x="{cx}" y="{gauge_y + 28}" font-family="{FONT_MONO}" font-size="13" fill="{INK_DIM}" text-anchor="middle">{mapped:,} / {total:,}</text>'

    # Domain label below
    body += f'<text x="{cx}" y="{gauge_y + 100}" font-family="{FONT_BODY}" font-size="15" letter-spacing="2" fill="{color}" text-anchor="middle" font-weight="bold">{label}</text>'

# Footer note — two lines, not one shared baseline, so the disclaimer and
# the file-path tag never collide regardless of string length.
body += f'<text x="48" y="{H - 50}" font-family="{FONT_BODY}" font-size="12.5" fill="{INK_FAINT}">A demo-scale vocabulary seed deliberately omits a couple of source codes, so this reads as a real gap — not a manufactured 100%.</text>'
body += f'<text x="48" y="{H - 28}" font-family="{FONT_MONO}" font-size="11.5" fill="{INK_FAINT}">See docs/adr/0004-synthetic-demo-data-and-vocabulary.md · src/transform/vocabulary_mapper.py</text>'

svg = svg_document(W, H, body, defs)
save(svg, "vocabulary_mapping_sankey", W, H)
