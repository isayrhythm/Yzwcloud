# YZWcloud

面向生信演示场景的轻量流程工作台。当前实现重点不在重调度，而在这三件事：

- 任务之间互不干扰
- 流程节点按需创建，不一次性铺满画布
- 数据上传后先经过 intake agent 检查、识别、规整、验证，再决定后续能做什么分析

## 当前状态

当前前后端已经不是最初的静态示例 DAG，而是一个可运行的 React Flow 工作台：

- 前端：`Vite + React + React Flow`
- 后端：`FastAPI`
- 任务存储：每个任务独立目录，保存图、日志、输入、输出
- 执行方式：FastAPI 轻量后台任务

已支持的主流程：

- 数据上传节点
- PCA 节点
- 差异分析选择器与分支节点
- 热图节点
- 火山图节点

## 数据上传与 Intake Agent

第一个节点是“数据上传”，不是固定死的“读取表达矩阵”。

上传后会进入一个受控的 intake agent 流程：

1. `inspect`
   读取文件基本信息、抽样、列特征、数值比例、表头模式。
2. `classify`
   判断更像哪类数据。
3. `plan`
   生成当前可尝试的处理策略列表。
4. `process`
   依次执行策略，而不是一次性硬跑。
5. `validate`
   验证处理后的结果是否真的能接入当前分析流程。
6. `stop / retry`
   成功则返回能力；失败则继续下一策略，直到达到最大轮次或确认不支持。

当前 intake 已经支持：

- `expression_matrix`
- `single_cell_matrix`
- `feature_table`
- `unknown_table`

说明：

- 目前真正接了标准化处理器的是 `expression_matrix`
- `single_cell_matrix` 和 `feature_table` 已经能被识别和拦下，但还没有进入后续分析的处理器

## 当前 Intake 架构

intake 不再是单个 if/else 大流程，而是按“注册表 + 状态机”组织：

- `src/yzwcloud/data_intake_agent.py`
  负责循环控制、checkpoint、失败报告、调用策略
- `src/yzwcloud/data_intake_registry.py`
  负责数据类型到策略列表、能力映射、停止原因等注册信息
- `src/yzwcloud/prompts.py`
  负责 LLM 分类提示词

后续新增数据类型时，主要补这几层：

- 识别规则
- 处理策略
- 验证规则
- 能力映射

而不是重写整个 intake 主流程。

## 失败报告

如果上传数据无法进入当前分析流程，前端不会只显示 Python 报错。

节点上的报告会告诉用户：

- 为什么现在不能分析
- Agent 实际看到了什么
- 建议怎么改文件
- 原始报错
- 已尝试过哪些处理策略

## 现有交互特点

- 节点可拖动
- `Ctrl + 滚轮` 缩放 React Flow
- 后续节点通过 `+` 按需创建
- 删除节点时会连同下游子节点一起删除
- 差异分析不会自动冒出来，必须由用户主动创建
- 上传失败时可点击查看报告

## 目录结构

```text
.
├── src/yzwcloud/
│   ├── main.py                   # FastAPI 入口
│   ├── models.py                 # Pydantic 数据模型
│   ├── node_registry.py          # 节点定义与节点执行路由
│   ├── executor.py               # 节点执行、状态流转、agent 进度
│   ├── task_store.py             # 任务目录与图持久化
│   ├── expression_matrix.py      # 上传节点入口，接入 intake agent
│   ├── data_intake_agent.py      # intake 循环控制与失败报告
│   ├── data_intake_registry.py   # 数据类型/策略/能力注册表
│   ├── prompts.py                # LLM 提示词
│   ├── analysis_outputs.py       # PCA/热图/火山图等输出生成
│   └── static/                   # 构建后的前端静态资源
├── web/                          # React 前端源码
├── data/tasks/                   # 运行后自动生成的任务目录
├── pyproject.toml
└── README.md
```

## 运行

要求：

- Python `>= 3.12`
- Node.js `>= 18`

安装依赖：

```bash
pdm install
npm install
```

前端构建：

```bash
npm run build:web
```

开发模式启动后端：

```bash
pdm run dev
```

默认地址：

```text
http://127.0.0.1:8000
```

如果你要和当前本地调试习惯保持一致，也可以手动起到 `8010`。

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

## 下一步建议

最值得继续做的不是再修一点 UI，而是补齐 intake 的多数据类型处理器：

- `single_cell_matrix` 的 inspector summary 与处理策略
- `feature_table` 的标准化与可视化能力
- bulk RNA 的更严格质量检查
- 差异分析输出结果表标准化

等这些补起来之后，平台的“能上传什么、能做什么、为什么不能做”才会真正稳定。
