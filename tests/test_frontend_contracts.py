from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLOT_STUDIO_PAGE = ROOT / "web" / "src" / "pages" / "PlotStudioPage.jsx"
STYLESHEET = ROOT / "web" / "src" / "styles.css"
STATIC_INDEX = ROOT / "src" / "yzwcloud" / "static" / "index.html"
STATIC_ASSETS = ROOT / "src" / "yzwcloud" / "static" / "assets"
I18N = ROOT / "web" / "src" / "i18n.jsx"


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_plot_studio_preview_forces_safe_plotly_config() -> None:
    source = _source(PLOT_STUDIO_PAGE)

    config_function = re.search(
        r"function fitPlotlyConfigToPreview\(config\) \{(?P<body>.*?)\n\}",
        source,
        flags=re.S,
    )
    assert config_function, "Plot Studio must keep a preview-specific Plotly config helper."
    body = config_function.group("body")

    assert re.search(r"\.\.\.\(config \|\| \{\}\).*displayModeBar:\s*false", body, flags=re.S)
    assert "responsive: true" in body
    assert "displaylogo: false" in body
    assert "scrollZoom: false" in body
    assert "Plotly.react(plotElement, spec.data || [], previewLayout, fitPlotlyConfigToPreview(spec.config))" in source


def test_plot_studio_preview_layout_is_container_bound() -> None:
    source = _source(PLOT_STUDIO_PAGE)
    styles = _source(STYLESHEET)

    assert "function fitPlotlyLayoutToPreview" in source
    assert "width: fittedWidth" in source
    assert "height: fittedHeight" in source
    assert "Math.min(Math.floor(width), 1120)" in source
    assert "Math.min(Math.floor(height), 640)" in source
    assert "automargin: true" in source
    assert "layout?.polar" in source
    assert "layout?.scene" in source
    assert "layout?.ternary" in source
    assert "domain:" in source

    required_css_fragments = [
        ".plot-page",
        "max-width: calc(100vw - 32px)",
        "overflow-x: clip",
        ".plot-studio-layout",
        "grid-template-columns: minmax(220px, 280px) minmax(0, 1fr) minmax(300px, 360px)",
        ".plot-library-panel",
        "overscroll-behavior: contain",
        ".plot-preview-panel",
        "overflow: hidden",
        ".plotly-preview",
        "contain: layout paint",
        "box-sizing: border-box",
        "isolation: isolate",
        "height: clamp(340px, calc(100vh - 430px), 520px)",
        ".plotly-preview .plotly",
        ".plotly-preview .svg-container",
        "inset: 0 !important",
        "position: relative !important",
    ]
    for fragment in required_css_fragments:
        assert fragment in styles


def test_built_frontend_entry_references_existing_static_assets() -> None:
    index_html = _source(STATIC_INDEX)
    asset_paths = re.findall(r'/(static/assets/[^"]+\.(?:js|css))', index_html)

    assert asset_paths
    assert len(asset_paths) == len(set(asset_paths))
    for asset_path in asset_paths:
        assert (ROOT / "src" / "yzwcloud" / asset_path).exists(), asset_path

    indexed_asset_names = {Path(asset_path).name for asset_path in asset_paths}
    built_asset_names = {path.name for path in STATIC_ASSETS.glob("index-*") if path.is_file()}
    assert indexed_asset_names == built_asset_names


def test_plot_studio_empty_preview_explains_renderability() -> None:
    page_source = _source(PLOT_STUDIO_PAGE)
    styles = _source(STYLESHEET)
    i18n = _source(I18N)

    assert "plotSpec?.renderability" in page_source
    assert "renderability?.current_data" in page_source
    assert "renderability?.requirements" in page_source
    assert "plot-renderability-grid" in page_source
    assert "currentData" in i18n
    assert "chartRequirements" in i18n

    for fragment in [
        ".plot-renderability-grid",
        "grid-template-columns: minmax(0, 0.9fr) minmax(0, 1.1fr)",
        ".plot-renderability-grid ul",
    ]:
        assert fragment in styles
