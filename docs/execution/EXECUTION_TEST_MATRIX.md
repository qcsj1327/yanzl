# Execution 测试矩阵

本文档定义 Execution 契约、Phase 4.1 实现目标和后续阶段测试矩阵。状态列只能使用：

- `Contract Done`
- `Phase 4.1`
- `Execution Runtime`
- `Stage A`
- `Stage B Contract`
- `Stage B`
- `Phase 4.2+`
- `Later Phase`

`Contract Done` 表示 Phase 4.0 文档契约已冻结，不表示实现完成。`Phase 4.1` 表示 pure mapper 阶段已实现并用单元测试覆盖。`Execution Runtime` 表示当前 Command/Report Runtime Layer 已实现并用单元测试覆盖。
`Stage A` 表示 ApplicationExecutionOrchestrator 已实现并用单元测试覆盖。
`Stage B Contract` 表示 Fill / Trade Domain Migration 契约已冻结，不表示代码、schema 或 repository 已实现。
`Stage B` 表示 Fill / Trade Domain Migration 已实现并用 domain、execution mapper 和 DB integration 测试覆盖。

## Contract Done

| 场景 | 预期 | 状态 |
|---|---|---|
| Final-state architecture | 文档显式区分 Final-state architecture / Current facts / Phase 4.1 / Phase 4.2+ / Later Phase。 | Contract Done |
| MockFuturesExchange command port current fact | 当前 Protocol 只有 `submit_limit_order(...) -> None` / `cancel_order(...) -> None`。 | Contract Done |
| no current report surface | 当前 Protocol 不返回 report，不包含 callback / polling / stream。 | Contract Done |
| no current EMS implementation | 当前没有 EMS implementation。 | Contract Done |
| no current MockExchange implementation | 当前没有 MockFuturesExchange implementation。 | Contract Done |
| no current mapper implementation before Phase 4.1 | Phase 4.0 只冻结 mapper 契约。 | Contract Done |
| OMS state entry | `OMSService.apply_order_event(...)` 是订单状态变更入口。 | Contract Done |
| EMS / Exchange boundary | EMS / Exchange 不直接改 OMS 状态，不写 DB。 | Contract Done |
| no settlement on MockFuturesExchange | `run_daily_settlement` 已从当前 MockFuturesExchange Protocol 移除。 | Contract Done |
| intentional interface migration | `run_daily_settlement` 移除记录为 intentional interface migration。 | Contract Done |
| no real trading interface | 不接 CTP / SimNow / broker adapter / 真实交易所。 | Contract Done |
| no live/prod/remote/KMS/cloud | 不新增生产、远程、密钥或云流程。 | Contract Done |
| no Position / Margin / PnL / Settlement | Phase 4.0 / Phase 4.1 不更新持仓、保证金、PnL 或结算。 | Contract Done |
| raw_payload fact forbidden | source-of-truth 字段不得只放 `raw_payload`。 | Contract Done |
| fill facts raw_payload forbidden | fill quantity / fill price / trade id / fill id 不得只放 `raw_payload`。 | Contract Done |
| OUT_OF_ORDER not report type | 乱序不是 `ExchangeReportType`，只能用 normal report + status mismatch 表达。 | Contract Done |
| UNKNOWN_REPORT later integration | `UNKNOWN_REPORT` 应用后移到 Phase 4.2+，等待 OMS public UNKNOWN entry。 | Contract Done |
| Phase 4.1 forbidden scope | Phase 4.1 不进入 EMS skeleton、MockExchange skeleton、report surface、orchestrator、OMS/Risk/DB/schema/domain facts、Position/Margin/PnL/Settlement 或真实交易。 | Contract Done |

## Phase 4.1 DTO And Enum

