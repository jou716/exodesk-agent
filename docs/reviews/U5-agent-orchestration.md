# U5 Agent 编排与安全校验验收

状态：**已人工验收**（2026-10-31）。U6 已开始。

## 本单元范围

- LangGraph 状态图：加载上下文 → 风险门 → 意图分类 → 工具规划 → 工具执行 → 草稿生成 → 校验 → 安全兜底/完成。
- 工具由 Agent 自主选择，但工具选择受白名单、最大调用次数和确定性上限约束。
- 高风险先于工具调用硬拦截：摔倒、锁死、突然断电、冒烟/起火/受伤等不检索手册、不生成调试步骤。
- 普通和故障场景检索手册，生成带页码引用的英文草稿。
- 输出校验：禁用指令、证据不足、必须停止使用等高危规则。
- 工具轨迹、节点状态和最终草稿持久化。
- 可选 LLM 润色；未配置时完全使用确定性草稿，效果可复现。

## 本单元不包含

- HTTP API 和 SSE 推送（U6）。
- 前端页面（U7/U8）。
- 工单小结真正写回（采纳动作在 API 单元实现）。

## 运行与检查

```powershell
cd "D:\工单agent项目\backend"
$env:PYTHONIOENCODING="utf-8"
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe scripts\check_agent.py
.\.venv\Scripts\python.exe scripts\check_tools.py
```

预期：全量测试通过；`check_agent.py` 覆盖 11 张未关闭工单和已关闭工单守卫并输出 `PASS`；`T-2403/T-2406` 被 blocked 且没有工具调用。

## 本次自动回归结果

- 全量测试：`24 passed`。
- Agent 场景：11 张未关闭工单全部符合预期，`T-2410` 已关闭工单启动运行被拒绝。
- 高危：`T-2403`、`T-2406` 为 `blocked`，工具调用为空，草稿只包含停止使用与升级安全话术。
- 普通/故障：`T-2401`、`T-2402`、`T-2404`、`T-2405`、`T-2407`、`T-2409`、`T-2412` 生成待审核英文草稿和手册页码。
- 检索边界：`T-2402` 首两条为 `Error E-12, p.18`、`Clicking noise, p.21`；`T-2408` 首条为 `Battery and charging, p.6`；`T-2412` 首条为 `Error E-21, p.19`。
- 证据不足：`T-2411` 无证据时请求型号、序列号、固件版本和错误码，并标记 `needs_info=true`。
- 风险否定：`没有看到冒烟，但充电口非常烫` 被识别为 `caution`，不触发高危拦截。
- 所有草稿状态均为 `pending`，不会自动发送给客户。

## 验收清单

- [ ] 普通工单能生成草稿，并带手册证据和页码。
- [ ] 故障工单能走 E-12/异响检索，不出现未经验证的维修步骤。
- [ ] 高危工单不调用手册检索，输出“停止使用、不要解锁/拆机、升级”的安全话术。
- [ ] 没有序列号/证据不足时询问型号、序列号、错误码，不编造步骤。
- [ ] 同一工单不允许并行 Agent 运行。
- [ ] 已关闭工单不能启动 Agent。
- [ ] 每个节点和工具都有可读的运行轨迹。

## 关键文件

- `backend/app/agent/state.py`
- `backend/app/agent/graph.py`
- `backend/app/agent/runtime.py`
- `backend/app/agent/drafting.py`
- `backend/app/services/validator.py`
- `backend/app/services/glossary.py`
- `backend/app/services/rag.py`
- `backend/tests/test_agent.py`
- `backend/scripts/check_agent.py`

