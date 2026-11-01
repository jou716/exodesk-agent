# U10 客户档案与创建工单会话验收

状态：**待人工验收**。

## 本单元范围

- 新增独立客户档案，工单通过 `customer_id` 关联客户，不再把客户姓名当作唯一标识。
- 邮箱统一去空格并转小写；邮箱唯一，重复使用同一邮箱时复用已有客户。
- 启动时自动为旧 `tickets` 表补 `customer_id` 字段和索引，并按现有工单回填客户档案。
- 坐席可以搜索选择已有客户，也可以新建客户后建单。
- 客户会话端新建工单时固定当前客户，不能选择或冒充其他客户。
- 创建工单时同时建立活跃会话和首条客户消息，并自动选中新工单。
- 业务规则：一个能独立追踪和解决的问题对应一个工单；后续追问继续在原工单回复。
- 新工单默认 `open`、`normal`，不自动运行 Agent。

## 本单元不包含

- 创建工单后自动启动 Agent；仍由坐席点击“启动 Agent”。
- Zendesk 远端建单、远端客户同步和工单合并。
- 客户资料编辑、合并、去重审批和附件上传。
- 客户端独立登录体系；当前仍处于演示环境。

## 数据模型

### Customer

| 字段 | 说明 |
|---|---|
| `id` | 由规范化邮箱哈希生成，形如 `C-XXXXXXXXXXXX` |
| `name` | 客户姓名，可修改，不作为唯一标识 |
| `email` | 规范化后的唯一邮箱 |
| `phone` | 可选电话 |
| `language` | 客户默认语言 |
| `notes` | 预留备注 |
| `extra` | Demo 标记、来源等扩展信息 |

### Ticket 变更

- 新增可空外键 `customer_id`，关联 `customers.id`。
- 保留 `customer_name`、`customer_email` 快照字段，便于列表展示和历史兼容。
- 本地 provider 建单时会确保客户档案存在，并同步工单的 `customer_id`。

## 接口

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/customers?query=&limit=` | 按姓名或邮箱搜索客户，返回工单数 |
| POST | `/api/tickets` | 使用已有客户或新客户创建工单，成功返回 `201` |

建单请求必须且只能提供 `customer_id` 与 `new_customer` 之一：

```json
{
  "customer_id": "C-XXXXXXXXXXXX",
  "subject": "问题标题",
  "initial_message": "客户首条消息",
  "serial_no": "K2-2025-00417",
  "created_via": "workbench"
}
```

或：

```json
{
  "new_customer": {
    "name": "客户姓名",
    "email": "customer@example.com",
    "phone": "可选"
  },
  "subject": "问题标题",
  "initial_message": "客户首条消息",
  "created_via": "customer"
}
```

返回：

- `ticket`：新工单，包含 `customer_id`。
- `customer`：实际关联或复用的客户档案。
- `message`：首条客户消息，角色固定为 `customer`。

## 校验与失败边界

- 客户不存在：`404 CUSTOMER_NOT_FOUND`。
- 序列号不存在：`422 DEVICE_NOT_FOUND`。
- `customer_id` 与 `new_customer` 同时提供或都不提供：`422` 请求校验失败。
- 问题标题、首条消息为空：`422` 请求校验失败。
- 新客户邮箱格式无效：`422` 请求校验失败。
- 邮箱大小写不同但规范化后相同：复用同一客户，不重复建档。
- 校验发生在写库前；写入失败会返回明确错误，不会向前端伪装成创建成功。

## 页面交互

- 坐席工作队列标题旁新增“新建”入口。
- 新建弹窗支持“已有客户 / 新建客户”切换、客户搜索、选中状态和工单数量展示。
- 客户会话端头部新增“新建会话”入口。
- 客户侧弹窗只显示“当前客户”卡片，不渲染客户选择器。
- 创建成功后关闭弹窗、刷新工作队列并选中新工单。
- 错误在弹窗内就地显示，创建过程中禁止重复提交和关闭弹窗。
- 弹窗保持简约，只展示客户、标题、可选序列号和首条消息。

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

- 后端全量测试：`64 passed`。
- 前端类型检查：通过。
- 生产构建：通过，JS `273.86 kB`、CSS `38.64 kB`。
- 后端与前端版本统一为 `0.10.0`。

新增回归覆盖：

- 客户目录返回客户及其工单数。
- 现有工单自动回填 `customer_id`。
- 选择已有客户建单，首条消息和活跃会话正确建立。
- 新建客户建单，邮箱自动规范化为小写。
- 相同邮箱再次建单复用同一客户。
- 客户不存在、设备不存在、客户来源组合错误均被拒绝。

## 浏览器回归结果

- 坐席选择已有客户 Emma Walker，使用序列号 `K2-2025-00417` 建单成功，生成 `T-C5D4CA4B`。
- 坐席新建客户“U10 测试客户”并建单成功，生成 `T-386CDA71`。
- 客户会话端固定当前客户，弹窗只显示“U10 测试客户”，无法切换其他客户；建单成功生成 `T-68170DE4`。
- 三个新工单均自动选中，首条客户消息正确显示，设备档案按序列号关联或显示“设备待确认”。
- 在 `T-68170DE4` 上客户继续发送消息，坐席回复后客户会话端无需刷新即收到。
- 页面控制台无 `error` / `warn` 日志。

## 语言回归修复（验收反馈）

人工验收发现：中文工单最后一次 Agent 运行返回了英文兜底。根因有三处：

- LLM 输出中混入 `">` 序列化脏字符，校验失败后进入安全兜底。
- 安全兜底和确定性草稿模板始终是英文。
- 草稿的 `draft_language` 被写死为 `en`。

