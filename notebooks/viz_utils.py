"""Shared palette and export helpers for the visualization notebooks.

The palette here isn't picked by eye — it's the validated default from this
project's dataviz skill (references/palette.md): eight categorical hues
ordered specifically so adjacent series clear a colorblind-safety floor
(CVD Delta-E >= 8 in OKLab), a status set reserved for pass/fail states so it
never doubles as a series color, and a single-hue sequential ramp for
magnitude. Every notebook in this directory imports from here rather than
picking its own colors, so a chart in one notebook and a chart in another
read as the same visual system.
"""

from pathlib import Path

import plotly.graph_objects as go
import plotly.io as pio

# Categorical — fixed order, never cycled or reassigned per-filter.
CATEGORICAL = {
    "blue": "#2a78d6",
    "orange": "#eb6834",
    "aqua": "#1baf7a",
    "yellow": "#eda100",
    "magenta": "#e87ba4",
    "green": "#008300",
    "violet": "#4a3aa7",
    "red": "#e34948",
}
CATEGORICAL_ORDER = list(CATEGORICAL.values())

# Status — reserved; never reused as a categorical series color.
STATUS = {
    "good": "#0ca30c",
    "warning": "#fab219",
    "serious": "#ec835a",
    "critical": "#d03b3b",
}

# Sequential — single hue (blue), light to dark, for continuous magnitude.
SEQUENTIAL_BLUE = ["#cde2fb", "#9ec5f4", "#5598e7", "#2a78d6", "#1c5cab", "#0d366b"]

# Chart chrome
INK_PRIMARY = "#0b0b0b"
INK_SECONDARY = "#52514e"
INK_MUTED = "#898781"
GRIDLINE = "#e1e0d9"
SURFACE = "#fcfcfb"

FONT_FAMILY = "system-ui, -apple-system, 'Segoe UI', sans-serif"

ASSETS_DIR = Path(__file__).resolve().parents[1] / "docs" / "assets" / "visualizations"


def apply_layout_defaults(fig: go.Figure, title: str, subtitle: str | None = None) -> go.Figure:
    """Apply the shared chrome — font, ink, gridlines, surface — every chart
    in this project uses, so layout choices live in one place, not five."""
    full_title = title if not subtitle else f"{title}<br><sup style='color:{INK_SECONDARY}'>{subtitle}</sup>"
    fig.update_layout(
        title=dict(text=full_title, font=dict(size=18, color=INK_PRIMARY, family=FONT_FAMILY), x=0.02, xanchor="left"),
        font=dict(family=FONT_FAMILY, color=INK_SECONDARY, size=13),
        plot_bgcolor=SURFACE,
        paper_bgcolor=SURFACE,
        margin=dict(t=80, l=60, r=40, b=60),
    )
    fig.update_xaxes(gridcolor=GRIDLINE, zeroline=False, linecolor=GRIDLINE, tickfont=dict(color=INK_MUTED))
    fig.update_yaxes(gridcolor=GRIDLINE, zeroline=False, linecolor=GRIDLINE, tickfont=dict(color=INK_MUTED))
    return fig


def save_chart(fig: go.Figure, name: str, width: int = 1000, height: int = 600) -> None:
    """Export a figure as both interactive HTML and static PNG into
    docs/assets/visualizations/ — BUILD_NOTES's own visualization standard for
    this project: reproducible from code, not a manually-saved screenshot,
    and available in both forms for the README to embed."""
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    html_path = ASSETS_DIR / f"{name}.html"
    png_path = ASSETS_DIR / f"{name}.png"
    pio.write_html(fig, html_path, include_plotlyjs="cdn", full_html=True)
    pio.write_image(fig, png_path, width=width, height=height, scale=2)
    print(f"Saved {html_path.relative_to(ASSETS_DIR.parents[2])} and {png_path.relative_to(ASSETS_DIR.parents[2])}")
