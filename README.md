# YZW BioCloud

下一代智能体驱动的生物信息云平台。

YZW BioCloud 当前聚焦转录组表达矩阵分析，先把“上传数据 -> Agent 检查 -> 按需创建分析节点 -> 生成真实可视化结果 -> 汇总报告上下文”这条链路跑通，并为后续更多数据类型和分析模块保留扩展骨架。

## 核心优势

相较于 Galaxy、TBtools 和传统生信云平台，YZW BioCloud 的目标不是把大量工具简单堆成菜单，而是让智能体参与分析流程的关键决策。

- 输入端由 intake agent 识别数据类型、检查文件结构、规整表达矩阵，并在失败时生成用户可读的处理报告
- 分析方向由数据本身驱动，根据样本数、分组数量、数据质量和已完成节点动态推荐下一步分析
- 工作流以可视化节点编排呈现，用户可以从 QC、PCA、热图、差异分析、WGCNA 到报告上下文逐步扩展，而不是一次性面对完整工具列表
- 分析节点保留参数、输入、输出和日志，后续可以接入 report agent，把“实验设计 + 数据分析 + 结果解释”串成闭环
- 当前首期聚焦表达矩阵和转录组分析，后续预留更多数据类型和分析模块扩展，但不在早期强行写死多组学联动

## 当前能力

- React Flow 流程画布，节点可拖动、可删除、可按 `+` 创建后续分析
- 数据上传节点，支持上传后由 intake agent 自动识别和规整
- bulk RNA 表达矩阵主流程
  - PCA
  - 差异分析
  - 差异热图
  - 火山图
  - 矩阵 QC
  - 样本相关性
  - 表达热图
  - 单基因表达
  - 差异结果导出
- 上传失败时提供用户可读报告，而不是只返回 Python 报错

## 当前支持的输入

上传节点当前接受：

- `.csv`
- `.xlsx`
- `.xlsm`
- `.zip`
- `.tar`
- `.tar.gz`
- `.tgz`
- `.gz`

其中压缩包会先进入预处理阶段：

1. 解压到任务私有目录
2. 自动挑选当前最像数据文件的成员
3. 再进入正式 intake 循环

注意：

- 现在真正接通标准化处理器的是 `bulk RNA expression matrix`
- 单细胞相关文件目前可以被识别、报告、拦停，但还没有进入后续分析流程

## Intake Agent

上传节点不是死板的“读取表达矩阵”，而是一个受控循环的 intake agent。

当前主流程：

1. `prepare_input`
   负责压缩包解压、输入展开、选择候选成员文件
2. `inspect`
   读取文件基本事实，例如行列规模、表头、数值列比例、预览信息
3. `classify`
   判断更像哪一类数据
4. `plan`
   生成当前可尝试的处理策略
5. `process`
   依次执行策略，而不是一次性硬跑
6. `validate`
   检查结果是否满足当前分析流程输入要求
7. `retry_or_stop`
   可恢复则换策略再试；不可恢复或达到轮次上限则停止

当前已识别的数据类型标签包括：

- `expression_matrix`
- `single_cell_matrix`
- `feature_table`
- `sample_metadata`
- `diff_result`
- `gene_list`
- `unknown_table`

## 失败报告

如果上传文件无法进入当前分析流程，前端节点会提供可点击报告。报告面向用户，而不是只展示异常字符串。

报告会尽量说明：

- 为什么现在不能分析
- Agent 实际看到了什么
- 已尝试过哪些处理策略
- 建议用户怎样整理文件
- 原始报错是什么

## 代码结构

这次整理后，分析输出已经从单个大文件拆成了模块化结构：

```text
src/yzwcloud/
├─ analyses/
│  ├─ __init__.py
│  ├─ common.py
│  ├─ differential.py
│  ├─ expression.py
│  ├─ rendering.py
│  └─ wgcna.py
├─ analysis_outputs.py
├─ config.py
├─ data_intake_agent.py
├─ data_intake_registry.py
├─ executor.py
├─ expression_matrix.py
├─ main.py
├─ models.py
├─ node_registry.py
├─ prompts.py
└─ task_store.py
```

职责边界：

- `data_intake_agent.py`
  - intake 主状态机
  - checkpoint、失败报告、循环控制
- `data_intake_registry.py`
  - 数据类型到策略、能力、停止原因的注册信息
