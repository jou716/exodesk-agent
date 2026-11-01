# U6 API、Webhook、SSE 与审计验收

状态：**已人工验收**（2026-10-31）。U7 已开始。

## 本单元范围

- FastAPI 应用入口、CORS、健康检查和统一错误响应。
- 工单列表/详情、客户消息写入、Agent 运行启动与查询。
- SSE 实时推送运行状态、节点/工具步骤、草稿和完成事件。
- 草稿采纳、拒绝、升级反馈；同一草稿只允许一次审核动作。
- 采纳默认只返回 `reply_text` 给回复框，不发送客户消息。
- 显式 `write_internal_note=true` 时才写内部备注，且备注不进入客户记忆。
- Webhook HMAC-SHA256 验签、时间窗、载荷上限、事件幂等和消息幂等。
- 运行级和工单级审计接口。
- 同一工单启动 Agent 时使用工单行锁，避免并发创建两个 active run。

## API

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/health` | 健康检查与当前 provider |
| GET | `/api/tickets` | 工单列表，支持 `status`、`limit` |
| GET | `/api/tickets/{ticket_id}` | 工单、设备、消息、会话、最近运行/草稿 |
| POST | `/api/tickets/{ticket_id}/messages` | 写入虚拟客户消息，支持 `external_msg_id` 幂等 |
| POST | `/api/tickets/{ticket_id}/runs` | 创建并后台执行 Agent，返回 `202` |
| GET | `/api/tickets/{ticket_id}/runs` | 工单运行历史 |
| GET | `/api/runs/{run_id}` | 运行、步骤和草稿 |
| GET | `/api/runs/{run_id}/events` | SSE 运行事件流 |
| GET | `/api/drafts/{draft_id}` | 草稿详情 |
| POST | `/api/drafts/{draft_id}/feedback` | `accept` / `reject` / `escalate` |
| GET | `/api/runs/{run_id}/audit` | 运行轨迹、草稿、反馈和写回审计 |
| GET | `/api/tickets/{ticket_id}/audit` | 工单消息、会话、运行、反馈和 Webhook 审计 |
| POST | `/api/webhooks/tickets` | 验签后的工单/消息事件入口 |

SSE 事件依次包括 `run`、若干 `step`、可选的 `draft` 和最终的 `done`。步骤事件 `id` 为 `seq`，可使用 `?after=N` 或 `Last-Event-ID` 续传。

## 反馈与写回边界

- `accept`：草稿标记为 `accepted`，响应返回 `reply_text`，前端只放入回复框。
- `reject`：草稿标记为 `rejected`，不写工单。
- `escalate`：草稿标记为 `escalated`，工单优先级改为 `urgent`，记录操作人备注。
- `write_internal_note`：只允许和 `accept` 一起使用；写的是 `internal_note`，`customer_visible=false`。
- 所有反馈响应均返回 `customer_message_sent=false`。U6 不提供发送客户消息的接口。

## Webhook 安全与幂等

请求头：

```text
X-Webhook-Timestamp: Unix 秒
X-Webhook-Signature: sha256=<hex>
X-Event-Id: 事件唯一 ID
```

签名原文为：

```text
<timestamp>.<原始请求体字节>
```

密钥为 `WEBHOOK_SECRET`。未配置密钥返回 `503`；缺少/错误签名或超出时间窗返回 `401`；同一事件 ID 重放返回 `200 duplicate`；同一事件 ID 携带不同载荷返回 `409`。默认载荷上限为 1,000,000 字节，可由 `WEBHOOK_MAX_BYTES` 调整。

## 运行与检查

```powershell
cd "D:\工单agent项目\backend"
$env:PYTHONIOENCODING="utf-8"
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe scripts\check_api.py
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

启动后可访问 `http://127.0.0.1:8000/docs`。如需启用 Webhook，在 `.env` 中设置 `WEBHOOK_SECRET` 后重启服务。

## 本次自动回归结果

- 全量测试：`33 passed`。
- 真实 MySQL HTTP 黑盒：健康检查 `200`；`T-2401` 返回 `202` 后进入 `succeeded`；SSE 收到 `run → step×15 → draft → done`。
- 采纳反馈：`reply_box_only=true`、`customer_message_sent=false`，工单消息角色仍只有 `customer`。
- 审计：4 次工具调用可见，`customer_message_sent=false`。
- 未配置密钥的 Webhook：`503 WEBHOOK_NOT_CONFIGURED`。
- 临时启用密钥后：首次 `accepted`，同事件重放 `duplicate`，工单审计只记录 1 个 Webhook 事件。

## 验收清单

- [ ] 工单列表、详情、设备和消息可正常查询。
- [ ] 启动 Agent 返回 `202`，SSE 能看到步骤并最终收到 `done`。
- [ ] 已关闭工单不能启动 Agent，同一工单不能并发启动两个 run。
- [ ] 采纳只进入回复框，不产生客户消息；显式写回只生成内部备注。
- [ ] 拒绝、升级动作有记录，重复审核被拒绝。
- [ ] 运行审计能看到节点、工具、草稿、反馈和写回结果。
- [ ] Webhook 未配置密钥时失败关闭，正确签名可接收，重放不重复入库。
- [ ] 错误响应统一为 `{"error":{"code":"...","message":"..."}}`。

## 已知边界

- U6 不包含前端页面，也不包含登录/角色权限；这些在 U7/U8 实现。
- 当前为本地 Demo，Zendesk 仍不执行远端写操作；Webhook 写入本地镜像。
- SSE 通过数据库轮询生成事件，适合单机演示，不面向多实例横向扩展。
