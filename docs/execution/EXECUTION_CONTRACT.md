# Execution 终态契约

本文档是 Execution 的冻结契约。它描述终态 Execution 架构，同时明确 Current facts、Phase 4.1 implementation target、Stage K Execution Gateway contract、Stage L Execution Report Normalization contract、Stage L.2 OMS Event Application contract、Stage L.3 OMS-to-Trade Bridge contract、Phase 4.2+ target 和 Later Phase 的落地区分。除非另开契约迁移，后续实现必须以本文档和 `EXECUTION_TEST_MATRIX.md` 为准。

Phase 4.0 只冻结契约。Phase 4.1 按本文档落地 DTO、enum、MappingContext、MappingResult、MappingError 和 pure mapper。Execution Runtime 和 Stage A ApplicationExecutionOrchestrator 已作为后续阶段实现。Stage K 在 `stage-j2-oms-bridge-core / ee4aace` 后实现 OMS Order -> Execution Gateway command boundary；它只支持 `MOCK` target，不实现真实 Broker、CTP、SimNow、Paper、Sim 或 Live。Stage L 在 `stage-k-execution-gateway-core / 94b498e` 后实现 Execution Report Normalization Core。Stage L.2 在 `stage-l-execution-report-normalization-core / 37cad40` 后实现 OMS event application core。Stage L.3 在 `stage-l2-oms-event-application-core / 54d6fc8` 后实现 OMS-to-Trade Bridge core，不进入 Runtime。

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
- 当前 EMS / MockFuturesExchange / Application Execution Orchestrator 已有本地测试实现和 staged runtime surface；它们仍不代表真实 Broker / CTP / SimNow / Paper / Sim / Live。
- 当前 Stage L.2 已实现 `OrderEventCandidate -> typed OrderEvent -> OMSService.apply_order_event(...)` 的 OMS event application boundary。
- 当前 Stage L.3 已实现 `NormalizedExecutionReport / applied OMS proof -> typed Trade fact -> TradeRepository` 的 OMS-to-Trade Bridge core，并通过 migration `0014_stage_l3_oms_to_trade_bridge.py` 扩展 existing `trades` / `normalized_execution_reports`。
- 当前 Phase 4 Execution Contract / pure mapper 阶段不接真实交易接口、CTP、SimNow 或 broker adapter；这些属于后续 Adapter 阶段。
- 当前不进入 Position / Margin / PnL / Settlement。
- 当前 `stage-j2-oms-bridge-core / ee4aace` 已实现 `OrderIntent -> OMSService.create_order` bridge；OMS 已能创建订单记录。
- 当前 Execution / Broker / Paper / Sim / Live 未进入。
- 当前 Stage K 已实现 Execution Gateway Core：`ExecutionCommand`、deterministic `command_id`、canonical payload/hash、`ExecutionCommandRepository`、SQLAlchemy repository、UoW integration、`execution_commands` migration、`ExecutionAdapter` Protocol、deterministic `MockExecutionAdapter`、`ExecutionGatewayService`、dry-run replay 和 tests。
- 当前 Stage K only supports `MOCK` target；`PAPER` / `SIM` / `LIVE` typed rejected / deferred。
- 当前 Stage K 不修改 OMS / OMS Bridge / Trading Workflow / Strategy / Risk / Broker / Runtime，不生成 `ExecutionReport` / `OrderEvent`，不生成 Fill / Trade，不修改 Accounting。
- 当前 Stage L 基线为 `stage-l-execution-report-normalization-core / 37cad40`。Stage L 已实现 Execution Report Normalization Core；`ExecutionCommandResult` 只表示 adapter accepted / rejected，不表示 exchange accepted、fill 或 trade。Stage L may build typed `OrderEvent` candidate, but does not call `OMSService.apply_order_event(...)`。
- 当前 Stage L.2 已实现 `OrderEventCandidate -> typed OrderEvent -> OMSService.apply_order_event(...)` 应用核心。Stage L.2 只推进 OMS `OrderStatus`，不生成 Trade / Fill ledger，不更新 Position / Accounting，不调用 Broker，不进入 Runtime，不新增 schema。
- 当前 Stage L.3 只创建并持久化 typed Trade fact。Stage L.3 不更新 Position / Accounting，不调用 Broker，不进入 Runtime。

`MockFuturesExchange.run_daily_settlement(trading_day)` 的移除是 intentional interface migration：

- 当前 Phase 4 MockFuturesExchange Protocol 不包含 settlement 方法。
- Future Settlement Protocol 必须在后续 Settlement 阶段另行定义。
- 即使 `interfaces/engines.py` 中存在 `SettlementEngine`，它也是全局后续阶段接口，不属于 Phase 4 execution surface。

