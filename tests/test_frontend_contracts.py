from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLOT_STUDIO_PAGE = ROOT / "web" / "src" / "pages" / "PlotStudioPage.jsx"
PLOT_STUDIO_MODULES = ROOT / "web" / "src" / "plotStudio"
MAIN_PAGE = ROOT / "web" / "src" / "main.jsx"
HOME_PAGE = ROOT / "web" / "src" / "pages" / "HomePage.jsx"
STYLESHEET = ROOT / "web" / "src" / "styles.css"
STATIC_INDEX = ROOT / "src" / "yzwcloud" / "static" / "index.html"
STATIC_ASSETS = ROOT / "src" / "yzwcloud" / "static" / "assets"
I18N = ROOT / "web" / "src" / "i18n.jsx"


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _plot_studio_source() -> str:
    module_sources = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted(PLOT_STUDIO_MODULES.glob("*.js*"))
    )
    return f"{_source(PLOT_STUDIO_PAGE)}\n{module_sources}"


def test_plot_studio_preview_forces_safe_plotly_config() -> None:
    source = _plot_studio_source()

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
    source = _plot_studio_source()
    styles = _source(STYLESHEET)

    assert "function fitPlotlyLayoutToPreview" in source
    assert "width: fittedWidth" in source
    assert "height: fittedHeight" in source
    assert "Math.max(260, Math.floor(width - renderInset))" in source
    assert "Math.max(300, Math.floor(height - renderInset))" in source
    assert "plotElement.closest(\".plotly-preview-shell\")" in source
    assert "plotly-preview-shell" in source
    assert "automargin: true" in source
    assert "layout?.polar" in source
    assert "layout?.scene" in source
    assert "layout?.ternary" in source
    assert "domain:" in source

    required_css_fragments = [
        ".plot-page",
        "width: 100%",
        "max-width: calc(100vw - 32px)",
        "overflow-x: clip",
        ".plot-studio-layout",
        "grid-template-columns: minmax(220px, 280px) minmax(0, 1fr) minmax(300px, 360px)",
        ".plot-library-panel",
        "min-height: 0",
        "max-height: none",
        "overflow: visible",
        ".plot-preview-panel",
        "overflow: hidden",
        ".plotly-preview-shell",
        "height: clamp(380px, calc(100vh - 410px), 560px)",
        ".plotly-preview",
        "contain: layout paint",
        "box-sizing: border-box",
        "isolation: isolate",
        ".plotly-preview .plotly",
        ".plotly-preview .svg-container",
        "max-width: 100% !important",
        "inset: 0 !important",
        "position: absolute !important",
        ".plotly-preview .modebar-container",
        "display: none !important",
        "@media (max-width: 1500px)",
        "@media (max-width: 980px)",
        "grid-column: 1 / -1",
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
    page_source = _plot_studio_source()
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


def test_plot_studio_marks_modified_parameters() -> None:
    page_source = _plot_studio_source()
    styles = _source(STYLESHEET)
    i18n = _source(I18N)

    assert "function parameterValueIsModified" in page_source
    assert "parameterValueIsModified(parameter, value)" in page_source
    assert "plot-param-modified" in page_source
    assert 't("parameterModified")' in page_source
    assert "parameterModified" in i18n

    for fragment in [
        ".plot-param-modified",
        "border-radius: 999px",
        "background: #edf2ff",
        "font-style: normal",
    ]:
        assert fragment in styles


def test_plot_studio_explains_unsupported_plot_cards() -> None:
    page_source = _plot_studio_source()
    styles = _source(STYLESHEET)

    assert "const unsupportedReason = tableSuitabilityWarning(plot, tableSummary)" in page_source
    assert "const supported = !unsupportedReason" in page_source
    assert "title={supported ? plot.label : unsupportedReason}" in page_source
    assert "plot-type-unsupported-reason" in page_source

    for fragment in [
        ".plot-type-unsupported-reason",
        "background: #fff8f6",
        "color: #9a352a !important",
        "-webkit-line-clamp: 3 !important",
    ]:
        assert fragment in styles


def test_plot_studio_surfaces_llm_report_guidance() -> None:
    page_source = _plot_studio_source()
    styles = _source(STYLESHEET)
    i18n = _source(I18N)

    for fragment in [
        "function ReportGuidance",
        "guidance.safe_claims",
        "guidance.avoid_claims",
        "guidance.next_checks",
        "const reportGuidance = studioReport?.agent_context?.report_guidance || null",
        "ReportGuidanceComponent={ReportGuidance}",
        "plot-report-guidance",
    ]:
        assert fragment in page_source

    for key in ["reportGuidance", "reportGuidanceHint", "safeClaims", "avoidClaims", "nextChecks"]:
        assert key in i18n

    for fragment in [
        ".plot-report-guidance",
        ".plot-report-guidance-card.safe",
        ".plot-report-guidance-card.avoid",
        ".plot-report-guidance-card.next",
        "background: #f8fbff",
    ]:
        assert fragment in styles


def test_plot_studio_surfaces_copyable_report_prompt() -> None:
    page_source = _plot_studio_source()
    styles = _source(STYLESHEET)
    i18n = _source(I18N)

    for fragment in [
        "function formatReportPrompt",
        "function ReportPrompt",
        "const [reportPromptCopied, setReportPromptCopied] = useState(false)",
        "const reportPrompt = studioReport?.agent_context?.report_prompt || null",
        "const reportPromptText = useMemo",
        "<ReportPrompt",
        "copyTextToClipboard(reportPromptText)",
        "setReportPromptCopied(copied)",
        "plot-report-prompt",
    ]:
        assert fragment in page_source

    for key in ["reportPrompt", "reportPromptHint", "copyPrompt", "promptChecklist"]:
        assert key in i18n

    for fragment in [
        ".plot-report-prompt",
        ".plot-report-prompt summary",
        ".plot-report-prompt pre",
        "max-height: 180px",
        "white-space: pre-wrap",
    ]:
        assert fragment in styles


def test_plot_studio_has_collapsed_categories_examples_and_upload() -> None:
    page_source = _plot_studio_source()
    styles = _source(STYLESHEET)
    i18n = _source(I18N)

    for fragment in [
        "expandedPlotCategories",
        "togglePlotCategory",
        "plot-type-section-header",
        "aria-expanded={expandedPlotCategories.has(group.category)}",
        "uploadPlotStudioTable",
        'fetch(`/api/plot-studio/uploads?filename=${encodeURIComponent(file.name)}`',
        "loadExampleData",
        "/api/plot-studio/examples/",
        'sourceKind === "plot_studio_example"',
        "selectedSource?.meta?.plot_id",
        "plot-example-action",
        "plot-upload-card",
        "plot-card-example",
        't("plotExample")',
        't("useExampleData")',
    ]:
        assert fragment in page_source

    for fragment in [
        ".plot-type-section-header",
        ".plot-type-section.expanded .plot-type-section-header",
        ".plot-upload-card",
        ".plot-type-select",
        ".plot-example-action",
        ".plot-card-example",
        ".plot-card-example em",
    ]:
        assert fragment in styles

    for key in ["uploadTable", "uploadTableHint", "uploading", "plotExample", "useExampleData", "loadingExample"]:
        assert key in i18n

    for removed in [
        "figureWorkspaceSummary",
        "chooseWorkflowResult",
        "plot-workflow-strip",
        "Attach an upstream",
        "Plot presets, parameters, and report text",
    ]:
        assert removed not in page_source
        assert removed not in i18n


def test_plot_studio_navigation_uses_empty_session_unless_source_is_explicit() -> None:
    main_source = _source(MAIN_PAGE)
    session_source = _source(PLOT_STUDIO_MODULES / "session.js")

    assert "createPlotStudioSession()" in main_source
    assert "createPlotStudioSessionFromSource(source)" in main_source
    assert "createPlotStudioSessionFromSource(source, { returnTarget: source })" in main_source
    assert 'if (nextPage === "plot")' in main_source
    assert "setPlotStudioSession(createPlotStudioSession())" in main_source
    assert 'mode: source ? "analysis_result" : "scratch"' in session_source
    assert "const source = normalizePlotStudioSource(overrides.source)" in session_source
    assert "const returnTarget = normalizePlotStudioSource(overrides.returnTarget)" in session_source


def test_homepage_keeps_agent_flow_animation_contract() -> None:
    source = _source(HOME_PAGE)
    styles = _source(STYLESHEET)
    i18n = _source(I18N)

    for fragment in [
        "const NODE_GROUPS",
        "const EDGES",
        "const DEMO_SEQUENCE",
        "setVisibleNodeIds",
        "workflow-node",
        "plot-card-preview",
        "DemoChart",
        "onOpenPlot",
    ]:
        assert fragment in source

    for node_id in ["intake", "qc", "pca", "diff", "heatmap", "volcano", "boxplot", "corr"]:
        assert f'id: "{node_id}"' in source

    for fragment in [
        ".landing-hero",
        ".hero-workflow",
        ".workflow-board",
        ".workflow-edges",
        ".workflow-node",
        ".plot-card-preview",
        ".demo-chart",
    ]:
        assert fragment in styles

    assert "homeWorkflowDemo" in i18n