- `analyses/common.py`
  - 分析共享数据结构、统计和读写辅助
- `analyses/differential.py`
  - 差异分析、火山图、差异热图、结果导出
  - 转录组/蛋白组差异统计均通过 `Rscript` 调用 `r/differential_transcriptomics.R` 或 `r/differential_protein.R`，Python 只负责输入整理、结果归一化和前端输出
- `analyses/expression.py`
  - PCA、矩阵 QC、样本相关性、表达热图、单基因表达
- `analyses/rendering.py`
  - 共用的热图渲染输出
- `analyses/wgcna.py`
  - 调用 `Rscript + WGCNA` 做标准共表达模块计算，再由 Python 生成交互 HTML
- `r/differential_transcriptomics.R`
  - R 转录组差异脚本；仅在输入矩阵为 count-like 非负整数时优先使用 `DESeq2`，否则降级为 R 内置双样本检验，避免对 log/标准化表达矩阵误用 DESeq2
- `r/differential_protein.R`
  - R 蛋白组差异脚本；使用 R 内置双样本检验和 fold-change 阈值输出上下调结果
- `r/run_wgcna.R`
  - R WGCNA 执行脚本，输出模块表、hub gene、module-trait correlation、soft-threshold 结果
- `analysis_outputs.py`
  - 兼容导出层，避免调用方跟着一起改

## 前端结构

前端目前仍然是单入口 React 应用：

- `web/src/main.jsx`
- `web/src/styles.css`

当前交互重点已经稳定：

- `Ctrl + 滚轮` 缩放 React Flow
- 普通滚轮滚动整页
- `+` 号按需创建后续节点
- 删除节点时同步删除其下游子节点
- 右下角 attribution 已隐藏
- MiniMap 仅在移动/拖动画布时短暂显示

前端后续仍值得继续拆，但这轮先优先收后端分析模块和文档，不额外扩大改动面。

## Plot Studio

Plot Studio is the standalone visualization workspace for downstream figures and analysis-node outputs.
It is separate from Molecular Lab: Molecular Lab remains the wet-lab utility area for primers, sequence tools, restriction scans, and cloning-related helpers.

Current positioning:

- Agent-first data intake: upload a table or send an upstream node output into Plot Studio, then let the system infer columns, variable types, grouping columns, and candidate plots.
- Interactive plotting stack: use mature JavaScript plotting libraries such as Plotly.js and ECharts for charts that need hover, zoom, export, and rich parameter control.
- Prism-like parameter depth: each plot type should expose controls for axis mapping, grouping, color palette, jitter, summary statistics, error bars, labels, themes, export size, and output format.
- Searchable plot toolbox: Plot Studio presents plot types as clickable thumbnails, with search and recommended-only filtering so users can quickly find the right chart.
- Style recipes: `Publication`, `Presentation`, and `Exploration` presets provide reusable visual defaults for common output contexts.
- Plot library presets: scatter, boxplot, grouped dot plot, Raincloud, violin, Ridgeline, bar, line, histogram, density curve, ECDF, calendar heatmap, heatmap, correlation heatmap, bubble, volcano, UpSet, Venn, lollipop, Dumbbell, enrichment dot plot, enrichment bar plot, composition bar, Donut/Pie, Sankey, treemap, sunburst, and word cloud are included in the current preset family.
- DataColor-inspired workbench layout: the studio keeps a stable left toolbox, central method/preview area, and right inspector. Each selected plot exposes a compact Application/Input/Output overview before rendering, so users understand what the chart expects and what it will produce.
- Hierarchy plots: Treemap and Sunburst are intended for enrichment categories, pathway hierarchies, taxonomic composition, and other parent-child summaries.
- Term overview plots: Word cloud provides a quick interactive overview for enriched terms, genes, taxa, and keyword-frequency tables, with hover details and adjustable font/layout controls.
- Workflow integration: analysis nodes keep their default diagnostic plots, while polished custom figures can be sent to Plot Studio for deeper editing and report reuse.

## Development And Test Notes

- Do not run project tests with short timeouts that can truncate a valid long run. If a test appears stuck, report how long it has been running and where it seems blocked, then ask before stopping it.
- Do not delete test or demo workflows/tasks by default. Leave generated workflows for inspection unless cleanup is explicitly requested.

