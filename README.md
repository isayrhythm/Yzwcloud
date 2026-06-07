# YZW BioCloud

智能体辅助的生物信息分析工作台。当前重点是把表达矩阵上传、数据检查、流程节点分析、Plot Studio 作图和报告输出跑通。

## 当前能力

- 表达矩阵上传和 intake agent 检查
- React Flow 分析流程画布
- bulk RNA 主流程：QC、PCA、样本相关性、表达热图、差异分析、火山图、差异热图、单基因表达、WGCNA、结果导出
- Plot Studio：从上传表格或分析节点输出生成可交互图形
- 节点级 Agent 报告和任务级 HTML/PDF 报告
- FastAPI 后端托管构建后的前端静态文件

## 环境要求

- Python `>= 3.12`
- Node.js `>= 18`
- R `>= 4.3`
- 命令行可找到 `Rscript`

R 包依赖主要包括：

```text
DESeq2, WGCNA, jsonlite, BiocManager, impute, preprocessCore, GO.db, AnnotationDbi
```

## 安装

```bash
pdm install
npm install
pdm run install-r
```

如果 `Rscript` 不在 PATH，先设置环境变量：

Windows PowerShell:

```powershell
$env:YZWCLOUD_RSCRIPT = "C:\Program Files\R\R-4.x.x\bin\Rscript.exe"
```

Linux/WSL:

```bash
export YZWCLOUD_RSCRIPT=/usr/bin/Rscript
```

## 本地开发

开发模式需要两个终端。

终端 1：启动后端。

```bash
pdm run dev
```

终端 2：启动前端。

```bash
npm run dev:web
```

默认地址：

```text
前端 http://127.0.0.1:10000
后端 http://127.0.0.1:10001
```

开发时前端只请求同源 `/api` 和 `/static`，由 Vite 代理到后端。

## WSL 和 Windows 端口

默认开发服务监听 `0.0.0.0`，方便 Windows 浏览器访问 WSL 服务。

如果 `http://127.0.0.1:10000` 打开的不是当前项目，通常是 Windows 或 VS Code 已经占用了端口转发。处理方式：

1. 在 VS Code Ports 面板关闭旧的 `10000` / `10001` 转发。
2. 或者直接用 Vite 输出的 WSL IP 地址，例如：

```text
http://172.xx.xx.xx:10000
```

确认当前前端是否正确：

```bash
curl http://127.0.0.1:10000/api/tasks
```

返回 `200` 就说明前端代理和后端都通了。

## 端口和代理配置

不需要改源码，通过环境变量覆盖。

```bash
YZWCLOUD_FRONTEND_HOST=127.0.0.1 npm run dev:web
YZWCLOUD_FRONTEND_PORT=3000 npm run dev:web
YZWCLOUD_BACKEND_HOST=127.0.0.1 pdm run dev
YZWCLOUD_BACKEND_PORT=9000 pdm run dev
YZWCLOUD_DEV_BACKEND_URL=http://127.0.0.1:9000 npm run dev:web
```

默认值：

```text
YZWCLOUD_FRONTEND_HOST=0.0.0.0
YZWCLOUD_FRONTEND_PORT=10000
YZWCLOUD_BACKEND_HOST=0.0.0.0
YZWCLOUD_BACKEND_PORT=10001
```

## 生产构建和服务器部署

在服务器部署目录执行：

```bash
git pull
pdm install
npm install
npm run build:web
pdm run start
```

后台运行：

```bash
pdm run start-bg
```

重启后台服务：

```bash
pdm run restart-bg
```

停止后台服务：

```bash
pdm run stop-bg
```

服务默认监听：

```text
http://0.0.0.0:10001
```

构建后的前端由 FastAPI 直接托管：

- `/` 返回前端页面
- `/static` 返回前端构建产物和静态资源
- `/api` 返回后端 API

如果使用 Nginx，可以把外部 `10000` 或域名反代到后端 `10001`。前端已经使用同源 `/api` 和 `/static`，不需要再改 JSX 里的地址。

最小 Nginx 示例：

```nginx
server {
    listen 10000;
    server_name _;

    location / {
        proxy_pass http://127.0.0.1:10001;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

## 日志

后台启动的日志写在 `logs/`：

```text
logs/server-<port>-<timestamp>.log
logs/server-<port>.pid
```

清理日志：

```bash
pdm run clean-logs
```

清理指定端口日志：

```bash
pdm run python -m yzwcloud.dev_server clean-logs --port 10001
```

## 测试

常用测试：

```bash
pdm run pytest
```

这次端口和前端契约相关的测试：

```bash
pdm run pytest tests/test_frontend_contracts.py tests/test_dev_server.py
```

## 主要 API

- `GET /api/health`
- `GET /api/tasks`
- `POST /api/tasks`
- `GET /api/tasks/{task_id}`
- `PATCH /api/tasks/{task_id}`
- `DELETE /api/tasks/{task_id}`
- `GET /api/tasks/{task_id}/logs`
- `POST /api/tasks/{task_id}/inputs`
- `POST /api/tasks/{task_id}/nodes/{node_id}/run`
- `DELETE /api/tasks/{task_id}/nodes/{node_id}`
- `POST /api/tasks/{task_id}/analysis-nodes`
- `POST /api/tasks/{task_id}/diff-analyses`
- `GET /api/tasks/{task_id}/comparison-options`
- `GET /api/tasks/{task_id}/sample-groups`
- `PUT /api/tasks/{task_id}/sample-groups`
- `GET /api/plot-studio/presets`

## 代码结构

```text
src/yzwcloud/
├─ analyses/              # 分析模块
├─ data_intake_agent.py   # 数据识别和处理状态机
├─ data_intake_registry.py
├─ executor.py            # 节点执行
├─ main.py                # FastAPI 应用
├─ node_registry.py       # 工作流节点定义
├─ plot_studio_*.py       # Plot Studio 预设、渲染和报告
├─ report_agent.py        # 节点报告
├─ task_report.py         # 任务报告
└─ task_store.py          # 任务持久化

web/src/
├─ main.jsx               # 前端入口和主工作台
├─ pages/                 # 页面
├─ components/            # 通用组件
├─ plotStudio/            # Plot Studio 前端逻辑
└─ workflow/              # 工作流布局和状态辅助
```

## 当前边界

当前项目仍是本地/单机工作台形态，不包含：

- 分布式任务调度
- 多用户权限系统
- 完整单细胞分析流程
- 富集数据库在线接入
- 任意代码生成并执行的黑箱 agent
