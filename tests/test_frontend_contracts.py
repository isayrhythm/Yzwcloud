from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLOT_STUDIO_PAGE = ROOT / "web" / "src" / "pages" / "PlotStudioPage.jsx"
PLOT_STUDIO_MODULES = ROOT / "web" / "src" / "plotStudio"
MAIN_PAGE = ROOT / "web" / "src" / "main.jsx"
HOME_PAGE = ROOT / "web" / "src" / "pages" / "HomePage.jsx"
DOCS_PAGE = ROOT / "web" / "src" / "pages" / "DocsPage.jsx"
STYLESHEET = ROOT / "web" / "src" / "styles.css"
STATIC_INDEX = ROOT / "src" / "yzwcloud" / "static" / "index.html"
STATIC_ASSETS = ROOT / "src" / "yzwcloud" / "static" / "assets"
I18N = ROOT / "web" / "src" / "i18n.jsx"
APP_CHROME = ROOT / "web" / "src" / "components" / "AppChrome.jsx"
ANALYSIS_NODE = ROOT / "web" / "src" / "components" / "AnalysisNode.jsx"
WORKFLOW_MODALS = ROOT / "web" / "src" / "components" / "WorkflowModals.jsx"
REPORTS_PAGE = ROOT / "web" / "src" / "pages" / "ReportsPage.jsx"
WORKFLOW_OPTIONS = ROOT / "web" / "src" / "workflow" / "options.js"
WORKFLOW_LAYOUT = ROOT / "web" / "src" / "workflow" / "layout.js"


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
        r"function fitPlotlyConfigToPreview\(config, layout\) \{(?P<body>.*?)\n\}",
        source,
        flags=re.S,
    )
    assert config_function, "Plot Studio must keep a preview-specific Plotly config helper."
    body = config_function.group("body")

    assert re.search(r"\.\.\.\(config \|\| \{\}\).*displayModeBar:\s*has3dScene \? \"hover\" : false", body, flags=re.S)
    assert "responsive: true" in body
    assert "displaylogo: false" in body
    assert "const has3dScene = Boolean(layout?.scene)" in body
    assert "scrollZoom: has3dScene || Boolean(config?.scrollZoom)" in body
    assert "Plotly.react(plotElement, spec.data || [], previewLayout, fitPlotlyConfigToPreview(spec.config, previewLayout))" in source


def test_plot_studio_preview_exposes_hd_image_and_pdf_export() -> None:
    source = _plot_studio_source()
    styles = _source(STYLESHEET)

    for fragment in [
        "function plotExportOptionsFromSpec",
        "function downloadDataUrl",
        "function downloadBlob",
        "function dataUrlToTiffBlob",
        "function createPlotExportPrintWindow",
        "function openPlotExportPrintWindow",
        "downloadTextFile(html, `${filename}-print.html`)",
        "Plotly.toImage(plotExportRef.current, options)",
        "Plotly.toImage(plotExportRef.current, { ...options, format: \"png\" })",
        "Plotly.toImage(plotExportRef.current, { ...options, format: \"svg\" })",
        "downloadBlob(tiffBlob, `${options.filename}.tif`)",
        "导出高清图",
        "导出 PDF",
        'import { Button } from "tdesign-react"',
        "<Button",
        'className="plot-export-action"',
        'className="plot-save-back"',
        "plotExportStatus",
        "plotRef={plotExportRef}",
    ]:
        assert fragment in source

    for fragment in [
        ".plot-export-action",
        ".plot-export-action:disabled",
    ]:
        assert fragment in styles


def test_plot_studio_parameters_and_report_actions_use_tdesign_buttons() -> None:
    source = _plot_studio_source()
    styles = _source(STYLESHEET)

    for fragment in [
        "onResetParams",
        "onRunPreview",
        "onClearParameterSearch",
        "onApplyEditCommand",
        "onCopyAgentContext",
        "onCopyReportPrompt",
        "<Button",
        "theme=\"primary\"",
        "variant=\"outline\"",
    ]:
        assert fragment in source

    for fragment in [
        ".plot-action-strip .t-button",
        ".plot-param-search .t-button",
        ".plot-agent-editor .t-button",
        ".plot-report-prompt summary .t-button",
        ".plot-agent-context summary .t-button",
    ]:
        assert fragment in styles


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


