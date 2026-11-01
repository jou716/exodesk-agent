# U2 工单/设备适配器验收

状态：**已人工验收**（2026-10-31）。U3 已开始。

## 本单元范围

- 统一 `TicketProvider` 接口，隔离 Mock 与真实 Zendesk。
- Mock 适配器直接读写 MySQL，支持工单、设备、消息查询。
- Zendesk 适配器只读远端工单并镜像到本地；不发送客户消息、不写内部备注。
- 消息幂等：同一 `external_msg_id` 重复写入只保留一条。
- 已关闭工单拒绝新增客户消息。
- 工厂通过 `TICKET_PROVIDER=mock|zendesk` 切换，无需改业务代码。

## 不包含

- Webhook HTTP 接口（属于后续 API 单元）。
- 真实 Zendesk 写操作和 iframe 鉴权。
- Agent 读取工具和 LangGraph 编排。

## 验收命令

```powershell
cd "D:\工单agent项目\backend"
$env:PYTHONIOENCODING="utf-8"
.\.venv\Scripts\python.exe -m pytest tests\test_adapters.py -q
.\.venv\Scripts\python.exe scripts\check_adapters.py
```

预期：4 个适配器测试通过；检查脚本显示 `provider mock`、`ticket_count 12`，并读取 `T-2403` 的召回设备 `K2-2024-00119`。

## 验收清单

- [ ] Mock 与 Zendesk 使用同一接口，业务层不直接依赖 `httpx`。
- [ ] `TICKET_PROVIDER=mock` 时完全离线可用。
- [ ] 未配置 Zendesk 凭据时明确报 `ProviderNotConfigured`，不静默访问网络。
- [ ] 重复消息不重复入库。
- [ ] 已关闭工单不接受新的客户消息。
- [ ] 工单可以直接关联设备档案，并读取召回/质保状态。

## 关键文件

- `backend/app/adapters/base.py`
- `backend/app/adapters/local.py`
- `backend/app/adapters/zendesk.py`
- `backend/app/adapters/factory.py`
- `backend/tests/test_adapters.py`

