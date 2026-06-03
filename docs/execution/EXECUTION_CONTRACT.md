# Execution 终态契约

本文档是 Phase 4 Execution 的冻结契约。它描述终态 Execution 架构，同时明确 Current facts、Phase 4.1 implementation target、Phase 4.2+ target 和 Later Phase 的落地区分。除非另开契约迁移，后续实现必须以本文档和 `EXECUTION_TEST_MATRIX.md` 为准。

Phase 4.0 只冻结契约。Phase 4.1 按本文档落地 DTO、enum、MappingContext、MappingResult、MappingError 和 pure mapper。EMS skeleton、MockFuturesExchange skeleton、report surface、Application Execution Orchestrator 和 UNKNOWN_REPORT 应用仍不属于当前实现事实。

## Final-state Architecture

### Application Execution Orchestrator

终态 Application Execution Orchestrator 负责执行链路编排：

- 接收 OMS 已创建、已通过 Risk、且处于可提交或可撤状态的订单。
- submit 前调用 `OMSService.apply_order_event(...)` 让订单进入 `SUBMITTING`。
- cancel 前调用 `OMSService.apply_order_event(...)` 让订单进入 `CANCEL_PENDING`。
- 调用 EMS submit / cancel command。
- 接收 EMS / Exchange report。
- 调用 pure ExchangeReport Mapper。
- 将 `MAPPED_ORDER_EVENT` 结果中的 `OrderEvent` 交回 `OMSService.apply_order_event(...)`。
- 对 `DUPLICATE_REPORT`、`IGNORED_REPORT`、`INSUFFICIENT_CONTEXT`、`MAPPING_ERROR`、`DOMAIN_FIELD_UNSUPPORTED` 和未来 `ENTER_UNKNOWN_CANDIDATE` 做分流。
- 不直接写 DB。
- 不直接修改 `OrderState.status`。
- 不计算 Risk、Position、Margin、PnL 或 Settlement。

### EMS

终态 EMS 是执行侧应用端口：

- 接收 submit / cancel command。
- 连接 MockFuturesExchange 或未来真实 adapter。
- 可在 report surface 定义后转发 ExchangeReport。
- 不直接修改 OMS 状态。
- 不直接写订单状态。
- 不解释 OMS 状态机。
- 不调用 RiskEngine。
- 不更新 Position / Margin / PnL / Settlement。

### Exchange Adapter / MockFuturesExchange

终态 Exchange Adapter / MockFuturesExchange 负责交易所侧交互或模拟：

- 接收 submit / cancel。
- 产生 ExchangeReport。
- 不知道 `OMSService`。
- 不知道 `RiskEngine`。
- 不写 DB。
- 不更新 Trade / Position / Margin / PnL / Settlement。
- 不包含 daily settlement 或 today/yesterday position roll。

### ExchangeReport Mapper

Phase 4.1 will define pure ExchangeReport Mapper：

- 输入 `ExchangeReport + MappingContext`。
- 输出 `MappingResult`。
- 不调用 OMS。
- 不写 DB。
- 不读 `raw_payload` 补 source-of-truth 字段。
- 不处理 Position / Margin / PnL / Settlement。
- 不连接真实交易接口。
- 不使用 `risk_events`。

### OMS

OMS 是订单状态唯一事实入口：

- 订单状态结果只通过 `OMSService.apply_order_event(...)` 或 future public UNKNOWN entry 应用。
- Execution 不绕过 OMS。
- `previous_status`、`new_status`、`external_event_id`、`EventApplicationStatus` 和终态保护以 OMS 文档为准。

### Submit Flow

终态 submit 流程：

1. Order 已由 OMS 创建，并由 Risk 接受。
2. Application layer 调用 `OMSService.apply_order_event(...)` 进入 `SUBMITTING`。
3. Application layer 调用 `EMS.submit(...)`。
4. EMS / Exchange 返回或异步产生 `ExchangeReport`。
5. Mapper 将 report 转为 `MappingResult`。
6. 若结果为 `MAPPED_ORDER_EVENT`，application layer 将 `OrderEvent` 交给 `OMSService.apply_order_event(...)`。
7. 若结果为 `DUPLICATE_REPORT`、`IGNORED_REPORT`、`INSUFFICIENT_CONTEXT`、`MAPPING_ERROR`、`DOMAIN_FIELD_UNSUPPORTED` 或 future `ENTER_UNKNOWN_CANDIDATE`，application layer 按类型分流。
8. OMS 决定最终 `OrderState`。

### Cancel Flow

终态 cancel 流程：

