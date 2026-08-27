"""A bespoke chart system, not a Plotly theme.

The first version of these charts used Plotly's default forms — a Sankey, a
heatmap, a funnel, a Gantt bar, a population pyramid — reskinned with a
validated color palette. They were accurate and readable, and they looked
like every other data-journalism chart built the same way, because that's
what those forms are: correct, general-purpose, and generic.

The Pudding's own writing on this (a multi-part guide literally called "How
to Make Dope Shit") keeps landing on the same idea from different angles:
the chart form should come from the subject, not from a library's chart-type
picker. Their "plum pudding chart" is a circular waffle chart shaped like
their own name; a story about pocket-size inequality uses pocket-shaped
marks. The chart *is* the metaphor, not a neutral container the data gets
poured into.

This project is about a health data warehouse, so the visual system here is
built around the one shape that already means "this is about a patient's
vitals" to anyone who has ever been in a hospital: an EKG trace. Every chart
below is hand-built SVG, not a chart-library default — the waveform, the
gauge arcs, the monitor-grid background are all real geometry computed here,
and in three of the five charts the waveform's shape isn't decorative at
all, it's how the actual data is encoded (amplitude, spacing, and glow
respond to real numbers pulled from the demo warehouse).

Rendered via cairosvg — no browser, no Observable account, just SVG this
module builds by hand and rasterizes directly to PNG. Every number drawn is
still pulled from the same real DuckDB warehouse the first version read
from; only the drawing changed.
"""

import math
from pathlib import Path

import cairosvg

# ── Palette: a clinical monitor, not a slide deck ──────────────────────────
# Near-black monitor surface, phosphor-style signal colors. Chosen to look
# like an actual patient monitor display, not a reskinned default chart.
BG = "#0a0e14"
BG_PANEL = "#0d1220"
GRID = "#1a2233"
GRID_STRONG = "#232d42"
INK = "#eef2ff"
INK_DIM = "#8b96b3"
INK_FAINT = "#4a5570"

MONITOR_GREEN = "#00e5a0"
MONITOR_AMBER = "#ffb020"
MONITOR_RED = "#ff4d5e"
MONITOR_BLUE = "#4da3ff"
MONITOR_VIOLET = "#b48cff"
MONITOR_CYAN = "#3ddbd9"

FONT_HEAD = "Georgia, 'Times New Roman', serif"
FONT_MONO = "Menlo, 'SF Mono', Consolas, monospace"
FONT_BODY = "'Helvetica Neue', Helvetica, Arial, sans-serif"


def glow_filter(id_: str, color: str, strength: float = 4) -> str:
    """A filter def that makes a stroke look like it's actually emitting
    light on a monitor, not just drawn in a bright color."""
    return f'''<filter id="{id_}" x="-50%" y="-50%" width="200%" height="200%">
        <feGaussianBlur stdDeviation="{strength}" result="blur"/>
        <feMerge>
            <feMergeNode in="blur"/>
            <feMergeNode in="SourceGraphic"/>
        </feMerge>
    </filter>'''


def ekg_waveform_path(
    x0: float, y: float, width: float, n_beats: int,
    amplitude: float = 1.0, jitter_seed: int = 0,
) -> str:
    """A parametric PQRST-complex path — the actual EKG trace shape, not an
    abstract squiggle. amplitude scales the R-wave spike height, which is
    how this function doubles as a real data encoder elsewhere in this
    module (a flatter trace reads as "less signal" the same way it would on
    a real monitor).
    """
    beat_width = width / n_beats
    points = []
    rng_state = jitter_seed

    def _jitter(scale):
        nonlocal rng_state
        rng_state = (rng_state * 1103515245 + 12345) & 0x7FFFFFFF
        return ((rng_state / 0x7FFFFFFF) - 0.5) * scale

    x = x0
    points.append((x, y))
    for _beat in range(n_beats):
        bx = x
        # P wave (small bump), PR segment, QRS complex (the spike), ST segment, T wave
        p_w = beat_width * 0.10
        points.append((bx + p_w * 0.5, y - 4 * amplitude + _jitter(1)))
        points.append((bx + p_w, y))
        qrs_x = bx + beat_width * 0.32
        points.append((qrs_x - 4, y))
        points.append((qrs_x - 2, y + 8 * amplitude))
        points.append((qrs_x, y - 42 * amplitude + _jitter(2)))
        points.append((qrs_x + 3, y + 14 * amplitude))
        points.append((qrs_x + 7, y))
        t_x = bx + beat_width * 0.62
        points.append((t_x, y - 10 * amplitude + _jitter(1.5)))
        points.append((t_x + p_w * 1.3, y))
        points.append((bx + beat_width, y))
        x = bx + beat_width

    d = f"M {points[0][0]:.1f},{points[0][1]:.1f} "
    d += " ".join(f"L {px:.1f},{py:.1f}" for px, py in points[1:])
    return d


