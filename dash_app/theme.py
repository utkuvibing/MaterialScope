"""Theme tokens for Dash / Plotly styling (aligned with ``assets/style.css`` variables)."""

from __future__ import annotations

THEME_TOKENS: dict[str, dict[str, str]] = {
    "light": {
        "ink": "#1C1A1A",
        "muted": "#66645E",
        "border": "#E0DDD6",
        "panel": "#FFFFFF",
        "panel_strong": "#F7F6F3",
        "accent": "#EBDBB7",
        "accent_strong": "#D9C9A3",
        "accent_ink": "#1C1A1A",
        "bg_top": "#FFFFFF",
        "bg_bottom": "#FFFFFF",
        "sidebar_bg": "#1C1A1A",
        "sidebar_text": "#F2F0EB",
        "sidebar_muted": "#A8A59C",
        "input_bg": "#FFFFFF",
        "input_border": "#D4D1CA",
    },
    "dark": {
        "ink": "#EEEDEA",
        "muted": "#9E9A93",
        "border": "#3D3B38",
        "panel": "#1A1917",
        "panel_strong": "#22211E",
        "accent": "#CBB896",
        "accent_strong": "#B8A382",
        "accent_ink": "#121110",
        "bg_top": "#121110",
        "bg_bottom": "#121110",
        "sidebar_bg": "#1C1A1A",
        "sidebar_text": "#F2F0EB",
        "sidebar_muted": "#9E9A93",
        "input_bg": "#1A1917",
        "input_border": "#3D3B38",
    },
}

FONT_FAMILY = "'IBM Plex Sans', -apple-system, BlinkMacSystemFont, sans-serif"
MONO_FAMILY = "'IBM Plex Mono', 'Consolas', 'Monaco', monospace"

PLOT_THEME = {
    "light": {
        "template": "plotly_white",
        "text": "#1C1A1A",
        "paper_bg": "#FFFFFF",
        "plot_bg": "#FFFFFF",
        "grid": "#E0DDD6",
    },
    "dark": {
        "template": "plotly_dark",
        "text": "#EEEDEA",
        "paper_bg": "#1A1917",
        "plot_bg": "#121110",
        "grid": "#3D3B38",
    },
}


def normalize_ui_theme(theme: str | None) -> str:
    return theme if theme in ("light", "dark") else "light"


def apply_figure_theme(fig, theme: str | None) -> None:
    """Set paper/plot/font/legend and axis grid colors from ``PLOT_THEME`` (matches Dash CSS tokens)."""
    pt = PLOT_THEME[normalize_ui_theme(theme)]
    grid = pt["grid"]
    text = pt["text"]
    fig.update_layout(
        template=pt["template"],
        paper_bgcolor=pt["paper_bg"],
        plot_bgcolor=pt["plot_bg"],
        font=dict(color=text, family=FONT_FAMILY),
        title=dict(font=dict(color=text, family=FONT_FAMILY)),
        legend=dict(font=dict(color=text, size=12), bgcolor="rgba(0,0,0,0)"),
    )
    fig.update_xaxes(
        gridcolor=grid,
        showgrid=True,
        linecolor=grid,
        zerolinecolor=grid,
        tickfont=dict(color=text, size=12),
        title_font=dict(color=text, size=13),
    )
    fig.update_yaxes(
        gridcolor=grid,
        showgrid=True,
        linecolor=grid,
        zerolinecolor=grid,
        tickfont=dict(color=text, size=12),
        title_font=dict(color=text, size=13),
    )
