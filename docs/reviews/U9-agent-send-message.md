# U9 坐席发送消息验收

状态：**已人工验收**。下一单元为 U10（客户档案与创建工单）。

## 本单元范围

- 坐席可以直接在会话底部输入并发送消息给客户。
- Agent 草稿旁保留“复制”，新增“发送给客户”；发送前有明确确认。
- 坐席发送的消息立即写入工单会话，并通过现有票级 SSE 同步到客户会话端。
- 草稿发送后状态变为“已发送”，发送按钮自动消失，避免重复发送。
- 坐席消息支持 Enter 发送、Shift + Enter 换行和中文输入法组合态保护。
- 已关闭工单禁止发送；已升级草稿禁止发送。
- 草稿发送使用确定性幂等键，重复提交不会产生第二条客户可见消息。
- 运行审计增加 `sent_messages`、`sent_message_count` 和真实的 `customer_message_sent`。
- 不恢复采纳/拒绝流程；草稿仍以复制和直接发送为主要操作。

## 本单元不包含

- 客户档案、客户选择或新建客户。
- 创建新工单对话；该部分留给 U10。
- Zendesk 远端发送。当前发送写入本地镜像，客户会话端通过本地 SSE 接收。
- 发送后的撤回、编辑和已读回执。

## 接口

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/tickets/{ticket_id}/agent-messages` | 坐席发送客户可见消息，可选关联草稿 ID |

请求示例：

```json
{
  "content": "回复正文",
  "draft_id": "可选，发送 Agent 草稿时填写"
}
```

返回：

- `created`：是否新建消息。草稿重复提交时返回 `false` 和原消息。
- `message`：坐席消息，角色固定为 `agent`，`extra.customer_visible=true`。
- `draft`：关联草稿的最新状态；未关联草稿时为 `null`。

## 发送与安全边界

- 客户消息接口继续固定写入 `customer` 角色；坐席消息使用独立接口，客户端不能通过修改角色冒充坐席。
- 只有 `open` / `pending` 等未关闭工单可以发送；`solved` / `closed` 返回 `409 TICKET_CLOSED`。
- 只有属于当前工单的草稿可以关联发送；其他工单的草稿返回 `404 DRAFT_NOT_FOUND`。
- 已升级草稿返回 `409 DRAFT_ESCALATED`；已拒绝或已发送草稿不会被重新发送。
- 草稿关联消息写入 `draft_id` 和 `run_id`，运行审计可以定位是哪次 Agent 输出被发送。
- 客户 SSE 继续只推送 `customer` / `agent` 消息，`internal_note` 不进入客户可见事件。
- API Key 不进入前端包、接口响应、消息扩展字段或审计。

## 页面交互

- 会话面板底部新增坐席回复框和发送按钮。
- 草稿头部保留“复制”，并显示“发送给客户”。
- 点击“发送给客户”先弹出确认框，说明发送后立即出现在客户会话中且演示环境不可撤回。
- 高风险草稿的确认框额外提示只能发送安全话术。
- 发送成功后，坐席端和客户会话端都直接出现该消息，无需刷新。
- 发送失败时保留输入内容，并在对应位置显示可读错误；不伪装为成功。

## 本次自动检查

```powershell
cd "D:\工单agent项目\backend"
$env:PYTHONIOENCODING="utf-8"
.\.venv\Scripts\python.exe -m pytest -q

cd "D:\工单agent项目\frontend"
pnpm typecheck
pnpm build
```

结果：

- 后端全量测试：`50 passed`。
- 前端类型检查：通过。
- 生产构建：通过，JS `265.35 kB`、CSS `32.40 kB`。
- 后端与前端版本统一为 `0.9.0`。

新增回归覆盖：

- 坐席手动消息写入成功，并通过工单 SSE 推送 `role=agent` 消息。
- 关闭工单发送被拒绝。
- 草稿发送后状态变为 `sent`，重复请求返回同一条消息。
- 运行审计记录发送消息、草稿 ID、运行 ID，`customer_message_sent=true`。
- 已升级草稿禁止发送。

## 浏览器回归结果

- 坐席在 `T-2404` 发送手动消息“我们正在核对保修信息，确认后会在本会话继续回复。”成功。
- 客户会话端无需刷新即出现该售后消息。
- 点击草稿旁“发送给客户”出现确认框；确认后草稿状态变为“已发送”，发送按钮消失。
- 客户会话端同步收到完整草稿内容。
- 工单消息角色依次为 `customer, agent, agent`，没有产生内部备注或重复消息。
- 运行审计显示 `customer_message_sent=true`、`sent_message_count=1`，并记录对应 `draft_id`。
- 坐席端控制台无 `error` / `warn` 日志。

## 本次验证用合成数据

- `T-2404` 新增一条坐席手动测试回复，并发送了该工单最近一次 Agent 草稿。
- 原有 `T-2402`、`T-2411` 双端测试数据继续保留。
- 以上均为本地 Demo 合成数据。

## 验收清单

- [ ] 会话底部能看到坐席回复框，Enter 发送、Shift + Enter 换行正常。
- [ ] 手动发送后坐席端立即出现消息，客户会话端无需刷新也收到。
- [ ] 草稿旁保留“复制”，并出现“发送给客户”。
- [ ] 点击“发送给客户”会先确认，不会直接发送。
- [ ] 确认后草稿状态变为“已发送”，发送按钮消失。
- [ ] 关闭工单和已升级草稿都不能发送。
- [ ] 同一草稿重复发送不会出现两条客户消息。
- [ ] 运行审计能看到发送消息、草稿 ID 和真实发送状态。
- [ ] 页面不出现采纳/拒绝按钮，整体仍保持简约。
- [ ] 客户仍看不到 Agent 日志、草稿来源、Token 或内部备注。

## 关键文件

- `backend/app/api/tickets.py`
- `backend/app/api/schemas.py`
- `backend/app/api/audit.py`
- `backend/app/services/memory.py`
- `backend/tests/test_api.py`
- `frontend/src/features/workbench/Conversation.tsx`
- `frontend/src/features/workbench/AgentPanel.tsx`
- `frontend/src/features/workbench/Workbench.tsx`
- `frontend/src/lib/api.ts`
- `frontend/src/types.ts`
- `frontend/src/styles.css`

## 已知边界

- 当前发送只写入本地镜像，没有调用 Zendesk 远端发消息。
- 演示环境发送后不可撤回；正式渠道接入时需要补失败重试、远端消息映射和状态回执。
- 手动消息不经过 LLM 安全校验；高风险工单仍由界面提示和坐席人工判断负责。
- U10 尚未实现客户档案和新建工单。
