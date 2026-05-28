export function DocsPage({ onStart }) {
  return (
    <main className="docs-page">
      <section className="docs-hero">
        <p className="eyebrow">Workflow Guide</p>
        <h1>操作文档</h1>
        <p>按下面顺序做，可以完成表达矩阵读取、PCA、分组差异分析、热图和火山图演示。</p>
        <button className="primary compact" onClick={onStart}>进入分析台</button>
      </section>
      <section className="doc-grid">
        <DocStep index="01" title="创建任务" text="进入分析台后点击创建示例任务，任务会出现在左侧列表。" />
        <DocStep index="02" title="上传数据" text="在数据上传节点选择数据文件，Agent 会自动识别类型、规整格式，并判断下一步可做哪些分析。" />
        <DocStep index="03" title="创建 PCA" text="表达矩阵节点完成后点击节点上的 +，选择 PCA，执行后点击预览打开交互图。" />
        <DocStep index="04" title="做差异分析" text="点击 + 选择差异分析，再选择 case/control 分组，例如 cancer vs normal。" />
        <DocStep index="05" title="生成图表" text="差异分析完成后点击该分支节点的 +，选择热图或火山图，执行后点击预览查看大图。" />
        <DocStep index="06" title="管理流程" text="节点可以拖动，Ctrl + 滚轮缩放；删除节点时，下游子节点会一起删除。" />
      </section>
    </main>
  );
}

function DocStep({ index, title, text }) {
  return (
    <article className="doc-step">
      <span>{index}</span>
      <h2>{title}</h2>
      <p>{text}</p>
    </article>
  );
}

