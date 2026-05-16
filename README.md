# 崖州湾生物信息云平台 MVP

这是一个轻量版起步实现，先解决“任务互不干扰”和“流程节点状态可恢复”。

## 当前能力

- 每次创建任务都会生成独立 `task_id` 和独立目录。
- 每个任务独立保存 `graph.json`、`status.json`、`outputs/`、`logs/`。
- 后端使用 FastAPI，任务执行使用轻量后台任务，不引入 Celery/Redis。
- 前端使用 Vite + React + React Flow，构建产物由 FastAPI 直接托管。
- 内置一个示例 DAG：读取表达矩阵 -> 差异分析 -> 热图/火山图/富集分析。
- 当前默认表达矩阵来源为项目根目录的 `expression_matrix.csv` 和 `sample_metadata.csv`。
- 差异分析节点是一个选择器：选择 case/control 分组后，会衍生一个独立比较分支，并自动生成该分支的热图、火山图、富集分析节点。

## 目录结构

```text
.
├── src/yzwcloud/
│   ├── main.py              # FastAPI 入口
│   ├── models.py            # 数据模型
│   ├── node_registry.py     # 节点定义和示例执行逻辑
│   ├── executor.py          # 节点执行与状态流转
│   ├── task_store.py        # 任务目录和 JSON 持久化
│   └── static/              # 静态前端
├── data/tasks/              # 运行后自动生成，保存任务数据
├── pyproject.toml
└── 需求文档.md
```

## 运行

项目配置要求 Python 3.12。

```bash
pdm install
npm install
npm run build:web
pdm run dev
```

启动后打开：

```text
http://127.0.0.1:8000
```

## API

- `GET /api/health`：健康检查。
- `POST /api/tasks`：创建任务。
- `GET /api/tasks`：任务列表。
- `GET /api/tasks/{task_id}`：查看任务详情。
- `DELETE /api/tasks/{task_id}`：删除任务及其独立目录。
- `POST /api/tasks/{task_id}/diff-analyses`：按 case/control 分组创建并执行一个差异分析分支。
- `POST /api/tasks/{task_id}/analysis-nodes`：从已完成节点按需创建后续分析节点。
- `POST /api/tasks/{task_id}/nodes/{node_id}/run`：执行节点。
- `DELETE /api/tasks/{task_id}/nodes/{node_id}`：删除节点及其下游子节点。
- `GET /api/tasks/{task_id}/logs`：查看任务日志。

## 后续升级方向

- 把模拟节点替换成真实生信脚本或容器命令。
- 增加真实文件上传与输入格式识别。
- 前端升级为 React/Next.js + React Flow。
- 当并发任务变多时，再把后台任务升级为 Celery/RQ/Arq + Redis。
