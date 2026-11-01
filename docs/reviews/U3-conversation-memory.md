# U3 会话记忆与上下文验收

状态：**已人工验收**（2026-10-31）。U4 已开始。

## 本单元范围

- 以 `ticket_id` 为唯一隔离范围，工单之间不共享消息。
- 每个工单有明确 `ConversationSession`：`active`、`closed`。
- 工单关闭或标记 solved 时结束当前会话。
- 工单重开后建立新会话，旧会话摘要保留为背景，不把旧消息重新塞回上下文。
- 原始消息全部保留在 MySQL；上下文只发送最近消息 + 滚动摘要，避免无限增长。
- 会话摘要使用确定性规则生成，不依赖外部模型。

## 运行与检查

```powershell
cd "D:\工单agent项目\backend"
$env:PYTHONIOENCODING="utf-8"
.\.venv\Scripts\python.exe -m app.seed.seed --force
.\.venv\Scripts\python.exe -m pytest tests\test_memory.py -q
.\.venv\Scripts\python.exe scripts\check_memory.py
```

预期：4 个记忆测试通过；`T-2402` 为 active 会话，`T-2410` 为 closed/ended 会话。

## 验收清单

- [ ] 两个工单同时有消息时，上下文不会串线。
- [ ] 长对话只发送近期消息，`omitted_count` 和摘要可见，原始消息仍在 MySQL。
- [ ] solved/closed 工单不能新增客户消息。
- [ ] 重开工单会创建新 session，并带上一段会话摘要。
- [ ] 上下文有字符预算，不会无界增长。
- [ ] 内部备注/system 消息不会作为客户记忆注入 Agent。

## 关键文件

- `backend/app/models.py` 中的 `ConversationSession`
- `backend/app/services/memory.py`
- `backend/tests/test_memory.py`

