import { createContext, useContext, useEffect, useMemo, useState } from "react";

const LOCALE_STORAGE_KEY = "yzwcloud.locale";

const zh = {
  home: "首页",
  analysisWorkspace: "开始分析",
  plotStudio: "Plot Studio",
  experimentDesign: "实验设计",
  reports: "报告",
  guide: "指南",
  bioinformaticsWorkflow: "生物信息流程",
  languageZh: "中文",
  languageEn: "EN",
  backToAnalysis: "返回分析",
  inputSource: "输入数据源",
  connected: "已连接",
  empty: "未选择",
  selectAnalysisOutput: "选择一个分析结果",
  chooseWorkflowResult: "从流程节点、报告输出或下方列表选择数据源。",
  currentTaskOutputs: "当前任务输出",
  runAnalysisNodeFirst: "请先运行一个分析节点。",
  selectAnalysisTaskFirst: "请先选择分析任务。",
  useAsSource: "作为数据源",
  figureTypes: "图表类型",
  updating: "更新中",
  selectSourceFirst: "请先选择数据源",
  recommendedForSource: "推荐用于当前数据",
  parameters: "参数",
  loadingPresets: "正在加载预设...",
  agentReport: "智能体报告",
  selectSourceReport: "选择数据源后生成基于数据的报告。",
  dataPreview: "数据预览",
  interactivePreview: "交互预览",
  rendering: "渲染中",
  ready: "就绪",
  plotWarnings: "图表提示",
  noRenderableChart: "选择数据源和图表类型后会在这里生成交互图。",
  noTable: "没有表格",
  numericColumns: "数值列",
  categoricalColumns: "分类列",
  sourceFile: "源文件",
  metadataAfterSource: "选择数据源后会显示元数据。",
  task: "任务",
  node: "节点",
  type: "类型",
  openInteractiveOutput: "打开交互结果",
  openPreview: "打开预览",
  sourceKind: "数据源类型",
  figureWorkspaceTitle: "智能体辅助作图工作台",
  figureWorkspaceSummary: "图表预设、参数和报告文本由 YZW BioCloud 作图 API 提供。",
  homeTitle: "智能体驱动的生物数据分析、作图和报告",
  homeSummary: "平台规划为从智能体输入、流程节点、Plot Studio 图形到报告解释的闭环。",
  startAnalysis: "开始分析",
  openPlotStudio: "打开 Plot Studio",
  analysisCardTitle: "工作流分析",
  analysisCardText: "QC、PCA、样本相关性、热图、差异分析、单基因表达和 WGCNA 都以可追踪节点创建。",
  reportWorkspace: "报告工作台",
  reportSummary: "分析输出会先汇总为固定报告结构，再接入报告智能体。",
  tasks: "任务",
  total: "总计",
  reportStructure: "报告结构",
  outputs: "输出",
  reportAgentInput: "报告智能体输入",
  logTail: "日志尾部",
  nodes: "节点",
  completed: "已完成",
  failed: "失败",
  warnings: "警告",
  logLines: "日志行",
  nodesInContext: "上下文节点",
  noTaskYet: "还没有任务。",
  selectTask: "选择任务",
  refresh: "刷新",
  newAnalysisTask: "+ 新建分析任务",
  taskList: "任务列表",
  deleteTask: "删除任务",
  rename: "重命名",
  pinToTop: "置顶",
  share: "分享",
  delete: "删除",
  reportButton: "报告",
  noLogYet: "暂无日志。",
  interactiveEnginePlan:
    "后续图形引擎规划：Plotly、ECharts、Observable Plot、Vega-Lite、deck.gl、Cytoscape.js、Mol*/NGL、3Dmol.js、Phylocanvas、Clustergrammer2、HiGlass。",
};

