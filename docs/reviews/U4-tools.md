# U4 工具层验收

状态：**已人工验收**（2026-10-31）。U5 已开始。

## 本单元范围

五个受控工具，全部走白名单和参数校验：

| 工具 | 作用 | 是否写库 |
|---|---|---|
| `get_ticket` | 查询工单状态、客户、序列号、风险标记 | 否 |
| `get_device` | 查询设备型号、固件、质保、召回 | 否 |
| `search_manual` | 检索当前型号的英文手册分片和引用 | 否 |
| `translate_terms` | 查询受控中英售后术语 | 否 |
| `prepare_ticket_summary` | 生成内部工单小结草稿 | 否，仅返回提案 |

工程措施：

- 每个工具独立 Pydantic 参数校验。
- 每个工具独立数据库会话，不共享请求会话。
- 每个工具独立超时，默认来自 `TOOL_TIMEOUT_SECONDS`。
- 未知工具、参数错误、数据不存在、超时、内部错误都有明确错误码。
- 工具结果包含 `summary`，供 Agent 轨迹展示，不暴露完整内部思维链。
- 小结工具不写工单；后续采纳动作才允许进入写回流程。

## 运行与检查

```powershell
cd "D:\工单agent项目\backend"
$env:PYTHONIOENCODING="utf-8"
.\.venv\Scripts\python.exe -m pytest tests\test_tools.py -q
.\.venv\Scripts\python.exe scripts\check_tools.py
```

预期：5 个工具测试通过；检查脚本能读取 `T-2402`，检索到 E-12/异响相关 K2 手册分片，并生成 `writeback=false` 的摘要。

## 验收清单

- [ ] 工具列表只有五个，未暴露任意代码或网络工具。
- [ ] 所有工具都声明为无副作用。
- [ ] 未知工具和空参数被拒绝，并返回明确错误码。
- [ ] 手册检索带型号过滤和页码引用。
- [ ] 小结工具不会新增消息或修改工单。
- [ ] 工具轨迹能拿到可展示的摘要和耗时。

## 关键文件

- `backend/app/tools/registry.py`
- `backend/tests/test_tools.py`
- `backend/scripts/check_tools.py`