| 场景 | 预期 | 状态 |
|---|---|---|
| `ExchangeReportType` values | 只包含 `ACK` / `REJECTED` / `PARTIAL_FILL` / `FULL_FILL` / `CANCELED` / `CANCEL_REJECTED` / `EXPIRED` / `TIMEOUT` / `EXCHANGE_UNAVAILABLE` / `UNKNOWN_REPORT`。 | Phase 4.1 |
| `ExecutionOperation` values | `SUBMIT` / `CANCEL`。 | Phase 4.1 |
| `DeliveryPhase` values | `PRE_SEND` / `POST_SEND_UNCERTAIN`。 | Phase 4.1 |
| `ExchangeReport` DTO defaults | DTO 可承载待校验 report；缺字段由 mapper typed result 表达。 | Phase 4.1 |
| ExchangeReport base required fields | 缺 `report_type`、`exchange_report_id`、`occurred_at`、`event_source`、order identity 时返回 `MAPPING_ERROR`。 | Phase 4.1 |
| ExchangeReport order identity | `order_id` 或 `client_order_id` 至少一个；只有 `client_order_id` 时不能产出 `OrderEvent`。 | Phase 4.1 |
| ExchangeReport conditional fields | `TIMEOUT` 必填 `operation`；`EXCHANGE_UNAVAILABLE` 必填 `operation + delivery_phase`。 | Phase 4.1 |
| operation consistency | `ACK` / `REJECTED` 若带 operation 必须是 `SUBMIT`；`CANCELED` / `CANCEL_REJECTED` 若带 operation 必须是 `CANCEL`。 | Phase 4.1 |
| `raw_payload` diagnostic only | mapper 不从 `raw_payload` 补 report facts。 | Phase 4.1 |

## Phase 4.1 MappingContext / Result / Error

| 场景 | 预期 | 状态 |
|---|---|---|
| `MappingContext` fields | 定义 `current_order_status`、`expected_previous_status`、`known_exchange_report_ids`、`operation`、`allow_status_only_fill`。 | Phase 4.1 |
| duplicate context | `known_exchange_report_ids` 缺失时不得声称 duplicate。 | Phase 4.1 |
| insufficient context | 缺少必要 current / expected status 时返回 `INSUFFICIENT_CONTEXT`。 | Phase 4.1 |
| status-only fill flag | `allow_status_only_fill=True` 时 fill 只映射订单状态。 | Phase 4.1 |
| fill unsupported flag | Phase 4.1 中 `allow_status_only_fill=False` 时 fill 返回 `DOMAIN_FIELD_UNSUPPORTED`；Stage B 后 typed fields 完整时迁移为 typed fill/trade fact。 | Phase 4.1 |
| `MappingResultStatus` values | 覆盖 `MAPPED_ORDER_EVENT` / `DUPLICATE_REPORT` / `IGNORED_REPORT` / `INSUFFICIENT_CONTEXT` / `ENTER_UNKNOWN_CANDIDATE` / `MAPPING_ERROR` / `DOMAIN_FIELD_UNSUPPORTED`。 | Phase 4.1 |
| `MappingErrorReason` values | 覆盖契约列出的 missing、unsupported、mismatch、same-status、raw-payload、unknown-entry reasons。 | Phase 4.1 |
| no bare string results | mapper 不返回裸字符串状态或裸字符串错误原因。 | Phase 4.1 |

## Phase 4.1 Mapping Rules

