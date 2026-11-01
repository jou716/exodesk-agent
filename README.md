# ExoDesk Agent

面向康复外骨骼售后场景的双端工单演示系统：坐席工作台与客户会话端共用同一套工单、消息和 Agent 数据。

## 功能

- 坐席工单队列、客户会话、Agent 启动、草稿审核与发送。
- 客户会话端创建工单、发送消息并接收坐席回复。
- Agent 自主规划工具调用，日志展示真实工具名、参数、结果和耗时。
- 支持手册知识库检索、设备档案、工单上下文、术语翻译和内部摘要。
- 三层记忆：会话最近消息、工单内历史摘要、同客户跨工单长期记忆，支持客户隔离与 Token 预算裁剪。
- 客户原语言识别、内部英文工作上下文、最终回复本地化。
- 高风险拦截、输出校验、语言不一致处理和 Agent 超时兜底。

## 记忆设计

- 会话层：保留最近消息，较早内容压缩为摘要，兼顾多轮连续性与上下文成本。
- 工单层：重新开启同一工单时，注入此前会话摘要；内部备注和系统消息不进入客户记忆。
- 客户层：按 `customer_id` 读取同一客户最近 3 个其他工单，提取设备、历史问题与处理结论，作为严格隔离的背景上下文注入规划和生成提示词。
- 所有历史记忆均标注为“过往工单”，不覆盖当前问题；超长历史按字符预算裁剪，避免重复注入和 Token 膨胀。

## 技术栈

- 后端：FastAPI、SQLAlchemy、MySQL、LangGraph、Chroma
- 前端：React、TypeScript、Vite
- LLM：兼容 OpenAI 协议的通义千问接口，默认模型为 `qwen-max`

## 目录

```text
backend/       FastAPI、Agent、工具、数据与测试
frontend/      React 双端界面
docs/          模块验收与设计记录
evaluation/    离线评测资料
```

## 本地运行

先准备 MySQL 数据库，并复制环境变量模板：

```powershell
cd backend
Copy-Item .env.example .env
```

按本机环境填写 `DATABASE_URL`、可选的 `LLM_API_KEY` 等配置，然后安装并启动后端：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m app.seed.seed --force
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

启动前端：

```powershell
cd frontend
pnpm install
pnpm dev --host 127.0.0.1
```

打开 `http://127.0.0.1:5173`。演示登录口令为 `123456`。

## 验证

```powershell
cd backend
$env:PYTHONIOENCODING="utf-8"
.\.venv\Scripts\python.exe -m pytest -q

cd ..\frontend
pnpm typecheck
pnpm build
```

## 说明

- 仓库不包含 `.env`、本地数据库、Chroma 索引、依赖目录和运行日志。
- 当前手册、设备档案、样例工单和术语表均为合成演示数据。
- 本项目的客户身份仍属于演示实现，正式部署时需接入真实认证与权限体系。
