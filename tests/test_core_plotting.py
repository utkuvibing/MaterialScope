import plotly.graph_objects as go

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
