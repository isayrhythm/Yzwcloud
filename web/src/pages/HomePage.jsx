import { useI18n } from "../i18n.jsx";

export function HomePage({ onStart, onOpenPlot }) {
  const { t } = useI18n();
  return (
    <main className="landing">
      <section className="landing-hero">
        <div className="hero-copy">
          <p className="eyebrow">YZW BioCloud</p>
          <h1>{t("homeTitle")}</h1>
          <p>{t("homeSummary")}</p>
          <div className="hero-actions">
            <button className="primary launch" onClick={onStart}>{t("startAnalysis")}</button>
            <button className="hero-ghost" onClick={onOpenPlot}>{t("openPlotStudio")}</button>
            <a href="#capabilities">{t("guide")}</a>
          </div>
        </div>
        <div className="hero-visual" aria-hidden="true">
          <div className="orbit orbit-a" />
          <div className="orbit orbit-b" />
          <div className="data-card card-a">
            <span>PCA</span>
            <strong>52 samples</strong>
          </div>
          <div className="data-card card-b">
            <span>Volcano</span>
            <strong>5k genes</strong>
          </div>
          <div className="data-card card-c">
            <span>Plot Studio</span>
            <strong>Plotly / ECharts</strong>
          </div>
          <div className="pipeline-line" />
          <div className="node-glow n1" />
          <div className="node-glow n2" />
          <div className="node-glow n3" />
        </div>
      </section>

      <section className="capabilities" id="capabilities">
        <FeatureCard title="Agent Intake" text="Uploaded tables are inspected first, then classified into analysis-ready data types with readable failure reports." />
        <FeatureCard title={t("analysisCardTitle")} text={t("analysisCardText")} />
        <FeatureCard title={t("plotStudio")} text="Plotly.js / ECharts templates with Prism-like parameter control." />
        <FeatureCard title="Report Agent" text="Outputs, warnings, graph state, and logs are collected into a stable context for future automated interpretation." />
      </section>
    </main>
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