## Stage K Execution Gateway Core

Stage K implements the Execution Gateway boundary between OMS orders and execution adapters. Execution Gateway owns command creation / adapter dispatch; OMS owns order state; Broker is not in Stage K; Accounting is not involved; Risk is already upstream; Strategy is not involved.

### Source Of Truth

Execution Gateway may consume only：

- OMS Order / `OrderState`。
- OMS `order_id`。
- `client_order_id`。
- instrument identity copied from OMS Order。
- `side` / `offset` / `quantity` / `price` / `order_type` / `tif` copied from OMS Order。
- typed execution config。
- trading session / calendar context。

Execution Gateway must not consume：

- `FeatureSnapshot`。
- `SignalDecision`。
- `OrderIntent` directly，except lineage via OMS Order metadata。
- `RiskEngine`。
- `raw_payload`。
- Broker state as source-of-truth。
- `ExchangeReport` as source-of-truth before normalized。
- Accounting tables。

### Outputs And Effects

Stage K implements / freezes：

- `ExecutionCommand`
- `ExecutionCommandResult`
- `ExecutionReport` normalized later

Execution Gateway outputs only：

- `ExecutionCommand`
- `ExecutionCommandResult`

Execution Gateway must not：

- mutate OMS state directly; future report handling must go through `OMSService.apply_order_event(...)` path。
- mutate Accounting。
- call Strategy / Risk。
- read Broker state as fact。
- submit to real Broker in Stage K contract。

### ExecutionCommand

Fields：

- `command_id`
- `order_id`
- `client_order_id`
- `account_id`
- `instrument_id`
- `trade_instrument_id`
- `exchange`
- `side`
- `offset`
- `quantity`
- `price`
- `order_type`
- `tif`
- `command_type`
- `execution_target`
- `command_payload_hash`
- `created_at`

`command_type`：

- `SUBMIT_ORDER`
- `CANCEL_ORDER` future / deferred if not implemented now

`execution_target`：

- `MOCK`
- `PAPER`
- `SIM`
- `LIVE`

Stage K Core only supports `MOCK` target. `PAPER` / `SIM` / `LIVE` are typed rejected / deferred unless separately scoped.

### Deterministic Identity And Canonical Payload

`command_id` must be deterministic from `order_id + command_type + execution_target`：

- no UUID。
- no timestamp。
- no DB id。
- same order + same target -> same `command_id`。

`ExecutionCommand` canonical includes：

- `order_id`
- `client_order_id`
- `account_id`
- instrument identity
- `side`
- `offset`
- `quantity`
- `price`
- `order_type`
- `tif`
- `command_type`
- `execution_target`

Canonical excludes：

- `raw_payload`
- `created_at`
- `received_at`
- broker response
- DB id

### Idempotency And Replay

same `command_id` + same canonical：

- duplicate / no-op。

same `command_id` + different canonical：

- conflict / error。

Same OMS order must not generate multiple submit commands for same target。

Execution replay：

- same OMS order + same target -> same `ExecutionCommand`。
- same canonical -> duplicate / no-op。
- different canonical -> conflict / error。
- dry-run default。
- must not submit to broker / adapter unless explicit live flag。
- does not mutate OMS / Accounting。

### Service And Repository Boundary

Implemented `ExecutionGatewayService`：

- receives OMS Order / `OrderState`。
- validates order is eligible for execution。
- builds `ExecutionCommand`。
- persists command if repository chosen。
- dispatches only to allowed execution adapter。

Stage K implements persistence：

- `ExecutionCommandRepository`。
- `execution_commands` table。
- reason：commands are facts / audit boundary before broker。

Repository methods：

- `append_execution_command(command)`
- `get_by_command_id(command_id)`
- `list_by_order_id(order_id)`
- `list_by_target(execution_target, start_ts, end_ts)`

Unique：

- `command_id`

Indexes：

- `order_id`
- `client_order_id`
- `execution_target`
- `created_at`

Stage K creates schema through `0012_stage_k_execution_gateway_core`. It does not add trades, fills, broker tables, execution reports, exchange tables or order events.

### Adapter Boundary

Protocol：

- `ExecutionAdapter.submit(command) -> ExecutionCommandResult`

Adapter must return typed result, not raw broker response。

Stage K Core implements deterministic `MockExecutionAdapter`. It must not implement CTP / SimNow / real broker and must not require network.

### ExecutionCommandResult

Fields：

- `command_id`
- `order_id`
- `status`
- `reason`
- `adapter_order_ref | None`
- `submitted_at | None`
- `raw_payload` diagnostic only