| 场景 | 预期 | 状态 |
|---|---|---|
| ACK mapping | `ACK -> OrderStatus.ACKED`。 | Phase 4.1 |
| REJECTED mapping | `REJECTED -> OrderStatus.REJECTED_BY_EXCHANGE`。 | Phase 4.1 |
| PARTIAL_FILL status-only mapping | `PARTIAL_FILL -> OrderStatus.PARTIALLY_FILLED`，不承载成交事实。 | Phase 4.1 |
| FULL_FILL status-only mapping | `FULL_FILL -> OrderStatus.FILLED`，不承载成交事实。 | Phase 4.1 |
| CANCELED mapping | `CANCELED -> OrderStatus.CANCELED`。 | Phase 4.1 |
| CANCEL_REJECTED mapping | `CANCEL_REJECTED -> OrderStatus.CANCEL_FAILED`。 | Phase 4.1 |
| EXPIRED mapping | `EXPIRED -> OrderStatus.EXPIRED`。 | Phase 4.1 |
| submit TIMEOUT mapping | `TIMEOUT + SUBMIT -> OrderStatus.SUBMIT_TIMEOUT`。 | Phase 4.1 |
| cancel TIMEOUT mapping | `TIMEOUT + CANCEL -> OrderStatus.CANCEL_FAILED`。 | Phase 4.1 |
| submit unavailable pre-send mapping | `EXCHANGE_UNAVAILABLE + SUBMIT + PRE_SEND -> OrderStatus.SUBMIT_FAILED`。 | Phase 4.1 |
| submit unavailable post-send mapping | `EXCHANGE_UNAVAILABLE + SUBMIT + POST_SEND_UNCERTAIN -> OrderStatus.SUBMIT_TIMEOUT`。 | Phase 4.1 |
| cancel unavailable pre-send mapping | `EXCHANGE_UNAVAILABLE + CANCEL + PRE_SEND -> OrderStatus.CANCEL_FAILED`。 | Phase 4.1 |
| cancel unavailable post-send mapping | `EXCHANGE_UNAVAILABLE + CANCEL + POST_SEND_UNCERTAIN -> OrderStatus.CANCEL_FAILED`。 | Phase 4.1 |
| duplicate report | 已知 `exchange_report_id` 返回 `DUPLICATE_REPORT`，不生成 `OrderEvent`。 | Phase 4.1 |
| out-of-order condition | normal report + mismatched expected/current status 仍产出候选事件交给 OMS，或在上下文不足时返回 `INSUFFICIENT_CONTEXT`。 | Phase 4.1 |
| illegal same-status submit | 当前为 `SUBMIT_TIMEOUT` 时，不生成 `SUBMIT_TIMEOUT -> SUBMIT_TIMEOUT`。 | Phase 4.1 |
| illegal same-status cancel | 当前为 `CANCEL_FAILED` 时，不生成 `CANCEL_FAILED -> CANCEL_FAILED`。 | Phase 4.1 |
| UNKNOWN_REPORT | Phase 4.1 不生成 `OrderEvent`，返回 typed non-event result with `UNKNOWN_REPORT_REQUIRES_OMS_UNKNOWN_ENTRY`。 | Phase 4.1 |
| raw_payload fact guard | 需要的事实字段只存在于 `raw_payload` 时返回 typed non-event result。 | Phase 4.1 |
| AST import boundary | execution 模块不 import OMSService / RiskEngine / DB / Repository / UnitOfWork / ORM / Position / Margin / PnL / Settlement / real adapter。 | Phase 4.1 |

## Existing Mock Exchange XFail Mapping

本表的 `Phase 4.1` 只表示 pure mapper 已覆盖对应回报语义，不表示 `tests/integration/mock_exchange` 场景已解除 xfail 或 MockFuturesExchange skeleton 已实现。

| xfail 场景 | 契约归属 | 状态 |
|---|---|---|
| `partial_fill` | Phase 4.1 status-only `PARTIAL_FILL` mapper；真实成交事实后移。 | Phase 4.1 |
| `full_fill` | Phase 4.1 status-only `FULL_FILL` mapper；真实成交事实后移。 | Phase 4.1 |
| `reject_order` | `REJECTED -> REJECTED_BY_EXCHANGE` mapper。 | Phase 4.1 |
| `cancel_order` | `CANCELED -> CANCELED` mapper。 | Phase 4.1 |
| `cancel_reject` | `CANCEL_REJECTED -> CANCEL_FAILED` mapper。 | Phase 4.1 |
| `price_limit_reject` | 交易所拒单原因，归入 `REJECTED` status-only mapper。 | Phase 4.1 |
| `submit_timeout` | submit `TIMEOUT` mapper。 | Phase 4.1 |
| `duplicate_report` | duplicate mapping result。 | Phase 4.1 |
| `out_of_order_report` | normal report + status mismatch；不是 report type。 | Phase 4.1 |
| `daily_settlement` | Settlement 阶段。 | Later Phase |
| `roll_today_to_yesterday` | Position / Settlement 阶段。 | Later Phase |