const en = {
  home: "Home",
  analysisWorkspace: "Analysis Workspace",
  plotStudio: "Plot Studio",
  experimentDesign: "Experiment Design",
  reports: "Reports",
  guide: "Guide",
  bioinformaticsWorkflow: "Bioinformatics Workflow",
  languageZh: "中文",
  languageEn: "EN",
  backToAnalysis: "Back To Analysis",
  inputSource: "Input Source",
  connected: "connected",
  empty: "empty",
  selectAnalysisOutput: "Select an analysis output",
  chooseWorkflowResult: "Choose a workflow result from the output list, reports, or an analysis node.",
  currentTaskOutputs: "Current Task Outputs",
  runAnalysisNodeFirst: "Run an analysis node first.",
  selectAnalysisTaskFirst: "Select an analysis task first.",
  useAsSource: "Use as source",
  figureTypes: "Figure Types",
  updating: "updating",
  selectSourceFirst: "select source first",
  recommendedForSource: "Recommended for current source",
  parameters: "Parameters",
  loadingPresets: "Loading presets...",
  agentReport: "Agent Report",
  selectSourceReport: "Select a source to generate a data-driven report.",
  dataPreview: "Data Preview",
  interactivePreview: "Interactive Preview",
  rendering: "rendering",
  ready: "ready",
  plotWarnings: "Plot warnings",
  noRenderableChart: "Select a source and plot type to render an interactive chart here.",
  noTable: "no table",
  numericColumns: "Numeric columns",
  categoricalColumns: "Categorical columns",
  sourceFile: "Source file",
  metadataAfterSource: "Metadata will appear after a source is selected.",
  task: "Task",
  node: "Node",
  type: "Type",
  openInteractiveOutput: "Open interactive output",
  openPreview: "Open preview",
  sourceKind: "Source kind",
  figureWorkspaceTitle: "Agent-assisted figure workspace",
  figureWorkspaceSummary: "Plot presets, parameters, and report text are loaded from the YZW BioCloud plotting API.",
  homeTitle: "Agent-driven analysis, plotting, and reporting for biological data",
  homeSummary: "The platform is planned as a closed loop from agent intake to workflow nodes, Plot Studio figures, and report interpretation.",
  startAnalysis: "Start Analysis",
  openPlotStudio: "Open Plot Studio",
  analysisCardTitle: "Workflow Analysis",
  analysisCardText: "QC, PCA, sample correlation, heatmaps, differential analysis, single-gene plots, and WGCNA are created as traceable nodes.",
  reportWorkspace: "Report Workspace",
  reportSummary: "Analysis outputs are collected into a fixed report structure before the report agent is attached.",
  tasks: "Tasks",
  total: "total",
  reportStructure: "Report Structure",
  outputs: "Outputs",
  reportAgentInput: "Report Agent Input",
  logTail: "Log Tail",
  nodes: "Nodes",
  completed: "Completed",
  failed: "Failed",
  warnings: "Warnings",
  logLines: "Log lines",
  nodesInContext: "Nodes in context",
  noTaskYet: "No task yet.",
  selectTask: "Select a task",
  refresh: "Refresh",
  newAnalysisTask: "+ New Analysis Task",
  taskList: "Task List",
  deleteTask: "Delete Task",
  rename: "Rename",
  pinToTop: "Pin to top",
  share: "Share",
  delete: "Delete",
  reportButton: "Reports",
  noLogYet: "No log yet.",
  interactiveEnginePlan:
    "Planned engines: Plotly, ECharts, Observable Plot, Vega-Lite, deck.gl, Cytoscape.js, Mol*/NGL, 3Dmol.js, Phylocanvas, Clustergrammer2, and HiGlass.",
};

const dictionaries = { zh, en };

const I18nContext = createContext({
  locale: "zh",
  setLocale: () => {},
  t: (key) => key,
});

function initialLocale() {
  const saved = localStorage.getItem(LOCALE_STORAGE_KEY);
  return saved === "en" ? "en" : "zh";
}

export function I18nProvider({ children }) {
  const [locale, setLocale] = useState(initialLocale);

  useEffect(() => {
    localStorage.setItem(LOCALE_STORAGE_KEY, locale);
    document.documentElement.lang = locale === "zh" ? "zh-CN" : "en";
  }, [locale]);

  const value = useMemo(
    () => ({
      locale,
      setLocale,
      t: (key) => dictionaries[locale][key] || dictionaries.zh[key] || key,
    }),
    [locale],
  );

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useI18n() {
  return useContext(I18nContext);
}

export function LanguageToggle() {
  const { locale, setLocale, t } = useI18n();
  return (
    <div className="language-toggle" role="group" aria-label="Language">
      <button className={locale === "zh" ? "active" : ""} onClick={() => setLocale("zh")} type="button">
        {t("languageZh")}
      </button>
      <button className={locale === "en" ? "active" : ""} onClick={() => setLocale("en")} type="button">
        {t("languageEn")}
      </button>
    </div>
  );
}
