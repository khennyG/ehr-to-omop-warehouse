import sys
sys.path.insert(0, "notebooks")
sys.path.insert(0, ".")
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine, text
from src.config.settings import settings
from dope_viz import (
    FONT_BODY, FONT_HEAD, FONT_MONO, GRID, GRID_STRONG, INK, INK_DIM, INK_FAINT,
    MONITOR_BLUE, MONITOR_VIOLET, glow_filter, header_block, save, svg_document,
)

settings.duckdb_path = Path("data/processed/omop_demo.duckdb")
engine = create_engine(settings.database_url)
with engine.connect() as conn:
    person = pd.read_sql(text("SELECT gender_concept_id, year_of_birth FROM cdm.person"), conn)

REFERENCE_YEAR = 2026
person["age"] = REFERENCE_YEAR - person["year_of_birth"]

bands = [(0, 17), (18, 29), (30, 39), (40, 49), (50, 59), (60, 69), (70, 79), (80, 120)]
band_labels = ["0-17", "18-29", "30-39", "40-49", "50-59", "60-69", "70-79", "80+"]


def band_of(age):
    for (lo, hi), label in zip(bands, band_labels):
        if lo <= age <= hi:
            return label
    return band_labels[-1]


person["age_band"] = person["age"].apply(band_of)
person["gender"] = person["gender_concept_id"].map({8507: "Male", 8532: "Female"}).fillna("Unknown")
counts = person.groupby(["age_band", "gender"]).size().unstack(fill_value=0).reindex(band_labels)

MALE_COLOR, FEMALE_COLOR = MONITOR_BLUE, MONITOR_VIOLET
under_18_pct = (person["age"] < 18).mean() * 100

W, H = 1150, 800
defs = glow_filter("male_glow", MALE_COLOR, 3) + glow_filter("female_glow", FEMALE_COLOR, 3)

body = header_block(
    "POPULATION VITALS",
    f"Age and sex distribution, {len(person):,}-patient demo population — the generator's own sampling weights, read back out",
    W,
)

# Legend
body += f'<circle cx="48" cy="162" r="6" fill="{MALE_COLOR}" filter="url(#male_glow)"/>'
body += f'<text x="62" y="167" font-family="{FONT_BODY}" font-size="13" fill="{INK_DIM}">Male</text>'
body += f'<circle cx="130" cy="162" r="6" fill="{FEMALE_COLOR}" filter="url(#female_glow)"/>'
body += f'<text x="144" y="167" font-family="{FONT_BODY}" font-size="13" fill="{INK_DIM}">Female</text>'

cx = W / 2
gap = 46
max_count = int(counts.values.max())
tick_max = 320
half_width = W / 2 - 48 - gap
scale = half_width / tick_max

row_y0 = 220
row_h = 56

# Tick gridlines, mirrored either side of the axis.
for t in range(0, tick_max + 1, 100):
    for side in (-1, 1):
        gx = cx + side * (gap + t * scale)
        body += f'<line x1="{gx:.1f}" y1="{row_y0-16}" x2="{gx:.1f}" y2="{row_y0 + len(band_labels)*row_h}" stroke="{GRID}" stroke-width="1"/>'
        body += (
            f'<text x="{gx:.1f}" y="{row_y0 + len(band_labels)*row_h + 24}" font-family="{FONT_MONO}" '
            f'font-size="11" fill="{INK_FAINT}" text-anchor="middle">{t}</text>'
        )

body += f'<line x1="{cx}" y1="{row_y0-16}" x2="{cx}" y2="{row_y0 + len(band_labels)*row_h}" stroke="{GRID_STRONG}" stroke-width="1.5"/>'

for i, band in enumerate(band_labels):
    y = row_y0 + i * row_h + row_h / 2
    male_n = int(counts.loc[band, "Male"]) if "Male" in counts.columns else 0
    female_n = int(counts.loc[band, "Female"]) if "Female" in counts.columns else 0

    male_w = male_n * scale
    body += (
        f'<rect x="{cx-gap-male_w:.1f}" y="{y-14}" width="{male_w:.1f}" height="28" rx="4" '
        f'fill="{MALE_COLOR}" opacity="0.85" filter="url(#male_glow)"/>'
    )
    body += (
        f'<text x="{cx-gap-male_w-10:.1f}" y="{y+5}" font-family="{FONT_MONO}" font-size="13" '
        f'fill="{INK}" text-anchor="end">{male_n}</text>'
    )

    female_w = female_n * scale
    body += (
        f'<rect x="{cx+gap:.1f}" y="{y-14}" width="{female_w:.1f}" height="28" rx="4" '
        f'fill="{FEMALE_COLOR}" opacity="0.85" filter="url(#female_glow)"/>'
    )
    body += (
        f'<text x="{cx+gap+female_w+10:.1f}" y="{y+5}" font-family="{FONT_MONO}" font-size="13" '
        f'fill="{INK}" text-anchor="start">{female_n}</text>'
    )

    body += (
        f'<text x="{cx:.1f}" y="{y+4}" font-family="{FONT_HEAD}" font-size="13" fill="{INK_DIM}" '
        f'text-anchor="middle">{band}</text>'
    )

# Editorial callout on the youngest band — this is the number the chart
# exists to confirm, so it gets pointed to explicitly rather than left for
# the reader to notice on their own. Centered above the axis and connected
# by a short straight drop, so it never depends on how long the bars happen
# to run (a leader line anchored to a bar's outer edge migrates off-canvas
# whenever that bar is the longest one in the chart).
body += (
    f'<text x="{cx:.1f}" y="190" font-family="{FONT_BODY}" font-size="12.5" fill="{INK_DIM}" '
    f'text-anchor="middle">{under_18_pct:.1f}% of the cohort is under 18 — close to AGE_BANDS\' 22% weight for that band</text>'
)
body += f'<line x1="{cx:.1f}" y1="196" x2="{cx:.1f}" y2="{row_y0-16}" stroke="{INK_FAINT}" stroke-width="1"/>'

body += (
    f'<text x="48" y="{H - 24}" font-family="{FONT_MONO}" font-size="11.5" fill="{INK_FAINT}">'
    "scripts/generate_demo_data.py · AGE_BANDS"
    "</text>"
)

svg = svg_document(W, H, body, defs)
save(svg, "population_pyramid", W, H)
