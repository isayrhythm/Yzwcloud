import { useEffect, useMemo, useState } from "react";

import { useI18n } from "../i18n.jsx";

const NODE_GROUPS = [
  {
    id: "intake",
    level: 0,
    labelKey: "homeDataNode",
    detailKey: "homeDataNodeDetail",
    x: 8,
    y: 44,
    unlocks: ["qc", "pca", "diff"],
  },
  {
    id: "qc",
    level: 1,
    labelKey: "homeQcNode",
    detailKey: "homeQcNodeDetail",
    x: 34,
    y: 22,
    unlocks: ["corr", "heatmap"],
  },
  {
    id: "pca",
    level: 1,
    labelKey: "homePcaNode",
    detailKey: "homePcaNodeDetail",
    x: 36,
    y: 56,
    unlocks: ["cluster"],
  },
  {
    id: "diff",
    level: 1,
    labelKey: "homeDiffNode",
    detailKey: "homeDiffNodeDetail",
    x: 32,
    y: 78,
    unlocks: ["volcano", "boxplot"],
  },
  {
    id: "corr",
    level: 2,
    labelKey: "homeCorrNode",
    detailKey: "homeCorrNodeDetail",
    x: 63,
    y: 12,
    chart: "corr",
  },
  {
    id: "heatmap",
    level: 2,
    labelKey: "homeHeatmapNode",
    detailKey: "homeHeatmapNodeDetail",
    x: 68,
    y: 32,
    chart: "heatmap",
  },
  {
    id: "cluster",
    level: 2,
    labelKey: "homeClusterNode",
    detailKey: "homeClusterNodeDetail",
    x: 70,
    y: 56,
    chart: "pca",
  },
  {
    id: "volcano",
    level: 2,
    labelKey: "homeVolcanoNode",
    detailKey: "homeVolcanoNodeDetail",
    x: 65,
    y: 76,
    chart: "volcano",
  },
  {
    id: "boxplot",
    level: 2,
    labelKey: "homeBoxplotNode",
    detailKey: "homeBoxplotNodeDetail",
    x: 82,
    y: 68,
    chart: "boxplot",
  },
];

const EDGES = [
  ["intake", "qc"],
  ["intake", "pca"],
  ["intake", "diff"],
  ["qc", "corr"],
  ["qc", "heatmap"],
  ["pca", "cluster"],
  ["diff", "volcano"],
  ["diff", "boxplot"],
];

const CHARTS = {
  pca: { titleKey: "homePcaChart", subtitle: "PC1 42.6% / PC2 18.3%" },
  heatmap: { titleKey: "homeHeatmapChart", subtitle: "Top variable genes · row z-score" },
  volcano: { titleKey: "homeVolcanoChart", subtitle: "log2FC / -log10(p)" },
  corr: { titleKey: "homeCorrChart", subtitle: "Pearson r · clustered samples" },
  boxplot: { titleKey: "homeBoxplotChart", subtitle: "Single gene expression by condition" },
};

const CHART_META = {
  pca: { metric: "52 samples", engine: "Plotly scatter" },
  heatmap: { metric: "40 genes", engine: "Clustered heatmap" },
  volcano: { metric: "128 hits", engine: "R differential" },
  corr: { metric: "52 x 52", engine: "Correlation heatmap" },
  boxplot: { metric: "3 groups", engine: "Interactive boxplot" },
};

const DEMO_SEQUENCE = ["intake", "qc", "heatmap", "pca", "cluster", "diff", "volcano", "boxplot", "corr"];