本次修复：

- 清理单个和连续出现的 `">` / `&gt;` 序列化脏字符，同时保留正常换行。
- 校验器增加单个 `">` 行尾脏字符检测，避免漏过最终草稿。
- 根据客户最近一条原文和消息自带的语言识别回复语言，支持中文、英文、土耳其语、西班牙语等 ISO 语言代码。
- 新增中文安全兜底、中文高风险管理兜底和中文确定性草稿。
- LLM 提示词显式传入 `CUSTOMER_REPLY_LANGUAGE`，没有证据时必须要求客户补充型号、序列号和固件信息。
- 新增独立“识别客户语言”节点：每次运行开始时由千问识别客户最近一条原文语言，写入 `customer_language` 标记。
- 草稿生成后固定执行一次千问最终本地化调用，只使用开头固化的语言标记，不再重新猜测目标语言。
- 本地化提示词第一行显式写入 `TARGET_LANGUAGE: <code> (<language>)`，翻译结果直接作为最终草稿。
- 客户可见正文统一清理 `>`、Markdown 引用、`">",` 和反斜杠序列化残留。
- 最终本地化失败时运行状态进入 `needs_review`，不会把未确认语言的草稿伪装成成功。

修复后真实回归：

- `T-68170DE4`（中文、无设备序列号）：运行状态 `needs_review`，兜底草稿为中文，并要求补充设备信息。
- `T-C5D4CA4B`（中文、有效序列号）：LLM 主路径 `succeeded`，最终草稿为中文，校验通过。
- `T-2401`（英文）：LLM 主路径 `succeeded`，最终草稿保持英文，没有被错误翻译成中文。
- `T-96C46EBE`（土耳其语、无序列号）：最终草稿为干净的土耳其语，日志包含 `final_llm_pass=true; translated=true`。
- `T-FEC03F42`（土耳其语、REX-K2 固件问题）：最终草稿为土耳其语，校验通过。
- `T-880EAE07`（希腊语、充电异常）：日志先显示 `customer_language=el; language_name=Greek; source=llm`，最终本地化使用 `language_marker=el`，草稿为完整希腊语。
- 新增语言标记和最终本地化回归测试后，后端全量测试为 `64 passed`。

## 本次验证用合成数据

- `T-C5D4CA4B`：Emma Walker，已有客户 + 有效序列号建单。
- `T-386CDA71`：U10 测试客户，新客户档案建单。
- `T-68170DE4`：U10 测试客户，客户端固定身份建单，并完成客户/坐席双向消息回归。
- `T-96C46EBE`：Ayşe Yılmaz，土耳其语无序列号工单。
- `T-FEC03F42`：Ayşe Yılmaz，土耳其语 REX-K2 固件与校准工单。
- `T-880EAE07`：Ελένη Παπαδοπούλου，希腊语充电异常工单。
- 以上均为本地 Demo 合成数据，可保留供人工验收。

## 验收清单

- [ ] 坐席工作队列能看到“新建”，并能打开新建工单弹窗。
- [ ] 可以选择已有客户，搜索姓名或邮箱正常。
- [ ] 可以新建客户并直接建单，邮箱格式错误时会提示。
- [ ] 相同邮箱再次建单会复用已有客户，不产生重复档案。
- [ ] 客户会话端“新建会话”只显示当前客户，没有客户选择器。
- [ ] 创建后自动选中新工单，首条消息出现在会话中。
- [ ] 新工单不会自动运行 Agent。
- [ ] 无效序列号会被拒绝；不填序列号可以正常建单。
- [ ] 新工单可以继续双向发消息，客户会话端实时同步。
- [ ] 中文客户的最终回复是中文，英文客户仍是英文。
- [ ] 草稿中不再出现 `">` 之类的序列化脏字符。
- [ ] 页面保持简约，没有出现不必要的客户管理信息。

## 已知边界

- 当前没有客户登录体系。“固定当前客户”属于演示端 UI 约束，API 仍信任请求中的 `customer_id`；正式环境必须从已认证的客户会话中解析身份，不能接受客户端自报客户 ID。
- 客户会话端仍保留“演示会话”下拉，用于切换合成演示工单；正式环境应改为客户自己的工单列表。
- 邮箱是当前唯一身份键，尚未处理同一客户多邮箱、邮箱变更和人工合并。
- 建单只写本地镜像，没有调用 Zendesk 远端建单。
- 建单不会自动触发 Agent，也不会自动翻译首条消息；仍沿用现有 Agent 运行链路。

## 关键文件

- `backend/app/models.py`
- `backend/app/db.py`
- `backend/app/api/customers.py`
- `backend/app/api/tickets.py`
- `backend/app/api/schemas.py`
- `backend/app/services/customers.py`
- `backend/app/agent/drafting.py`
- `backend/app/agent/graph.py`
- `backend/app/agent/state.py`
- `backend/app/services/llm.py`
- `backend/app/services/risk.py`
- `backend/app/services/validator.py`
- `backend/app/services/serialization.py`
- `backend/app/adapters/base.py`
- `backend/app/adapters/local.py`
- `backend/app/seed/seed.py`
- `backend/tests/test_api.py`
- `frontend/src/features/workbench/CreateTicketModal.tsx`
- `frontend/src/features/workbench/Workbench.tsx`
- `frontend/src/features/workbench/TicketList.tsx`
- `frontend/src/features/workbench/CustomerChat.tsx`
- `frontend/src/lib/api.ts`
- `frontend/src/types.ts`
- `frontend/src/styles.css`