def test_plot_studio_gallery_cards_load_targeted_examples_directly() -> None:
    page_source = _plot_studio_source()
    styles = _source(STYLESHEET)

    assert "onClick={() => {" in page_source
    assert "onLoadExampleData(plot)" in page_source
    assert "title={plot.label}" in page_source
    assert "plot-gallery-card-main" in page_source
    assert "plot-type-select" in page_source

    for removed in [
        "plot-gallery-example",
        "plot-example-action",
        "plot-type-unsupported-reason",
        "plot-type-card.unsupported",
        "unsupported-badge",
    ]:
        assert removed not in page_source
        assert removed not in styles

    for fragment in [
        ".plot-gallery-card-main",
        ".plot-type-select",
        "cursor: pointer",
    ]:
        assert fragment in styles


def test_plot_studio_preview_allows_3d_camera_interaction() -> None:
    page_source = _plot_studio_source()
    styles = _source(STYLESHEET)

    for fragment in [
        "const has3dScene = Boolean(layout?.scene)",
        'previewLayout.dragmode = ["orbit", "turntable"].includes(layout.dragmode) ? layout.dragmode : "orbit"',
        'displayModeBar: has3dScene ? "hover" : false',
        "scrollZoom: has3dScene || Boolean(config?.scrollZoom)",
        "fitPlotlyConfigToPreview(spec.config, previewLayout)",
    ]:
        assert fragment in page_source

    assert ".plotly-preview .modebar-container {\n  display: none !important;" not in styles


def test_plot_studio_preview_empty_explains_unsupported_selected_plot() -> None:
    page_source = _plot_studio_source()

    for fragment in [
        "function PlotPreviewEmpty",
        "const warning = tableSuitabilityWarning(preset, tableSummary)",
        't("chartNotSuitable")',
    ]:
        assert fragment in page_source

    assert ".plot-type-unsupported-reason" not in page_source


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
        'selectedSource.sourceKind !== "plot_studio_example"',
        "selectedSource?.meta?.plot_id",
        "<Button",
        "theme={recommendedOnly ? \"primary\" : \"default\"}",
        "exampleLoadingId === plot.id",
        "onSelectSource?.(normalizePlotStudioSource(output))",
        "plot-upload-card",
        "plot-card-example",
        't("plotExample")',
    ]:
        assert fragment in page_source

    for fragment in [
        ".plot-type-section-header",
        ".plot-type-section.expanded .plot-type-section-header",
        ".plot-upload-card",
        ".plot-type-select",
        ".plot-type-filter .t-button",
        ".plot-output-grid article .t-button",
        ".plot-card-example",
        ".plot-card-example em",
    ]:
        assert fragment in styles

    for key in ["uploadTable", "uploadTableHint", "uploading", "plotExample", "loadingExample"]:
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


def test_diff_followup_options_do_not_show_export_or_report_nodes() -> None:
    source = _source(WORKFLOW_OPTIONS)
    diff_options = re.search(
        r'if \(node\.id\.startsWith\("diff_analysis__"\).*?return \[(?P<body>.*?)\];',
        source,
        flags=re.S,
    )
    assert diff_options, "Differential follow-up options must stay explicit."
    body = diff_options.group("body")

    assert "diff_export" not in body
    assert "analysis_report" not in body
    assert "Result export" not in body
    assert "Report" not in body


def test_analysis_nodes_surface_agent_summary_reports() -> None:
    node_source = _source(ANALYSIS_NODE)
    modal_source = _source(WORKFLOW_MODALS)
    styles = _source(STYLESHEET)

    for removed in [
        "const canOpenAgentSummary = Boolean(node.output?.meta?.agent_report)",
        "result-preview-agent",
        "inline-agent-summary",
        "upload-agent-summary",
        "node-output-tools",
    ]:
        assert removed not in node_source

    for fragment in [
        "const analysisReport = node.output?.meta?.agent_report || null",
        "关键发现",
        "方法与参数",
        "解释边界",
        "下一步建议",
        "规则化回退",
    ]:
        assert fragment in modal_source

    for removed in [
        ".analysis-node .agent-summary",
        ".result-preview-agent",
        ".analysis-node .inline-agent-summary",
        ".upload-agent-summary",
        ".node-output-tools",
    ]:
        assert removed not in styles

    for fragment in [
        ".analysis-agent-report-modal",
        ".agent-report-badge.fallback",
        "background: var(--td-warning-1)",
        ".analysis-agent-report-grid",
    ]:
        assert fragment in styles