## Phase 4.2+

| 场景 | 预期 | 状态 |
|---|---|---|
| report surface | 定义 callback / polling / stream 或等价 report surface。 | Phase 4.2+ |
| EMS skeleton | DTO / mapper 完成后再实现 EMS shell。 | Phase 4.2+ |
| MockFuturesExchange skeleton | report surface 完成后再实现 MockFuturesExchange shell。 | Phase 4.2+ |
| UNKNOWN_REPORT integration | 等待 OMS public UNKNOWN entry 后接入。 | Phase 4.2+ |
| ENTER_UNKNOWN_CANDIDATE application | future application layer 调 OMS UNKNOWN public entry。 | Phase 4.2+ |

## Execution Runtime

| 场景 | 预期 | 状态 |
|---|---|---|
| `ExchangeCommandPort` | 定义 submit / cancel command port，方法返回 `None`。 | Execution Runtime |
| `ExecutionReportSink` | 定义当前 local / in-memory report surface，只承载 `ExchangeReport`。 | Execution Runtime |
| report sink behavior | `append` / `list_reports` / `drain_reports` 可用于当前内存实现和单元测试。 | Execution Runtime |
| no production event bus | report sink 不代表 Kafka / Redis / Celery，不作为生产事件总线。 | Execution Runtime |
| EMS command boundary | EMS 只依赖 `ExchangeCommandPort`，不依赖具体 MockFuturesExchange。 | Execution Runtime |
| MockFuturesExchange skeleton | 可配置 MockExchange 实现 command port，command 产生 typed `ExchangeReport`。 | Execution Runtime |
| submit reports | 支持 ACK / REJECTED / TIMEOUT / EXCHANGE_UNAVAILABLE PRE_SEND / POST_SEND_UNCERTAIN。 | Execution Runtime |
| cancel reports | 支持 CANCELED / CANCEL_REJECTED / TIMEOUT / EXCHANGE_UNAVAILABLE PRE_SEND / POST_SEND_UNCERTAIN。 | Execution Runtime |
| deterministic report id | 默认 deterministic counter，可注入固定 id generator 用于 duplicate replay。 | Execution Runtime |
| report handler | `ExecutionReportHandler.handle(...)` 只调用 mapper 并原样返回 `MappingResult`。 | Execution Runtime |
| no application routing | 当前 handler 不 split、不调 OMS、不应用 `OrderEvent`。 | Execution Runtime |
| no current UNKNOWN application | 不新增 OMS UNKNOWN entry，不消费 UNKNOWN candidate。 | Execution Runtime |
| runtime boundary | EMS / MockExchange / report layer 不 import OMS / Risk / DB / Settlement / real adapter / Kafka / Redis / Celery。 | Execution Runtime |

## Stage A Application Execution Orchestrator

| 场景 | 预期 | 状态 |
|---|---|---|
| orchestrator object | 定义 `ApplicationExecutionOrchestrator` 和 typed orchestration result。 | Stage A |
| submit pre-event | submit 前先通过 OMS event 推进到 `SUBMITTING`。 | Stage A |
| submit command gate | pre-event 非 `APPLIED` 时不调用 EMS submit。 | Stage A |
| cancel pre-event | cancel 前先通过 OMS event 推进到 `CANCEL_PENDING`。 | Stage A |
| cancel command gate | pre-event 非 `APPLIED` 时不调用 EMS cancel。 | Stage A |
| report collection | 使用 `ExecutionReportSink.list_reports()`，只过滤处理当前 order / operation，不 drain all。 | Stage A |
| mapping context | 按最新 OMS application result order status 构造 `MappingContext`。 | Stage A |
| mapped routing | `MAPPED_ORDER_EVENT` 且存在 `OrderEvent` 时调用 `OMSService.apply_order_event(...)`。 | Stage A |
| passthrough routing | `DUPLICATE_REPORT` / `IGNORED_REPORT` / `INSUFFICIENT_CONTEXT` / `ENTER_UNKNOWN_CANDIDATE` / `MAPPING_ERROR` / `DOMAIN_FIELD_UNSUPPORTED` 不调用 OMS。 | Stage A |
| no reports | 无匹配 report 时返回 typed `NO_REPORTS`。 | Stage A |
| OMS application rejection | OMS 应用 mapped event 非 `APPLIED` 时返回 typed orchestration result。 | Stage A |
| UNKNOWN boundary | 不新增 OMS public UNKNOWN entry，不调用 OMS 私有 UNKNOWN 方法，不自动进入 `UNKNOWN`。 | Stage A |
| orchestrator boundary | Orchestrator 不 import DB / Repository / UoW / ORM / Risk / Position / Margin / PnL / Settlement / broker adapter / runtime infra。 | Stage A |