## Node Report Agent

Every completed workflow node writes a structured Agent summary in JSON and a printable HTML report.
The report records the node output, method metadata, evidence-backed findings, interpretation boundaries, and next-step suggestions.

- When `DEEPSEEK_API_KEY` is configured, the node report agent requests a concise LLM interpretation from DeepSeek.
- When the key is missing or the request fails, the workflow keeps a rule-based fallback report so results remain inspectable and exportable.
- `DEEPSEEK_REPORT_MODEL` can override the report model independently from `DEEPSEEK_ROUTER_MODEL`.

The Reports workspace can also generate a task-level presentation report:

- `GET /api/tasks/{task_id}/report.html` returns a 16:9 paginated HTML report with workflow lineage, method history, Agent summaries, and embedded result previews.
- `GET /api/tasks/{task_id}/report.pdf` uses local Edge or Chrome headless printing when available.
- In the workflow canvas, the `流程报告` entry sits beside the `流程节点` title and opens the HTML report.
- The HTML report always keeps a `打印 / 保存为 PDF` action as the portable PDF export path.

## 本地运行

要求：

- Python `>= 3.12`
- Node.js `>= 18`
- R `>= 4.3`，并且命令行可找到 `Rscript`
- R packages: `DESeq2`, `WGCNA`, `jsonlite`, `BiocManager`, `impute`, `preprocessCore`, `GO.db`, `AnnotationDbi`

安装依赖：

```bash
pdm install
npm install
```

安装 R 依赖：
```bash
pdm run install-r
```

等价底层命令为 `Rscript src/yzwcloud/r/install_wgcna_packages.R`。该脚本会安装差异分析与 WGCNA 所需的 R 包。

如果 `Rscript` 不在 PATH，可以设置：
```bash
set YZWCLOUD_RSCRIPT=C:\Program Files\R\R-4.x.x\bin\Rscript.exe
```

构建前端：

```bash
npm run build:web
```

启动后端开发服务：

```bash
pdm run dev
```

默认开发端口在 `pyproject.toml` 里是：

```text
http://127.0.0.1:8010
```

前端开发代理和后端服务都默认走 `8010`。本地运行日志统一放在 `logs/` 目录，仓库只保留 `logs/.gitkeep`，生成的 `server-*.log` 不提交。

清理本地服务日志：

```bash
pdm run clean-logs
```

后台启动 8010（日志写入 `logs/server-8010-*.log`，pid 写入 `logs/server-8010.pid`）：

```bash
pdm run start-bg
```

重启 8010 并清理旧的 `server-*.log`（包括历史端口日志）：

```bash
pdm run restart-bg
```

如果之前开过其他端口的临时服务，可以清理所有 `server-*.log`：

```bash
pdm run python -m yzwcloud.dev_server clean-logs --all-ports
```

## 主要 API

- `GET /api/health`
- `POST /api/tasks`
- `GET /api/tasks`
- `GET /api/tasks/{task_id}`
- `DELETE /api/tasks/{task_id}`
- `POST /api/tasks/{task_id}/inputs/{input_kind}`
- `POST /api/tasks/{task_id}/nodes/{node_id}/run`
- `DELETE /api/tasks/{task_id}/nodes/{node_id}`
- `POST /api/tasks/{task_id}/analysis-nodes`
- `POST /api/tasks/{task_id}/diff-analyses`
- `GET /api/tasks/{task_id}/comparison-options`
- `GET /api/tasks/{task_id}/sample-groups`
- `PUT /api/tasks/{task_id}/sample-groups`
- `GET /api/tasks/{task_id}/logs`

## 当前边界

这个项目现在的合理定位是：

- 轻执行内核
- 可扩展数据入口
- 以 bulk RNA 为主线的演示型工作台

暂时不做重型能力：

- 分布式任务调度
- 富集数据库接入
- 真正完整的单细胞分析链路
- 自由生成代码并执行的“黑箱 agent”

## 下一步最合理的方向

如果继续往下做，优先级建议是：

1. 完善 `single_cell_matrix` 和 `feature_table` 的 inspector summary
2. 把更多数据类型接进 registry，而不是继续堆在 intake 主流程里
3. 拆前端 `main.jsx` 和历史编码文案
4. 把 bulk RNA 统计流程继续从演示实现推进到更严格的分析实现