1. Application layer 确认订单可撤。
2. Application layer 调用 `OMSService.apply_order_event(...)` 进入 `CANCEL_PENDING`。
3. Application layer 调用 `EMS.cancel(...)`。
4. EMS / Exchange 返回或异步产生 `ExchangeReport`。
5. Mapper 将 report 转为 `MappingResult`。
6. 若结果为 `MAPPED_ORDER_EVENT`，application layer 将 `OrderEvent` 交给 `OMSService.apply_order_event(...)`。
7. OMS 决定最终 `OrderState`。

## Current Facts

当前仓库事实：

- 当前 `src/futures_mvp/interfaces/engines.py` 中 `MockFuturesExchange` Protocol 只有 command port：
  - `submit_limit_order(order: OrderState) -> None`
  - `cancel_order(order: OrderState) -> None`
- 当前 submit / cancel command 返回 `None`。
- 当前 `MockFuturesExchange` Protocol 不承载 report surface。
- 当前没有 report stream、callback、polling 或返回 report 的接口。
- 当前 `src/futures_mvp/modules/execution/` 已实现 Phase 4.1 DTO / enum / MappingContext / MappingResult / MappingError / pure mapper。
- 当前没有 EMS implementation。
- 当前没有 MockFuturesExchange implementation。
- 当前没有 Application Execution Orchestrator。
- 当前没有 Execution -> OMS 集成。
- 当前不修改 OMS / Risk / DB / schema / Domain 字段事实。
- 当前 Phase 4 Execution Contract / pure mapper 阶段不接真实交易接口、CTP、SimNow 或 broker adapter；这些属于后续 Adapter 阶段。
- 当前不进入 Position / Margin / PnL / Settlement。

`MockFuturesExchange.run_daily_settlement(trading_day)` 的移除是 intentional interface migration：

- 当前 Phase 4 MockFuturesExchange Protocol 不包含 settlement 方法。
- Future Settlement Protocol 必须在后续 Settlement 阶段另行定义。
- 即使 `interfaces/engines.py` 中存在 `SettlementEngine`，它也是全局后续阶段接口，不属于 Phase 4 execution surface。

## Phase 4.1 Implementation Target

Phase 4.1 implementation target 是 DTO / enum / MappingContext / MappingResult / MappingError / pure mapper / unit tests。Phase 4.1 不实现 EMS skeleton、MockFuturesExchange skeleton、report surface 或 Application Execution Orchestrator，除非另开阶段。

### DTO And Enum Drafts

Phase 4.1 must define `ExchangeReportType`：

- `ACK`
- `REJECTED`
- `PARTIAL_FILL`
- `FULL_FILL`
- `CANCELED`
- `CANCEL_REJECTED`
- `EXPIRED`
- `TIMEOUT`
- `EXCHANGE_UNAVAILABLE`
- `UNKNOWN_REPORT`

乱序不得作为 `ExchangeReportType`。乱序只能表达为 normal report + `expected_previous_status` / `current_order_status` mismatch。

Phase 4.1 must define `ExecutionOperation`：

- `SUBMIT`
- `CANCEL`

Phase 4.1 must define `DeliveryPhase`：

- `PRE_SEND`：请求确认未送达交易所。
- `POST_SEND_UNCERTAIN`：请求可能已送达，但没有确定回报。

### ExchangeReport Draft

Phase 4.1 must define `ExchangeReport` as a typed boundary DTO。DTO 可以承载已解析但待校验的外部回报；mapper 负责返回 typed `MAPPING_ERROR` 或 `INSUFFICIENT_CONTEXT`，不得用裸异常替代契约结果。

基础必填语义：

- `report_type`
- `exchange_report_id`
- `occurred_at`
- `event_source`
- `order_id` 或 `client_order_id` 至少一个稳定可关联身份

Phase 4.1 pure mapper 只有拿到 `order_id` 才能产出 `OrderEvent`。若 report 只有 `client_order_id`，mapper 不得猜测 OMS 订单 ID，必须返回 `INSUFFICIENT_CONTEXT`，等待 application layer 解析。

条件必填语义：

- `TIMEOUT` requires `operation`。
- `EXCHANGE_UNAVAILABLE` requires `operation + delivery_phase`。
- `ACK` / `REJECTED` 是 submit-side report；若显式提供 `operation`，必须为 `SUBMIT`。
- `CANCELED` / `CANCEL_REJECTED` 是 cancel-side report；若显式提供 `operation`，必须为 `CANCEL`。
- `PARTIAL_FILL` / `FULL_FILL` require order identity，但 Phase 4.1 status-only mapper 不要求 fill quantity / fill price / trade id。

可选诊断字段：

- `raw_payload`