## Stage B Fill / Trade Contract

| 场景 | 预期 | 状态 |
|---|---|---|
| FillEvent decimal contract | `FillEvent.price` / `FillEvent.quantity` / `fee_amount` 使用 `Decimal`，禁止 float。 | Stage B |
| Trade decimal contract | `Trade.price` / `Trade.quantity` / `fee_amount` 使用 `Decimal`，禁止 float。 | Stage B |
| typed fill fields | `PARTIAL_FILL` / `FULL_FILL` typed mode 必须携带 price、quantity、exchange_trade_id、traded_at 等字段。 | Stage B |
| raw_payload forbidden | 成交价、数量、trade id、fill id、fee、trading_day 不得只存在于 `raw_payload`。 | Stage B |
| MappingResult extension | `MappingResult` 扩展为可表达 `OrderEvent + FillEvent + Trade` bundle，mapper 仍不写 DB。 | Stage B |
| status-only compatibility | `allow_status_only_fill=True` 保留旧状态映射，不生成 Trade。 | Stage B |
| typed fill extraction | `allow_status_only_fill=False` 且 typed fields 完整时产出 typed fill/trade fact。 | Stage B |
| typed fill missing fields | typed fields 缺失时返回 `MAPPING_ERROR` / `INSUFFICIENT_CONTEXT` / `DOMAIN_FIELD_UNSUPPORTED`，不得从 `raw_payload` 补。 | Stage B |
| partial fill sequence | 多次 `PARTIAL_FILL` 保留 `PARTIALLY_FILLED -> PARTIALLY_FILLED` 合法映射，并生成独立成交事实。 | Stage B |
| full fill sequence | `FULL_FILL` 可同时产出 `OrderStatus.FILLED` 事件和 typed trade fact。 | Stage B |
| duplicate trade same payload | `account_id + exchange + exchange_trade_id` 重复且 payload 一致时返回 existing。 | Stage B |
| duplicate trade conflict payload | 重复 trade key 但 payload 不一致时抛 `TradeIdempotencyConflictError`。 | Stage B |
| repository/UoW | `TradeRepository` 和 UoW `trades` 入口存在，且不修改 OMS/Position。 | Stage B |
| schema round trip | `trades` 字段、fee、`source_exchange_report_id`、`trading_day`、`raw_payload` 可持久化往返。 | Stage B |
| unique constraint | 保留 `UNIQUE(account_id, exchange, exchange_trade_id)`。 | Stage B |
| no Position mutation | Stage B 不更新 Position / Margin / PnL / Settlement。 | Stage B |

## Later Phase

| 场景 | 预期 | 状态 |
|---|---|---|
| Position update | 成交后更新持仓。 | Later Phase |
| Margin update | 更新保证金。 | Later Phase |
| PnL update | 更新盯市或成交盈亏。 | Later Phase |
| Settlement | 每日结算。 | Later Phase |
| today/yesterday roll | 今仓转昨仓。 | Later Phase |
| true CTP adapter | 真实 CTP 接入。 | Later Phase |
| true SimNow adapter | 真实 SimNow 接入。 | Later Phase |
| broker adapter | 真实 broker adapter。 | Later Phase |
| live / prod / production / remote / KMS / cloud | 生产、远程、密钥或云流程。 | Later Phase |