`status`：

- `ACCEPTED_BY_ADAPTER`
- `REJECTED_BY_ADAPTER`
- `DUPLICATE`
- `CONFLICT`
- `ERROR`

Rules：

- Adapter accepted does not mean exchange accepted。
- Broker / exchange reports are later normalized to OMS `OrderEvent`。
- `raw_payload` diagnostic only。

### OMS Relation

Execution Gateway must not mutate OMS directly in Stage K。

Future flow：

```text
ExecutionCommandResult / ExecutionReport
-> normalized OrderEvent
-> OMS.apply_order_event
```

Stage K does not implement normalized broker reports unless separately scoped。

### Stage K Tests

Stage K tests cover：

- deterministic `command_id`。
- canonical excludes raw / timestamps。
- duplicate same canonical。
- duplicate different canonical conflict。
- unsupported `execution_target` reject。
- OMS order not executable reject。
- mock adapter submit result。
- replay dry-run no adapter call。
- explicit replay submit flag。
- repository round trip。
- schema contract。
- no Broker / CTP / SimNow imports。
- no Accounting mutation。
- no OMS direct state mutation。

### Stage K Explicit Non-goals

Stage K does not implement：

- real Broker adapter。
- CTP。
- SimNow。
- live trading。
- exchange connectivity。
- fill matching。
- trade generation。
- accounting update。
- broker reconciliation。
- runtime scheduler。
- Kafka / FastAPI / Celery。

## Stage L Execution Report Normalization Core

Stage L implements the Execution Report Normalizer boundary. The normalizer converts typed adapter report input into deterministic `NormalizedExecutionReport` facts and may build a typed OMS `OrderEvent` candidate for later application-layer routing. Stage L does not apply the candidate to OMS and does not generate Trade / Fill ledger facts.

Implemented Stage L Core boundary：

1. normalize typed adapter report。
2. build `OrderEvent` candidate when report status is mappable。
3. persist `NormalizedExecutionReport`。
4. do not mutate OMS。

### Source Of Truth

Execution Report Normalizer may consume only：

- `ExecutionCommand`。
- `ExecutionCommandResult`。
- typed adapter report input。
- adapter identity。
- `command_id` / `order_id` / `client_order_id` lineage。
- typed timestamp normalization rule。

Execution Report Normalizer must not consume：

- `FeatureSnapshot`。
- `SignalDecision`。
- `TradingRiskResult`。
- `OrderIntent` mutation。
- Accounting tables。
- Position tables。
- Margin / PnL / Settlement。
- Broker state as source-of-truth。
- `raw_payload` as facts。

### RawExecutionReport

`RawExecutionReport` is the typed raw adapter input. It is raw only relative to the normalizer; it must already expose source-of-truth fields as typed domain values.

Fields：

| Field | Type | Semantics |
|---|---|---|
| `raw_report_id` | `str` | adapter report identity, unique per adapter when available。 |
| `adapter_name` | `str` | adapter identity。 |
| `execution_target` | `ExecutionTarget` | adapter target。 |
| `command_id` | `str` | originating `ExecutionCommand.command_id`。 |
| `order_id` | `str` | OMS order identity lineage。 |
| `client_order_id` | `str` | OMS client order identity lineage。 |
| `adapter_order_ref` | `str` | adapter-local order reference。 |
| `exchange_order_id` | `str \| None` | external exchange order id if available。 |
| `report_type` | `str` | adapter-normalized report type。 |
| `filled_qty` | `Decimal` | quantity represented by this report。 |
| `fill_price` | `Decimal \| None` | fill price when applicable。 |
| `cumulative_filled_qty` | `Decimal` | cumulative filled quantity。 |
| `remaining_qty` | `Decimal` | remaining quantity。 |
| `report_ts` | `datetime` | normalized report event time。 |
| `received_at` | `datetime` | local adapter receive time; excluded from canonical equality。 |
| `raw_payload` | `dict[str, Any]` | diagnostic only。 |

Rules：

- `raw_payload` is diagnostic only and must not supply source-of-truth fields。
- Adapter must normalize external millisecond / microsecond / nanosecond timestamps before entering domain if possible。
- Quantities and prices must be `Decimal` only。
- Float is forbidden for quantities and prices。

### NormalizedExecutionReport

`NormalizedExecutionReport` is the deterministic execution report fact emitted by the normalizer.

Fields：