`raw_payload` 永远不是 source-of-truth。

### MappingContext Draft

Phase 4.1 must define `MappingContext`：

- `current_order_status: OrderStatus | None`
- `expected_previous_status: OrderStatus | None`
- `known_exchange_report_ids: set[str] | None`
- `operation: ExecutionOperation | None`
- `allow_status_only_fill: bool`

语义：

- `current_order_status` 缺失且 mapper 需要判断非法同态事件时，返回 `INSUFFICIENT_CONTEXT`。
- `expected_previous_status` 缺失且 mapper 需要构造 `OrderEvent.previous_status` 时，可使用 `current_order_status`；两者均缺失时返回 `INSUFFICIENT_CONTEXT`。
- `known_exchange_report_ids` 用于 duplicate 判断；缺失时 mapper 不得声称 duplicate。
- `operation` 可作为 report 缺失 operation 时的上下文补充，但只允许来自类型化 context，不得来自 `raw_payload`。
- `allow_status_only_fill=True` 时，`PARTIAL_FILL` / `FULL_FILL` 只能映射订单状态。
- `allow_status_only_fill=False` 时，fill report 返回 `DOMAIN_FIELD_UNSUPPORTED`，直到完成 Domain / interface / schema migration。

### MappingResultStatus Draft

Phase 4.1 must define `MappingResultStatus`：

- `MAPPED_ORDER_EVENT`：已产出可交给 OMS 的 `OrderEvent`。
- `DUPLICATE_REPORT`：幂等重复，不产出事实事件。
- `IGNORED_REPORT`：迟到、同态或无需应用，不产出事实事件。
- `INSUFFICIENT_CONTEXT`：report 本身字段完整，但 mapper 缺少必要上下文。
- `ENTER_UNKNOWN_CANDIDATE`：UNKNOWN 候选；Phase 4.1 可预留 enum，但不得作为当前可执行应用路径。
- `MAPPING_ERROR`：report 字段缺失、类型不支持或 report 语义非法。
- `DOMAIN_FIELD_UNSUPPORTED`：当前 Domain 无法承载事实字段，例如真实 fill quantity / fill price / trade id。

Phase 4.1 mapper 不得返回裸字符串。

### MappingErrorReason Draft

Phase 4.1 must define `MappingErrorReason` at least：

- `MISSING_REPORT_TYPE`
- `MISSING_EXCHANGE_REPORT_ID`
- `MISSING_OCCURRED_AT`
- `MISSING_EVENT_SOURCE`
- `MISSING_ORDER_IDENTITY`
- `MISSING_OPERATION`
- `MISSING_DELIVERY_PHASE`
- `UNSUPPORTED_REPORT_TYPE`
- `UNSUPPORTED_OPERATION`
- `UNSUPPORTED_DELIVERY_PHASE`
- `OPERATION_REPORT_TYPE_MISMATCH`
- `MISSING_CURRENT_ORDER_STATUS`
- `MISSING_EXPECTED_PREVIOUS_STATUS`
- `ILLEGAL_SAME_STATUS_EVENT`
- `DOMAIN_FIELD_UNSUPPORTED`
- `RAW_PAYLOAD_ONLY_FACT_FORBIDDEN`
- `UNKNOWN_REPORT_REQUIRES_OMS_UNKNOWN_ENTRY`

上下文不足类 reason 可以随 `INSUFFICIENT_CONTEXT` 返回，不混成 report 字段错误。

### Status-only Mapping Rules

Phase 4.1 mapper must implement status-only mapping：

| ExchangeReport | Mapping |
|---|---|
| `ACK` | `OrderStatus.ACKED` |
| `REJECTED` | `OrderStatus.REJECTED_BY_EXCHANGE` |
| `PARTIAL_FILL` | `OrderStatus.PARTIALLY_FILLED` when `allow_status_only_fill=True` |
| `FULL_FILL` | `OrderStatus.FILLED` when `allow_status_only_fill=True` |
| `CANCELED` | `OrderStatus.CANCELED` |
| `CANCEL_REJECTED` | `OrderStatus.CANCEL_FAILED` |
| `EXPIRED` | `OrderStatus.EXPIRED` |
| `TIMEOUT + SUBMIT` | `OrderStatus.SUBMIT_TIMEOUT` |
| `TIMEOUT + CANCEL` | `OrderStatus.CANCEL_FAILED` |
| `EXCHANGE_UNAVAILABLE + SUBMIT + PRE_SEND` | `OrderStatus.SUBMIT_FAILED` |
| `EXCHANGE_UNAVAILABLE + SUBMIT + POST_SEND_UNCERTAIN` | `OrderStatus.SUBMIT_TIMEOUT` |
| `EXCHANGE_UNAVAILABLE + CANCEL + PRE_SEND` | `OrderStatus.CANCEL_FAILED` |
| `EXCHANGE_UNAVAILABLE + CANCEL + POST_SEND_UNCERTAIN` | `OrderStatus.CANCEL_FAILED` |