export function HomePage({ onStart, onOpenPlot }) {
  const { t } = useI18n();
  const [visibleNodeIds, setVisibleNodeIds] = useState(() => new Set(["intake"]));
  const [selectedNodeId, setSelectedNodeId] = useState("intake");
  const [selectedChart, setSelectedChart] = useState("pca");
  const [demoStep, setDemoStep] = useState(0);
  const [autoPlay, setAutoPlay] = useState(() => !window.matchMedia?.("(prefers-reduced-motion: reduce)").matches);

  const visibleNodes = useMemo(
    () => NODE_GROUPS.filter((node) => visibleNodeIds.has(node.id)),
    [visibleNodeIds],
  );
  const visibleEdges = useMemo(
    () => EDGES.filter(([source, target]) => visibleNodeIds.has(source) && visibleNodeIds.has(target)),
    [visibleNodeIds],
  );
  const selectedNode = NODE_GROUPS.find((node) => node.id === selectedNodeId) || NODE_GROUPS[0];
  const chart = CHARTS[selectedChart] || CHARTS.pca;
  const chartMeta = CHART_META[selectedChart] || CHART_META.pca;
  const unlockedChartCount = visibleNodes.filter((node) => node.chart).length;
  const selectedNodeHasChart = Boolean(selectedNode.chart);

  useEffect(() => {
    if (!autoPlay) return undefined;
    const timer = window.setInterval(() => {
      setDemoStep((current) => (current + 1) % DEMO_SEQUENCE.length);
    }, 1350);
    return () => window.clearInterval(timer);
  }, [autoPlay]);

  useEffect(() => {
    if (!autoPlay) return;
    const node = NODE_GROUPS.find((item) => item.id === DEMO_SEQUENCE[demoStep]) || NODE_GROUPS[0];
    revealNode(node);
  }, [autoPlay, demoStep]);

  function revealNode(node) {
    setSelectedNodeId(node.id);
    setVisibleNodeIds((current) => {
      const next = demoStep === 0 ? new Set(["intake"]) : new Set(current);
      next.add("intake");
      for (const demoNodeId of DEMO_SEQUENCE.slice(0, demoStep + 1)) {
        next.add(demoNodeId);
      }
      next.add(node.id);
      for (const childId of node.unlocks || []) {
        next.add(childId);
      }
      return next;
    });
    if (node.chart) {
      setSelectedChart(node.chart);
    }
  }

  function activateNode(node) {
    setAutoPlay(false);
    setVisibleNodeIds((current) => {
      const next = new Set(current);
      next.add(node.id);
      for (const childId of node.unlocks || []) {
        next.add(childId);
      }
      return next;
    });
    if (node.chart) {
      setSelectedChart(node.chart);
    }
    setSelectedNodeId(node.id);
  }

  function expandAll() {
    setAutoPlay(false);
    setVisibleNodeIds(new Set(NODE_GROUPS.map((node) => node.id)));
    setSelectedNodeId("volcano");
    setSelectedChart("volcano");
  }

  return (
    <main className="landing">
      <section className="landing-hero">
        <div className="hero-copy">
          <p className="eyebrow">YZW BioCloud</p>
          <h1>{t("homeTitle")}</h1>
          <p>{t("homeSummary")}</p>
          <div className="hero-actions">
            <button className="primary launch" onClick={onStart}>
              {t("startAnalysis")}
            </button>
            <button className="hero-ghost" onClick={onOpenPlot}>
              {t("openPlotStudio")}
            </button>
            <button className="hero-ghost compact" onClick={expandAll}>
              {t("homeExpandDemo")}
            </button>
            <button className={`hero-ghost compact ${autoPlay ? "active" : ""}`} onClick={() => setAutoPlay((current) => !current)}>
              {autoPlay ? t("homePauseDemo") : t("homePlayDemo")}
            </button>
          </div>
          </div>

        <div className="hero-workflow" aria-label={t("homeWorkflowDemo")}>
          <div className="workflow-board">
            <div className="demo-data-packet" aria-hidden="true">
              <span>{t("homeDataPacket")}</span>
              <strong>expression_matrix.csv</strong>
            </div>
            <svg className="workflow-edges" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">
              {visibleEdges.map(([source, target]) => {
                const sourceNode = NODE_GROUPS.find((node) => node.id === source);
                const targetNode = NODE_GROUPS.find((node) => node.id === target);
                if (!sourceNode || !targetNode) return null;
                return (
                  <path
                    key={`${source}-${target}`}
                    d={`M ${sourceNode.x + 8} ${sourceNode.y + 5} C ${sourceNode.x + 22} ${sourceNode.y + 5}, ${targetNode.x - 12} ${targetNode.y + 5}, ${targetNode.x} ${targetNode.y + 5}`}
                  />
                );
              })}
            </svg>
            {visibleNodes.map((node) => (
              <button
                key={node.id}
                type="button"
                className={`workflow-node level-${node.level} ${selectedNodeId === node.id ? "active" : ""}`}
                style={{ left: `${node.x}%`, top: `${node.y}%` }}
                onClick={() => activateNode(node)}
              >
                <span>{t(node.labelKey)}</span>
                <small>{t(node.detailKey)}</small>
              </button>
            ))}
            {selectedNodeHasChart ? (
              <div className="board-chart-popout" aria-live="polite">
                <div className="plot-card-top">
                  <div>
                    <strong>{t(chart.titleKey)}</strong>
                    <span>{chart.subtitle}</span>
                  </div>
                  <button type="button" onClick={onOpenPlot}>
                    Plot Studio
                  </button>
                </div>
                <DemoChart chart={selectedChart} />
              </div>
            ) : null}
          </div>

          <div className={`workflow-inspector ${selectedNodeHasChart ? "chart-expanded" : ""}`}>
            <div>
              <p className="eyebrow">{t("homeSelectedNode")}</p>
              <h2>{t(selectedNode.labelKey)}</h2>
              <p>{t(selectedNode.detailKey)}</p>
            </div>
            <div className="agent-trace" aria-label="Agent workflow trace">
              <span className={visibleNodeIds.has("intake") ? "done" : ""}>1 Data intake</span>
              <span className={visibleNodeIds.has("qc") ? "done" : ""}>2 QC gate</span>
              <span className={unlockedChartCount ? "done" : ""}>3 Plot candidates</span>
              <span className={selectedNodeHasChart ? "done" : ""}>4 Report context</span>
            </div>
            <div className="plot-card-preview">
              <div className="plot-card-top">
                <div>
                  <strong>{t(chart.titleKey)}</strong>
                  <span>{chart.subtitle}</span>
                </div>
                <button type="button" onClick={onOpenPlot}>
                  Plot Studio
                </button>
              </div>
              <div className="plot-preview-meta" aria-label="Plot preview metrics">
                <span>{chartMeta.metric}</span>
                <span>{chartMeta.engine}</span>
                <span>{selectedNodeHasChart ? "expanded preview" : "waiting for chart node"}</span>
              </div>
              <DemoChart chart={selectedChart} />
            </div>
          </div>
        </div>
      </section>

      <section className="capabilities" id="capabilities">
        <FeatureCard title={t("homeAgentIntakeTitle")} text={t("homeAgentIntakeText")} />
        <FeatureCard title={t("analysisCardTitle")} text={t("analysisCardText")} />
        <FeatureCard title={t("plotStudio")} text={t("homePlotStudioText")} />
        <FeatureCard title={t("homeReportAgentTitle")} text={t("homeReportAgentText")} />
      </section>
    </main>
  );
}