| Field | Type | Semantics |
|---|---|---|
| `report_id` | `str` | deterministic normalized report identity。 |
| `raw_report_id` | `str` | lineage to `RawExecutionReport.raw_report_id`。 |
| `adapter_name` | `str` | adapter identity。 |
| `execution_target` | `ExecutionTarget` | adapter target。 |
| `command_id` | `str` | originating command identity。 |
| `order_id` | `str` | OMS order identity lineage。 |
| `client_order_id` | `str` | OMS client order identity lineage。 |
| `adapter_order_ref` | `str` | adapter-local order reference。 |
| `exchange_order_id` | `str \| None` | external exchange order id if available。 |
| `execution_status` | `ExecutionReportStatus` | normalized execution status, not OMS `OrderStatus`。 |
| `filled_qty` | `Decimal` | quantity represented by this report。 |
| `fill_price` | `Decimal \| None` | fill price when applicable。 |
| `cumulative_filled_qty` | `Decimal` | cumulative filled quantity。 |
| `remaining_qty` | `Decimal` | remaining quantity。 |
| `report_ts` | `datetime` | normalized report event time。 |
| `normalized_at` | `datetime` | local normalization time; excluded from canonical equality。 |
| `reason` | `str \| None` | typed reason / diagnostic summary。 |
| `source_report_hash` | `str` | hash of canonical `RawExecutionReport`。 |

Rules：

- `report_id` must be deterministic。
- `source_report_hash` is derived from canonical `RawExecutionReport`。
- Same raw report must produce the same normalized report。
- The normalizer may not use broker raw facts beyond the typed raw report。
- The normalizer must not directly mutate OMS。

### ExecutionReportStatus

`ExecutionReportStatus` is frozen as：

- `SUBMITTED`
- `ACKED`
- `PARTIALLY_FILLED`
- `FILLED`
- `REJECTED`
- `CANCELED`
- `ERROR`

`ExecutionReportStatus` is not OMS `OrderStatus`。Mapping to OMS `OrderEvent` happens later at the application layer / Stage L implementation boundary。

### Mapping To OMS OrderEvent

Future mapping：

```text
NormalizedExecutionReport
-> OrderEvent
```

Mapping table：

| `ExecutionReportStatus` | OMS event |
|---|---|
| `ACKED` | OMS `ACKED` event |
| `PARTIALLY_FILLED` | OMS `PARTIALLY_FILLED` event |
| `FILLED` | OMS `FILLED` event |
| `REJECTED` | OMS `REJECTED_BY_EXCHANGE` event |
| `CANCELED` | OMS `CANCELED` event |

Rules：

- Normalizer may create typed `OrderEvent` candidate。
- Normalizer must not call `OMSService.apply_order_event(...)` directly。OMS application is owned by Stage L.2 application service。
- Stage L Core recommendation is to normalize report, build `OrderEvent` candidate, persist normalized report, and not mutate OMS。
- OMS apply is the Stage L.2 bridge / application step。

### Fill And Trade Boundary

Stage L must not：

- create Trade ledger directly。
- update Position。
- update Margin / PnL / Settlement。
- generate accounting facts。

Fill-like fields in execution reports are execution-state facts only. They are not Trade facts yet。

Future trade creation remains later：

```text
Normalized filled report
-> OMS OrderEvent
-> Trade/Fills ledger adapter later
```

### Idempotency

`RawExecutionReport` identity：

- `raw_report_id` unique per adapter if available。
- fallback deterministic key：`adapter_name + command_id + report_type + report_ts + cumulative_filled_qty`。

`NormalizedExecutionReport` identity：

- `report_id` deterministic。
- same canonical -> duplicate / no-op。
- different canonical -> conflict / error。

Canonical excludes：

- `raw_payload`
- `received_at`
- `normalized_at`
- DB id

### Repository / Migration Contract

Implemented repository：

- `ExecutionReportRepository`
- SQLAlchemy repository。
- `UnitOfWork.execution_reports`。
- narrow `ExecutionReportUnitOfWork`。
- `normalized_execution_reports` table。
- no `raw_execution_reports` table。

Repository methods：

- `append_normalized_report(report)`
- `get_by_report_id(report_id)`
- `list_by_order_id(order_id)`
- `list_by_command_id(command_id)`
- `list_by_status(execution_status, start_ts, end_ts)`

Unique：

- `report_id`

Indexes：

- `order_id`
- `command_id`
- `client_order_id`
- `execution_status`
- `report_ts`

### Replay

Report replay：

- consumes ordered `RawExecutionReport`。
- same raw -> same normalized report。
- same canonical -> duplicate / no-op。
- different canonical -> conflict。
- must not call OMS。
- must not update Accounting。
- must not generate Trade。

### Boundary Split

- Execution Gateway：creates commands。
- Execution Report Normalizer：normalizes adapter reports。
- OMS：owns order state。
- Accounting：not involved。
- Trade ledger：not involved。
- Broker：not source-of-truth。