`UNKNOWN_REPORT`：

- Phase 4.1 不产出 `OrderEvent`。
- Phase 4.1 不新增 OMS Protocol。
- Phase 4.1 不新增 OMS public UNKNOWN entry。
- Phase 4.1 mapper 不把 `ENTER_UNKNOWN_CANDIDATE` 写成当前可执行应用路径。
- Phase 4.1 对完整 `UNKNOWN_REPORT` 返回 typed non-event result，并带 `UNKNOWN_REPORT_REQUIRES_OMS_UNKNOWN_ENTRY` reason。
- Phase 4.2+ 等待 OMS public UNKNOWN entry 后再集成。

Duplicate：

- 如果 `exchange_report_id` 已在 `known_exchange_report_ids` 中，返回 `DUPLICATE_REPORT`。
- 不生成新的事实事件。
- `DUPLICATE_REPORT` 是 mapper result 的 idempotency classifier，不是交易所事实状态，也不是 `ExchangeReportType`。

Out-of-order：

- 不作为 report type。
- 用 normal report + `expected_previous_status` / `current_order_status` mismatch 表达。
- mapper 可产出带 `expected_previous_status` 的候选 `OrderEvent`，由 OMS `EventApplicationStatus` 语义处理。
- 若没有足够上下文判断，返回 `INSUFFICIENT_CONTEXT`。

Illegal same-status：

- mapper 产出的普通 `OrderEvent` 必须满足 OMS 状态机合法迁移。
- 禁止 `SUBMIT_TIMEOUT -> SUBMIT_TIMEOUT` 普通事件。
- 禁止 `CANCEL_FAILED -> CANCEL_FAILED` 普通事件。
- 这类重复、迟到或同态异常返回 `IGNORED_REPORT`、`DUPLICATE_REPORT` 或 `MAPPING_ERROR`，不得生成普通 `OrderEvent`。

### raw_payload Contract Done

以下 source-of-truth 字段不得只存在于 `raw_payload`：

- `report_type`
- `order status`
- `previous_status`
- `exchange_report_id`
- `operation`
- `delivery_phase`
- `occurred_at`
- `event_source`
- `fill quantity`
- `fill price`
- `trade id`
- `fill id`

Phase 4.1 status-only fill mapping 不承载 fill quantity / fill price / trade id / fill id。真实成交事实必须先做 Domain / interface / schema migration 或 Trade / Fill 专属契约。

### Phase 4.1 Not Allowed In This Phase

Phase 4.1 不允许：

- 修改 OMSService 行为。
- 修改 OMS 状态机。
- 修改 RiskEngine / RiskConfig / RiskResult。
- 修改 DB / Repository / UnitOfWork / ORM / Alembic / schema。
- 修改 Domain 业务事实字段。
- 进入 EMS skeleton。
- 进入 MockFuturesExchange skeleton。
- 实现 report surface / callback / polling / stream。
- 实现 Application Execution Orchestrator。
- 进入 Position / Margin / PnL / Settlement。
- 接真实交易接口、CTP、SimNow 或 broker adapter；这些属于后续 Adapter 阶段。
- 新增 live / prod / production / remote / KMS / cloud；这些属于后续 Runtime / Infrastructure 阶段。
- 写 `risk_events`。
- 把 facts 放入 `raw_payload`。

## Phase 4.2+ Target

Phase 4.2+ target：

- report surface interface gate。
- EMS skeleton。
- MockFuturesExchange skeleton。
- Application Execution Orchestrator skeleton。
- report callback / polling / stream 方案。
- `UNKNOWN_REPORT` integration after OMS public UNKNOWN entry。
- `ENTER_UNKNOWN_CANDIDATE` 到 OMS UNKNOWN public entry 的应用层编排。

Phase 4.2+ 仍不接真实交易接口，除非另开真实 adapter 契约阶段。

## Later Phase

Later Phase：

- true fill / trade modeling。
- Fill / Trade 专属契约。
- Domain / interface / schema migration for fill quantity / fill price / trade id / fill id。
- Position update。
- Margin update。
- PnL update。
- Settlement。
- today/yesterday position roll。
- true CTP adapter。
- true SimNow adapter。
- broker adapter。
- live / prod / production / remote / KMS / cloud。