def test_result_modal_keeps_plot_studio_next_to_title() -> None:
    modal_source = _source(WORKFLOW_MODALS)
    main_source = _source(MAIN_PAGE)
    styles = _source(STYLESHEET)

    for fragment in [
        "result-title-row",
        "result-plot-send",
        "result-agent-summary",
        "Plot Studio",
        "Agent 总结",
    ]:
        assert fragment in modal_source

    assert "agentReportNode={modal.agentReportNode}" in main_source
    assert "onOpenAgentReport={openAgentReport}" in main_source

    title_row = modal_source.index("result-title-row")
    plot_button = modal_source.index("result-plot-send")
    agent_button = modal_source.index("result-agent-summary")
    header_actions = modal_source.index("result-header-actions")
    assert title_row < plot_button < agent_button < header_actions

    for fragment in [
        ".result-title-row",
        ".result-title-row .result-plot-send",
        ".result-title-row .result-agent-summary",
    ]:
        assert fragment in styles


def test_reports_page_links_slide_html_and_pdf_exports() -> None:
    source = _source(REPORTS_PAGE)
    styles = _source(STYLESHEET)

    for fragment in [
        "/report.html",
        "/report.pdf",
        "演示版 HTML",
        "导出 PDF",
        "report-hero-actions",
    ]:
        assert fragment in source

    for fragment in [
        ".report-hero-actions",
        ".report-hero-actions .t-button",
        ".report-output-table",
    ]:
        assert fragment in styles

    for fragment in [
        'import { Button, Table } from "tdesign-react"',
        'className="report-output-table"',
    ]:
        assert fragment in source


def test_docs_page_is_split_into_analysis_and_plot_studio_guides() -> None:
    source = _source(DOCS_PAGE)
    main_source = _source(MAIN_PAGE)
    styles = _source(STYLESHEET)

    for fragment in [
        "数据分析模块",
        "Plot Studio 模块",
        "ANALYSIS_STEPS",
        "PLOT_STUDIO_STEPS",
        "ANALYSIS_CHECKS",
        "PLOT_STUDIO_CHECKS",
        "进入分析台",
        "打开 Plot Studio",
        "导出高清图",
        "保存回分析结果",
    ]:
        assert fragment in source

    assert "<DocsPage onStart={openWorkbench} onOpenPlot={openPlotStudio} />" in main_source

    for fragment in [".doc-module", ".doc-step-list", ".doc-checklist", ".docs-actions"]:
        assert fragment in styles


def test_app_chrome_uses_tdesign_buttons_for_navigation() -> None:
    app_chrome = _source(APP_CHROME)
    i18n = _source(I18N)
    styles = _source(STYLESHEET)

    for fragment in [
        'import { Button } from "tdesign-react"',
        "<Button",
        "theme={page === item.id ? \"primary\" : \"default\"}",
        "variant={page === item.id ? \"base\" : \"text\"}",
    ]:
        assert fragment in app_chrome

    for fragment in [
        'import { Button } from "tdesign-react"',
        "theme={locale === \"zh\" ? \"primary\" : \"default\"}",
        "variant={locale === \"en\" ? \"base\" : \"text\"}",
    ]:
        assert fragment in i18n

    for fragment in [
        ".topnav .t-button",
        ".language-toggle .t-button",
    ]:
        assert fragment in styles