def flatline_decay_path(x0: float, y: float, width: float, n_beats: int, decay: list) -> str:
    """Like ekg_waveform_path, but each beat's amplitude is set explicitly
    from `decay` (one value per beat, 0..1) — this is the literal encoding
    used for the attrition chart: each heartbeat *is* one funnel step, and
    the trace visibly flattens as the cohort narrows."""
    beat_width = width / n_beats
    points = [(x0, y)]
    x = x0
    for i in range(n_beats):
        amp = decay[i]
        bx = x
        qrs_x = bx + beat_width * 0.32
        p_w = beat_width * 0.10
        points.append((bx + p_w * 0.5, y - 3 * amp))
        points.append((bx + p_w, y))
        points.append((qrs_x - 4, y))
        points.append((qrs_x - 2, y + 6 * amp))
        points.append((qrs_x, y - 40 * amp))
        points.append((qrs_x + 3, y + 12 * amp))
        points.append((qrs_x + 7, y))
        t_x = bx + beat_width * 0.62
        points.append((t_x, y - 8 * amp))
        points.append((t_x + p_w * 1.3, y))
        points.append((bx + beat_width, y))
        x = bx + beat_width
    d = f"M {points[0][0]:.1f},{points[0][1]:.1f} "
    d += " ".join(f"L {px:.1f},{py:.1f}" for px, py in points[1:])
    return d


def gauge_arc(cx: float, cy: float, r: float, frac: float, span_deg: float = 270) -> str:
    """An SVG arc path for a gauge dial, sweeping clockwise from the
    bottom-left. frac=1.0 draws the full span_deg arc; frac=0.5 draws half
    of it — this is the needle-free, filled-arc style real vitals monitors
    use for a percentage readout.
    """
    start_deg = 90 + (360 - span_deg) / 2  # bottom-left start
    sweep_deg = span_deg * max(0.0001, min(1.0, frac))
    end_deg = start_deg + sweep_deg
    start_rad, end_rad = math.radians(start_deg), math.radians(end_deg)
    x1, y1 = cx + r * math.cos(start_rad), cy + r * math.sin(start_rad)
    x2, y2 = cx + r * math.cos(end_rad), cy + r * math.sin(end_rad)
    large_arc = 1 if sweep_deg > 180 else 0
    return f"M {x1:.2f},{y1:.2f} A {r},{r} 0 {large_arc} 1 {x2:.2f},{y2:.2f}"


def monitor_grid(x: float, y: float, w: float, h: float, spacing: int = 24) -> str:
    """The faint graph-paper grid every EKG monitor and printout has."""
    lines = []
    xi = x
    while xi <= x + w:
        lines.append(f'<line x1="{xi:.1f}" y1="{y}" x2="{xi:.1f}" y2="{y+h}" stroke="{GRID}" stroke-width="1"/>')
        xi += spacing
    yi = y
    while yi <= y + h:
        lines.append(f'<line x1="{x}" y1="{yi:.1f}" x2="{x+w}" y2="{yi:.1f}" stroke="{GRID}" stroke-width="1"/>')
        yi += spacing
    return "\n".join(lines)


def header_block(title: str, subtitle: str, width: float, tag: str = "OMOP-CDM") -> str:
    """Consistent masthead across every chart in this set — a monitor-style
    corner tag, a serif headline, a monospace subtitle line."""
    return f'''
    <text x="48" y="52" font-family="{FONT_MONO}" font-size="12" letter-spacing="3" fill="{MONITOR_GREEN}">{tag}</text>
    <text x="{width - 48}" y="52" font-family="{FONT_MONO}" font-size="12" fill="{INK_FAINT}" text-anchor="end">SYNTHETIC DEMO DATA</text>
    <text x="48" y="92" font-family="{FONT_HEAD}" font-size="30" font-weight="bold" fill="{INK}">{title}</text>
    <text x="48" y="118" font-family="{FONT_BODY}" font-size="14" fill="{INK_DIM}">{subtitle}</text>
    <line x1="48" y1="136" x2="{width - 48}" y2="136" stroke="{GRID_STRONG}" stroke-width="1"/>
    '''


def svg_document(width: int, height: int, body: str, defs: str = "") -> str:
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
    <defs>{defs}</defs>
    <rect width="{width}" height="{height}" fill="{BG}"/>
    {body}
    </svg>'''


ASSETS_DIR = Path(__file__).resolve().parents[1] / "docs" / "assets" / "visualizations"


def save(svg_content: str, name: str, width: int, height: int) -> None:
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    svg_path = ASSETS_DIR / f"{name}.svg"
    png_path = ASSETS_DIR / f"{name}.png"
    svg_path.write_text(svg_content)
    cairosvg.svg2png(
        bytestring=svg_content.encode(), write_to=str(png_path),
        output_width=width * 2, output_height=height * 2,  # 2x for crisp GitHub rendering
    )
    print(f"Saved docs/assets/visualizations/{name}.svg and {name}.png")
