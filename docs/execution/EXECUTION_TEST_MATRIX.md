# Execution 测试矩阵

本文档定义 Execution 契约、Phase 4.1 实现目标和后续阶段测试矩阵。状态列只能使用：

- `Contract Done`
- `Phase 4.1`
- `Phase 4.2+`
- `Later Phase`

`Contract Done` 表示 Phase 4.0 文档契约已冻结，不表示实现完成。`Phase 4.1` 表示当前 execution 模块应实现并用单元测试覆盖。

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
| fill unsupported flag | `allow_status_only_fill=False` 时 fill 返回 `DOMAIN_FIELD_UNSUPPORTED`。 | Phase 4.1 |
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
| application orchestrator skeleton | 编排 OMS pre-state、EMS command、report mapper、OMS apply。 | Phase 4.2+ |
| UNKNOWN_REPORT integration | 等待 OMS public UNKNOWN entry 后接入。 | Phase 4.2+ |
| ENTER_UNKNOWN_CANDIDATE application | future application layer 调 OMS UNKNOWN public entry。 | Phase 4.2+ |

## Later Phase

| 场景 | 预期 | 状态 |
|---|---|---|
| true fill / trade modeling | 成交数量、成交价、trade id、fill id 类型化建模。 | Later Phase |
| Trade mapping | Exchange fill report 到 Trade / Fill 的专属契约。 | Later Phase |
| Domain / interface / schema migration | 真实成交事实进入类型化 Domain 和 schema。 | Later Phase |
| Position update | 成交后更新持仓。 | Later Phase |
| Margin update | 更新保证金。 | Later Phase |
| PnL update | 更新盯市或成交盈亏。 | Later Phase |
| Settlement | 每日结算。 | Later Phase |
| today/yesterday roll | 今仓转昨仓。 | Later Phase |
| true CTP adapter | 真实 CTP 接入。 | Later Phase |
| true SimNow adapter | 真实 SimNow 接入。 | Later Phase |
| broker adapter | 真实 broker adapter。 | Later Phase |
| live / prod / production / remote / KMS / cloud | 生产、远程、密钥或云流程。 | Later Phase |