def test_workflow_header_exposes_task_report_exports() -> None:
    source = _source(MAIN_PAGE)
    styles = _source(STYLESHEET)

    for fragment in [
        "taskReportHtmlUrl",
        "/report.html",
        "workflow-title-row",
        "workflow-report-actions",
        "workflow-report-primary",
        "流程报告",
        "arrangeWorkflowNodes",
        "arrangeGraphNodePositions",
        "整理节点",
        "fitView({ padding: 0.18, duration: 300 })",
    ]:
        assert fragment in source

    for removed in [
        "taskReportPdfUrl",
        "workflow-report-secondary",
        ">PDF<",
        "出报告",
    ]:
        assert removed not in source

    for fragment in [
        ".workflow-title-row",
        ".workflow-report-actions",
        ".workflow-report-primary",
        ".workflow-arrange-button",
    ]:
        assert fragment in styles

    assert ".workflow-report-secondary" not in styles


def test_workbench_sidebar_does_not_show_reports_menu_button() -> None:
    source = _source(MAIN_PAGE)
    sidebar_actions = re.search(
        r'<div className="task-sidebar-actions">(?P<body>.*?)</div>',
        source,
        flags=re.S,
    )
    assert sidebar_actions, "Workbench sidebar actions should remain explicit."
    body = sidebar_actions.group("body")

    assert "openReports" not in source
    assert "reportButton" not in body
    assert "loadTasks" in body


def test_task_refresh_preserves_current_workbench_selection() -> None:
    source = _source(MAIN_PAGE)
    load_tasks_body = re.search(
        r"const loadTasks = useCallback\(async \(\) => \{(?P<body>.*?)\n  \}, \[\]\);",
        source,
        flags=re.S,
    )
    assert load_tasks_body, "loadTasks should be stable and not close over a stale activeTaskId."
    body = load_tasks_body.group("body")

    assert "setActiveTaskId((currentTaskId)" in body
    assert "data.some((task) => task.task_id === currentTaskId)" in body
    assert "return currentTaskId" in body
    assert "if (!activeTaskId && data.length)" not in body


def test_browser_reload_restores_active_workbench_task() -> None:
    source = _source(MAIN_PAGE)

    assert 'const TASK_STORAGE_KEY = "yzwcloud.activeTaskId"' in source
    assert "useState(() => localStorage.getItem(TASK_STORAGE_KEY) || null)" in source
    assert "localStorage.setItem(TASK_STORAGE_KEY, activeTaskId)" in source
    assert "localStorage.removeItem(TASK_STORAGE_KEY)" in source


def test_workbench_task_selection_fits_flow_view() -> None:
    source = _source(MAIN_PAGE)

    assert "const pendingFitTaskIdRef = useRef(null)" in source
    assert "const fitWorkflowView = useCallback" in source
    assert "fitView({ padding: 0.18, duration: 300 })" in source
    assert "pendingFitTaskIdRef.current = activeTaskId" in source
    assert 'pendingFitTaskIdRef.current !== detail.task.task_id' in source
    assert "const selectTask = (taskId) =>" in source
    assert "pendingFitTaskIdRef.current = taskId" in source
    assert "onClick={() => selectTask(task.task_id)}" in source


def test_workbench_polling_uses_bounded_logs_and_slower_idle_refresh() -> None:
    source = _source(MAIN_PAGE)

    assert "const LOG_RENDER_LIMIT = 12000" in source
    assert "function tailText" in source
    assert "function hasRunningWorkflow" in source
    assert "hasRunningWorkflow(detail) ? 3000 : 10000" in source
    assert "}, [activeTaskId, detail, loadDetail]);" in source
    assert '<pre className="logs">{tailText(logs)}</pre>' in source


def test_workflow_edges_route_through_directional_handles() -> None:
    main_source = _source(MAIN_PAGE)
    node_source = _source(ROOT / "web" / "src" / "components" / "AnalysisNode.jsx")
    styles = _source(ROOT / "web" / "src" / "styles.css")

    assert "edgeHandlesForPositions" in main_source
    assert "edgeHandlesForGraphEdge" in main_source
    assert "edgeSourceHandle" in main_source
    assert "edgeTargetHandle" in main_source
    assert "edgeChannelHandle" in main_source
    assert "EDGE_SIDE_CHANNELS = 5" in main_source
    assert "const visibleEdges = detail.graph.edges.filter" in main_source
    assert "sourceHandle: handles.sourceHandle" in main_source
    assert "targetHandle: handles.targetHandle" in main_source
    assert 'type: "smoothstep"' not in main_source
    assert "pathOptions: { borderRadius: 18, offset: 42 }" not in main_source
    for handle_id in [
        'id="source-right"',
        'id="source-top"',
        'id="source-bottom"',
        'id="target-left"',
        'id="target-top"',
        'id="target-bottom"',
        "edgeHandleChannels.map",
        "source-right-${channel}",
        "target-left-${channel}",
    ]:
        assert handle_id in node_source
    assert ".analysis-node .node-handle" in styles
    assert "opacity: 0" in styles