function DemoChart({ chart }) {
  if (chart === "volcano") return <VolcanoPreview />;
  if (chart === "heatmap") return <HeatmapPreview />;
  if (chart === "corr") return <CorrelationPreview />;
  if (chart === "boxplot") return <BoxplotPreview />;
  return <PcaPreview />;
}

function PcaPreview() {
  const points = [
    [24, 36, "#3d7eff"],
    [31, 29, "#3d7eff"],
    [37, 42, "#3d7eff"],
    [56, 61, "#18a999"],
    [62, 54, "#18a999"],
    [70, 64, "#18a999"],
    [47, 27, "#ee6c4d"],
    [53, 34, "#ee6c4d"],
  ];
  return (
    <svg className="demo-chart" viewBox="0 0 420 260" role="img" aria-label="PCA chart preview">
      <ChartAxes />
      {points.map(([x, y, color], index) => (
        <circle key={index} cx={x * 4.1} cy={230 - y * 2.7} r="7" fill={color} opacity="0.9" />
      ))}
      <text x="176" y="248">PC1</text>
      <text x="12" y="88" transform="rotate(-90 12 88)">PC2</text>
    </svg>
  );
}

function HeatmapPreview() {
  const values = [0.1, 0.6, 0.9, 0.45, 0.2, 0.72, 0.84, 0.35, 0.12, 0.68, 0.94, 0.52];
  return (
    <svg className="demo-chart" viewBox="0 0 420 260" role="img" aria-label="Heatmap preview">
      <path className="dendrogram" d="M74 28 H130 M130 28 V56 M130 56 H168 M168 56 V86 M168 86 H196" />
      <path className="dendrogram accent" d="M208 28 H260 M260 28 V60 M260 60 H316 M316 60 V86 M316 86 H350" />
      {Array.from({ length: 8 }).map((_, row) =>
        Array.from({ length: 12 }).map((__, col) => {
          const value = values[(row * 3 + col) % values.length];
          const hue = value > 0.5 ? `rgba(238, 108, 77, ${0.35 + value * 0.55})` : `rgba(61, 126, 255, ${0.35 + (1 - value) * 0.55})`;
          return <rect key={`${row}-${col}`} x={52 + col * 27} y={66 + row * 20} width="25" height="18" rx="3" fill={hue} />;
        }),
      )}
    </svg>
  );
}