### Stage L Tests

Stage L tests cover：

- Decimal-only raw report。
- deterministic `report_id`。
- `source_report_hash`。
- status mapping。
- `OrderEventCandidate` mapping。
- `SUBMITTED` / `ERROR` no candidate。
- duplicate same canonical。
- conflict different canonical。
- `raw_payload` excluded。
- replay deterministic。
- repository round trip。
- UoW exposes execution reports。
- `normalized_execution_reports` schema。
- no `raw_execution_reports` table。
- no `OMSService.apply_order_event(...)` call。
- no Trade / Fill / Position / Accounting mutation。
- no Broker / CTP / SimNow dependency。

### Stage L Explicit Non-goals

Stage L does not implement：

- Broker adapter。
- CTP / SimNow / live。
- Trade ledger generation。
- Fill ledger generation。
- Position update。
- Accounting update。
- OMS direct mutation unless separately scoped。
- Runtime scheduler。
- Kafka / FastAPI / Celery。

## Stage L.2 OMS Event Application Core

Stage L.2 implements the application core that turns an `OrderEventCandidate` into a typed OMS `OrderEvent` and applies it through OMS only when `allow_live_apply=True`. It only advances OMS `OrderStatus` and deliberately stops before Trade / Fill / Position / Accounting / Broker / Runtime.

Implemented objects：

- `OMSEventApplyResultStatus`
- `OMSEventApplyResult`
- `OMSEventApplyContext`
- deterministic `event_id`
- candidate -> typed `OrderEvent` mapper
- canonical order event payload
- `OMSOrderEventApplier` Protocol
- `OMSOrderEventLookup` read-only Protocol
- `OMSEventApplicationService`
- dry-run default `replay_oms_order_events`

Source-of-truth flow：

```text
NormalizedExecutionReport
-> OrderEventCandidate
-> typed OrderEvent
-> OMSService.apply_order_event(...)
-> OMS OrderState transition
```

### Stage L.2 Source Of Truth

Allowed inputs：

- `NormalizedExecutionReport`。
- `OrderEventCandidate`。
- current OMS `OrderState`。
- typed application context。

Forbidden inputs：

- `FeatureSnapshot`。
- `SignalDecision`。
- `TradingRiskResult`。
- `OrderIntent` mutation。
- `raw_payload` facts。
- Broker state。
- Accounting tables。
- Position tables。
- Margin / PnL / Settlement。

OMS state changes can only happen through：

```text
OrderEventCandidate -> typed OrderEvent -> OMS.apply_order_event
```

### Event Identity

`event_id` must be deterministic from：

- `report_id`
- `order_id`
- `execution_status`
- `cumulative_filled_qty`
- `report_ts`

Forbidden identity sources：

- UUID。
- timestamp-now。
- DB id。

### Candidate To OrderEvent Mapping

| `OrderEventCandidate` status | OMS event |
|---|---|
| `ACKED` | `ACKED` |
| `PARTIALLY_FILLED` | `PARTIALLY_FILLED` |
| `FILLED` | `FILLED` |
| `REJECTED` | `REJECTED_BY_EXCHANGE` |
| `CANCELED` | `CANCELED` |
| `SUBMITTED` | no-op / no event |
| `ERROR` | no event |

`SUBMITTED` and `ERROR` must not call OMS.

Stage L normalizer normally emits `OrderEventCandidate` only for
`ACKED` / `PARTIALLY_FILLED` / `FILLED` / `REJECTED` / `CANCELED`.
It does not emit candidates for `SUBMITTED` or `ERROR`. Stage L.2 still
defensively handles manually supplied `SUBMITTED` and `ERROR` candidates as
no-event results (`NO_OP` / `REJECTED_NO_EVENT`) without calling OMS.

### OMS Apply Boundary

Only Stage L.2 application service may call：

- `OMSService.apply_order_event`

It must not call：

- `OMSService.create_order`
- Execution adapter
- Broker
- Accounting
- PositionManager
- TradeRepository

Terminal order protection remains owned by OMS state machine.

### Idempotency And Replay

Idempotency：

- same candidate -> same `OrderEvent` -> same OMS transition / no-op。
- before live OMS apply, Stage L.2 must lookup existing OMS `order_events` by deterministic `event_source + event_id` and compare the typed canonical order-event payload。
- existing same canonical -> `DUPLICATE` / no-op before calling OMS。
- existing different canonical, or existing event missing typed canonical fields -> `CONFLICT` before calling OMS。
- different candidate same `event_id` -> `CONFLICT`。
- duplicate event behavior uses existing OMS `order_events` semantics。
- terminal order protection remains owned by OMS state machine。

