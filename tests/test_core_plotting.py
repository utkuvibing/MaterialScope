import plotly.graph_objects as go
import math

from core import plotting


def test_normalize_plot_display_settings_swaps_ranges_and_clamps_export_scale():
    settings = plotting.normalize_plot_display_settings(
        {
            "legend_mode": "nonsense",
            "export_scale": 99,
            "x_range_enabled": True,
            "x_min": 4000,
            "x_max": 1000,
            "y_range_enabled": True,
            "y_min": 2,
            "y_max": -1,
        }
    )

    assert settings["legend_mode"] == "auto"
    assert settings["export_scale"] == 4
    assert settings["x_min"] == 1000.0
    assert settings["x_max"] == 4000.0
    assert settings["y_min"] == -1.0
    assert settings["y_max"] == 2.0


def test_build_plotly_config_applies_shared_export_filename_and_scale():
    config = plotting.build_plotly_config({"export_scale": 3}, filename="materialscope_demo")

    assert config["displaylogo"] is False
    assert config["responsive"] is True
    assert config["toImageButtonOptions"]["filename"] == "materialscope_demo"
    assert config["toImageButtonOptions"]["scale"] == 3
    assert config["toImageButtonOptions"]["width"] == plotting.DEFAULT_EXPORT_WIDTH


def test_apply_materialscope_plot_theme_records_result_mode_and_settings():
    fig = go.Figure(data=[go.Scatter(x=[1, 2], y=[3, 4], mode="lines", line={"width": 2})])

    plotting.apply_materialscope_plot_theme(
        fig,
        {
            "legend_mode": "hidden",
            "show_grid": False,
            "show_spikes": False,
            "line_width_scale": 1.5,
            "x_range_enabled": True,
            "x_min": 1,
            "x_max": 2,
        },
        theme="dark",
        title="Shared",
        view_mode="result",
    )

    assert fig.layout.template.layout.paper_bgcolor is not None
    assert fig.layout.paper_bgcolor == plotting.PLOT_THEME["dark"]["paper_bg"]
    assert fig.layout.showlegend is False
    assert fig.layout.xaxis.showgrid is False
    assert fig.layout.xaxis.showspikes is False
    assert list(fig.layout.xaxis.range) == [1.0, 2.0]
    assert float(fig.data[0].line.width) == 3.0
    assert fig.layout.meta["plot_view_mode"] == "result"
    assert fig.layout.meta["plot_display_settings"]["legend_mode"] == "hidden"


def test_apply_materialscope_plot_theme_debug_mode_forces_spikes():
    fig = go.Figure(data=[go.Scatter(x=[1, 2], y=[3, 4], mode="lines")])

    plotting.apply_materialscope_plot_theme(fig, {"show_spikes": False}, view_mode="debug")

    assert fig.layout.xaxis.showspikes is True
    assert fig.layout.yaxis.showspikes is True
    assert fig.layout.meta["plot_view_mode"] == "debug"


def test_extract_plot_display_settings_reads_figure_meta():
    fig = go.Figure()
    plotting.apply_materialscope_plot_theme(fig, {"export_scale": 4})

    extracted = plotting.extract_plot_display_settings(fig)

    assert extracted["export_scale"] == 4


def test_apply_materialscope_plot_theme_preserves_shapes_and_sets_contrast():
    fig = go.Figure(data=[go.Scatter(x=[1, 2], y=[3, 4], mode="lines")])
    fig.add_shape(type="line", x0=1, y0=3, x1=2, y1=4, line={"color": "#000000"})

    plotting.apply_materialscope_plot_theme(fig, theme="dark")

    assert len(fig.layout.shapes) == 1
    assert fig.layout.shapes[0].line.color == plotting.PLOT_THEME["dark"]["shape_line"]
    assert fig.layout.shapes[0].line.width >= 2
    assert fig.layout.newshape.line.color == plotting.PLOT_THEME["dark"]["shape_line"]


def test_apply_materialscope_plot_theme_recolors_materialscope_default_shape_colors():
    fig = go.Figure(data=[go.Scatter(x=[1, 2], y=[3, 4], mode="lines")])
    fig.add_shape(type="line", x0=1, y0=3, x1=2, y1=4, line={"color": "#1C1A1A"})

    plotting.apply_materialscope_plot_theme(fig, theme="dark")
    assert fig.layout.shapes[0].line.color == plotting.PLOT_THEME["dark"]["shape_line"]

    plotting.apply_materialscope_plot_theme(fig, theme="light")
    assert fig.layout.shapes[0].line.color == plotting.PLOT_THEME["light"]["shape_line"]


def test_apply_materialscope_plot_theme_preserves_custom_shape_color():
    fig = go.Figure(data=[go.Scatter(x=[1, 2], y=[3, 4], mode="lines")])
    fig.add_shape(type="line", x0=1, y0=3, x1=2, y1=4, line={"color": "rgba(148, 163, 184, 0.55)"})

    plotting.apply_materialscope_plot_theme(fig, theme="dark")

    assert len(fig.layout.shapes) == 1
    assert fig.layout.shapes[0].line.color == "rgba(148, 163, 184, 0.55)"


def test_apply_materialscope_plot_theme_uses_compact_export_layout():
    fig = go.Figure(data=[go.Scatter(x=[1, 2], y=[3, 4], mode="lines")])

    plotting.apply_materialscope_plot_theme(fig, title="Export", subtitle="Sample", for_export=True)

    assert fig.layout.width == plotting.DEFAULT_EXPORT_WIDTH
    assert fig.layout.height == plotting.DEFAULT_EXPORT_HEIGHT
    assert fig.layout.margin.b == 54
    assert fig.layout.margin.t <= 82


def test_primary_y_range_ignores_non_finite_values_and_pads():
    result = plotting.primary_y_range([1, 2, "bad"], [float("nan"), 3])

    assert result is not None
    assert result[0] < 1
    assert result[1] > 3


def test_primary_y_range_handles_numpy_like_iterables_without_truthiness():
    class ArrayLike:
        def __bool__(self):
            raise ValueError("ambiguous truth value")

        def __iter__(self):
            return iter([1.0, 2.0, 3.0])

    result = plotting.primary_y_range(ArrayLike(), (4.0, 5.0))

    assert result is not None
    assert result[0] < 1.0
    assert result[1] > 5.0


def test_sparse_label_indices_prefers_strongest_spaced_points():
    points = [
        {"position": 10.0, "intensity": 1.0},
        {"position": 10.2, "intensity": 0.95},
        {"position": 20.0, "intensity": 0.8},
        {"position": 30.0, "intensity": 0.7},
    ]

    chosen = plotting.sparse_label_indices(points, max_labels=3, min_distance_floor=1.0)

    assert 0 in chosen
    assert 1 not in chosen
    assert len(chosen) <= 3


def test_normalize_plot_display_settings_rejects_non_finite_ranges():
    settings = plotting.normalize_plot_display_settings(
        {
            "x_range_enabled": True,
            "x_min": float("nan"),
            "x_max": "inf",
            "y_range_enabled": True,
            "y_min": "-inf",
            "y_max": math.inf,
        }
    )

    assert settings["x_min"] is None
    assert settings["x_max"] is None
    assert settings["y_min"] is None
    assert settings["y_max"] is None