def test_workflow_new_node_placement_searches_open_space_around_parent() -> None:
    source = _source(WORKFLOW_LAYOUT)
    main_source = _source(MAIN_PAGE)

    for fragment in [
        "arrangeGraphNodePositions",
        'import { Graph, layout as dagreLayout } from "@dagrejs/dagre"',
        "arrangeGraphNodePositionsWithDagre",
        "rankdir: \"LR\"",
        "ranker: \"network-simplex\"",
        "acyclicer: \"greedy\"",
        "nodesep: 190",
        "ranksep: 270",
        "dagreLayout(graph)",
        "arrangeGraphNodePositionsWithLocalLayers",
        "nodeSortValue",
        "nodePositionCandidates",
        "const rowOffsets = [0, 1, -1",
        "const colOffsets = [0, 1, -1",
        "firstOpenCandidate(candidates, occupiedRects, viewportBounds)",
        "firstOpenCandidate(candidates, occupiedRects, expandedBounds)",
        "leastCrowdedCandidate(candidates, occupiedRects, expandedBounds)",
        "rectOverlapArea",
    ]:
        assert fragment in source

    assert "findOpenNodePosition(desired, occupiedRects, bounds)" in main_source


def test_feature_intensity_profile_uses_generic_feature_labels() -> None:
    options_source = _source(ROOT / "web" / "src" / "workflow" / "options.js")
    heatmap_source = _source(ROOT / "web" / "src" / "components" / "HeatmapParamsModal.jsx")

    for fragment in [
        'meta.assay_profile === "feature_intensity"',
        'shortLabel: "Feature"',
        'fullLabel: "Feature intensity matrix"',
        'featureLabel: "features"',
        'featureSingular: "feature"',
    ]:
        assert fragment in options_source

    assert 'sourceMeta.assay_profile === "feature_intensity"' in heatmap_source
    assert "Top variable metabolites heatmap" not in options_source
    assert "Single metabolite abundance" not in options_source
    assert "metabolomics_ml_modeling" in options_source
    assert "metabolomics_ml_svm" in options_source
    assert "metabolomics_ml_naive_bayes" in options_source
    assert "metabolomics_ml_random_forest" in options_source
    assert "SHAP summary plot" in options_source
    assert "Permutation importance" in options_source
    assert "RF importance" in options_source
    assert "metabolomics_ml_result" in options_source
    assert "metabolomics_ml_explainability_result" in options_source


def test_metabolomics_qc_exposes_normalization_before_ml() -> None:
    options_source = _source(ROOT / "web" / "src" / "workflow" / "options.js")

    assert 'profile.qcProfile === "metabolomics"' in options_source
    assert 'type: "metabolomics_normalization"' in options_source
    assert 'label: "Normalize / impute / scale"' in options_source
    assert 'node.id.startsWith("metabolomics_normalization__")' in options_source
    assert 'type: "metabolomics_ml_modeling"' in options_source
    assert "sampleCount >= 100" in options_source


def test_output_urls_stay_same_origin_outside_explicit_api_base() -> None:
    source = _source(ROOT / "web" / "src" / "workflow" / "format.js")
    plot_source = _source(PLOT_STUDIO_PAGE)
    main_source = _source(ROOT / "src" / "yzwcloud" / "main.py")

    assert "VITE_YZWCLOUD_API_BASE" in source
    assert "window.location.port" not in source
    assert "window.location.port" not in plot_source
    assert "window.location.port" not in main_source
    assert ":10001" not in source
    assert ":10001" not in plot_source
    assert ":10001" not in main_source