Replay：

- same normalized report -> same candidate -> same `OrderEvent`。
- live replay must run a full canonical preflight across the replay batch before any OMS apply。
- if any batch item has same `event_id` + different canonical payload, replay returns `CONFLICT` and performs no OMS apply。
- replay may call OMS only in explicit OMS replay mode。
- default review recommendation：dry-run first。
- live apply requires explicit flag。

### Repository Decision

Stage L.2 uses existing `order_events` as the OMS event ledger. No Stage L.2 audit table, repository, migration or schema change is added.

If extra audit is needed later, it must be introduced by a separate contract amendment.

### Explicit Non-goals

Stage L.2 does not implement：

- Trade ledger。
- Fill ledger。
- Position update。
- Margin / PnL / Settlement update。
- Broker / CTP / SimNow。
- Runtime / Kafka / Celery / FastAPI。

## Stage L.3 OMS-to-Trade Bridge Core

Stage L.3 implements the boundary that turns OMS-confirmed filled reports into typed `Trade` facts and persists them through the existing `TradeRepository`.

Migration `0014_stage_l3_oms_to_trade_bridge.py` extends only existing bridge inputs / outputs：`trades` gets `identity_source`、`client_order_id`、`trade_instrument_id`、`symbol`、`source_report_id`、`source_order_event_id`；`normalized_execution_reports` gets optional typed `exchange_trade_id`、`fill_id`、`fee_amount`、`fee_currency`、`fee_source`。No second trade ledger is created.

Source-of-truth flow：

```text
NormalizedExecutionReport / OrderEventCandidate / applied OMS OrderEvent
-> OMS-to-Trade Bridge
-> typed Trade fact
-> TradeRepository persistence
-> PositionManager handoff later
```

### Stage L.3 Source Of Truth

Allowed inputs：

- `NormalizedExecutionReport` with `execution_status` in `PARTIALLY_FILLED` / `FILLED`。
- applied OMS `OrderEvent` or OMS `OrderState` proving OMS accepted the compatible filled status。
- existing OMS `OrderState` / order identity。
- typed instrument/account identity。
- typed fee input if available。
- `exchange_trade_id` / fill identity from typed report fields if available。

Forbidden inputs：

- `raw_payload` facts。
- Broker state as truth。
- `FeatureSnapshot`。
- `SignalDecision`。
- `TradingRiskResult`。
- `OrderIntent` mutation。
- Position table。
- Margin / PnL / Settlement。
- Runtime / Kafka / Celery / FastAPI。

### Stage L.3 Required Gate

Trade fact may be created only if：

- normalized report status is `PARTIALLY_FILLED` or `FILLED`。
- corresponding OMS `OrderEvent` has been applied and binds to the current report, or OMS `OrderState` confirms a compatible filled state with typed filled quantity proof。
- `order_id` / `client_order_id` lineage matches。
- `filled_qty > 0`。
- `fill_price > 0`。
- trade identity is stable。

Applied OMS `OrderEvent` proof must match current `NormalizedExecutionReport` on `event_source == EXECUTION_REPORT_NORMALIZER`、`order_id`、`report_id`、`execution_status` and mapped OMS `new_status`、`filled_qty`、`fill_price`、`cumulative_filled_qty` and `report_ts`。Missing typed proof fields are rejected conservatively; Stage L.3 must not recover proof from `raw_payload`。

Compatible `OrderState` proof without applied event is allowed only when `FILLED` report maps to `FILLED` state, `PARTIALLY_FILLED` report maps to `PARTIALLY_FILLED` or `FILLED` state, and `OrderState.filled_quantity >= NormalizedExecutionReport.cumulative_filled_qty`。State-only proof confirms eligibility, not event identity, so `source_order_event_id` must be absent / `None` unless a matching applied OMS `OrderEvent` proof exists。

No Trade may be created from：

- `ACKED`。
- `SUBMITTED`。
- `REJECTED`。
- `CANCELED`。
- `ERROR`。
- adapter accepted only。
- un-applied `OrderEventCandidate`。

### Stage L.3 Trade Identity

Preferred identity：

- `account_id + exchange + exchange_trade_id`。

If `exchange_trade_id` is unavailable：

- must not invent random id。
- may use fallback only if deterministic and collision-safe：
  `account_id + exchange + order_id + report_id + cumulative_filled_qty + fill_price + report_ts`。
- fallback must be explicitly marked `identity_source=derived_from_report`。
- if fallback identity cannot be proven stable, bridge must return typed reject。

Forbidden identity sources：

