const ANALYSIS_STEPS = [
  {
    title: "1. 准备表格",
    text: "推荐使用 CSV、TSV 或 Excel。第一列放基因、蛋白或代谢物名称，后面的列放样本；样本名不要重复。",
  },
  {
    title: "2. 创建分析任务",
    text: "进入分析台后点击“新建分析任务”，输入任务名。任务会出现在左侧任务列表，后续结果都会归档到这个任务下。",
  },
  {
    title: "3. 上传矩阵",
    text: "在上传节点选择表达矩阵或强度矩阵文件。系统会读取列名、识别数值列，并生成可继续分析的标准化输入。",
  },
  {
    title: "4. 检查样本分组",
    text: "如果有 metadata，可以一并上传；也可以在样本分组里手动调整 condition。差异分析前至少需要两个分组。",
  },
  {
    title: "5. 执行常用分析",
    text: "先运行 QC，再按需要添加 PCA、样本相关性、热图、差异分析、火山图等节点。每个节点运行后都能打开预览。",
  },
  {
    title: "6. 导出报告",
    text: "分析完成后进入报告页，选择任务，查看流程、节点结果、日志摘要和可导出的 HTML / PDF 报告。",
  },
];

const PLOT_STUDIO_STEPS = [
  {
    title: "1. 选择数据源",
    text: "从当前任务输出里选择一个结果表，也可以上传独立表格，或直接使用内置示例数据试图。",
  },
  {
    title: "2. 选择图表类型",
    text: "根据数据字段选择 PCA、火山图、热图、箱线图、散点图、相关性图等图型。推荐图型会优先显示。",
  },
  {
    title: "3. 调整参数",
    text: "在参数面板里修改字段映射、颜色、标题、坐标轴、阈值、标签和图例。基础参数用于快速出图，高级参数用于精修。",
  },
  {
    title: "4. 套用样式模板",
    text: "可以选择 publication、prism clean 等样式模板，一键统一字号、边距、配色和默认导出格式。",
  },
  {
    title: "5. 导出高清图",
    text: "点击高清图导出，默认导出 TIF。DPI 可选 150、300、600、1000；投稿图通常从 300 或 600 开始。",
  },
  {
    title: "6. 保存回分析结果",
    text: "从任务结果进入 Plot Studio 时，可以把当前图和参数上下文保存回原分析节点，方便后续报告引用。",
  },
];

const ANALYSIS_CHECKS = ["矩阵第一列是特征名", "样本列都是数值", "分组名和样本名能对应", "先完成 QC 再继续下游分析"];
const PLOT_STUDIO_CHECKS = ["数据源已选中", "字段映射没有空缺", "标题和坐标轴单位已确认", "导出前检查格式和 DPI"];

export function DocsPage({ onStart, onOpenPlot }) {
  return (
    <main className="docs-page">
      <section className="docs-hero">
        <div>
          <p className="eyebrow">Workflow Guide</p>
          <h1>操作文档</h1>
          <p>按照下面两个模块操作，可以完成从数据上传、流程分析到 Plot Studio 精修作图和导出的完整演示。</p>
        </div>
        <div className="docs-actions">
          <button className="primary compact" onClick={onStart} type="button">
            进入分析台
          </button>
          <button className="secondary compact" onClick={onOpenPlot} type="button">
            打开 Plot Studio
          </button>
        </div>
      </section>

      <GuideModule
        actionLabel="进入分析台"
        checks={ANALYSIS_CHECKS}
        eyebrow="Module 01"
        example="示例：上传转录组表达矩阵，完成 QC、PCA、差异分析，然后生成火山图和热图。"
        onAction={onStart}
        steps={ANALYSIS_STEPS}
        title="数据分析模块"
      />

      <GuideModule
        actionLabel="打开 Plot Studio"
        checks={PLOT_STUDIO_CHECKS}
        eyebrow="Module 02"
        example="示例：选择差异分析结果表，生成火山图，调整阈值、标签和配色，最后导出 600 DPI TIF。"
        onAction={onOpenPlot}
        steps={PLOT_STUDIO_STEPS}
        title="Plot Studio 模块"
      />
    </main>
  );
}

function GuideModule({ actionLabel, checks, eyebrow, example, onAction, steps, title }) {
  return (
    <section className="doc-module">
      <div className="doc-module-header">
        <div>
          <p className="eyebrow">{eyebrow}</p>
          <h2>{title}</h2>
          <p>{example}</p>
        </div>
        <button className="primary compact" onClick={onAction} type="button">
          {actionLabel}
        </button>
      </div>

      <div className="doc-step-list">
        {steps.map((step) => (
          <article className="doc-step" key={step.title}>
            <h3>{step.title}</h3>
            <p>{step.text}</p>
          </article>
        ))}
      </div>

      <div className="doc-checklist" aria-label={`${title}检查清单`}>
        <strong>操作前检查</strong>
        <ul>
          {checks.map((check) => (
            <li key={check}>{check}</li>
          ))}
        </ul>
      </div>
    </section>
  );
}