function VolcanoPreview() {
  const points = Array.from({ length: 54 }).map((_, index) => {
    const x = 210 + Math.sin(index * 1.7) * (28 + (index % 7) * 13);
    const y = 214 - Math.abs(Math.cos(index * 0.82)) * (32 + (index % 9) * 14);
    const signal = index % 8 === 0 || index % 11 === 0;
    return { x, y, signal, up: x > 210 };
  });
  return (
    <svg className="demo-chart" viewBox="0 0 420 260" role="img" aria-label="Volcano plot preview">
      <ChartAxes />
      <line className="threshold" x1="158" x2="158" y1="34" y2="218" />
      <line className="threshold" x1="262" x2="262" y1="34" y2="218" />
      <line className="threshold" x1="48" x2="382" y1="132" y2="132" />
      {points.map((point, index) => (
        <circle
          key={index}
          cx={point.x}
          cy={point.y}
          r={point.signal ? 5 : 3}
          fill={point.signal ? (point.up ? "#ee6c4d" : "#3d7eff") : "#9fb2c3"}
          opacity={point.signal ? 0.92 : 0.42}
        />
      ))}
    </svg>
  );
}

function CorrelationPreview() {
  return (
    <svg className="demo-chart" viewBox="0 0 420 260" role="img" aria-label="Correlation heatmap preview">
      <path className="dendrogram" d="M70 42 H118 V64 H150 M118 42 V22 H184 M210 24 H268 V52 H318" />
      {Array.from({ length: 9 }).map((_, row) =>
        Array.from({ length: 9 }).map((__, col) => {
          const distance = Math.abs(row - col);
          const opacity = 0.95 - distance * 0.075;
          return <rect key={`${row}-${col}`} x={76 + col * 25} y={58 + row * 19} width="23" height="17" rx="3" fill={`rgba(238, 108, 77, ${Math.max(0.18, opacity)})`} />;
        }),
      )}
    </svg>
  );
}

function BoxplotPreview() {
  const groups = [
    { x: 110, color: "#3d7eff", median: 124, top: 82, bottom: 172 },
    { x: 210, color: "#18a999", median: 96, top: 56, bottom: 148 },
    { x: 310, color: "#ee6c4d", median: 146, top: 102, bottom: 198 },
  ];
  return (
    <svg className="demo-chart" viewBox="0 0 420 260" role="img" aria-label="Boxplot preview">
      <ChartAxes />
      {groups.map((group) => (
        <g key={group.x}>
          <line x1={group.x} x2={group.x} y1={group.top - 30} y2={group.bottom + 24} stroke={group.color} strokeWidth="3" />
          <rect x={group.x - 28} y={group.top} width="56" height={group.bottom - group.top} rx="8" fill={group.color} opacity="0.22" stroke={group.color} strokeWidth="3" />
          <line x1={group.x - 28} x2={group.x + 28} y1={group.median} y2={group.median} stroke="#07131f" strokeWidth="3" />
          <circle cx={group.x - 13} cy={group.top - 24} r="4" fill={group.color} />
          <circle cx={group.x + 18} cy={group.bottom + 20} r="4" fill={group.color} />
        </g>
      ))}
    </svg>
  );
}

function ChartAxes() {
  return (
    <>
      <line className="chart-axis" x1="48" x2="382" y1="218" y2="218" />
      <line className="chart-axis" x1="48" x2="48" y1="34" y2="218" />
      <line className="chart-grid" x1="48" x2="382" y1="156" y2="156" />
      <line className="chart-grid" x1="48" x2="382" y1="94" y2="94" />
    </>
  );
}

function FeatureCard({ title, text }) {
  return (
    <article className="feature-card">
      <h2>{title}</h2>
      <p>{text}</p>
    </article>
  );
}