- UUID。
- timestamp-now。
- DB id。
- raw-payload-only field。

### Stage L.3 Trade Fields

Trade fact must include：

- `trade_id` or `id`。
- `account_id`。
- `exchange`。
- `exchange_trade_id` or deterministic fallback identity。
- `identity_source`。
- `order_id`。
- `client_order_id`。
- `instrument_id`。
- `trade_instrument_id`。
- `symbol`。
- `side` / `direction`。
- `offset`。
- Decimal `price`。
- Decimal `quantity`。
- `fee_amount | None`。
- `fee_currency | None`。
- `fee_source | None`。
- `trade_time`。
- `trading_day | None`。
- `source_report_id`。
- `source_order_event_id`。
- diagnostic-only `raw_payload`。

Fee semantics：

- `fee_amount is None` means unknown。
- `fee_amount == Decimal("0")` means known zero。
- if `fee_amount is not None`, `fee_currency` and typed `fee_source` are required。
- Stage L.3 does not compute fee。

### Stage L.3 TradeBridgeResult

`TradeBridgeResultStatus` is frozen as：

- `CREATED`。
- `DUPLICATE`。
- `REJECTED_NOT_FILLED`。
- `REJECTED_OMS_NOT_APPLIED`。
- `REJECTED_MISSING_TRADE_IDENTITY`。
- `REJECTED_LINEAGE_MISMATCH`。
- `CONFLICT`。
- `ERROR`。

`TradeBridgeResult` fields：

- `status`。
- `trade | None`。
- `source_report_id`。
- `source_order_event_id | None`。
- `reason | None`。

### Stage L.3 Repository And Canonical

Stage L.3 reuses existing `TradeRepository`. It must not create a second trade ledger.

Required repository behavior：

- same trade identity + same canonical -> duplicate / no-op。
- same trade identity + different canonical -> `CONFLICT`。
- `raw_payload` excluded from canonical。
- fees included in canonical with unknown vs zero distinction。

Current `Trade` / `trades` schema supports the implemented L.3 boundary directly：basic Trade facts, fees, `trading_day`, `source_exchange_report_id`, diagnostic `raw_payload`, `UNIQUE(account_id, exchange, exchange_trade_id)`, plus `identity_source`、`client_order_id`、`trade_instrument_id`、`symbol`、`source_report_id` and `source_order_event_id`。

`TradeRepository` keeps `create_or_get_trade(trade)` and adds `append_trade(trade)`、`get_by_trade_identity(account_id, exchange, exchange_trade_id)` and `list_by_order_id(order_id)` for the bridge and replay surface.

Trade canonical includes：

- `account_id`。
- `exchange`。
- `exchange_trade_id` or fallback identity。
- `identity_source`。
- `order_id`。
- `client_order_id`。
- `instrument_id`。
- `trade_instrument_id`。
- `symbol`。
- `side` / `direction`。
- `offset`。
- `price`。
- `quantity`。
- `fee_amount`。
- `fee_currency`。
- `fee_source`。
- `trade_time`。
- `trading_day`。
- `source_report_id`。
- `source_order_event_id`。

Trade canonical excludes：

- `raw_payload`。
- `created_at`。
- `updated_at`。
- DB id。

### Stage L.3 OMS Boundary

OMS-to-Trade Bridge may read OMS `OrderState` / applied `OrderEvent` through typed read-only ports.

It must not：

- call `OMS.apply_order_event`。
- call `OMS.create_order`。
- mutate OMS state。
- alter order status。
- infer fills from OMS status alone without normalized report quantity / price。

OMS status confirms eligibility. `NormalizedExecutionReport` provides fill economics.

### Stage L.3 Position / Accounting Boundary

Stage L.3 must not：

- call `PositionManager.apply_trade`。
- update positions。
- update margin。
- update pnl。
- update settlement。
- update account snapshot。

It may emit typed Trade fact for later PositionManager handoff.

### Stage L.3 Replay And Idempotency

Replay：

- consumes ordered eligible normalized reports + applied OMS event proof。
- same input -> same Trade。
- same canonical -> duplicate / no-op。
- different canonical -> `CONFLICT`。
- does not update Position / Accounting。
- does not mutate OMS。

### Stage L.3 Explicit Non-goals

Stage L.3 does not implement：

- Position update。
- Margin update。
- PnL update。
- Settlement update。
- broker reconciliation。
- runtime scheduling。
- Kafka / FastAPI / Celery。
- CTP / SimNow / live broker。
- fee calculation。
- trade correction / cancel flows。

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
- `PARTIAL_FILL` / `FULL_FILL` require order identity。Stage B typed fill mode 还要求类型化成交字段，不得只放在 `raw_payload`。

Stage B typed fill fields：

- `exchange_trade_id: str`
- `fill_id: str | None`
- `fill_price: Decimal`
- `fill_quantity: Decimal`
- `fee_amount: Decimal | None`
- `fee_currency: str | None`
- `fee_source: str | None`
- `traded_at: datetime`
- `trading_day: date | None`

`fee_currency` 在 `fee_amount is not None` 时必填。`fee_amount is None` 表示未知，`fee_amount == Decimal("0")` 表示明确为零。

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
- `allow_status_only_fill=True` 时，`PARTIAL_FILL` / `FULL_FILL` 保持兼容行为，只映射订单状态。
- `allow_status_only_fill=False` 且 typed fill fields 完整时，`PARTIAL_FILL` / `FULL_FILL` 允许产出 typed fill / trade fact。
- `allow_status_only_fill=False` 但 typed fill fields 缺失时，返回 typed non-event result：字段缺失用 `MAPPING_ERROR`，缺上下文用 `INSUFFICIENT_CONTEXT`，当前契约无法承载时用 `DOMAIN_FIELD_UNSUPPORTED`。

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

### Stage B MappingResult Extension

Stage B 选择扩展 `MappingResult`，而不是新增独立 `FillMappingResult` / `TradeExtractionResult`。

冻结后的 `MappingResult` 语义：

- `status: MappingResultStatus`
- `order_event: OrderEvent | None`
- `fill_event: FillEvent | None`
- `trade: Trade | None`
- `error: MappingError | None`

选择原因：

- `PARTIAL_FILL` / `FULL_FILL` 同时影响订单状态和成交事实；同一个 report 需要在一个 pure mapper result 中表达 `OrderEvent + FillEvent + Trade` bundle。
- Orchestrator 已经按 `MappingResult` 做分流，扩展同一 result 可减少并行结果类型造成的 routing drift。
- Mapper 仍保持纯函数，只产出类型化事实，不写 DB、不更新 OMS、不更新 Position。

Stage B 路由边界：

- `order_event` 只交给 OMS apply。
- `fill_event` 只作为 execution typed fact，不直接更新 Position。
- `trade` 只交给 `TradeRepository.create_or_get_trade(...)` 或后续 accounting application service。
- `DUPLICATE_REPORT`、`IGNORED_REPORT`、`INSUFFICIENT_CONTEXT`、`MAPPING_ERROR`、`DOMAIN_FIELD_UNSUPPORTED` 和 `ENTER_UNKNOWN_CANDIDATE` 不写 Trade。

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
- `PARTIALLY_FILLED -> PARTIALLY_FILLED` 继续允许，用于多次部分成交的合法状态事件；它仍不代表 Trade ledger 已入账。
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
- `exchange_trade_id`
- `fee amount`
- `fee currency`
- `fee source`
- `traded_at`
- `trading_day`

Phase 4.1 status-only fill mapping 不承载 fill quantity / fill price / trade id / fill id。真实成交事实必须先做 Domain / interface / schema migration 或 Trade / Fill 专属契约。

Stage B 后，`allow_status_only_fill=True` 仍保留旧行为，只映射订单状态；`allow_status_only_fill=False` 必须使用 typed fill fields 产出 `FillEvent` / `Trade`，缺 typed fields 时不得从 `raw_payload` 补事实。

### Stage B Trade Repository Contract

Stage B 冻结 `TradeRepository`：

- `create_or_get_trade(trade)`：以 `account_id + exchange + exchange_trade_id` 幂等写入或返回 existing。
- `get_by_exchange_trade_id(account_id, exchange, exchange_trade_id)`：按交易所成交身份查询。
- duplicate same payload 返回 existing。
- duplicate different payload 抛 `TradeIdempotencyConflictError`。
- repository 不更新 Position，不修改 OMS，不调用 mapper，不消费 `OrderEvent`。

`UNIQUE(account_id, exchange, exchange_trade_id)` 是 `trades` ledger 必须保留的唯一约束。如 broker 无 `exchange_trade_id`，不能用随机 id；必须先冻结稳定替代键，否则不允许入账。

### Stage B Not Allowed

Stage B 不实现：

- Position update。
- Margin update。
- PnL update。
- Settlement。
- broker reconciliation。
- OMS public UNKNOWN entry。
- Runtime infra。
- CTP / SimNow / broker adapter。

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

- Position update。
- Margin update。
- PnL update。
- Settlement。
- today/yesterday position roll。
- true CTP adapter。
- true SimNow adapter。
- broker adapter。
- live / prod / production / remote / KMS / cloud。
