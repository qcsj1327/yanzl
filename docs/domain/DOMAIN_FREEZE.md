# Domain 冻结契约

本文档冻结 `futures_mvp` 当前已经存在的 Domain 事实。本文档只基于当前实现，不冻结未来设计，也不迁移旧项目中已经废弃的字段。

## 事实来源

当前权威事实来源为：

- `src/futures_mvp/domain/enums.py`
- `src/futures_mvp/domain/models.py`
- `src/futures_mvp/interfaces/engines.py`
- `src/futures_mvp/interfaces/repositories.py`
- `src/futures_mvp/db/models.py`
- `alembic/versions/0001_initial_schema.py`
- `alembic/versions/0002_oms_repository_support.py`
- `alembic/versions/0011_stage_j_trading_workflow_core.py`
- `alembic/versions/0012_stage_k_execution_gateway_core.py`

`DOMAIN_FREEZE.md` 不得遗漏当前 Domain 契约中已经存在的字段。新增字段、删除字段、字段重命名或字段语义变化，必须通过 domain migration，并同步更新本文档。

`DOMAIN_FREEZE.md` 只冻结接口契约边界，不复制 Repository / UnitOfWork 的详细设计。Repository / UnitOfWork 的职责、事务边界、幂等行为和持久化细节以 `docs/oms/OMS_REPOSITORY.md` 为准。

## 冻结规则

`domain/*` 的长期目标：

- 只允许 enum、dataclass、类型字段和默认值。
- 禁止业务逻辑、IO、adapter、config、UI 和 orchestration 调用。
- `metadata`、`raw`、`details`、`raw_payload` 不得承载 source-of-truth 字段。
- 未来字段在真正进入代码和 schema 前，只能写入 Known Deviations 或 Future Migration。

当前 Phase 1 偏差：

- `domain/models.py` 当前使用 Pydantic `BaseModel`，不是 dataclass。
- `domain/models.py` 当前使用 validator 做 Decimal/float 基础模型校验。
- 这些偏差在 Phase 1 暂时允许；后续只能通过独立 domain migration 迁移。迁移时不得顺手改变字段语义。

## 全局语义

时间：

- Domain model 当前使用 `datetime` 和 `date`。
- 数据库 model 使用 `DateTime(timezone=True)` 和 `Date`。
- `created_at`、`occurred_at`、`trade_time`、`snapshot_time`、`trading_day` 各有独立语义，不得混用。

合约身份：

- `instrument_id` 是当前已经冻结的期货合约字段。
- Stage G 已在 Market Data domain/schema 中实现 `symbol` 和 `trade_instrument_id`。
- Market Data identity 当前包括：`symbol` 是基础品种，例如 `au`；`instrument_id` 是行情合约 identity；`trade_instrument_id` 是交易合约 identity；`exchange` 是交易所；`trading_day` 是 calendar/session rule 给出的交易日。
- 非 Market Data 事实如果后续要分离 `symbol`、`instrument_id`、`trade_instrument_id`，必须通过 domain migration；不得通过 `raw_payload` 或 JSON 字段偷带缺失的身份字段。

价格：

- `limit_price` 是委托限价。
- `Trade.price` 是成交价。
- `Position.last_price` 是最新行情价。
- `settlement_price` 是结算价。
- `expected_price` 当前不是 Domain 字段，不得当作当前冻结事实。

订单、成交与持仓：

- pending、submitted、rejected 或其他未成交订单都不是真实持仓。
- OMS 订单状态是订单状态事实来源。
- 每次订单状态变化必须对应一条 `order_events` 记录。
- 当前 live position 事实来源是每个 `account_id + instrument_id` 一行的 `positions`。
- `account_snapshots` 和 `settlement_snapshots` 是快照，不是 live source of truth。

## 当前 Enums

### Direction

| 名称 | 值 |
|---|---|
| `BUY` | `BUY` |
| `SELL` | `SELL` |

### Offset

| 名称 | 值 |
|---|---|
| `OPEN` | `OPEN` |
| `CLOSE` | `CLOSE` |
| `CLOSE_TODAY` | `CLOSE_TODAY` |
| `CLOSE_YESTERDAY` | `CLOSE_YESTERDAY` |

### OrderType

| 名称 | 值 |
|---|---|
| `LIMIT` | `LIMIT` |

### OrderStatus

| 名称 | 值 |
|---|---|
| `CREATED` | `CREATED` |
| `RISK_CHECKING` | `RISK_CHECKING` |
| `REJECTED_BY_RISK` | `REJECTED_BY_RISK` |
| `RISK_ACCEPTED` | `RISK_ACCEPTED` |
| `SUBMITTING` | `SUBMITTING` |
| `SUBMIT_TIMEOUT` | `SUBMIT_TIMEOUT` |
| `SUBMIT_FAILED` | `SUBMIT_FAILED` |
| `SUBMITTED` | `SUBMITTED` |
| `ACKED` | `ACKED` |
| `PARTIALLY_FILLED` | `PARTIALLY_FILLED` |
| `CANCEL_PENDING` | `CANCEL_PENDING` |
| `CANCEL_FAILED` | `CANCEL_FAILED` |
| `CANCELED` | `CANCELED` |
| `FILLED` | `FILLED` |
| `REJECTED_BY_EXCHANGE` | `REJECTED_BY_EXCHANGE` |
| `EXPIRED` | `EXPIRED` |
| `UNKNOWN` | `UNKNOWN` |

### EventSource

| 名称 | 值 |
|---|---|
| `STRATEGY` | `STRATEGY` |
| `RISK` | `RISK` |
| `OMS` | `OMS` |
| `EMS` | `EMS` |
| `EXCHANGE` | `EXCHANGE` |
| `SETTLEMENT` | `SETTLEMENT` |
| `SYSTEM` | `SYSTEM` |

### RiskDecision

`RiskDecision` 是 enum，不是 Domain Model。

| 名称 | 值 |
|---|---|
| `ACCEPTED` | `ACCEPTED` |
| `REJECTED` | `REJECTED` |

### EventApplicationStatus

`EventApplicationStatus` 是 OMS application service 的类型化事件应用结果。它不得写成裸字符串散落在 OMSService 内部，也不得藏进 `raw_payload` 作为 source-of-truth。

| 名称 | 值 |
|---|---|
| `APPLIED` | `APPLIED` |
| `DUPLICATE` | `DUPLICATE` |
| `OLD_IGNORED` | `OLD_IGNORED` |
| `MISMATCH_REJECTED` | `MISMATCH_REJECTED` |
| `ENTERED_UNKNOWN` | `ENTERED_UNKNOWN` |
| `RECOVERED_FROM_UNKNOWN` | `RECOVERED_FROM_UNKNOWN` |
| `IGNORED_TERMINAL` | `IGNORED_TERMINAL` |
| `EVENT_KEY_COLLISION` | `EVENT_KEY_COLLISION` |

## 当前 Domain Models

所有 Decimal 兼容字段在 Domain 语义中必须保持为 Decimal。不得引入 float 字段。

### DomainModel

当前实现基类：`pydantic.BaseModel`。

当前配置：

- `frozen=True`
- `extra="forbid"`

### Signal

| 字段 | 类型 | 默认值 | 语义 |
|---|---|---|---|
| `signal_id` | `str` | required | 信号 ID。 |
| `account_id` | `str` | required | 账户 ID。 |
| `instrument_id` | `str` | required | 当前期货合约 ID。 |
| `exchange` | `str` | required | 交易所代码。 |
| `direction` | `Direction` | required | 买卖方向。 |
| `offset` | `Offset` | required | 开平方向。 |
| `limit_price` | `Decimal` | required | 策略建议限价，不是成交价。 |
| `quantity` | `Decimal` | required | 信号数量。 |
| `created_at` | `datetime` | required | 信号创建时间。 |

策略引擎只能输出 `Signal`。`Signal` 不是订单。

Stage I 已新增 Strategy / Signal Lifecycle 专用 `SignalCandidate` / `SignalDecision` / `TriggerResult`。不得把当前 legacy `Signal` 扩展成 Stage I 订单入口；legacy `Signal` 仍只是早期最小信号模型，不代表 Strategy lifecycle。

### OrderRequest

| 字段 | 类型 | 默认值 | 语义 |
|---|---|---|---|
| `client_order_id` | `str` | required | 客户端订单幂等键。 |
| `account_id` | `str` | required | 账户 ID。 |
| `instrument_id` | `str` | required | 当前期货合约 ID。 |
| `exchange` | `str` | required | 交易所代码。 |
| `direction` | `Direction` | required | 买卖方向。 |
| `offset` | `Offset` | required | 开平方向。 |
| `order_type` | `OrderType` | `OrderType.LIMIT` | 订单类型。 |
| `limit_price` | `Decimal` | required | 委托限价。 |
| `quantity` | `Decimal` | required | 委托数量。 |

OMS 不计算风控。`OMSService.create_order` 只创建 `CREATED` 订单和初始 OMS 事件；风控结果通过 `OMSService.apply_risk_result` 消费外部 `RiskResult` 推进订单状态。

`RiskDecision.ACCEPTED` 推进到 `RISK_ACCEPTED`，`RiskDecision.REJECTED` 推进到 `REJECTED_BY_RISK`。`Signal -> OrderRequest -> RiskResult` 的上层应用编排不属于 OMS `create_order` 的内部前置条件。

Phase 3 pure Risk 可以实现风控计算，但不得直接调用 `OMSService` 或写 DB。未来 Risk -> OMS 集成不得提前写成当前事实。

### OrderState

| 字段 | 类型 | 默认值 | 语义 |
|---|---|---|---|
| `order_id` | `str` | required | OMS 订单 ID。 |
| `request` | `OrderRequest` | required | 原始订单请求。 |
| `status` | `OrderStatus` | `OrderStatus.CREATED` | 当前 OMS 订单状态。 |
| `filled_quantity` | `Decimal` | `Decimal("0")` | 累计成交数量。 |
| `reject_reason` | `str \| None` | `None` | 拒绝原因。 |
| `version` | `int` | `0` | 来自 `orders.version`，用于 OMS 状态更新乐观锁。 |

OMS 是订单状态唯一事实来源。

`OrderState.version` 只表示 `orders.version` 乐观锁版本。每次 Repository `update_status` 成功后递增。它不表示业务事件序号，不表示交易所版本，也不替代 `order_events.id`、`order_events.occurred_at` 或 `external_event_id`。

### RiskResult

`RiskResult` 是包含 `RiskDecision` 的 Domain Model。

| 字段 | 类型 | 默认值 | 语义 |
|---|---|---|---|
| `decision` | `RiskDecision` | required | 风控决策 enum。 |
| `rule_name` | `str` | required | 产生结果的风控规则。 |
| `reason` | `str \| None` | `None` | 可选风控说明。 |

### OrderEvent

| 字段 | 类型 | 默认值 | 语义 |
|---|---|---|---|
| `order_id` | `str` | required | OMS 订单 ID。 |
| `previous_status` | `OrderStatus \| None` | required | 变更前订单状态。 |
| `new_status` | `OrderStatus` | required | 变更后订单状态。 |
| `event_source` | `EventSource` | required | 事件来源。 |
| `external_event_id` | `str` | required | 事件摄入幂等键。 |
| `raw_payload` | `dict[str, Any]` | required | 原始诊断 payload，不是事实来源。 |
| `occurred_at` | `datetime` | required | 事件发生时间。 |

当前 schema 幂等约束为 `UNIQUE(event_source, external_event_id)`。

### OrderEventApplicationResult

`OrderEventApplicationResult` 是 OMS application service 返回的类型化事件应用结果。

| 字段 | 类型 | 默认值 | 语义 |
|---|---|---|---|
| `status` | `EventApplicationStatus` | required | OMS 对事件或恢复操作的类型化处理结果。 |
| `order` | `OrderState` | required | 处理完成后当前请求订单的状态，不得返回其他订单状态。 |
| `reason` | `str \| None` | `None` | 可选诊断原因，不是 source-of-truth。 |

`OrderEventApplicationResult` 只描述 OMS 应用层语义，不替代 `order_events` 事件流，也不进入 DB schema。

### FillEvent

Stage B 冻结 `FillEvent` 作为 execution report 中的类型化成交事实。它描述“收到了一条成交事实”，不直接更新 Position，也不替代 `Trade` ledger。

| 字段 | 类型 | 默认值 | 语义 |
|---|---|---|---|
| `id` | `str` | required | FillEvent 本地身份。 |
| `order_id` | `str` | required | OMS 订单 ID。 |
| `account_id` | `str` | required | 账户 ID。 |
| `exchange` | `str` | required | 交易所代码。 |
| `instrument_id` | `str` | required | 当前期货合约 ID。 |
| `exchange_report_id` | `str` | required | 产生该成交事实的交易所回报 ID。 |
| `exchange_trade_id` | `str` | required | 交易所成交 ID；Trade 幂等主身份。 |
| `fill_id` | `str \| None` | `None` | 交易所或 broker 提供的 fill 子身份；不能替代 `exchange_trade_id`。 |
| `direction` | `Direction` | required | 买卖方向。 |
| `offset` | `Offset` | required | 开平方向。 |
| `price` | `Decimal` | required | 成交价。 |
| `quantity` | `Decimal` | required | 成交数量。 |
| `fee_amount` | `Decimal \| None` | `None` | 手续费金额；`None` 表示未知。 |
| `fee_currency` | `str \| None` | `None` | 手续费币种；`fee_amount is not None` 时必须提供。 |
| `fee_source` | `str \| None` | `None` | 手续费来源，例如 `EXCHANGE_REPORT`、`BROKER_QUERY`、`SETTLEMENT`。 |
| `traded_at` | `datetime` | required | 交易所成交时间。 |
| `trading_day` | `date \| None` | `None` | 交易日；未解析时不得用 `raw_payload` 补。 |
| `raw_payload` | `dict[str, Any]` | required | 诊断 payload；不承载成交 source-of-truth。 |

`FillEvent` 的价格、数量、trade id、fill id、fee、trading day 等 source-of-truth 字段必须类型化。`raw_payload` 只保留诊断信息。
`quantity` 必须为正 Decimal；零数量或负数量不得进入成交事实。

### Trade

| 字段 | 类型 | 默认值 | 语义 |
|---|---|---|---|
| `id` | `str` | required | Trade ledger 本地身份。 |
| `account_id` | `str` | required | 账户 ID。 |
| `exchange` | `str` | required | 交易所代码。 |
| `exchange_trade_id` | `str` | required | 交易所成交 ID。 |
| `order_id` | `str` | required | OMS 订单 ID。 |
| `instrument_id` | `str` | required | 当前期货合约 ID。 |
| `direction` | `Direction` | required | 买卖方向。 |
| `offset` | `Offset` | required | 开平方向。 |
| `price` | `Decimal` | required | 成交价。 |
| `quantity` | `Decimal` | required | 成交数量。 |
| `fee_amount` | `Decimal \| None` | `None` | 手续费金额；`None` 表示未知，`Decimal("0")` 表示明确为零。 |
| `fee_currency` | `str \| None` | `None` | 手续费币种；`fee_amount is not None` 时必须提供。 |
| `fee_source` | `str \| None` | `None` | 手续费来源，例如 `EXCHANGE_REPORT`、`BROKER_QUERY`、`SETTLEMENT`。 |
| `trade_time` | `datetime` | required | 交易所成交时间。 |
| `trading_day` | `date \| None` | `None` | 交易日；未解析时不得用 `raw_payload` 补。 |
| `source_exchange_report_id` | `str` | required | 产生该 Trade 的交易所回报 ID。 |
| `raw_payload` | `dict[str, Any]` | required | 诊断 payload；不承载成交 source-of-truth。 |

成交去重基于 `account_id + exchange + exchange_trade_id`。

`Trade` 是 accounting source-of-truth。Position、Margin、PnL 和 Settlement 只能消费去重后的 `Trade` ledger；`OrderStatus.FILLED`、`OrderStatus.PARTIALLY_FILLED`、`OrderEvent`、`ExchangeReport` 和 `raw_payload` 都不是成交账本事实。
`Trade.quantity` 必须为正 Decimal；零数量或负数量不得进入 Trade ledger。

如 broker 无 `exchange_trade_id`，不得生成随机 ID 入账；必须先冻结稳定替代键，否则该成交不得进入 `Trade` ledger。

### Position

Stage C 已实现 Position Manager 契约。`Trade` ledger 是 Position 更新唯一输入事实；`positions(account_id, instrument_id)` 是 live position projection / current source-of-truth；`PositionEvent` 是 idempotency、replay 和 audit ledger。

Position 禁止消费 `OrderStatus`、`OrderEvent`、`ExchangeReport` 或 `raw_payload`。只靠 `positions` snapshot 不允许作为 repeated trade replay no-op 的幂等依据。

Stage C 当前负责字段：

| 字段 | 类型 | 默认值 | 语义 |
|---|---|---|---|
| `account_id` | `str` | required | 账户 ID。 |
| `instrument_id` | `str` | required | 当前期货合约 ID。 |
| `long_today_qty` | `Decimal` | `Decimal("0")` | 多头今仓数量。 |
| `long_yesterday_qty` | `Decimal` | `Decimal("0")` | 多头昨仓数量。 |
| `short_today_qty` | `Decimal` | `Decimal("0")` | 空头今仓数量。 |
| `short_yesterday_qty` | `Decimal` | `Decimal("0")` | 空头昨仓数量。 |
| `long_avg_price` | `Decimal` | `Decimal("0")` | 多头开仓均价；开仓按加权平均更新，平仓不在 Stage C 改写剩余均价。 |
| `short_avg_price` | `Decimal` | `Decimal("0")` | 空头开仓均价；开仓按加权平均更新，平仓不在 Stage C 改写剩余均价。 |
| `version` | `int` | `0` | 乐观并发和 replay divergence 检查版本。 |
| `updated_at` | `datetime` | required | live projection 最后更新时间。 |

当前已存在但 Stage C 不更新的字段：

| 字段 | 类型 | 默认值 | 语义 |
|---|---|---|---|
| `frozen_long_qty` | `Decimal` | `Decimal("0")` | 冻结多头数量。 |
| `frozen_short_qty` | `Decimal` | `Decimal("0")` | 冻结空头数量。 |
| `settlement_price` | `Decimal` | `Decimal("0")` | 结算价。 |
| `last_price` | `Decimal` | `Decimal("0")` | 最新行情价。 |
| `realized_pnl` | `Decimal` | `Decimal("0")` | 已实现盈亏。 |
| `unrealized_pnl` | `Decimal` | `Decimal("0")` | 未实现盈亏。 |
| `margin_used` | `Decimal` | `Decimal("0")` | 持仓占用保证金。 |

`frozen_long_qty` / `frozen_short_qty` 可保留为字段，但 Stage C 不从 `OrderStatus` 推导冻结；冻结/解冻后续必须由 typed reservation event 驱动。Stage C 不更新 realized/unrealized PnL、`margin_used`、settlement roll、today -> yesterday roll。

Stage C update rules：

- BUY + OPEN：增加 `long_today_qty`，按同侧 `long_today_qty + long_yesterday_qty` 总量做 Decimal 加权平均并更新 `long_avg_price`。
- SELL + OPEN：增加 `short_today_qty`，按同侧 `short_today_qty + short_yesterday_qty` 总量做 Decimal 加权平均并更新 `short_avg_price`。
- SELL + CLOSE_TODAY：扣减 `long_today_qty`。
- SELL + CLOSE_YESTERDAY：扣减 `long_yesterday_qty`。
- BUY + CLOSE_TODAY：扣减 `short_today_qty`。
- BUY + CLOSE_YESTERDAY：扣减 `short_yesterday_qty`。
- Partial close 只扣成交数量。
- Close 数量超过对应 bucket 时返回 typed rejection，不修改 position。
- Unsupported offset 返回 typed error。
- 任何 resulting quantity 不得为负。
- 平仓不计算 realized PnL，不改变剩余 open avg price。

### PositionEvent

Stage C 选择 `PositionEvent`，不选择仅 `position_applied_trades`，因为 replay 和 audit 需要 before/after snapshot。

| 字段 | 类型 | 默认值 | 语义 |
|---|---|---|---|
| `id` | `str` | required | Position event 本地身份。 |
| `account_id` | `str` | required | 账户 ID。 |
| `instrument_id` | `str` | required | 合约 ID。 |
| `exchange` | `str` | required | 交易所。 |
| `exchange_trade_id` | `str` | required | 交易所成交 ID。 |
| `trade_id` | `str` | required | 对应 Trade ledger 本地身份。 |
| `position_id` | `str` | required | 对应 live position row。 |
| `direction` | `str` | required | Trade direction / side。 |
| `offset` | `str` | required | OPEN / CLOSE_TODAY / CLOSE_YESTERDAY。 |
| `price` | `Decimal` | required | 成交价。 |
| `quantity` | `Decimal` | required | 应用数量。 |
| `before_snapshot` | `PositionSnapshot` | required | 应用前 position typed snapshot；DB 以 JSON serialization 存储。 |
| `after_snapshot` | `PositionSnapshot` | required | 应用后 position typed snapshot；DB 以 JSON serialization 存储。 |
| `event_type` | `str` | required | 例如 `TRADE_APPLIED`。 |
| `occurred_at` | `datetime` | required | 使用 Trade time 或业务发生时间。 |
| `created_at` | `datetime` | required | 本地写入时间。 |
| `raw_payload` | `dict[str, Any]` | `{}` | 诊断 payload；不承载 position source-of-truth。 |

PositionEvent 幂等键沿用 Trade identity：`account_id + exchange + exchange_trade_id`。已存在且 canonical payload 一致时，`apply_trade` 必须比对 live `positions` projection 与 `PositionEvent.after_snapshot`；一致才 no-op / duplicate applied，不一致必须返回 typed conflict / replay divergence。已存在但 canonical payload 不一致时，必须返回 typed conflict；未存在时，必须在同一 UoW 内更新 `positions` 并写入 `position_events`。
PositionEvent canonical payload 必须包含 `before_snapshot` 和 `after_snapshot` 的 normalized typed representation；`raw_payload` 不参与 canonical payload。

PositionEvent 必须支持回答：

- 哪笔 Trade 已应用。
- 应用前后 Position 是什么。
- Replay 是否重复。
- Conflict 如何判定。

### Margin Engine

Stage D 已实现 Margin Engine 契约。Margin 只能消费 `Position`、typed `MarginRule`、typed `AccountContext` 和 typed price input / price basis。

Margin 禁止消费：

- `OrderStatus`
- `OrderEvent`
- `ExchangeReport`
- `raw_payload`
- broker adapter query
- Risk direct DB lookup

`Instrument.margin_rate` 不是完整 MarginRule，只能作为兼容数据来源之一。完整保证金规则必须由 typed `MarginRule` 表达；`raw_payload` 不承载规则事实。

#### MarginRule

| 字段 | 类型 | 默认值 | 语义 |
|---|---|---|---|
| `rule_id` | `str \| None` | `None` | 可选规则身份。 |
| `instrument_id` | `str` | required | 合约 ID。 |
| `exchange` | `str` | required | 交易所。 |
| `contract_multiplier` | `Decimal` | required | 合约乘数，必须 `> 0`。 |
| `long_initial_margin_rate` | `Decimal` | required | 多头初始保证金率，必须 `>= 0`。 |
| `short_initial_margin_rate` | `Decimal` | required | 空头初始保证金率，必须 `>= 0`。 |
| `long_maintenance_margin_rate` | `Decimal` | required | 多头维持保证金率，必须 `>= 0`。 |
| `short_maintenance_margin_rate` | `Decimal` | required | 空头维持保证金率，必须 `>= 0`。 |
| `price_basis` | `str` | required | `LAST_PRICE \| SETTLEMENT_PRICE \| AVG_PRICE \| MANUAL`。 |
| `price` | `Decimal \| None` | `None` | `price_basis=MANUAL` 时使用的 typed price。 |
| `effective_from` | `datetime \| None` | `None` | 可选生效开始时间。 |
| `effective_to` | `datetime \| None` | `None` | 可选生效结束时间。 |

所有 rates 必须 Decimal 且 `>= 0`；`contract_multiplier` 必须 Decimal 且 `> 0`。`price_basis` 决定价格来源；如果所需价格缺失，MarginEngine 返回 `REJECTED_MISSING_PRICE` typed result。

#### AccountContext

| 字段 | 类型 | 默认值 | 语义 |
|---|---|---|---|
| `account_id` | `str` | required | 账户 ID。 |
| `equity` | `Decimal` | required | 账户权益。 |
| `available_cash` | `Decimal` | required | 可用资金，可为 0。 |
| `frozen_cash` | `Decimal` | required | 冻结资金。 |
| `currency` | `str \| None` | `None` | 币种。 |
| `snapshot_time` | `datetime` | required | 上下文快照时间。 |

`AccountContext` 的 Decimal 字段必须 Decimal-only。`AccountSnapshot` 可以是数据来源之一，但 MarginEngine 消费 typed `AccountContext`，不直接等同 DB `AccountSnapshot`。

#### MarginRequirement

| 字段 | 类型 | 默认值 | 语义 |
|---|---|---|---|
| `account_id` | `str` | required | 账户 ID。 |
| `instrument_id` | `str` | required | 合约 ID。 |
| `long_initial_margin` | `Decimal` | required | 多头初始保证金。 |
| `short_initial_margin` | `Decimal` | required | 空头初始保证金。 |
| `total_initial_margin` | `Decimal` | required | 总初始保证金。 |
| `long_maintenance_margin` | `Decimal` | required | 多头维持保证金。 |
| `short_maintenance_margin` | `Decimal` | required | 空头维持保证金。 |
| `total_maintenance_margin` | `Decimal` | required | 总维持保证金。 |
| `margin_used` | `Decimal` | required | live margin projection，等于 `total_initial_margin`。 |
| `required_cash` | `Decimal` | required | 所需资金，等于 `total_initial_margin`。 |
| `is_sufficient` | `bool` | required | `available_cash >= required_cash`。 |
| `reason` | `str \| None` | `None` | typed reason。 |

Insufficient cash 返回 `REJECTED_INSUFFICIENT_CASH` typed result，不抛业务异常，不 append `MarginSnapshot`，不更新 `positions.margin_used`。

#### MarginSnapshot

| 字段 | 类型 | 默认值 | 语义 |
|---|---|---|---|
| `account_id` | `str` | required | 账户 ID。 |
| `instrument_id` | `str` | required | 合约 ID。 |
| `position_version` | `int` | required | 输入 Position version。 |
| `rule_id` | `str \| None` | `None` | 应用的规则身份。 |
| `rule_version` | `str \| None` | `None` | 应用的规则版本。 |
| `calculation_key` | `str` | required | deterministic calculation identity；不得用随机 UUID 或当前时间生成。 |
| `long_qty` | `Decimal` | required | `long_today_qty + long_yesterday_qty`。 |
| `short_qty` | `Decimal` | required | `short_today_qty + short_yesterday_qty`。 |
| `price` | `Decimal` | required | 本次计算使用的 typed price。 |
| `contract_multiplier` | `Decimal` | required | 本次计算使用的合约乘数。 |
| `initial_margin` | `Decimal` | required | 总初始保证金。 |
| `maintenance_margin` | `Decimal` | required | 总维持保证金。 |
| `margin_used` | `Decimal` | required | live margin projection。 |
| `available_cash` | `Decimal` | required | 计算时可用资金。 |
| `equity` | `Decimal` | required | 计算时账户权益。 |
| `calculated_at` | `datetime` | required | 本地计算时间；持久化但不参与 canonical equality。 |

`MarginSnapshot` canonical payload 字段包括 `account_id`、`instrument_id`、`position_version`、`rule_id`、`rule_version`、`long_qty`、`short_qty`、`price`、`contract_multiplier`、`initial_margin`、`maintenance_margin`、`margin_used`、`available_cash`、`equity`、`calculation_key`。`calculated_at` 不参与 canonical equality；`raw_payload` 不参与 canonical。Same canonical 时 no-op / duplicate snapshot accepted；different canonical 时返回 `CONFLICT` / divergence；不得静默覆盖历史 snapshot。同一 `account_id + instrument_id + position_version` 不得写入第二条不同 Margin fact；除 `calculation_key` 外经济事实一致时返回 existing，经济事实不一致时 conflict。

#### MarginResult

`MarginResultStatus` 冻结为：

- `CALCULATED`
- `REJECTED_MISSING_RULE`
- `REJECTED_MISSING_POSITION`
- `REJECTED_MISSING_PRICE`
- `REJECTED_INSUFFICIENT_CASH`
- `CONFLICT`
- `ERROR`

| 字段 | 类型 | 默认值 | 语义 |
|---|---|---|---|
| `status` | `MarginResultStatus` | required | 计算结果状态。 |
| `requirement` | `MarginRequirement \| None` | `None` | 保证金需求。 |
| `snapshot` | `MarginSnapshot \| None` | `None` | 写入或待写入的保证金快照。 |
| `reason` | `str \| None` | `None` | typed reason。 |
| `account_id` | `str \| None` | `None` | 账户 ID。 |
| `instrument_id` | `str \| None` | `None` | 合约 ID。 |

#### Margin calculation rules

- `long_qty = long_today_qty + long_yesterday_qty`
- `short_qty = short_today_qty + short_yesterday_qty`
- `long_initial = long_qty * price * contract_multiplier * long_initial_margin_rate`
- `short_initial = short_qty * price * contract_multiplier * short_initial_margin_rate`
- `long_maintenance = long_qty * price * contract_multiplier * long_maintenance_margin_rate`
- `short_maintenance = short_qty * price * contract_multiplier * short_maintenance_margin_rate`
- `total_initial = long_initial + short_initial`
- `total_maintenance = long_maintenance + short_maintenance`
- `margin_used = total_initial`
- `required_cash = total_initial`
- `is_sufficient = account.available_cash >= required_cash`

所有计算必须使用 Decimal-only，不得引入 float。

Margin calculation 必须校验 typed identity：`position.account_id == account.account_id`，`rule.instrument_id == position.instrument_id`。Mismatch 返回 typed `ERROR`，不 append `MarginSnapshot`，不更新 `positions.margin_used`。如果 Position 当前没有 exchange 字段，Stage D 暂不强制 exchange 校验；后续如为 Position 引入 exchange identity，必须同步校验 `rule.exchange`。

Price source policy：

- `LAST_PRICE` 使用 typed latest price input。
- `SETTLEMENT_PRICE` 使用 typed settlement price input。
- `AVG_PRICE` 使用 Position avg price；mixed long/short position 下，long 使用 `long_avg_price`，short 使用 `short_avg_price`，分别计算后相加。
- `MANUAL` 使用 `MarginRule.price`。
- 如果 price missing，返回 `REJECTED_MISSING_PRICE`。
- 不从 `raw_payload` 或 broker adapter query 取 price。

#### positions.margin_used update boundary

Stage D 可更新 `positions.margin_used`，但必须满足：

- 只有 `MarginResultStatus.CALCULATED` 才允许 append `MarginSnapshot` 并更新 `positions.margin_used`。
- `REJECTED_MISSING_RULE`、`REJECTED_MISSING_POSITION`、`REJECTED_MISSING_PRICE`、`REJECTED_INSUFFICIENT_CASH` 或 `ERROR` 不落库、不更新 position。
- 必须和 `MarginSnapshot` 在同一 UoW / transaction。
- 固定顺序为：先 calculate `MarginRequirement` / `MarginSnapshot`，再 append `MarginSnapshot`，最后 `update positions.margin_used using expected_version=position.version`。
- 如果任一步失败，整个 transaction rollback。
- 不允许只更新 `positions.margin_used` 而没有 snapshot。
- 不允许只写 snapshot 但声称 live `margin_used` 已更新。
- 必须使用 margin-only repository method 更新 `positions.margin_used`，不得复用会写 qty / avg price 的通用 position update。
- 不更新 `realized_pnl`。
- 不更新 `unrealized_pnl`。
- 不更新 qty / avg price。
- 不更新 settlement fields。

#### Margin replay

Margin replay 使用同一 calculator 重算。输入为 Position projection + MarginRule + AccountContext + typed price input。同一 `account_id + instrument_id + position_version` 的 existing snapshot 已是该 position version 的 margin fact；同一 `calculation_key` canonical same 时 no-op / duplicate snapshot accepted，canonical different 时返回 `CONFLICT` / divergence；`calculation_key` 不同但同一 position version 经济事实一致时 no-op，经济事实不一致时 conflict，不得追加第二条 snapshot 或更新 `positions.margin_used`。Replay 不更新 Position qty/avg。

#### PnL / Settlement / Risk boundary

Stage D 不实现 realized PnL、unrealized PnL、settlement、today -> yesterday roll、fee/PnL attribution 或 mark-to-market PnL。Stage D 不实现 order freeze/reservation、broker reconciliation、CTP、SimNow、broker adapter、FastAPI、Kafka、Redis、Celery、KMS、cloud runtime 或 raw_payload margin facts。

Stage D 不让 RiskEngine 直接查 DB 或直接调用 MarginEngine。后续 RiskContext 由 application layer 注入 typed margin context。

### PnL Engine

Stage E 已实现 PnL Engine 契约。PnL 只能消费 `Trade`、`Position` 或 typed pre/post position snapshot、typed price input 和 typed Trade fee。`MarginSnapshot` 只可用于 audit correlation，不参与 realized / unrealized PnL 公式。

PnL 禁止消费：

- `OrderStatus`
- `OrderEvent`
- `ExchangeReport`
- `raw_payload`
- broker adapter query
- Risk direct DB lookup

#### PnLPriceBasis

`PnLPriceBasis` 冻结为：

- `LAST_PRICE`
- `SETTLEMENT_PRICE`
- `MANUAL`

#### PnLResultStatus

`PnLResultStatus` 冻结为：

- `CALCULATED`
- `REJECTED_MISSING_POSITION`
- `REJECTED_MISSING_PRICE`
- `REJECTED_MISSING_MULTIPLIER`
- `REJECTED_MISSING_FEE`
- `DOMAIN_FIELD_UNSUPPORTED`
- `CONFLICT`
- `ERROR`

#### RealizedPnL

| 字段 | 类型 | 默认值 | 语义 |
|---|---|---|---|
| `account_id` | `str` | required | 账户身份。 |
| `instrument_id` | `str` | required | 合约身份。 |
| `trade_id` | `str` | required | close trade 身份。 |
| `direction` | `Direction` | required | close trade direction。 |
| `offset` | `Offset` | required | close trade offset。 |
| `quantity` | `Decimal` | required | 平仓数量。 |
| `close_price` | `Decimal` | required | 平仓成交价。 |
| `avg_cost` | `Decimal` | required | typed pre-close avg cost 或显式 avg cost。 |
| `contract_multiplier` | `Decimal` | required | 合约乘数。 |
| `gross_realized_pnl` | `Decimal` | required | 未扣手续费 realized PnL。 |
| `fee_amount` | `Decimal \| None` | `None` | typed Trade fee；`None` 表示未知。 |
| `net_realized_pnl` | `Decimal \| None` | `None` | 扣手续费 realized PnL；fee unknown 时为 `None`。 |
| `currency` | `str \| None` | `None` | fee / pnl currency。 |
| `calculated_at` | `datetime` | required | 计算时间。 |

Realized PnL 只处理 close trade：

- `SELL + CLOSE_TODAY` / `SELL + CLOSE_YESTERDAY` closes long。
- `BUY + CLOSE_TODAY` / `BUY + CLOSE_YESTERDAY` closes short。
- Long close：`gross = (trade.price - avg_cost) * quantity * contract_multiplier`。
- Short close：`gross = (avg_cost - trade.price) * quantity * contract_multiplier`。
- Open trade 不产生 realized PnL。

Fee policy：

- `fee_amount` 为 Decimal 时，`net_realized_pnl = gross_realized_pnl - fee_amount`。
- `fee_amount == Decimal("0")` 表示明确零手续费。
- `fee_amount is None` 表示手续费未知；calculator 可返回 `CALCULATED`，`reason="fee_unknown"`，并设置 `net_realized_pnl=None` 以保留 gross 诊断信息。
- Persistent PnL projection 必须使用 net realized PnL。PnLEngine 遇到 `net_realized_pnl is None` 必须返回 `REJECTED_MISSING_FEE`，不得 append `PnLSnapshot`，不得更新 `positions.realized_pnl`。

Critical before-state requirement：

- Close trade realized PnL 必须消费 typed pre-close position snapshot/context，或显式 `avg_cost`。
- 不得从历史 close 后的 current live Position 推导 avg cost，除非该 live Position 明确就是 pre-close position。
- 不得从 `raw_payload`、`OrderEvent` 或 broker query 推导 avg cost。

#### UnrealizedPnL

| 字段 | 类型 | 默认值 | 语义 |
|---|---|---|---|
| `account_id` | `str` | required | 账户身份。 |
| `instrument_id` | `str` | required | 合约身份。 |
| `long_qty` | `Decimal` | required | `long_today_qty + long_yesterday_qty`。 |
| `short_qty` | `Decimal` | required | `short_today_qty + short_yesterday_qty`。 |
| `long_avg_price` | `Decimal` | required | 多头 avg cost。 |
| `short_avg_price` | `Decimal` | required | 空头 avg cost。 |
| `price_basis` | `PnLPriceBasis` | required | mark price basis。 |
| `mark_price` | `Decimal` | required | typed mark price。 |
| `contract_multiplier` | `Decimal` | required | 合约乘数。 |
| `gross_unrealized_pnl` | `Decimal` | required | 未实现盈亏。 |
| `net_unrealized_pnl` | `Decimal` | required | Stage E 默认等于 gross；fee attribution 后置。 |

Unrealized PnL calculation：

- Long：`(mark_price - long_avg_price) * long_qty * contract_multiplier`。
- Short：`(short_avg_price - mark_price) * short_qty * contract_multiplier`。
- Mixed position 下 long / short 分别计算后相加。
- Missing mark price 返回 `REJECTED_MISSING_PRICE`。
- 不从 `raw_payload` 或 broker query 取 price。

#### Contract multiplier

`contract_multiplier` 必须来自 typed input 或 typed rule object。它必须是 Decimal 且 `> 0`。缺失或非正数返回 `REJECTED_MISSING_MULTIPLIER` 或 typed `ERROR`，不得从 `raw_payload` 推导。

#### PnLSnapshot

| 字段 | 类型 | 默认值 | 语义 |
|---|---|---|---|
| `account_id` | `str` | required | 账户身份。 |
| `instrument_id` | `str` | required | 合约身份。 |
| `position_version` | `int` | required | 输入 Position / snapshot version。 |
| `trade_id` | `str \| None` | `None` | realized close trade identity；unrealized-only snapshot 可为空。 |
| `margin_snapshot_id` | `str \| None` | `None` | audit correlation only。 |
| `calculation_key` | `str` | required | deterministic calculation identity；不得用随机 UUID 或当前时间生成。 |
| `price_basis` | `PnLPriceBasis` | required | mark price basis。 |
| `mark_price` | `Decimal` | required | typed mark price。 |
| `contract_multiplier` | `Decimal` | required | 合约乘数。 |
| `realized_pnl` | `Decimal` | required | 本次或累计 realized PnL projection。 |
| `unrealized_pnl` | `Decimal` | required | 本次 unrealized PnL projection。 |
| `total_pnl` | `Decimal` | required | `realized_pnl + unrealized_pnl`。 |
| `fee_amount` | `Decimal \| None` | `None` | typed fee；unknown 时为 `None`。 |
| `calculated_at` | `datetime` | required | 本地计算时间；持久化但不参与 canonical equality。 |
| `created_at` | `datetime` | required | DB 创建时间。 |

`PnLSnapshot` canonical payload 字段包括 `account_id`、`instrument_id`、`position_version`、`trade_id`、`margin_snapshot_id`、`calculation_key`、`price_basis`、`mark_price`、`contract_multiplier`、`realized_pnl`、`unrealized_pnl`、`total_pnl`、`fee_amount`。`calculated_at` 不参与 canonical equality；`raw_payload` 不允许进入 PnL facts。Same canonical 时 no-op / duplicate accepted；different canonical 时返回 `CONFLICT` / divergence；不得静默覆盖历史 snapshot。同一 `account_id + instrument_id + position_version` 的 existing snapshot 已是该 position version 的 PnL fact；除 `calculation_key` 外经济事实一致时 duplicate no-op，经济事实不一致时返回 conflict/divergence，不得追加第二条 PnL fact。

#### PnLResult

| 字段 | 类型 | 默认值 | 语义 |
|---|---|---|---|
| `status` | `PnLResultStatus` | required | typed result status。 |
| `realized` | `RealizedPnL \| None` | `None` | realized PnL result。 |
| `unrealized` | `UnrealizedPnL \| None` | `None` | unrealized PnL result。 |
| `snapshot` | `PnLSnapshot \| None` | `None` | 写入或待写入的 PnL snapshot。 |
| `reason` | `str \| None` | `None` | typed reason。 |
| `account_id` | `str \| None` | `None` | 账户身份。 |
| `instrument_id` | `str \| None` | `None` | 合约身份。 |

#### positions PnL update boundary

Stage E 可更新 `positions.realized_pnl` / `positions.unrealized_pnl`，但必须满足：

- 只有 successful PnL calculation 才允许 append `PnLSnapshot` 并更新 position PnL fields。
- 必须和 `PnLSnapshot` 在同一 UoW / transaction。
- 固定顺序为：先 calculate `RealizedPnL` / `UnrealizedPnL` / `PnLSnapshot`，再 append `PnLSnapshot`，最后用 pnl-only repository method 更新 `positions.realized_pnl` / `positions.unrealized_pnl`。
- 如果任一步失败，整个 transaction rollback。
- 不允许只更新 position PnL fields 而没有 snapshot。
- 不允许只写 snapshot 但声称 live PnL fields 已更新。
- 不更新 qty / avg price。
- 不更新 `margin_used`。
- 不更新 settlement fields。
- 不触发 Margin recompute。

#### PnL replay

PnL replay 使用同一 calculator 重算，且必须使用 deterministic `calculation_key`。Same canonical 时 no-op；different canonical 时返回 `CONFLICT` / divergence；即使 `calculation_key` 不同，同一 position version 的经济事实一致也必须 no-op，经济事实不一致必须 conflict。Replay 不得静默覆盖 position PnL fields。Replay divergence 判定必须读取 repository / UoW 内真实 live Position row；调用方传入的 Position 只作为 calculator input，不得替代 live row。若 live position PnL fields 与 snapshot divergence，除非当前 transaction 正在更新它，否则必须返回 `CONFLICT`。

#### Margin / Settlement / Risk boundary

PnL 不使用 `margin_used` 参与公式。`MarginSnapshot` 只可作为 audit correlation，不参与 PnL 公式。PnL 不触发 Margin recompute；MarginEngine 不调用 PnLEngine。

Stage E 不实现 daily settlement、today -> yesterday roll、settlement snapshots、settlement price finalization、daily PnL carry、account equity mutation、broker reconciliation、CTP、SimNow、broker adapter、FastAPI、Kafka、Redis、Celery、KMS、cloud runtime、Risk direct DB integration 或 raw_payload PnL facts。

### Settlement Engine

Stage F 冻结 Settlement Engine 契约。Settlement 是日终状态归档、PnL / Margin fact finalization、account snapshot 和 today -> yesterday roll 边界；它不是 PnL/Margin 重新计算器，也不是 broker reconciliation 或交易所结算单接入器。

Stage F 当前已实现：Settlement domain objects、SettlementCalculator / planner、SettlementEngine、replay path、SettlementSnapshotRepository、AccountSnapshotRepository、settlement-only position roll method、UoW integration 和 `0007_stage_f_settlement_engine` migration。实现仍遵守下列 source-of-truth 和边界。

Settlement 只能消费：

- `Position` live projection。
- `PnLSnapshot`。
- `MarginSnapshot`。
- `AccountContext` / `AccountSnapshot`。
- typed `SettlementPrice` input。
- `TradingCalendar` / typed `trading_day`。
- `Trade` / `PositionEvent` only for audit / replay proof, not as primary live settlement path。

Settlement 禁止消费：

- `OrderStatus`
- `OrderEvent`
- `ExchangeReport`
- `raw_payload`
- broker adapter query
- Risk direct DB lookup

#### SettlementResultStatus

`SettlementResultStatus` 冻结为：

- `SETTLED`
- `DUPLICATE`
- `REJECTED_NON_TRADING_DAY`
- `REJECTED_MISSING_POSITION`
- `REJECTED_MISSING_PNL`
- `REJECTED_MISSING_MARGIN`
- `REJECTED_MISSING_SETTLEMENT_PRICE`
- `REJECTED_FROZEN_POSITION`
- `CONFLICT`
- `ERROR`

#### SettlementPrice

| 字段 | 类型 | 默认值 | 语义 |
|---|---|---|---|
| `instrument_id` | `str` | required | 合约身份。 |
| `exchange` | `str` | required | 交易所。 |
| `trading_day` | `date` | required | 结算交易日。 |
| `price` | `Decimal` | required | typed settlement price。 |
| `source` | `str \| None` | `None` | typed 来源标签；不是 raw payload。 |
| `received_at` | `datetime` | required | 收到该 typed input 的时间。 |

`price` 必须 Decimal 且 `> 0`。Settlement price 不得从 `raw_payload`、broker query 或 system date 推导。

#### SettlementContext

| 字段 | 类型 | 默认值 | 语义 |
|---|---|---|---|
| `account_id` | `str` | required | 账户身份。 |
| `trading_day` | `date` | required | 结算交易日。 |
| `account_before` | `AccountContext \| AccountSnapshot` | required | 结算前 typed account state。 |
| `positions` | `Sequence[Position]` | required | 结算前 live positions。 |
| `pnl_snapshots` | `Sequence[PnLSnapshot]` | required | Stage E PnL facts。 |
| `margin_snapshots` | `Sequence[MarginSnapshot]` | required | Stage D margin facts。 |
| `settlement_prices` | `Sequence[SettlementPrice]` | required | typed settlement price inputs。 |
| `calculation_key` | `str` | required | deterministic settlement identity。 |
| `settled_at` | `datetime` | required | settlement calculation time。 |

`calculation_key` 必须由 application layer 提供 deterministic value，不得使用随机 UUID 或当前时间生成。

#### SettlementSnapshot

| 字段 | 类型 | 默认值 | 语义 |
|---|---|---|---|
| `id` | `str \| None` | `None` | 持久化 ID。 |
| `account_id` | `str` | required | 账户身份。 |
| `trading_day` | `date` | required | 结算交易日。 |
| `calculation_key` | `str` | required | deterministic settlement identity。 |
| `positions_before` | typed snapshot payload | required | 结算前 positions typed representation。 |
| `positions_after` | typed snapshot payload | required | 结算后 positions typed representation。 |
| `settlement_prices` | typed snapshot payload | required | typed settlement prices representation。 |
| `pnl_snapshot_ids` | `Sequence[str]` | required | 被 finalization 的 PnL facts。 |
| `margin_snapshot_ids` | `Sequence[str]` | required | 被 finalization 的 Margin facts。 |
| `account_snapshot_before_id` | `str \| None` | `None` | 结算前 account snapshot identity。 |
| `account_snapshot_after_id` | `str \| None` | `None` | 结算后 account snapshot identity。 |
| `cash_before` | `Decimal` | required | 结算前 cash。 |
| `cash_after` | `Decimal` | required | 结算后 cash。 |
| `realized_pnl` | `Decimal` | required | 来自 PnLSnapshot 的已实现盈亏。 |
| `unrealized_pnl` | `Decimal` | required | 来自 PnLSnapshot 的未实现盈亏。 |
| `margin_used` | `Decimal` | required | 来自 MarginSnapshot 的 margin used。 |
| `status` | `SettlementResultStatus` | required | settlement result status。 |
| `reason` | `str \| None` | `None` | typed reason。 |
| `created_at` | `datetime` | required | DB 创建时间。 |

`positions_before`、`positions_after`、`settlement_prices` 是 typed snapshot payload，不是 raw source payload。`raw_payload` 不允许作为 Settlement fact 或 canonical payload。

#### SettlementResult

| 字段 | 类型 | 默认值 | 语义 |
|---|---|---|---|
| `status` | `SettlementResultStatus` | required | typed result status。 |
| `snapshot` | `SettlementSnapshot \| None` | `None` | 写入或 existing settlement snapshot。 |
| `reason` | `str \| None` | `None` | typed reason。 |
| `account_id` | `str \| None` | `None` | 账户身份。 |
| `trading_day` | `date \| None` | `None` | 结算交易日。 |

#### Today -> yesterday roll

Stage F today -> yesterday roll 冻结为：

- `long_yesterday_qty = long_yesterday_qty + long_today_qty`
- `short_yesterday_qty = short_yesterday_qty + short_today_qty`
- `long_today_qty = Decimal("0")`
- `short_today_qty = Decimal("0")`

Stage F 不改变 `long_avg_price` / `short_avg_price`。Stage F 不重新计算 `realized_pnl` / `unrealized_pnl`。Stage F 不重新计算 `margin_used`。

如果任一 position 的 `frozen_long_qty > 0` 或 `frozen_short_qty > 0`：

- 返回 `REJECTED_FROZEN_POSITION`。
- 不 roll。
- 不 append `SettlementSnapshot`。
- 不创建 / 更新 account after snapshot。
- 不静默清空 frozen qty。

#### PnL finalization

Settlement 消费 `PnLSnapshot` facts。Settlement 不重新计算 Stage E PnL，且不修改历史 `pnl_snapshots`。

Settlement 必须校验：

- 每个 settled instrument 有 relevant `PnLSnapshot`。
- `PnLSnapshot.price_basis == PnLPriceBasis.SETTLEMENT_PRICE`，或该 PnLSnapshot 被明确标记为 settlement-compatible typed fact。
- `PnLSnapshot.mark_price == SettlementPrice.price`。

`realized_pnl` 必须来自 PnLSnapshot，且 fee 已由 Stage E policy 决定。Settlement 不做 fee recomputation。

#### Margin finalization

Settlement 消费 `MarginSnapshot` facts 和 `margin_used`。Settlement 不重新计算 Stage D margin，且不修改历史 `margin_snapshots`。

如果 settlement-price margin 是业务要求，Stage D 必须在 Settlement 前生成对应 `MarginSnapshot`。Settlement 只引用该 fact。

#### Account formula and snapshots

Stage F 账户公式冻结为 typed formula：

- `cash_after = cash_before + realized_pnl`
- `equity_after = cash_after + unrealized_pnl`
- `available_cash_after = cash_after - margin_used`
- `frozen_cash_after = account_before.frozen_cash`

公式输入必须是 typed facts：

- `cash_before` / `frozen_cash` 来自 `AccountContext` 或 `AccountSnapshot`。
- `realized_pnl` / `unrealized_pnl` 来自 `PnLSnapshot`。
- `margin_used` 来自 `MarginSnapshot`。

Settlement 不查询 broker cash，不从 `raw_payload` 取账户事实，不重新计算 fee。

Stage F 必须创建或引用 `account_snapshot_after`。`account_snapshot_before` 可以引用 existing snapshot，或由 typed `AccountContext` 构造。`SettlementSnapshot` 必须记录 account before / after IDs 和 typed cash / PnL / margin values。

Successful settlement 的 `SettlementSnapshot` append、account after snapshot 创建 / 更新、position roll 必须在同一 UoW / transaction。任一步失败必须 rollback all。

#### Position roll update boundary

Settlement 需要 settlement-only position roll repository method，例如：

- `PositionRepository.roll_today_to_yesterday_for_settlement(...)`

该方法必须使用 `expected_version`，且只允许更新：

- `long_today_qty`
- `long_yesterday_qty`
- `short_today_qty`
- `short_yesterday_qty`
- `version`
- `updated_at`

该方法不得更新：

- `long_avg_price`
- `short_avg_price`
- `realized_pnl`
- `unrealized_pnl`
- `margin_used`
- settlement price fields

#### Settlement rejected result persistence

Stage F rejected results 不持久化：

- 不 append `SettlementSnapshot`。
- 不 roll position。
- 不创建 / 更新 account snapshot。

Stage F 不引入 rejected audit snapshots；如未来需要 rejected audit，必须另行冻结 status、schema 和 idempotency。

#### Trading calendar

`trading_day` 必须来自 typed input，并由 typed `TradingCalendar` 或 trading calendar repository 校验。

- 非交易日返回 `REJECTED_NON_TRADING_DAY`。
- invalid `trading_day` 不允许 settlement。
- 不得从 system date 推导 settlement trading day。

#### Settlement idempotency and canonical payload

同一 `account_id + trading_day` 只能有一个 final settlement fact。

- Same canonical payload：返回 `DUPLICATE` / existing no-op。
- Different canonical payload：返回 `CONFLICT`。
- `calculated_at` / `created_at` 不参与 canonical。
- `raw_payload` 不参与 canonical，也不是 Settlement fact。

Settlement canonical payload 包括：

- `account_id`
- `trading_day`
- `calculation_key`
- `positions_before`
- `positions_after`
- `settlement_prices`
- `pnl_snapshot_ids`
- `margin_snapshot_ids`
- `cash_before`
- `cash_after`
- `realized_pnl`
- `unrealized_pnl`
- `margin_used`
- `status`

#### Settlement replay

Settlement replay 使用同一 settlement calculator / engine。

- Existing same canonical：返回 `DUPLICATE` / no-op。
- Existing different canonical：返回 `CONFLICT`。
- Live position projection 或 live account projection 与 `SettlementSnapshot.positions_after` / account after-state divergence：返回 `CONFLICT`。
- Replay 不得静默覆盖 live projection。
- Replay 不得修改历史 `Trade`、`PositionEvent`、`PnLSnapshot` 或 `MarginSnapshot`。

#### Settlement boundary

Stage F 不实现：

- Broker reconciliation。
- 真实 exchange settlement file ingestion。
- CTP / SimNow。
- Risk direct integration。
- runtime infra。
- 修改历史 trades。
- 修改历史 position_events。
- 修改历史 pnl_snapshots。
- 修改历史 margin_snapshots。
- raw_payload settlement facts。
- Settlement file parser。

### TradingCalendar

| 字段 | 类型 | 默认值 | 语义 |
|---|---|---|---|
| `exchange` | `str` | required | 交易所代码。 |
| `trading_day` | `date` | required | 交易日。 |
| `is_trading_day` | `bool` | required | 是否为可交易日。 |
| `night_session_trading_day` | `date \| None` | `None` | 夜盘归属交易日。 |
| `note` | `str \| None` | `None` | 可选备注。 |

### TradingSession

| 字段 | 类型 | 默认值 | 语义 |
|---|---|---|---|
| `exchange` | `str` | required | 交易所代码。 |
| `product_id` | `str \| None` | `None` | 可选品种 ID。 |
| `instrument_id` | `str \| None` | `None` | 可选合约 ID。 |
| `session_name` | `str` | required | 交易时段名称。 |
| `start_time` | `str` | required | 时段开始时间。 |
| `end_time` | `str` | required | 时段结束时间。 |
| `is_night` | `bool` | `False` | 是否夜盘。 |
| `effective_from` | `date \| None` | `None` | 可选生效开始日期。 |
| `effective_to` | `date \| None` | `None` | 可选生效结束日期。 |

交易时段是结构化 Domain 事实，不得隐藏在 instrument JSON 中。

## Stage G Market Data Contract Freeze

Stage G 已实现 Market Data Core：typed `Tick` / `Bar` / `MarketDataEvent` / `MarketDataSnapshot` / `DataQualityResult`、`DataQualityGate`、`MarketTickRepository` / `MarketBarRepository`、SQLAlchemy repository、UoW integration、`market_ticks` / `market_bars` migration、MarketDataService ingestion 和 deterministic market replay。

Stage G 未实现 `FeatureSnapshot` generation、Feature indicators、Strategy / Signal、Tick -> Bar Aggregator、Broker adapter、CTP / SimNow、Kafka ingestion、FastAPI service、live market feed、Accounting mutation 或 Risk direct market lookup。

### Market Data source-of-truth

Market Data Core 只能消费以下类型化输入：

- external market adapter typed input。
- instrument identity mapping。
- trading calendar / trading session。
- timestamp normalization rule。
- data quality policy。

Market Data Core 输出以下类型化事实：

- typed `Tick`。
- typed `Bar`。
- typed `MarketDataEvent`。
- typed `MarketDataSnapshot`。
- `DataQualityResult`。
- replayable market facts。

Market Data Core 禁止：

- 创建订单。
- 调用 OMS。
- 调用 Risk。
- 调用 Execution。
- 修改 `Trade`、`Position`、`MarginSnapshot`、`PnLSnapshot` 或 `SettlementSnapshot`。
- 从 `raw_payload` 补 source-of-truth 字段。
- 把 Redis / Kafka message 当 DB fact。

`raw_payload` 在 Market Data 中只能作为 optional diagnostic payload，不参与 canonical equality、idempotency、replay conflict 判定或任何 source-of-truth 字段恢复。

### Instrument identity contract

`Tick`、`Bar` 和未来 `FeatureSnapshot` 必须携带完整 instrument identity：

| 字段 | 语义 |
|---|---|
| `symbol` | 基础品种，例如 `au`。 |
| `instrument_id` | 行情合约 identity。 |
| `trade_instrument_id` | 交易合约 identity。 |
| `exchange` | 交易所。 |
| `trading_day` | 由 calendar/session rule 给出的交易日。 |
| calendar/session 归属 | 对应交易所、品种或合约的交易日与交易时段归属。 |

规则：

- 不得混用主力连续合约、行情合约、交易合约和 base symbol。
- Adapter 负责把外部字段 normalize 成 typed identity。
- Market Data Core 不猜测合约映射。
- 缺失 identity 必须由 data quality gate 返回 typed reject，不得通过 `raw_payload`、Redis/Kafka payload 或 runtime message 补齐。

### Timestamp and bar_ts contract

- External timestamp 可以是 ms/us/ns，但 adapter 必须 normalize。
- Domain timestamp 使用与当前 Domain 契约一致的 typed `datetime` / `date`；不得在 Market Data Core 内混用 system date、adapter receive time 和 exchange event time。
- `Tick.ts` 表示 normalized market event timestamp。
- `Bar.bar_ts` 冻结为 bar start timestamp，不使用 bar end timestamp。
- `trading_day` 不得从系统日期推断，必须由 calendar/session rule 给出。
- `received_at`、`calculated_at` 等本地处理时间只可作为 diagnostic / audit 时间，不参与 canonical equality。

### Market Data domain contracts

Stage G 已新增或冻结以下类型：

- `Tick`
- `Bar`
- `MarketDataEvent`
- `MarketDataSnapshot`
- `DataQualityResult`
- `MarketDataResultStatus`
- `MarketDataEventType`
- `BarTimeframe`

#### Tick

| 字段 | 类型 | 默认值 | 语义 |
|---|---|---|---|
| `symbol` | `str` | required | 基础品种。 |
| `instrument_id` | `str` | required | 行情合约 identity。 |
| `trade_instrument_id` | `str` | required | 交易合约 identity。 |
| `exchange` | `str` | required | 交易所。 |
| `trading_day` | `date` | required | 交易日，由 calendar/session rule 给出。 |
| `ts` | `datetime` | required | normalized market event timestamp。 |
| `price` | `Decimal` | required | 最新价，必须 `> 0`。 |
| `volume` | `Decimal` | required | 成交量，必须 `>= 0`。 |
| `turnover` | `Decimal` | required | 成交额，必须 `>= 0`。 |
| `open_interest` | `Decimal` | required | 持仓量，必须 `>= 0`。 |
| `bid_price_1` | `Decimal \| None` | `None` | 一档买价。 |
| `ask_price_1` | `Decimal \| None` | `None` | 一档卖价。 |
| `bid_volume_1` | `Decimal \| None` | `None` | 一档买量，存在时必须 `>= 0`。 |
| `ask_volume_1` | `Decimal \| None` | `None` | 一档卖量，存在时必须 `>= 0`。 |
| `source` | `str` | required | typed market source。 |
| `raw_payload` | `dict[str, Any] \| None` | `None` | 可选诊断 payload；不承载 source-of-truth。 |

#### Bar

| 字段 | 类型 | 默认值 | 语义 |
|---|---|---|---|
| `symbol` | `str` | required | 基础品种。 |
| `instrument_id` | `str` | required | 行情合约 identity。 |
| `trade_instrument_id` | `str` | required | 交易合约 identity。 |
| `exchange` | `str` | required | 交易所。 |
| `trading_day` | `date` | required | 交易日，由 calendar/session rule 给出。 |
| `timeframe` | `BarTimeframe` | required | Bar 周期。 |
| `bar_ts` | `datetime` | required | bar start timestamp。 |
| `open` | `Decimal` | required | 开盘价，必须 `> 0`。 |
| `high` | `Decimal` | required | 最高价，必须 `> 0`。 |
| `low` | `Decimal` | required | 最低价，必须 `> 0`。 |
| `close` | `Decimal` | required | 收盘价，必须 `> 0`。 |
| `volume` | `Decimal` | required | 成交量，必须 `>= 0`。 |
| `turnover` | `Decimal` | required | 成交额，必须 `>= 0`。 |
| `open_interest` | `Decimal` | required | 持仓量，必须 `>= 0`。 |
| `source` | `str` | required | typed market source。 |
| `quality_status` | `MarketDataResultStatus` | required | data quality gate 结果。 |
| `raw_payload` | `dict[str, Any] \| None` | `None` | 可选诊断 payload；不承载 source-of-truth。 |

#### DataQualityResult

`DataQualityResult` 必须是 typed result，不得返回裸字符串或依赖 exception 文本作为契约。

字段：

- `status: MarketDataResultStatus`
- `event_type: MarketDataEventType | None`
- `instrument_id: str | None`
- `exchange: str | None`
- `trading_day: date | None`
- `ts: datetime | None`
- `reason: str | None`

#### MarketDataEvent

`MarketDataEvent` 是行情质量门和 replay 可消费的 typed event envelope，不是运行时 transport message。

字段：

- `event_id: str`
- `event_type: MarketDataEventType`
- `instrument_id: str`
- `exchange: str`
- `trading_day: date`
- `ts: datetime`
- `source: str`
- `result: DataQualityResult`
- `tick: Tick | None`
- `bar: Bar | None`

`MarketDataEvent` 不得包含订单、风控、执行或 accounting mutation intent。

#### MarketDataSnapshot

`MarketDataSnapshot` 是给 FeatureSnapshot / Strategy 上游消费的 typed market view。

字段：

- `symbol: str`
- `instrument_id: str`
- `trade_instrument_id: str`
- `exchange: str`
- `trading_day: date`
- `as_of_ts: datetime`
- `latest_tick: Tick | None`
- `latest_bars: Mapping[BarTimeframe, Bar]`
- `quality_status: MarketDataResultStatus`

`MarketDataSnapshot` 是行情视图，不是 DB fact 的替代；持久化 source-of-truth 仍是 market tick/bar facts。

#### MarketDataResultStatus

| 名称 | 语义 |
|---|---|
| `ACCEPTED` | 类型化行情事实通过质量门。 |
| `REJECTED_MISSING_IDENTITY` | 缺失 symbol / instrument / exchange / trading_day / session identity。 |
| `REJECTED_BAD_TIMESTAMP` | timestamp 缺失、无法 normalize 或不符合 Domain 时间契约。 |
| `REJECTED_OUT_OF_SESSION` | 不属于有效 trading session。 |
| `REJECTED_BAD_PRICE` | price、bid/ask 或 OHLC 价格非法。 |
| `REJECTED_NON_MONOTONIC` | 对同一 identity 的 timestamp 非单调。 |
| `DUPLICATE` | canonical 相同的重复 Tick / Bar，no-op。 |
| `GAP_DETECTED` | 检测到行情缺口。 |
| `ERROR` | 未分类错误或 duplicate different canonical conflict。 |

如果后续需要区分 duplicate different canonical，可以新增 `CONFLICT`，但 Stage G 冻结期接受返回 `ERROR`。

#### MarketDataEventType

| 名称 | 语义 |
|---|---|
| `TICK_ACCEPTED` | Tick 通过质量门并成为 typed market fact。 |
| `BAR_ACCEPTED` | Bar 通过质量门并成为 typed market fact。 |
| `TICK_REJECTED` | Tick 被质量门拒绝。 |
| `BAR_REJECTED` | Bar 被质量门拒绝。 |
| `DUPLICATE` | 重复 canonical fact no-op。 |
| `GAP_DETECTED` | 检测到行情缺口。 |
| `ERROR` | 未分类错误或 conflict event。 |

#### BarTimeframe

`BarTimeframe` 必须是枚举或等价 typed value，不得使用任意裸字符串散落在实现中。

初始值：

- `M1`
- `M5`
- `M15`
- `M30`
- `H1`
- `D1`

如需新增周期，必须通过 domain migration 和测试更新；同一周期的 duration / session alignment 必须 deterministic。

### Price / volume validation

- `price` 必须是 `Decimal > 0`。
- `volume >= 0`。
- `turnover >= 0`。
- `open_interest >= 0`。
- Bar 必须满足 `high >= max(open, close, low)`。
- Bar 必须满足 `low <= min(open, close, high)`。
- `bid_price_1` 和 `ask_price_1` 同时存在时必须 `bid_price_1 <= ask_price_1`。
- Zero-volume bar 只有 data quality policy 显式允许时可接受。
- 非法事实必须返回 typed rejected，不得静默修正、截断、默认填值或从 diagnostic payload 补值。

### Data quality gate

冻结行为：

- Missing identity：`REJECTED_MISSING_IDENTITY`。
- Bad timestamp：`REJECTED_BAD_TIMESTAMP`。
- Out of session：`REJECTED_OUT_OF_SESSION`。
- Duplicate same canonical：`DUPLICATE` no-op。
- Duplicate different canonical：`ERROR`，或后续 migration 明确新增 `CONFLICT`。
- Non-monotonic timestamp：`REJECTED_NON_MONOTONIC`。
- Market gap：`GAP_DETECTED`；只有显式 policy `allow_gap=True` 时才可继续接受。
- Bad price：`REJECTED_BAD_PRICE`。
- Bad OHLC：`REJECTED_BAD_PRICE`。
- Quality result 必须 typed。

### Bar aggregation contract

Stage G Contract Freeze 只定义 aggregation contract，不实现 aggregation。

后续实现规则：

- `Tick -> Bar` aggregator 必须 deterministic。
- Bar identity 为 `instrument_id + timeframe + bar_ts`，并必须同时保留 `exchange`、`symbol`、`trade_instrument_id`、`trading_day` 和 `source`。
- Same canonical duplicate no-op。
- Different canonical duplicate conflict / `ERROR`。
- Aggregator 不创建订单。
- Aggregator 不调用 OMS / Risk / Execution。
- Aggregator 不生成 Strategy signal。

### Repository and DB future contract

Stage G 已创建 Market facts 持久化契约：

- `MarketTickRepository`
- `MarketBarRepository`
- `market_ticks` table
- `market_bars` table

Tick idempotency：

- `account_id` 与 Market Data 无关。
- 默认唯一身份：`exchange + instrument_id + ts + source`。
- 如果未来交易所或 vendor 提供稳定 exchange tick id，应优先使用 exchange tick id。

Bar idempotency：

- `exchange + instrument_id + timeframe + bar_ts + source`。

Canonical payload 排除：

- `raw_payload`
- `received_at`
- `calculated_at`

### Replay contract

- Market replay 使用 ordered typed market facts。
- Same canonical 返回 no-op。
- Different canonical 返回 conflict / `ERROR`。
- Replay 必须 deterministic。
- Replay 不直接调用 Strategy，除非后续 Strategy Replay stage 另行定义。
- Replay 不修改 `Trade`、`Position`、`MarginSnapshot`、`PnLSnapshot`、`SettlementSnapshot` 或 account state。
- Redis/Kafka replay payload 只能作为 transport input；持久化 DB fact 仍是 replay source-of-truth。

## Stage H Feature Snapshot Core

Stage H 已实现 `FeatureSnapshot` Core：typed `FeatureSnapshot` / `FeatureConfig` / `FeatureBuildResult`、`FeatureQualityStatus` / `FeatureResultStatus`、pure `FeatureBuilder`、canonical payload、`FeatureSnapshotRepository`、SQLAlchemy repository、UoW integration、`feature_snapshots` migration、`FeatureService`、deterministic feature replay 和 tests。

Stage H 不实现 Tick -> Bar Aggregator、Strategy / Signal Lifecycle、Broker adapter、Runtime infra、ML features、portfolio features、cross-instrument features、OMS / Risk / Execution integration 或 Accounting mutation。

### FeatureSnapshot source-of-truth

`FeatureSnapshot` 只能消费：

- typed `Bar`。
- typed `MarketDataSnapshot`。
- trading calendar / trading session。
- instrument identity。
- deterministic feature config / rule version。

`FeatureSnapshot` 禁止消费：

- `raw_payload` 作为 source-of-truth。
- `OrderStatus`。
- `OrderEvent`。
- `ExchangeReport`。
- `Trade` / `Position` / `Margin` / `PnL` / `Settlement`。
- Broker query。
- Redis / Kafka 作为 source-of-truth。

`raw_payload` 如未来存在，只能作为 optional diagnostic payload，不参与 canonical equality、idempotency、replay conflict 判定或 feature 字段恢复。

### FeatureSnapshot identity

`FeatureSnapshot` 必须携带：

- `symbol: str`
- `instrument_id: str`
- `trade_instrument_id: str`
- `exchange: str`
- `trading_day: date`
- `timeframe: BarTimeframe`
- `bar_ts: datetime`
- `feature_version: str`
- `feature_config_hash: str`
- `source_bar_keys: Sequence[str]`

Identity 规则：

- `symbol`、`instrument_id`、`trade_instrument_id`、`exchange`、`trading_day` 必须与 source bars 一致。
- `timeframe` 必须与 source bars 一致。
- `bar_ts` 使用 feature 所属 bar 的 bar start timestamp。
- `feature_version` 是 feature rule/version label，但不能单独作为完整 config identity。
- `feature_config_hash` 必须由 `feature_version`、`timeframe`、全部 configured windows 和 `allow_gap` deterministic 派生。
- `source_bar_keys` 使用 deterministic format：`{exchange}|{instrument_id}|{timeframe}|{bar_ts.isoformat()}|{source}`。
- `source_bar_keys` 不得使用 database id、`received_at`、`calculated_at` 或 random value。
- `FeatureSnapshot` 不猜测合约映射，不从主力连续合约、行情合约、交易合约或 base symbol 自动推断 identity。
- source bars identity 不一致时，后续实现必须 typed reject，不得合成 snapshot。
- source bars timeframe 不一致时，后续实现必须 typed reject，不得合成 snapshot。

### FeatureSnapshot fields

Stage H 冻结以下字段：

- `returns`
- `bar_return`
- `price_range`
- `range`
- `atr`
- `volume_ratio`
- `moving_average`
- `bias`
- `breakout_level`
- `volatility`
- `momentum`
- `source_window_start`
- `source_window_end`
- `warmup_complete`
- `quality_status`
- `missing_bar_count`
- `gap_count`
- `raw_payload` diagnostic only if present
- `feature_config_hash`

Decimal / `None` policy：

- Numeric features 必须为 `Decimal | None`。
- 禁止使用 `float` 表示 feature 数值。
- Insufficient warmup 时 affected feature values 必须为 `None`，且 `warmup_complete=False`。
- 不得静默使用 `0` 填补 missing / insufficient values。
- `raw_payload` 不属于 canonical feature fields。

### Feature calculation rules

Stage H 实现以下最小计算规则：

- `bar_return = close - open`。
- `returns = close - previous_close`，无 previous close 时为 `None`。
- `range` / `price_range = high - low`。
- `atr` 使用 configured window 和 typed OHLC；`true_range = max(high-low, abs(high-previous_close), abs(low-previous_close))`。
- `moving_average` 使用 configured window 和 close average。
- `bias = close - moving_average`。
- 如后续需要 ratio 形式 bias，必须新增独立字段 `bias_ratio`，不得改变 `bias` 语义。
- `volume_ratio = current_volume / average(previous volume window)`。
- `breakout_level = max(high over breakout_window)`。
- `volatility = average(abs(close - previous_close) over volatility_window)`。
- `momentum = close - close_n_periods_ago over momentum_window`。

### Warmup and missing data

- 如果 source bars 少于某个 feature 的 required window，`warmup_complete=False`，affected features 为 `None`，不得 fake 0。
- 如果 gaps detected，`quality_status` 必须反映 gap，`gap_count > 0`。
- `quality_status=ACCEPTED` 时 `warmup_complete=True`、`gap_count=0`、`missing_bar_count=0`，且全部 implemented numeric features 非 `None`。
- `quality_status=WARMUP_INCOMPLETE` 时 `warmup_complete=False`。
- Gap 情况下仅当 explicit policy `allow_gap=True` 时可以 emit `FeatureSnapshot`。
- Missing bars 必须由 `missing_bar_count` 记录。
- Rejected input 或 insufficient input 不得创建 fake facts。

### FeatureSnapshotRepository contract

Stage H 已新增：

- `FeatureSnapshotRepository`。
- `feature_snapshots` table。

Repository methods 冻结为：

- `append_feature_snapshot(snapshot)`。
- `get_by_identity(exchange, instrument_id, timeframe, bar_ts, feature_version, feature_config_hash)`。
- `list_by_instrument(exchange, instrument_id, timeframe, start_bar_ts, end_bar_ts)`。
- `list_by_trading_day(exchange, instrument_id, timeframe, trading_day)`。

Unique constraint：

- `exchange + instrument_id + timeframe + bar_ts + feature_version + feature_config_hash`。

Canonical equality 必须排除：

- `raw_payload`。
- `calculated_at`。
- `received_at`。

### Feature Builder and Service boundary

- `FeatureBuilder` 是 pure calculation boundary，只从 typed bars + deterministic config 生成 `FeatureSnapshot`。
- `FeatureBuilder` 不持久化 facts。
- `FeatureBuilder` 不查询 DB，不使用 UoW。
- `FeatureService` 负责持久化 snapshots。
- `FeatureService` 接收 caller supplied bars + config，不查询 `MarketBarRepository`。
- Fatal rejected input 不持久化；warmup incomplete 可持久化 typed snapshot，但 affected feature values 必须为 `None`。
- `FeatureBuilder` / `FeatureService` 不调用 Strategy。
- `FeatureBuilder` / `FeatureService` 不创建 Signal。
- `FeatureBuilder` / `FeatureService` 不直接查 Risk。
- `FeatureBuilder` / `FeatureService` 不 mutate Accounting。

### Feature replay

- Feature replay 消费 ordered Bars。
- 相同 inputs/config 必须生成相同 `FeatureSnapshot`。
- Replay grouping 必须包含 `feature_config_hash`，同一 `feature_version` 的不同 config 不得互相覆盖或误判 duplicate/conflict。
- Existing same canonical 返回 no-op。
- Existing different canonical 返回 conflict / error。
- Replay 不调用 Strategy。
- Replay 不修改 Market facts。
- Replay 不修改 Accounting。

### Relation to Strategy

- Strategy 后续消费 `FeatureSnapshot`。
- `FeatureSnapshot` 不是 `Signal`。
- `FeatureBuilder` 不做交易决策。
- Strategy 不得为了补齐缺失 feature 直接读取 raw bars，除非后续 Strategy replay contract 显式允许。

### Stage H implementation tests

Stage H tests 覆盖：

- FeatureSnapshot Decimal validation。
- FeatureSnapshot warmup / gap / quality invariant validation。
- FeatureConfig deterministic config hash。
- Insufficient warmup -> affected features `None`，no zero-fill。
- MA calculation。
- ATR calculation。
- Bias formula。
- Volume ratio。
- Breakout level。
- Volatility。
- Momentum。
- Source identity mismatch reject。
- Timeframe mismatch reject。
- Gap handling。
- Duplicate same canonical。
- Duplicate different canonical。
- Replay deterministic。
- No Strategy / Risk / Accounting mutation。
- `raw_payload` excluded from canonical equality。

### Stage H explicit non-goals

Stage H 不实现：

- Strategy。
- Signal。
- OMS / Risk integration。
- Tick -> Bar Aggregator，除非另行 scoped。
- Broker adapter。
- Live feed。
- Kafka / FastAPI / Celery runtime。
- ML features。
- Portfolio features。
- Cross-instrument features。
- Execution / Accounting mutation。

## Stage I Strategy / Signal Lifecycle Core

Stage I 已实现 Strategy / Signal Lifecycle Core：`StrategyConfig` canonicalization / hash、`StrategyContext`、deterministic `signal_id`、`SignalCandidate`、`SignalDecision`、`SignalLifecycleEvent`、`TriggerResult`、`StrategyResult`、signal lifecycle、canonical payload、Signal repository Protocol、SQLAlchemy repository、UoW integration、`signal_candidates` / `signal_events` migration、`StrategyService` / `SignalLifecycleService`、deterministic replay 和 tests。

Stage I 不实现 Order creation、`OrderRequest` creation、Risk check、OMS integration、Execution integration、Broker adapter、runtime scheduling、paper / sim / live、portfolio optimization、ML model serving、cross-instrument strategy 或 Accounting mutation。

### Strategy source-of-truth

Strategy 只能消费：

- `FeatureSnapshot`。
- `MarketDataSnapshot`，optional。
- typed PositionContext / PortfolioContext，optional，且必须由 application layer 提供。
- `StrategyConfig` / `StrategyVersion`。
- trading calendar / session context。

Strategy 禁止消费：

- `raw_payload`。
- DB directly。
- Repository / UoW directly。
- `OMSService`。
- `RiskEngine` directly。
- Execution / Broker。
- `OrderStatus` / `OrderEvent`。
- `ExchangeReport`。
- Trade / Position / Margin / PnL / Settlement tables directly。

`raw_payload` 永远只用于 diagnostic，不得补充或覆盖 source-of-truth。

### Strategy output boundary

Strategy 只能输出：

- `SignalCandidate`。
- `SignalDecision`。
- `TriggerResult`，仅当 lifecycle gate included。

Strategy 禁止：

- create Order。
- call OMS。
- call Risk。
- call Execution。
- mutate Position / Accounting。
- submit / cancel order。
- read broker state。

Signal 是 pre-risk intent，不是 Order、不是 `RiskResult`、不是 OMS state。

### Strategy identity

Strategy / Signal identity 必须携带：

- `strategy_name`
- `strategy_version`
- `strategy_config_hash`
- `runtime_id`
- `signal_id` deterministic policy
- `symbol`
- `instrument_id`
- `trade_instrument_id`
- `exchange`
- `trading_day`
- `timeframe`
- `bar_ts`
- `feature_version`
- `feature_config_hash`

`signal_id` 必须由 strategy identity、feature identity 和 decision params deterministic 派生。不得使用 runtime random value、system time、DB id 或 `runtime_id` 作为 canonical signal identity。`runtime_id` 是 runtime lineage / audit 字段，保留在 `SignalDecision` / `SignalCandidate` 中，但不参与 `signal_id` hash。

### SignalCandidate contract

字段：

- `signal_id`
- `strategy_name`
- `strategy_version`
- `strategy_config_hash`
- `runtime_id`
- `symbol`
- `instrument_id`
- `trade_instrument_id`
- `exchange`
- `trading_day`
- `timeframe`
- `bar_ts`
- `decision`
- `side`
- `position_side`
- `confidence`
- `strength`
- `reason`
- `expected_price`
- `stop_loss`
- `take_profit`
- `holding_period_hint`
- `tags`
- `features_ref`
- `raw_payload`

规则：

- `signal_id` deterministic from strategy identity + feature identity + decision params，且排除 `runtime_id`。
- `confidence` 是 Decimal，范围为 0 到 1，包含边界。
- `expected_price` 在 `decision` 不是 HOLD 时必须为 Decimal > 0。
- HOLD 不得携带 BUY / SELL side；HOLD 的 side 必须是 NONE 或等价空方向。
- `features_ref` 必须引用 `FeatureSnapshot` identity，不得复制 raw bars 作为事实来源。
- `raw_payload` diagnostic only，不参与 canonical equality。

### SignalDecision contract

字段：

- `decision`
- `side`
- `strength`
- `confidence`
- `reason`
- `signal_id`
- `strategy_name`
- `strategy_version`
- `strategy_config_hash`
- `runtime_id`
- `symbol`
- `instrument_id`
- `trade_instrument_id`
- `exchange`
- `trading_day`
- `timeframe`
- `bar_ts`
- `feature_version`
- `feature_config_hash`
- `position_side`
- `expected_price`
- `stop_loss`
- `take_profit`
- `tags`
- `raw_payload`

规则：

- `SignalDecision` 保留 feature identity propagation。
- `SignalDecision` 不创建 Order，不携带 OMS status，不携带 Risk result。
- `confidence`、`expected_price`、HOLD side 和 `raw_payload` 规则与 `SignalCandidate` 一致。

### StrategyResult contract

`StrategyResult` 状态语义：

- `GENERATED` 必须携带 `decision`。
- `REJECTED_*` 必须不携带 `decision`。
- `ERROR` 必须不携带 `decision`。
- 非法状态组合由 `StrategyService` 返回 typed `ERROR`，不得 append candidate，不得 append lifecycle event。

### Trigger lifecycle contract

已实现 lifecycle gate，状态冻结为：

- `CANDIDATE`
- `CONFIRMED`
- `TRIGGERED`
- `DUPLICATE`
- `BLOCKED`
- `EXPIRED`

规则：

- duplicate same canonical -> `DUPLICATE` / no-op。
- duplicate different canonical -> `CONFLICT` / `ERROR`。
- expired signal cannot trigger。
- blocked signal cannot trigger。
- already triggered signal returns `DUPLICATE` / no-op and does not append another `TRIGGERED` event。
- trigger does not create Order。
- trigger only emits `TriggerResult` / application-level intent。

### StrategyConfig contract

字段：

- `strategy_name`
- `strategy_version`
- `strategy_config_hash`
- `feature_version`
- `feature_config_hash`
- `timeframe`
- `params`
- `allow_position_context`
- `allow_market_snapshot`
- `enabled`

规则：

- `strategy_version` deterministic and required。
- `params` 必须 canonicalized。Mapping key 只允许 `str`；value 只允许 stable JSON-like values：`None`、`bool`、`int`、`str`、`Decimal`、`date`、`datetime`、enum、list/tuple、dict。禁止 float、set、`object()`、非 string key 和 arbitrary class instance；不得通过 `str()` 静默转换 unknown object。
- `strategy_config_hash` 必须 deterministic，且 hash input 排除 `strategy_config_hash` 自身。
- no runtime random version。
- `raw_payload` not source-of-truth。

### Repository / DB contract

Stage I 已实现：

- `SignalCandidateRepository`
- `SignalEventRepository`
- `signal_candidates` table
- `signal_events` table

唯一约束：

- `signal_id` unique。
- `strategy_name + strategy_version + strategy_config_hash + instrument_id + timeframe + bar_ts + feature_version + feature_config_hash` unique。
- `signal_events.event_key` unique。

`SignalLifecycleEvent.event_key` 由 `signal_id + lifecycle_status + event_ts + event_reason` stable JSON + sha256 deterministic 生成。`raw_payload`、`created_at` 和 DB id 不参与 event key，也不参与 lifecycle event canonical equality。

Canonical excludes：

- `raw_payload`
- `calculated_at`
- `received_at`
- `created_at`
- DB id

Stage I 已新增 `UnitOfWork.signal_candidates`、`UnitOfWork.signal_events` 和窄 `StrategySignalUnitOfWork` Protocol。Repository duplicate same canonical 返回 existing / no-op；duplicate different canonical 返回 typed `SignalCandidateConflictError` 或 `SignalLifecycleConflictError`，不得泄漏裸 `IntegrityError`。

### Replay / idempotency contract

- Strategy replay consumes ordered `FeatureSnapshot`。
- same strategy config + same feature snapshot -> same `signal_id`。
- same canonical -> duplicate / no-op。
- different canonical -> conflict / error。
- replay does not call OMS / Risk / Execution。
- replay does not mutate Accounting。
- replay does not create orders。

### Relation to Risk / OMS

- Signal is pre-risk intent。
- Risk later consumes `SignalDecision` / OrderIntent through application orchestration。
- Strategy does not know `RiskResult`。
- Strategy does not know OMS state machine。
- OMS does not consume `FeatureSnapshot` directly。
- OMS / Risk / Execution 已存在不改变 Strategy 边界；Strategy 不得直接调用它们。

### Stage I implementation tests

Stage I tests 覆盖：

- deterministic `signal_id`。
- HOLD side NONE。
- non-HOLD `expected_price` required。
- confidence range。
- feature identity propagation。
- strategy config hash。
- duplicate same canonical。
- duplicate different canonical。
- lifecycle duplicate / block / expire。
- replay deterministic。
- no OMS / Risk / Execution / Accounting imports。
- `raw_payload` excluded。

### Stage I explicit non-goals

Stage I does not implement：

- Order creation。
- Risk check。
- OMS integration。
- Execution integration。
- Broker adapter。
- runtime scheduling。
- paper / sim / live。
- portfolio optimization。
- ML model serving。
- cross-instrument strategy unless separately scoped。

### signal_candidates

Stage I 已新增 `signal_candidates` 表作为 persisted SignalCandidate facts ledger。

字段：

- `signal_id`
- `strategy_name`
- `strategy_version`
- `strategy_config_hash`
- `runtime_id`
- `symbol`
- `instrument_id`
- `trade_instrument_id`
- `exchange`
- `trading_day`
- `timeframe`
- `bar_ts`
- `feature_version`
- `feature_config_hash`
- `decision`
- `side`
- `position_side`
- `confidence`
- `strength`
- `reason`
- `expected_price`
- `stop_loss`
- `take_profit`
- `holding_period_hint`
- `tags`
- `features_ref`
- `raw_payload`
- `created_at`

约束和索引：

- `UNIQUE(signal_id)`，名称为 `uq_signal_candidates_signal_id`
- `UNIQUE(strategy_name, strategy_version, strategy_config_hash, instrument_id, timeframe, bar_ts, feature_version, feature_config_hash)`，名称为 `uq_signal_candidates_strategy_feature_identity`
- `(strategy_name, strategy_version)` 复合索引
- `(exchange, instrument_id, trading_day)` 复合索引
- `(timeframe, bar_ts)` 复合索引
- `signal_id` 索引

Canonical payload 包含 strategy identity、feature identity、decision / side / position_side、confidence / strength / reason、expected_price / stop_loss / take_profit、holding_period_hint、tags 和 features_ref。`raw_payload`、`created_at`、`received_at`、`calculated_at` 和 DB id 不参与 canonical equality。

### signal_events

Stage I 已新增 `signal_events` 表作为 Signal lifecycle event ledger。

字段：

- `id`
- `signal_id`
- `lifecycle_status`
- `event_reason`
- `event_ts`
- `raw_payload`
- `created_at`

索引：

- `signal_id` 索引
- `(signal_id, created_at)` 复合索引

`signal_events` 只记录 lifecycle status，不创建 Order、不写 Risk/OMS/Execution facts。`raw_payload` diagnostic only。

## Stage J Trading Workflow Core Contract Freeze

Stage J 已实现 Trading Workflow Core：`SignalDecision -> TradingRiskResult -> OrderIntent`。本阶段停止在 `OrderIntent` persistence，不调用 OMS，不调用 Execution，不调用 Broker，不写 `orders` / `order_events`，不进入 Broker / Runtime / Paper / Sim / Live。

Stage J 已新增 Stage J 专用 `TradingRiskResult`，避免和早期 pure Risk / OMS legacy `RiskResult(decision, rule_name, reason)` 混淆。Legacy `RiskResult`、现有 `RiskEngine` 和 OMS state machine 未被修改。Stage J 本身仍不调用 OMS；`OrderIntent -> OMS.create_order` bridge 已由 Stage J.2 独立实现。

### Trading Workflow source-of-truth

Trading Workflow 只允许消费：

- `SignalDecision`
- `StrategyConfig`
- `PositionContext`
- `PortfolioContext`
- `AccountContext`
- `MarginSnapshot`
- `RiskConfig` 或 Stage J `risk_config_hash`
- `requested_quantity`
- `evaluation_context_hash`
- `TradingCalendar` / `Session`

Trading Workflow 禁止消费：

- `OrderStatus`
- `OrderEvent`
- `ExchangeReport`
- `raw_payload`
- Broker state
- OMS state machine internals

`raw_payload` 只能 diagnostic，不得参与 RiskResult、OrderIntent、idempotency、replay 或 canonical equality。

### RiskResultStatus contract

Stage J `RiskResultStatus` 冻结为：

- `ACCEPT`：完整接受 signal requested quantity。
- `REDUCE`：接受降低后的 positive quantity。
- `REJECT`：拒绝，不生成 `OrderIntent`。
- `BLOCK`：策略、账户、组合、交易时段或安全门禁阻断，不生成 `OrderIntent`。
- `UNKNOWN`：风控无法确定 typed result，不生成 `OrderIntent`。

### TradingRiskResult contract

Stage J `TradingRiskResult` 是 trading workflow 的 deterministic 风控事实。它不同于早期 pure Risk / OMS legacy `RiskResult(decision, rule_name, reason)`；后续实现如需迁移，必须显式处理兼容边界，不得把 legacy 字段扩展成隐式事实来源。

字段冻结：

| 字段 | 类型 | 默认值 | 语义 |
|---|---|---|---|
| `signal_id` | `str` | required | 输入 `SignalDecision` 身份。 |
| `risk_result_id` | `str` | required | deterministic RiskResult identity。 |
| `evaluation_context_hash` | `str` | required | 上层应用基于 typed deterministic inputs 供应的评价上下文身份。 |
| `risk_status` | `RiskResultStatus` | required | `ACCEPT` / `REDUCE` / `REJECT` / `BLOCK` / `UNKNOWN`。 |
| `risk_reason` | `str \| None` | `None` | 类型化风控说明；不是 raw diagnostic payload。 |
| `risk_level` | `str` | required | 风控等级，例如 rule/policy severity；后续 enum 化前仍必须 canonical。 |
| `requested_quantity` | `Decimal` | required | 原始请求数量，来自 Stage J context。 |
| `approved_quantity` | `Decimal` | required | 允许下单数量；`ACCEPT` 等于 requested quantity，`REDUCE` 为降低后的 positive quantity，其他状态为 `Decimal("0")`。 |
| `max_quantity` | `Decimal` | required | 本次上下文允许的最大数量。 |
| `expected_margin` | `Decimal` | required | 预期保证金。 |
| `expected_notional` | `Decimal` | required | 预期名义金额。 |
| `config_hash` | `str` | required | `RiskConfig` canonical hash。 |
| `evaluation_ts` | `datetime` | required | 风控评价时间；用于 audit；当前实现不参与 `risk_result_id` / canonical。 |
| `raw_payload` | `dict[str, Any] \| None` | `None` | 诊断字段，不参与 facts / canonical / id。 |

规则：

- `TradingRiskResult` 必须 deterministic。
- `raw_payload` 不参与事实。
- same inputs -> same result。
- `signal_id + config_hash + evaluation_context_hash` 必须得到 deterministic result。
- `risk_result_id` 必须由 canonical payload deterministic 派生，不得使用 runtime random value、DB id、`raw_payload` 或系统当前时间。
- `evaluation_ts` 不参与 `risk_result_id` 或 canonical equality。
- same canonical -> no-op。
- different canonical -> conflict / error。
- `TradingRiskResult.config_hash` 必须等于 `TradingWorkflowContext.risk_config_hash`。
- `TradingRiskResult.evaluation_context_hash` 必须等于 `TradingWorkflowContext.evaluation_context_hash`。
- `requested_quantity`、`approved_quantity`、`max_quantity`、`expected_margin`、`expected_notional` 均 required Decimal；`None` 不允许进入 Stage J core facts。
- `REJECT` / `BLOCK` / `UNKNOWN` 用 `Decimal("0")` 表达明确 none/blocked。

### OrderIntent contract

`OrderIntent` 是经过 RiskResult 授权后的下单意图。`OrderIntent` 不是 Order，不承载 OMS state，不替代 `OrderState`、`OrderEvent` 或 Execution command。

字段冻结：

| 字段 | 类型 | 默认值 | 语义 |
|---|---|---|---|
| `intent_id` | `str` | required | deterministic OrderIntent identity。 |
| `signal_id` | `str` | required | 来源 `SignalDecision` 身份。 |
| `risk_result_id` | `str` | required | 来源 `RiskResult` 身份。 |
| `strategy_name` | `str` | required | strategy identity。 |
| `strategy_version` | `str` | required | strategy identity。 |
| `strategy_config_hash` | `str` | required | strategy identity。 |
| `runtime_id` | `str` | required | runtime lineage / audit 字段，不代表 deterministic signal identity。 |
| `symbol` | `str` | required | display / market symbol identity。 |
| `instrument_id` | `str` | required | instrument identity。 |
| `trade_instrument_id` | `str` | required | tradable instrument identity。 |
| `exchange` | `str` | required | exchange identity。 |
| `trading_day` | `date` | required | 交易日。 |
| `timeframe` | `BarTimeframe` | required | 策略 timeframe。 |
| `bar_ts` | `datetime` | required | source bar timestamp。 |
| `feature_version` | `str` | required | feature identity。 |
| `feature_config_hash` | `str` | required | feature identity。 |
| `side` | enum / `str` | required | 买卖方向。 |
| `offset` | enum / `str` | required | 开平方向。 |
| `quantity` | `Decimal` | required | 授权下单数量。 |
| `price` | `Decimal` | required | 下单价格。 |
| `order_type` | enum / `str` | required | 订单类型。 |
| `tif` | enum / `str` | required | time-in-force。 |
| `expected_margin` | `Decimal` | required | 来自 `RiskResult` 的预期保证金。 |
| `expected_notional` | `Decimal` | required | 来自 `RiskResult` 的预期名义金额。 |
| `intent_reason` | `str \| None` | `None` | 生成意图的 typed reason。 |
| `raw_payload` | `dict[str, Any] \| None` | `None` | 诊断字段，不参与 facts / canonical / id。 |

规则：

- `intent_id` 必须 deterministic。
- `OrderIntent` 不得从 `OrderStatus`、`OrderEvent`、`ExchangeReport`、Broker state、OMS internals 或 `raw_payload` 派生。
- `OrderIntent` same canonical -> no-op。
- `OrderIntent` different canonical -> conflict / error。
- Stage J 当前不调用 `OMS.create_order(...)`。当前 OMS 实现仍是 legacy `OrderRequest` 入口；`OrderIntent -> OMS` bridge 由 Stage J.2 独立 adapter 显式迁移，`OrderIntent` 仍不是 Order。

### Workflow contract

冻结 workflow：

```text
SignalDecision
↓
RiskEvaluator.evaluate(...)
↓
TradingRiskResult
↓
OrderIntentBuilder
↓
OrderIntent
↓
OrderIntent persistence
```

只有以下 `RiskResultStatus` 允许进入 `OrderIntentBuilder` 并创建 `OrderIntent`：

- `ACCEPT`
- `REDUCE`

以下状态必须停止 workflow：

- `REJECT`
- `BLOCK`
- `UNKNOWN`

停止 workflow 时：

- 不创建 `OrderIntent`。
- 不调用 OMS。
- 不调用 Execution。
- 不修改 Accounting。

### Quantity reduction contract

`REDUCE` 必须满足：

- reduced quantity `> 0`
- reduced quantity `< original requested quantity`

如果 reduced quantity `<= 0`，必须转换为 `REJECT`。

如果 reduced quantity 等于 original requested quantity，必须 normalize 为 `ACCEPT`。

`ACCEPT` 必须保持 approved quantity 等于 original requested quantity。`approved_quantity > requested_quantity` 必须返回 `ERROR` 且不持久化。`REJECT` / `BLOCK` / `UNKNOWN` 的 approved quantity 必须为 `Decimal("0")`。

### Replay / idempotency contract

RiskResult idempotency：

- same canonical -> no-op。
- different canonical -> conflict / error。

OrderIntent idempotency：

- same canonical -> no-op。
- different canonical -> conflict / error。

Replay 输入相同：

- `SignalDecision`
- `RiskConfig`
- `PositionContext`
- `PortfolioContext`
- `MarginSnapshot`

Replay 结果必须相同：

- `TradingRiskResult`
- `OrderIntent`

Replay 禁止：

- 调用 OMS。
- 调用 Execution。
- 修改 Accounting。
- 读取 Broker state。
- 使用 `raw_payload` 补事实。

### Boundary contract

- Strategy 不创建 `OrderIntent`。
- Strategy 不调用 OMS。
- Risk 不知道 Execution。
- Execution 不知道 Signal。
- OMS 不消费 `FeatureSnapshot`。
- OMS 不消费 `StrategyConfig`。
- Broker 不参与 Stage J。
- `TradingWorkflowService` 负责连接 `SignalDecision`、`RiskEvaluator.evaluate(...)`、`OrderIntentBuilder` 和 repository persistence，但不得 import OMS / Execution / Broker，不得把 OMS state machine internals 暴露给 Risk 或 Strategy。

### Repository / UoW contract

Stage J 已实现：

- `TradingRiskResultRepository`
- `OrderIntentRepository`
- `UnitOfWork.trading_risk_results`
- `UnitOfWork.order_intents`
- 窄 `TradingWorkflowUnitOfWork`

唯一键：

- `TradingRiskResult`：`risk_result_id`
- `OrderIntent`：`intent_id`

Canonical excludes：

- `raw_payload`
- `created_at`
- `received_at`
- 非 deterministic `evaluation_ts`

Canonical includes：

- `evaluation_context_hash`
- `requested_quantity`

Repository behavior：

- duplicate same canonical -> return existing / no-op。
- duplicate different canonical -> typed conflict / error。
- 不裸露 `IntegrityError`。

### Stage J implementation tests

Stage J tests 覆盖：

- `ACCEPT`
- `REDUCE`
- `REJECT`
- `BLOCK`
- `UNKNOWN`
- deterministic RiskResult
- deterministic OrderIntent
- REDUCE quantity rule
- REJECT / BLOCK / UNKNOWN no OMS call
- replay deterministic
- duplicate same canonical
- duplicate different canonical
- no Strategy direct OMS call
- no Execution direct Signal consumption
- no raw_payload facts

### Stage J explicit non-goals

Stage J 不实现：

- Execution submit。
- Broker adapter。
- Paper。
- Sim。
- Live。
- Exchange connectivity。
- OMS state machine changes。
- Portfolio optimization。

## Stage J.2 OMS Bridge Core Contract Freeze

Stage J.2 已实现 `OrderIntent -> OMS.create_order` bridge V1。Stage J.2 不修改 Stage J Trading Workflow，不修改 OMS state machine，不进入 Execution / Broker / Paper / Sim / Live，不新增 bridge table，不新增 migration。

已实现：

- `OMSBridgeResultStatus`
- `OMSBridgeContext`
- `OMSBridgeResult`
- deterministic `client_order_id`
- OMS bridge canonical payload / `bridge_payload_hash`
- `OMSOrderCreator` / `OMSOrderLookup` Protocol
- `OMSBridgeService`
- dry-run `replay_oms_bridge`

### OMS Bridge source-of-truth

OMS Bridge 只能消费：

- `OrderIntent`。
- `TradingRiskResult` reference / `risk_result_id`。
- 从 `OrderIntent` 复制的 Strategy / Signal identity。
- 从 `OrderIntent` 复制的 instrument identity。
- application layer 提供的 typed account / order config。

OMS Bridge 禁止消费：

- `FeatureSnapshot` directly。
- `SignalDecision` directly，除非只通过 `OrderIntent` lineage 追溯。
- concrete `RiskEngine`。
- `raw_payload`。
- Broker state。
- `ExchangeReport`。
- `OrderEvent`。
- `ExecutionResult`。
- Accounting tables。

`raw_payload`、metadata 或 diagnostic payload 不得参与 bridge canonical、idempotency、risk gate 或 replay equality。

### Bridge output

OMS Bridge 输出：

- OMS `create_order` input / `OrderRequest` adapter object。
- `OMSService.create_order(...)` result。
- `OMSBridgeResult`。

OMS Bridge 禁止：

- call Execution。
- call Broker。
- submit order to exchange。
- modify Accounting。
- recompute Risk。
- mutate Strategy / Signal / Trading Workflow facts。

### OrderIntent -> OMS mapping

Bridge 必须从 `OrderIntent` 读取以下字段：

- `intent_id`
- `signal_id`
- `risk_result_id`
- strategy identity
- instrument identity
- `side`
- `offset`
- `quantity`
- `price`
- `order_type`
- `tif`
- `expected_margin`
- `expected_notional`

映射到 OMS create-order input：

| OMS create-order input | Source |
|---|---|
| `client_order_id` | deterministic from `intent_id` |
| `account_id` | application context / typed order config |
| `instrument_id` | `OrderIntent.instrument_id` |
| `trade_instrument_id` | `OrderIntent.trade_instrument_id` |
| `exchange` | `OrderIntent.exchange` |
| `side` / direction | `OrderIntent.side` |
| `offset` | `OrderIntent.offset` |
| `quantity` | `OrderIntent.quantity` |
| `price` / `limit_price` | `OrderIntent.price` |
| `order_type` | `OrderIntent.order_type` |
| `tif` | `OrderIntent.tif` |
| `source` | literal `"oms_bridge"` |
| `external_ref` / `intent_ref` | `OrderIntent.intent_id` |
| metadata | diagnostic only |

Mapping 禁止从 `raw_payload`、`FeatureSnapshot`、`SignalDecision`、`ExchangeReport`、Broker state、Accounting tables 或 OMS internals 补字段。

Stage J.2 V1 不扩展 legacy `OrderRequest` 字段；当前 OMS request 实际承载 `client_order_id`、`account_id`、`instrument_id`、`exchange`、direction、`offset`、`order_type`、`limit_price` 和 `quantity`。`trade_instrument_id`、`tif`、`source`、`external_ref` / `intent_ref` 和 bridge metadata 作为 bridge canonical/result lineage 冻结，后续如需进入 OMS persisted metadata 必须另行扩展 schema / OMS contract。

### Bridge idempotency

同一 `intent_id`：

- same canonical bridge payload -> duplicate / no-op / return existing OMS order reference。
- different canonical bridge payload -> `CONFLICT` / typed error。
- duplicate/conflict 判断必须优先使用 existing bridge `bridge_payload_hash`；hash 缺失时只能使用 `client_order_id`、`intent_id`、`risk_result_id` 和 OMS request canonical 作为 fallback，不得只依赖 OMS request equality。

`client_order_id`：

- 必须 deterministic。
- 必须 derived from `intent_id`。
- 不得使用 random UUID。
- 不得使用 timestamp。
- 不得使用 DB id。

`bridge_payload_hash` 必须 deterministic，且必须排除 `raw_payload`、metadata diagnostic values、runtime timestamp、DB id、`created_at` 和 `bridge_ts`。

### Risk gate boundary

Bridge 必须验证：

- `OrderIntent.risk_result_id` present。
- `OrderIntent` references `ACCEPT` / `REDUCE` 的 `TradingRiskResult`。
- `OrderIntent.quantity > 0`。
- 如果未来 `OrderIntent` 添加 status，rejected / blocked / unknown intent 不得进入 OMS。

Bridge 不得：

- call `RiskEngine`。
- re-run risk。
- override approved quantity。
- increase quantity。
- change side / price to bypass risk。
- 把 `expected_margin` / `expected_notional` 重新解释为新的 risk decision。

### OMS boundary

Bridge may call：

- `OMSService.create_order`。

Bridge must not call：

- `OMSService.apply_order_event`。
- Execution。
- Broker。
- direct exchange submit。

`OMSService.apply_risk_result` 不属于 Stage J.2 bridge 常规路径；只有当未来 OMS create-order design 明确需要并经单独验收时，才能进入 bridge implementation。

Stage J.2 冻结选择：

- Bridge 调用 `OMSService.create_order` 时，输入已是 upstream risk accepted / reduced。
- 如果当前 OMS 仍存在 internal risk phases，Bridge implementation 必须使用现有 accepted path 或 adapter result，不得在 contract freeze 中修改 OMS state machine。
- OMS 在 `create_order` 后 owns order lifecycle；Bridge 不处理后续 order events。

### Bridge result contract

`OMSBridgeResultStatus` 冻结为：

- `CREATED`
- `DUPLICATE`
- `REJECTED_INVALID_INTENT`
- `REJECTED_RISK_NOT_ACCEPTED`
- `CONFLICT`
- `ERROR`

`OMSBridgeResult` 字段冻结：

| 字段 | 类型 | 语义 |
|---|---|---|
| `status` | `OMSBridgeResultStatus` | bridge typed result。 |
| `intent_id` | `str` | source `OrderIntent.intent_id`。 |
| `client_order_id` | `str` | deterministic OMS client id。 |
| `order_id` | `str \| None` | OMS order reference；reject/error 可为 `None`。 |
| `reason` | `str \| None` | typed reason / diagnostic summary。 |
| `bridge_payload_hash` | `str` | deterministic canonical bridge payload hash。 |
| `created_at` / `bridge_ts` | `datetime \| None` | optional audit timestamp；不参与 idempotency。 |

### Future repository / audit decision

Future implementation 可选择新增：

- `OMSBridgeEventRepository`
- `OMSBridgeAuditRepository`
- `oms_bridge_events` table

V1 contract choice：

- Stage J.2 V1 不新增 bridge table，依赖 OMS `orders.client_order_id`、Order lookup 返回的 bridge lineage metadata、`OrderIntent.intent_id` lineage 和 `OMSBridgeResult.bridge_payload_hash`。如果 legacy `OrderRequest` 无法存储 metadata，OMS adapter / fake lookup 必须 out-of-band 携带 `bridge_payload_hash` / lineage。
- 如果 audit gap 明确存在，再通过后续 migration 添加 bridge audit table。
- 即使不建 audit table，Bridge 也必须输出 deterministic `bridge_payload_hash`，供日志、result、test 和 replay comparison 使用。

### Bridge replay contract

Bridge replay：

- consumes ordered `OrderIntent`。
- same intent -> same `client_order_id`。
- same canonical -> no-op。
- different canonical -> typed conflict。
- 默认 dry-run，不调用 OMS。
- 不调用 Execution。
- 不调用 Broker。
- 不修改 Accounting。
- 不创建 exchange order。

任何 live replay 调用 OMS 必须通过后续显式 flag / gate 冻结，不得作为默认 replay 行为。

### Stage J.2 boundary split

- Strategy：不参与。
- Risk：已在 upstream 完成，不被 bridge 调用。
- TradingWorkflow：只创建并持久化 `OrderIntent`。
- OMS Bridge：只把 `OrderIntent` 转换为 OMS create-order input，并调用允许的 OMS create-order boundary。
- OMS：`create_order` 后 owns order lifecycle。
- Execution：不参与。
- Broker：不参与。
- Accounting：不参与。

### Stage J.2 implementation tests

Stage J.2 tests 覆盖：

- deterministic `client_order_id`。
- `OrderIntent -> OMS create_order` field mapping。
- missing `risk_result_id` -> `REJECTED_INVALID_INTENT`。
- risk not accepted / reduced -> `REJECTED_RISK_NOT_ACCEPTED`。
- `quantity <= 0` -> `REJECTED_INVALID_INTENT`。
- duplicate same canonical -> no-op / existing OMS order reference。
- duplicate different OMS payload -> `CONFLICT`。
- OMS creator error -> controlled `ERROR`。
- no `RiskEngine` call。
- no Execution / Broker call。
- no Accounting mutation。
- replay dry-run deterministic。
- `raw_payload` excluded from canonical/idempotency。
- no bridge repository。
- no bridge table / migration。

### Stage J.2 explicit non-goals

Stage J.2 不实现：

- Execution submit。
- Broker adapter。
- Paper。
- Sim。
- Live。
- Exchange connectivity。
- OMS state machine redesign。
- Risk recalculation。
- Accounting mutation。
- Portfolio optimization。
- Runtime scheduling。

## Stage K Execution Gateway Core Contract

Stage K 已实现 Execution Gateway Core：OMS Order / `OrderState` -> deterministic `ExecutionCommand` -> typed `ExecutionCommandResult`。Stage K 不修改 OMS / OMS Bridge / Trading Workflow / Strategy / Risk / Broker / Runtime，不生成 `ExecutionReport` / `OrderEvent`，不生成 Fill / Trade，不修改 Accounting。

Stage K Core only supports `MOCK` target。`PAPER` / `SIM` / `LIVE` typed rejected / deferred。真实 broker、CTP、SimNow、fill matching、trade generation 和 accounting update 全部 deferred。

### Execution Gateway source-of-truth

Execution Gateway 只能消费：

- OMS Order / `OrderState`。
- OMS `order_id`。
- `client_order_id`。
- 从 OMS Order 复制的 instrument identity。
- 从 OMS Order 复制的 `side` / `offset` / `quantity` / `price` / `order_type` / `tif`。
- typed execution config。
- trading session / calendar context。

Execution Gateway 禁止消费：

- `FeatureSnapshot`。
- `SignalDecision`。
- `OrderIntent` directly，除非只通过 OMS Order metadata lineage 追溯。
- `RiskEngine`。
- `raw_payload`。
- Broker state as source-of-truth。
- `ExchangeReport` as source-of-truth before normalized。
- Accounting tables。

### Execution Gateway output

Stage K freeze 新增 / 冻结：

- `ExecutionCommand`
- `ExecutionCommandResult`
- `ExecutionReport` normalized later

Execution Gateway 输出：

- `ExecutionCommand`
- `ExecutionCommandResult`

Execution Gateway 禁止：

- mutate OMS state directly，除非后续通过 `OMSService.apply_order_event(...)` path。
- mutate Accounting。
- call Strategy / Risk。
- read Broker state as fact。
- submit to real Broker in Stage K contract。

### ExecutionCommand contract

`ExecutionCommand` 字段冻结：

| 字段 | 类型 | 语义 |
|---|---|---|
| `command_id` | `str` | deterministic command identity。 |
| `order_id` | `str` | OMS order identity。 |
| `client_order_id` | `str` | OMS client order id。 |
| `account_id` | `str` | 账户 ID。 |
| `instrument_id` | `str` | OMS Order 复制的合约 identity。 |
| `trade_instrument_id` | `str` | OMS Order 复制的交易合约 identity。 |
| `exchange` | `str` | 交易所。 |
| `side` | `str` | 买卖方向。 |
| `offset` | `str` | 开平方向。 |
| `quantity` | `Decimal` | 委托数量。 |
| `price` | `Decimal` | 委托价格。 |
| `order_type` | `str` | 订单类型。 |
| `tif` | `str` | time-in-force。 |
| `command_type` | `ExecutionCommandType` | submit / cancel command type。 |
| `execution_target` | `ExecutionTarget` | execution adapter target。 |
| `command_payload_hash` | `str` | deterministic canonical payload hash。 |
| `created_at` | `datetime` | 本地创建时间；不参与 canonical equality。 |

`ExecutionCommandType` 冻结为：

- `SUBMIT_ORDER`
- `CANCEL_ORDER`：future / deferred，除非另开实现范围。

`ExecutionTarget` 冻结为：

- `MOCK`
- `PAPER`
- `SIM`
- `LIVE`

Stage K implementation only allows `MOCK`。`PAPER` / `SIM` / `LIVE` typed rejected / deferred。

### Deterministic command_id

`command_id` rule：

- deterministic from `order_id + command_type + execution_target`。
- no UUID。
- no timestamp。
- no DB id。
- same order + same target -> same `command_id`。

`command_id` 不得包含 `command_payload_hash` 自身，不得包含 `created_at` / `received_at`，不得包含 adapter / broker response。

### ExecutionCommand canonical payload

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

`ExecutionCommand` canonical excludes：

- `raw_payload`
- `created_at`
- `received_at`
- broker response
- DB id

### Execution idempotency

Same `command_id` + same canonical：

- duplicate / no-op。

Same `command_id` + different canonical：

- conflict / error。

Same OMS order must not generate multiple submit commands for same target。

### Execution Gateway service boundary

Future `ExecutionGatewayService`：

- receives OMS Order / `OrderState`。
- validates order is eligible for execution。
- builds `ExecutionCommand`。
- persists command if repository chosen。
- dispatches only to allowed execution adapter。

Eligibility 必须基于 OMS Order / `OrderState` 和 typed execution config。不得用 Strategy / Risk / Broker / Accounting 事实补资格判断。

### Repository / migration contract

Stage K 已实现：

- `ExecutionCommandRepository`
- `execution_commands` table

原因：

- `ExecutionCommand` 是 broker 前的事实 / audit boundary。
- 同一 OMS order + target 的 submit idempotency 必须可持久化检查。
- Replay 需要读取 command ledger 判断 duplicate / conflict。

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

Stage K 已通过 `0012_stage_k_execution_gateway_core` migration 创建 `execution_commands` table。不得在 Stage K 添加 trades、fills、broker tables、execution reports、exchange tables 或 order events。

### Execution adapter boundary

Protocol：

- `ExecutionAdapter.submit(command) -> ExecutionCommandResult`

Adapter must return typed result, not raw broker response。

Stage K Core：

- implements deterministic `MockExecutionAdapter`。
- must not implement CTP / SimNow / real broker。
- must not require network。

### ExecutionCommandResult contract

`ExecutionCommandResult` 字段冻结：

| 字段 | 类型 | 语义 |
|---|---|---|
| `command_id` | `str` | 对应 `ExecutionCommand.command_id`。 |
| `order_id` | `str` | 对应 OMS order。 |
| `status` | `ExecutionCommandResultStatus` | adapter command result status。 |
| `reason` | `str \| None` | typed reason / diagnostic summary。 |
| `adapter_order_ref` | `str \| None` | adapter 返回的本地/模拟引用；不是 exchange acceptance fact。 |
| `submitted_at` | `datetime \| None` | adapter submit time；不参与 command canonical。 |
| `raw_payload` | `dict[str, Any]` | diagnostic only，不承载 source-of-truth。 |

`ExecutionCommandResultStatus` 冻结为：

- `ACCEPTED_BY_ADAPTER`
- `REJECTED_BY_ADAPTER`
- `DUPLICATE`
- `CONFLICT`
- `ERROR`

Rules：

- Adapter accepted does not mean exchange accepted。
- Broker / exchange reports are later normalized to OMS `OrderEvent`。
- `raw_payload` diagnostic only。

### OMS relation

Execution Gateway must not mutate OMS directly in contract freeze。

Future flow：

```text
ExecutionCommandResult / ExecutionReport
-> normalized OrderEvent
-> OMS.apply_order_event
```

Stage K does not implement normalized broker reports unless separately scoped。

### Execution replay

Execution replay：

- same OMS order + same target -> same `ExecutionCommand`。
- same canonical -> duplicate / no-op。
- different canonical -> conflict / error。
- dry-run default。
- replay must not submit to broker / adapter unless explicit live flag。
- replay does not mutate OMS / Accounting。

### Stage K boundary split

- OMS：owns order state。
- Execution Gateway：owns command creation / adapter dispatch。
- Broker：not in Stage K。
- Accounting：not involved。
- Risk：already upstream。
- Strategy：not involved。

### Stage K implementation tests

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

### Stage K explicit non-goals

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

## Stage L Execution Report Normalization Contract

Stage L freezes the Execution Report Normalizer boundary on baseline `stage-k-execution-gateway-core / 94b498e`。This is a documentation-only contract freeze. It does not add code, schema, migrations or tests。

Stage K `ExecutionCommandResult` remains adapter command-result semantics only：adapter accepted / rejected does not mean exchange accepted, filled or traded。

### Execution Report Normalizer source-of-truth

Execution Report Normalizer 只能消费：

- `ExecutionCommand`。
- `ExecutionCommandResult`。
- typed adapter report input。
- adapter identity。
- `command_id` / `order_id` / `client_order_id` lineage。
- typed timestamp normalization rule。

Execution Report Normalizer 禁止消费：

- `FeatureSnapshot`。
- `SignalDecision`。
- `TradingRiskResult`。
- `OrderIntent` mutation。
- Accounting tables。
- Position tables。
- Margin / PnL / Settlement。
- Broker state as source-of-truth。
- `raw_payload` as facts。

### RawExecutionReport contract

`RawExecutionReport` 是 typed raw adapter input。Adapter 必须尽量在进入 domain 前把外部 ms / us / ns timestamp normalize 为 `datetime`。

字段冻结：

| 字段 | 类型 | 语义 |
|---|---|---|
| `raw_report_id` | `str` | adapter report identity；adapter 可提供时 per adapter unique。 |
| `adapter_name` | `str` | adapter identity。 |
| `execution_target` | `ExecutionTarget` | execution adapter target。 |
| `command_id` | `str` | `ExecutionCommand` lineage。 |
| `order_id` | `str` | OMS order lineage。 |
| `client_order_id` | `str` | OMS client order lineage。 |
| `adapter_order_ref` | `str` | adapter-local order reference。 |
| `exchange_order_id` | `str \| None` | external exchange order id。 |
| `report_type` | `str` | adapter-normalized report type。 |
| `filled_qty` | `Decimal` | report-level filled quantity。 |
| `fill_price` | `Decimal \| None` | fill price when applicable。 |
| `cumulative_filled_qty` | `Decimal` | cumulative filled quantity。 |
| `remaining_qty` | `Decimal` | remaining quantity。 |
| `report_ts` | `datetime` | normalized report event time。 |
| `received_at` | `datetime` | local receive time；excluded from canonical equality。 |
| `raw_payload` | `dict[str, Any]` | diagnostic only。 |

Rules：

- `raw_payload` diagnostic only。
- Decimal-only for quantities / prices。
- no float。

### NormalizedExecutionReport contract

`NormalizedExecutionReport` 是 normalizer 输出的 deterministic execution report fact。

字段冻结：

| 字段 | 类型 | 语义 |
|---|---|---|
| `report_id` | `str` | deterministic normalized report identity。 |
| `raw_report_id` | `str` | raw report lineage。 |
| `adapter_name` | `str` | adapter identity。 |
| `execution_target` | `ExecutionTarget` | execution adapter target。 |
| `command_id` | `str` | `ExecutionCommand` lineage。 |
| `order_id` | `str` | OMS order lineage。 |
| `client_order_id` | `str` | OMS client order lineage。 |
| `adapter_order_ref` | `str` | adapter-local order reference。 |
| `exchange_order_id` | `str \| None` | external exchange order id。 |
| `execution_status` | `ExecutionReportStatus` | normalized execution status。 |
| `filled_qty` | `Decimal` | report-level filled quantity。 |
| `fill_price` | `Decimal \| None` | fill price when applicable。 |
| `cumulative_filled_qty` | `Decimal` | cumulative filled quantity。 |
| `remaining_qty` | `Decimal` | remaining quantity。 |
| `report_ts` | `datetime` | normalized report event time。 |
| `normalized_at` | `datetime` | local normalization time；excluded from canonical equality。 |
| `reason` | `str \| None` | typed reason / diagnostic summary。 |
| `source_report_hash` | `str` | hash of canonical `RawExecutionReport`。 |

Rules：

- `report_id` deterministic。
- `source_report_hash` from canonical `RawExecutionReport`。
- same raw report -> same normalized report。
- no broker raw facts beyond typed raw report。
- no direct OMS mutation。

### ExecutionReportStatus

`ExecutionReportStatus` 冻结为：

- `SUBMITTED`
- `ACKED`
- `PARTIALLY_FILLED`
- `FILLED`
- `REJECTED`
- `CANCELED`
- `ERROR`

`ExecutionReportStatus` is not OMS `OrderStatus`。Mapping to OMS `OrderEvent` happens later in application layer / Stage L implementation boundary。

### Normalized report to OMS OrderEvent mapping

Future mapping：

| `ExecutionReportStatus` | OMS `OrderEvent` |
|---|---|
| `ACKED` | OMS `ACKED` event |
| `PARTIALLY_FILLED` | OMS `PARTIALLY_FILLED` event |
| `FILLED` | OMS `FILLED` event |
| `REJECTED` | OMS `REJECTED_BY_EXCHANGE` event |
| `CANCELED` | OMS `CANCELED` event |

Rules：

- Normalizer may create typed `OrderEvent` candidate。
- Normalizer must not call `OMSService.apply_order_event(...)` directly unless Stage L implementation explicitly includes application service with Unit-of-Work boundary。
- Recommended Stage L Core：normalize report；build `OrderEvent` candidate；persist normalized report；do not mutate OMS。
- OMS apply remains next bridge / application step unless explicitly scoped。

### Fill / Trade boundary

Stage L must not：

- create Trade ledger directly。
- update Position。
- update Margin / PnL / Settlement。
- generate accounting facts。

Fill-like fields in report are execution-state facts only, not Trade facts yet。

Trade creation remains later：

```text
Normalized filled report
-> OMS OrderEvent
-> Trade/Fills ledger adapter later
```

### Execution report idempotency

`RawExecutionReport`：

- `raw_report_id` unique per adapter if available。
- fallback deterministic key：`adapter_name + command_id + report_type + report_ts + cumulative_filled_qty`。

`NormalizedExecutionReport`：

- `report_id` deterministic。
- same canonical -> duplicate / no-op。
- different canonical -> conflict / error。

Canonical excludes：

- `raw_payload`
- `received_at`
- `normalized_at`
- DB id

### ExecutionReportRepository / future migration contract

Future：

- `ExecutionReportRepository`。
- `raw_execution_reports` table optional。
- `normalized_execution_reports` table required if Stage L persists reports。

Recommendation：

- Stage L Core should add `normalized_execution_reports`。
- `raw_execution_reports` optional；`raw_payload` only diagnostic。

Repository methods：

- `append_normalized_report(report)`
- `get_by_report_id(report_id)`
- `list_by_order_id(order_id)`
- `list_by_command_id(command_id)`

Unique：

- `report_id`

Indexes：

- `order_id`
- `command_id`
- `client_order_id`
- `execution_status`
- `report_ts`

### Execution report replay

Report replay：

- consumes ordered `RawExecutionReport`。
- same raw -> same normalized。
- same canonical -> duplicate / no-op。
- different canonical -> conflict。
- replay must not call OMS。
- replay must not update Accounting。
- replay must not generate Trade。

### Stage L boundary split

- Execution Gateway：creates commands。
- Execution Report Normalizer：normalizes adapter reports。
- OMS：owns order state。
- Accounting：not involved。
- Trade ledger：not involved。
- Broker：not source-of-truth。

### Stage L future tests

Future implementation must cover：

- Decimal-only raw report。
- deterministic `report_id`。
- `source_report_hash`。
- status mapping。
- duplicate same canonical。
- conflict different canonical。
- `raw_payload` excluded。
- replay deterministic。
- no `OMSService.apply_order_event(...)`。
- no Trade / Position / Accounting mutation。
- no Broker / CTP / SimNow dependency。

### Stage L explicit non-goals

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

### feature_snapshots

Stage H 已新增 `feature_snapshots` 表作为 FeatureSnapshot derived facts ledger。

字段：

- `id`
- `symbol`
- `instrument_id`
- `trade_instrument_id`
- `exchange`
- `trading_day`
- `timeframe`
- `bar_ts`
- `feature_version`
- `feature_config_hash`
- `source_bar_keys`
- `returns`
- `bar_return`
- `price_range`
- `range`
- `atr`
- `volume_ratio`
- `moving_average`
- `bias`
- `breakout_level`
- `volatility`
- `momentum`
- `source_window_start`
- `source_window_end`
- `warmup_complete`
- `quality_status`
- `missing_bar_count`
- `gap_count`
- `raw_payload`
- `calculated_at`
- `received_at`

约束和索引：

- `UNIQUE(exchange, instrument_id, timeframe, bar_ts, feature_version, feature_config_hash)`，名称为 `uq_feature_snapshots_identity`
- `exchange` 索引
- `instrument_id` 索引
- `trading_day` 索引
- `timeframe` 索引
- `bar_ts` 索引
- `feature_version` 索引
- `feature_config_hash` 索引
- `(exchange, instrument_id, trading_day)` 复合索引

Canonical payload 字段为 identity、`feature_version`、`feature_config_hash`、`source_bar_keys`、全部 feature values、`source_window_start`、`source_window_end`、`warmup_complete`、`quality_status`、`missing_bar_count` 和 `gap_count`。`raw_payload`、`calculated_at`、`received_at` 和 database id 不参与 canonical equality。

### Runtime boundary

- Kafka / Redis 未来只能作为 transport / cache。
- DB 仍是 persisted market facts 的 source-of-truth。
- Redis 不能作为 source-of-truth。
- Kafka 不能替代 DB facts。
- FastAPI / Celery 不属于 Market Data Core。

### Implementation tests

Stage G tests 覆盖：

- Tick Decimal validation。
- Bar OHLC validation。
- missing identity reject。
- bad timestamp reject。
- out-of-session reject。
- duplicate same canonical。
- duplicate different canonical conflict / `ERROR`。
- `raw_payload` diagnostic only。
- non-monotonic reject。
- gap detection。
- bar idempotency。
- replay deterministic。
- no OMS / Risk / Execution / Accounting mutation。

### Explicit non-goals

Stage G 不实现：

- Strategy。
- Signal。
- Feature indicators。
- Broker adapter。
- CTP / SimNow。
- Kafka ingestion。
- FastAPI service。
- live market feed。
- paper / sim / live。
- accounting mutation。
- risk direct market lookup。

## 当前接口边界

- `MarketDataMock.latest_price(instrument_id: str) -> Decimal`：Mock 行情价格查询。
- `StrategyEngine.on_market_data(...) -> list[Signal]`：策略代码只能输出信号。
- `FuturesRiskEngine.check_order(signal: Signal) -> RiskResult`：pure Risk 风控计算边界；OMS 不调用该接口。
- `RiskEvaluator.evaluate(context: TradingWorkflowContext) -> TradingRiskResult`：Stage J trading workflow 风控评价端口；`TradingWorkflowService` 只依赖该 Protocol，不依赖 concrete RiskEngine。
- `TradingWorkflowService.run(context: TradingWorkflowContext) -> TradingWorkflowResult`：Stage J workflow application service；持久化 `TradingRiskResult`，仅 `ACCEPT` / `REDUCE` 生成并持久化 `OrderIntent`；不调用 OMS / Execution / Broker。
- `TradingWorkflowReplay.replay(contexts: Iterable[TradingWorkflowContext]) -> list[TradingWorkflowResult]`：Stage J deterministic replay；使用同一 service path，不调用 OMS / Execution / Accounting。
- `OMSBridgeService.build_order_request(context: OMSBridgeContext) -> OrderRequest`：Stage J.2 bridge mapping；只消费 `OrderIntent` lineage 和 typed account/order config。
- `OMSBridgeService.create_order(context: OMSBridgeContext) -> OMSBridgeResult`：Stage J.2 bridge boundary；通过 `OMSOrderCreator` Protocol 调用 `OMSService.create_order`，不得调用 Execution / Broker，不得 rerun Risk。
- `replay_oms_bridge(contexts: Iterable[OMSBridgeContext], *, dry_run: bool = True, allow_live_oms: bool = False) -> list[OMSBridgeReplayPreview] | list[OMSBridgeResult]`：Stage J.2 replay boundary；默认 dry-run，不调用 OMS / Execution / Broker / Accounting。
- `ExecutionGatewayService.build_command(order: OrderState, *, execution_target: ExecutionTarget, command_type: ExecutionCommandType, symbol: str, trade_instrument_id: str, tif: str) -> ExecutionCommand`：Stage K gateway command builder；只消费 OMS Order / typed execution config identity。
- `ExecutionGatewayService.submit(order: OrderState, *, symbol: str, trade_instrument_id: str, tif: str, execution_target: ExecutionTarget = MOCK, command_type: ExecutionCommandType = SUBMIT_ORDER, dry_run: bool = False) -> ExecutionGatewayResult`：Stage K submit boundary；先 append `ExecutionCommand`，再 dispatch 到 allowed adapter only when new command and not dry-run；不得直接 mutate OMS / Accounting。
- `ExecutionCommandRepository.append_execution_command(command: ExecutionCommand) -> ExecutionCommand`：按 `command_id` 幂等 append；same canonical duplicate no-op，different canonical conflict。
- `ExecutionCommandRepository.get_by_command_id(command_id: str) -> ExecutionCommand | None`：按 command identity 查询。
- `ExecutionCommandRepository.list_by_order_id(order_id: str) -> list[ExecutionCommand]`：按 OMS order 查询 commands。
- `ExecutionCommandRepository.list_by_target(execution_target: ExecutionTarget, start_ts: datetime, end_ts: datetime) -> list[ExecutionCommand]`：按 target 和时间范围查询 commands。
- `ExecutionAdapter.submit(command: ExecutionCommand) -> ExecutionCommandResult`：Stage K execution adapter Protocol；返回 typed result，不返回 raw broker response 作为事实。
- `replay_execution_gateway(service: ExecutionGatewayService, orders: Iterable[OrderState], *, execution_target: ExecutionTarget = MOCK, symbol: str, trade_instrument_id: str, tif: str, dry_run: bool = True, allow_submit: bool = False) -> list[ExecutionGatewayResult]`：Stage K replay boundary；默认 dry-run，不提交 adapter / broker，不修改 OMS / Accounting。
- `OMS.create_order(request: OrderRequest, *, client_order_id: str) -> OrderState`：创建或幂等返回 OMS 订单。
- `OMS.apply_risk_result(order_id: str, risk_result: RiskResult, *, external_event_id: str, occurred_at: datetime | None = None) -> OrderEventApplicationResult`：消费外部 `RiskResult` 推进风控状态，不计算风控。
- `OMS.apply_order_event(event: OrderEvent) -> OrderEventApplicationResult`：订单状态变化通过 OMS 事件处理。
- `OMS.recover_order(order_id: str) -> OrderEventApplicationResult`：基于 `orders + order_events` 对单笔订单恢复。
- `OMS.get_by_client_order_id(client_order_id: str) -> OrderState | None`：客户端订单幂等查询。
- `EMS.submit(order: OrderState) -> None`：执行提交边界。
- `EMS.cancel(order: OrderState) -> None`：执行撤单边界。
- `MockFuturesExchange.submit_limit_order(order: OrderState) -> None`：仅限 Mock 的订单提交。
- `MockFuturesExchange.cancel_order(order: OrderState) -> None`：仅限 Mock 的撤单。
- 当前 `MockFuturesExchange` Protocol 只冻结 submit / cancel command port，返回 `None`；它不承载 report surface，不表示 exchange report 已产生或已消费。
- Phase 4 可实现的 `MockFuturesExchange` 当前不包含 settlement 方法；每日结算属于后续 Settlement 阶段，不得挂在 Execution skeleton 上。
- 移除 `MockFuturesExchange.run_daily_settlement(trading_day)` 是 intentional interface migration；Future Settlement Protocol 必须在后续 Settlement 阶段另行定义。
- `TradeProcessor.apply_trade(trade: Trade) -> bool`：成交应用，返回是否实际应用。
- `PositionManager.apply_trade(trade: Trade) -> PositionApplicationResult`：Stage C 成交更新持仓的 application service 入口；只消费 `Trade`。
- `PositionManager.replay_trades(trades: Sequence[Trade]) -> PositionReplayResult`：如 Stage C 实现 replay runner，则按冻结排序逐笔应用 Trade；已应用 trade no-op。
- `MarginEngine`：Stage D 保证金计算边界；消费 Position、MarginRule、AccountContext 和 typed price input，返回 typed MarginResult，不消费订单状态或 raw payload。
- `PnLEngine.mark_to_market(account_id: str) -> Decimal`：盯市计算边界。
- `SettlementEngine.settle(account_id: str, trading_day: str) -> None`：结算边界。

`TradeProcessor`、`FuturesPositionManager`、`MarginEngine`、`PnLEngine` 和 `SettlementEngine` 是全局后续阶段接口，不属于 Phase 4.0 / Phase 4.1 status-only execution mapper。Phase 4.1 不实现、不调用、不测试这些接口，不更新 Trade / Position / Margin / PnL / Settlement。真实 fill / trade / position / margin / pnl / settlement 必须另开阶段。

Stage B 冻结 `TradeRepository`：

- `create_or_get_trade(trade: Trade) -> Trade`：按 `account_id + exchange + exchange_trade_id` 幂等写入或返回 existing。
- `get_by_exchange_trade_id(account_id: str, exchange: str, exchange_trade_id: str) -> Trade | None`：按交易所成交身份查询。
- 重复键且 canonical payload 一致时返回 existing，不重复入账。
- 重复键但 `order_id`、`instrument_id`、`direction`、`offset`、`price`、`quantity`、`trade_time`、fee 或 source report 不一致时抛 `TradeIdempotencyConflictError`。
- Repository 不更新 Position，不修改 OMS，不应用 `OrderEvent`，不调用 Risk、Execution 或 Runtime。
- UnitOfWork 在 Stage B 需要暴露 `trades: TradeRepository`，但不把 `trades` 写入 OMSService 的职责边界。

Stage C 冻结 `PositionRepository`：

- `get_by_account_instrument(account_id: str, instrument_id: str) -> Position | None`：按 live position 身份查询。
- `create_or_get_position(account_id: str, instrument_id: str) -> Position`：创建或返回当前 live projection。
- `update_position(position: Position, expected_version: int | None = None) -> Position`：更新 live projection，并在提供 `expected_version` 时执行乐观并发检查。
- `list_by_account(account_id: str) -> list[Position]`：列出账户当前持仓。
- Repository 不读取 `OrderStatus`、`OrderEvent`、`ExchangeReport` 或 `raw_payload` 推导持仓，不更新 OMS，不调用 Risk、Execution、Broker 或 Runtime。

Stage C 冻结 `PositionEventRepository`：

- `append_position_event(event: PositionEvent) -> PositionEvent`：追加 applied-trade audit event。
- `get_by_trade_key(account_id: str, exchange: str, exchange_trade_id: str) -> PositionEvent | None`：按 Trade identity 查询是否已应用。
- `list_by_position(account_id: str, instrument_id: str) -> list[PositionEvent]`：列出单合约持仓事件。
- `list_by_account(account_id: str) -> list[PositionEvent]`：列出账户持仓事件。

Stage C `UnitOfWork` 需要暴露 `positions: PositionRepository` 和 `position_events: PositionEventRepository`。同一 Trade 首次应用时，`positions` update 与 `position_events` append 必须在同一 UoW 内完成。

Stage D 冻结 `MarginSnapshotRepository`：

- `append_margin_snapshot(snapshot: MarginSnapshot) -> MarginSnapshot`：追加 margin audit snapshot；同一 `account_id + instrument_id + position_version` 已存在时，除 `calculation_key` 外经济事实一致返回 existing，经济事实不一致抛 `MarginSnapshotConflictError`。
- `get_latest(account_id: str, instrument_id: str) -> MarginSnapshot | None`：查询单合约最新 margin snapshot。
- `list_by_account(account_id: str) -> list[MarginSnapshot]`：列出账户 margin snapshots。
- `get_by_position_version(account_id: str, instrument_id: str, position_version: int) -> MarginSnapshot | None`：按 position version 查询 snapshot。

Stage D `UnitOfWork` 需要暴露 `margin_snapshots: MarginSnapshotRepository`。首次写入某次 margin projection 时，`MarginSnapshot` append 与 `positions.margin_used` update 必须在同一 UoW 内完成。

Stage E 冻结 `PnLSnapshotRepository`：

- `append_pnl_snapshot(snapshot: PnLSnapshot) -> PnLSnapshot`：追加 PnL audit snapshot。
- `get_latest(account_id: str, instrument_id: str) -> PnLSnapshot | None`：查询单合约最新 PnL snapshot。
- `list_by_account(account_id: str) -> list[PnLSnapshot]`：列出账户 PnL snapshots。
- `get_by_calculation_key(account_id: str, instrument_id: str, calculation_key: str) -> PnLSnapshot | None`：按 deterministic calculation identity 查询 snapshot。
- `get_by_position_version(account_id: str, instrument_id: str, position_version: int) -> PnLSnapshot | None`：按 position version 查询 snapshot。

Repository behavior：

- Same canonical payload 时返回 existing / no-op。
- Different canonical payload 时抛 `PnLSnapshotConflictError`。
- 同一 `account_id + instrument_id + position_version` 不得写入第二条不同 PnL fact；除 `calculation_key` 外经济事实一致时返回 existing，经济事实不一致时抛 `PnLSnapshotConflictError`。
- 不裸露 `IntegrityError`。

Stage E `UnitOfWork` 需要暴露 `pnl_snapshots: PnLSnapshotRepository`。首次写入某次 PnL projection 时，`PnLSnapshot` append 与 `positions.realized_pnl` / `positions.unrealized_pnl` update 必须在同一 UoW 内完成。Position PnL update 必须通过 pnl-only repository method，不得复用会写 qty / avg price / margin / settlement fields 的通用 update。

Stage F 冻结 `SettlementSnapshotRepository`：

- `append_settlement_snapshot(snapshot: SettlementSnapshot) -> SettlementSnapshot`：追加 settlement final snapshot。
- `get_by_account_trading_day(account_id: str, trading_day: date) -> SettlementSnapshot | None`：按 one-final-fact identity 查询。
- `get_by_calculation_key(account_id: str, trading_day: date, calculation_key: str) -> SettlementSnapshot | None`：按 deterministic calculation identity 查询。
- `list_by_account(account_id: str) -> list[SettlementSnapshot]`：列出账户 settlement snapshots。
- `list_by_trading_day(trading_day: date) -> list[SettlementSnapshot]`：列出交易日 settlement snapshots。

Repository behavior：

- Same canonical payload 时返回 existing / `DUPLICATE` no-op。
- Different canonical payload 时返回 `CONFLICT` 或抛 typed settlement conflict error。
- 不裸露 `IntegrityError`。

Stage F `UnitOfWork` 需要暴露 `settlement_snapshots: SettlementSnapshotRepository`，并需要 account snapshot write/read port。成功 settlement 时，`SettlementSnapshot` append、account after snapshot 创建 / 更新、`positions` settlement roll 必须在同一 UoW 内完成。Position roll 必须通过 settlement-only repository method，不得复用会写 avg / PnL / margin fields 的通用 update。

Stage C `PositionApplicationStatus` 冻结为：

- `APPLIED`：Trade 首次应用，position 已更新并写入 PositionEvent。
- `DUPLICATE_IGNORED`：同一 Trade identity 已应用且 canonical payload 一致，本次 no-op。
- `REJECTED_INSUFFICIENT_POSITION`：平仓数量超过对应 today/yesterday bucket，position 不变。
- `CONFLICT`：同一 Trade identity 已存在但 canonical payload 不一致，或 replay divergence。
- `ERROR`：unsupported offset、非法方向、Decimal contract 失败或其他 typed error。

Stage C 不 import OMS / Risk / Execution mapper / Broker / Runtime，不写 Margin / PnL / Settlement，不更新 Order。

Stage C replay contract：

- Full replay 可以从 ordered `Trade` ledger 重建 `positions`。
- Incremental replay 逐笔调用 `apply_trade`；已应用 Trade 返回 `DUPLICATE_IGNORED`，不重复修改 position。
- Trade ordering 使用 `trade_time`，稳定 secondary key 使用 `id` 或 `exchange_trade_id`。
- Replay divergence 不能静默覆盖 live projection，必须返回 typed conflict/report。
- 只靠 `positions` snapshot 不能作为 replay idempotency 依据。

Stage C testing matrix：

- OPEN LONG。
- OPEN SHORT。
- CLOSE TODAY LONG。
- CLOSE YESTERDAY LONG。
- CLOSE TODAY SHORT。
- CLOSE YESTERDAY SHORT。
- Partial close。
- Insufficient today bucket。
- Insufficient yesterday bucket。
- Duplicate trade no-op。
- Duplicate trade conflict。
- Replay deterministic。
- Position event unique trade key。
- DB round trip。
- UoW exposes `positions` / `position_events`。
- No OMS / Risk / Execution mapper / Broker / Runtime import。
- No Margin / PnL / Settlement mutation。

Stage D testing matrix：

- Long margin。
- Short margin。
- Mixed margin。
- Today + yesterday qty。
- Contract multiplier。
- Initial vs maintenance margin。
- Insufficient cash typed result。
- Missing rule typed result。
- Missing price typed result。
- Decimal-only。
- Snapshot persistence。
- Replay deterministic。
- Replay divergence。
- `positions.margin_used` update boundary and rollback。
- Canonical duplicate snapshot no-op。
- Canonical conflict。
- No PnL / Settlement mutation。
- No `OrderStatus` / `OrderEvent` / `ExchangeReport` / `raw_payload` consumption。

Stage E testing matrix：

- Long close realized PnL。
- Short close realized PnL。
- Open trade no realized PnL。
- Fee known。
- Fee zero。
- Fee unknown。
- Long unrealized PnL。
- Short unrealized PnL。
- Mixed unrealized PnL。
- LAST_PRICE / SETTLEMENT_PRICE / MANUAL。
- Missing price typed result。
- Missing multiplier typed result。
- Decimal-only。
- Pre-close position required。
- Snapshot persistence。
- Duplicate no-op。
- Canonical conflict。
- Replay deterministic。
- Position PnL update boundary and rollback。
- Fee unknown rejected for persistent projection。
- Same position version duplicate PnL fact guard。
- No Margin mutation。
- No Settlement mutation。
- No `OrderStatus` / `OrderEvent` / `ExchangeReport` / `raw_payload` consumption。

Stage F testing matrix：

- Domain Decimal validation。
- Non-trading day returns `REJECTED_NON_TRADING_DAY`。
- Missing position returns `REJECTED_MISSING_POSITION`。
- Missing PnL returns `REJECTED_MISSING_PNL`。
- Missing Margin returns `REJECTED_MISSING_MARGIN`。
- Missing settlement price returns `REJECTED_MISSING_SETTLEMENT_PRICE`。
- Frozen qty returns `REJECTED_FROZEN_POSITION`。
- Rejected result no persistence。
- Today -> yesterday roll。
- Avg price unchanged。
- `realized_pnl` / `unrealized_pnl` not recalculated。
- `margin_used` not recalculated。
- PnL snapshots not mutated。
- Margin snapshots not mutated。
- Account after formula。
- SettlementSnapshot append and DB round trip。
- Duplicate same canonical no-op / `DUPLICATE`。
- Same account/day different canonical `CONFLICT`。
- Replay same canonical no-op / `DUPLICATE`。
- Replay live position divergence `CONFLICT`。
- Replay live account divergence `CONFLICT`。
- Settlement-only position update boundary。
- Schema unique `(account_id, trading_day)`。
- No OMS / Risk / Execution / Broker / Runtime import。
- No `OrderStatus` / `OrderEvent` / `ExchangeReport` / `raw_payload` consumption。

本阶段任何接口都不得连接真实期货柜台、CTP、SimNow 或真实交易网关。

## 当前数据库契约

类型化 source-of-truth 数值字段使用 SQL `NUMERIC(28, 8)`，并映射为 Python `Decimal`。

快照 JSON 字段，例如 `settlement_snapshots.settlement_prices`，用于快照 payload，不是 live source-of-truth 数值字段。JSON payload 不得作为交易主链 source-of-truth。

### instruments

字段：

- `id`
- `instrument_id`
- `product_id`
- `exchange`
- `multiplier`
- `price_tick`
- `upper_limit_price`
- `lower_limit_price`
- `margin_rate`
- `delivery_month`
- `is_disabled`
- `created_at`
- `updated_at`

约束和索引：

- `UNIQUE(instrument_id)`
- `product_id` 索引
- `exchange` 索引

### trading_calendars

字段：

- `id`
- `exchange`
- `trading_day`
- `is_trading_day`
- `night_session_trading_day`
- `note`

约束：

- `UNIQUE(exchange, trading_day)`，名称为 `uq_calendar_exchange_day`

### trading_sessions

字段：

- `id`
- `exchange`
- `product_id`
- `instrument_id`
- `session_name`
- `start_time`
- `end_time`
- `is_night`
- `effective_from`
- `effective_to`

索引：

- `exchange` 索引
- `product_id` 索引
- `instrument_id` 索引

### orders

字段：

- `id`
- `client_order_id`
- `account_id`
- `instrument_id`
- `exchange`
- `direction`
- `offset`
- `order_type`
- `limit_price`
- `quantity`
- `filled_quantity`
- `status`
- `reject_reason`
- `version`
- `created_at`
- `updated_at`

约束和索引：

- `UNIQUE(client_order_id)`
- `account_id` 索引
- `instrument_id` 索引
- `exchange` 索引
- `version` 是 OMS Repository 状态更新的乐观并发版本字段，当前默认值为 `0`，不得用于表达业务订单状态、事件序号或交易所版本。

### order_events

字段：

- `id`
- `order_id`
- `previous_status`
- `new_status`
- `event_source`
- `external_event_id`
- `raw_payload`
- `occurred_at`
- `created_at`

约束和索引：

- `UNIQUE(event_source, external_event_id)`，名称为 `uq_order_events_source_external`
- `order_id, created_at` 索引，名称为 `ix_order_events_order_id_created_at`
- `order_id` references `orders.id`

`raw_payload` 是诊断 payload。凡是订单状态事实来源需要的字段，都必须有类型化列承载，不得只存在于 `raw_payload`。
`occurred_at` 是业务事件发生时间，`created_at` 是本地入库时间，二者不得混用。

### trades

字段：

- `id`
- `account_id`
- `exchange`
- `exchange_trade_id`
- `order_id`
- `instrument_id`
- `direction`
- `offset`
- `price`
- `quantity`
- `trade_time`
- `created_at`

约束和索引：

- `UNIQUE(account_id, exchange, exchange_trade_id)`，名称为 `uq_trades_account_exchange_trade`
- `account_id` 索引
- `instrument_id` 索引
- `order_id` references `orders.id`

当前代码中的 `trades` 表已包含基础字段、Stage B fee / lineage / diagnostic 字段，以及 `UNIQUE(account_id, exchange, exchange_trade_id)`。

Stage B implemented fields：

- `fee_amount`
- `fee_currency`
- `fee_source`
- `trading_day`
- `source_exchange_report_id`
- `raw_payload`

Fee 语义：

- `fee_amount is None` 表示未知。
- `fee_amount == Decimal("0")` 表示明确为零。
- `fee_currency` 在 `fee_amount is not None` 时必填。
- `fee_source` 表示 fee 的事实来源，例如 `EXCHANGE_REPORT`、`BROKER_QUERY`、`SETTLEMENT`。
- Stage B 不计算 PnL。

### positions

字段：

- `id`
- `account_id`
- `instrument_id`
- `long_today_qty`
- `long_yesterday_qty`
- `short_today_qty`
- `short_yesterday_qty`
- `frozen_long_qty`
- `frozen_short_qty`
- `long_avg_price`
- `short_avg_price`
- `settlement_price`
- `last_price`
- `realized_pnl`
- `unrealized_pnl`
- `margin_used`
- `created_at`
- `updated_at`

约束和索引：

- `UNIQUE(account_id, instrument_id)`，名称为 `uq_positions_account_inst`
- `account_id` 索引
- `instrument_id` 索引

Stage C implemented migration：

- `positions.version INTEGER NOT NULL DEFAULT 0`
- `version` 用于 optimistic update 和 replay divergence 检查。
- Stage C migration 不新增 margin / pnl / settlement 表，不改变 `orders` / `order_events` / `trades` 语义。

### position_events

Stage C 已新增 `position_events` 表作为 idempotency + replay audit ledger。

字段：

- `id`
- `account_id`
- `instrument_id`
- `exchange`
- `exchange_trade_id`
- `trade_id`
- `position_id`
- `direction`
- `offset`
- `price`
- `quantity`
- `before_snapshot`
- `after_snapshot`
- `event_type`
- `occurred_at`
- `created_at`
- `raw_payload`

约束和索引：

- `UNIQUE(account_id, exchange, exchange_trade_id)`
- `position_id` references `positions.id`
- `trade_id` references `trades.id`
- `account_id` 索引
- `instrument_id` 索引
- `(account_id, instrument_id)` 复合索引
- `trade_id` 索引
- `exchange_trade_id` 索引

`before_snapshot` / `after_snapshot` 用于 replay audit，不替代 live `positions` source-of-truth。`raw_payload` 只诊断，不参与 position canonical payload 或 replay conflict 判定。

### margin_snapshots

Stage D 已新增 `margin_snapshots` 表作为 margin audit / replay ledger。本阶段不新增 `margin_rules` 表；`MarginRule` typed input 由 application layer 注入，`margin_snapshots` 记录 `rule_id` / `rule_version`。

字段：

- `id`
- `account_id`
- `instrument_id`
- `position_version`
- `rule_id`
- `rule_version`
- `calculation_key`
- `long_qty`
- `short_qty`
- `price`
- `contract_multiplier`
- `initial_margin`
- `maintenance_margin`
- `margin_used`
- `available_cash`
- `equity`
- `calculated_at`

约束和索引：

- `account_id` 索引
- `instrument_id` 索引
- `(account_id, instrument_id)` 复合索引
- `position_version` 索引
- `(account_id, instrument_id, position_version)` 复合索引
- `UNIQUE(account_id, instrument_id, calculation_key)`

Migration 范围只新增 `margin_snapshots` table，不新增 pnl table，不新增 settlement table，不新增 `margin_events`，不改变 `orders` / `order_events` / `trades` 事实语义。

`margin_snapshots` canonical payload 字段为 `account_id`、`instrument_id`、`position_version`、`rule_id`、`rule_version`、`long_qty`、`short_qty`、`price`、`contract_multiplier`、`initial_margin`、`maintenance_margin`、`margin_used`、`available_cash`、`equity`、`calculation_key`。`calculated_at` 不参与 canonical equality；`raw_payload` 不参与 canonical；same canonical no-op / duplicate accepted；different canonical 返回 `CONFLICT` / divergence，不静默覆盖历史 snapshot。同一 `account_id + instrument_id + position_version` 不得写入第二条不同 Margin fact；除 `calculation_key` 外经济事实一致时返回 existing，经济事实不一致时 conflict。

### pnl_snapshots

Stage E 已新增 `pnl_snapshots` 表作为 PnL audit / replay ledger。本阶段不新增 settlement table、broker reconciliation table 或 risk table；不改变 Stage B `trades` schema，不改变 `orders` / `order_events` 事实语义。

字段：

- `id`
- `account_id`
- `instrument_id`
- `position_version`
- `trade_id`
- `margin_snapshot_id`
- `calculation_key`
- `price_basis`
- `mark_price`
- `contract_multiplier`
- `realized_pnl`
- `unrealized_pnl`
- `total_pnl`
- `fee_amount`
- `calculated_at`
- `created_at`

约束和索引：

- `account_id` 索引
- `instrument_id` 索引
- `(account_id, instrument_id)` 复合索引
- `position_version` 索引
- `trade_id` 索引
- `calculation_key` 索引
- `UNIQUE(account_id, instrument_id, calculation_key)`

Migration 范围只新增 `pnl_snapshots` table，不新增 settlement table，不新增 broker reconciliation table，不新增 risk table，不改变 `orders` / `order_events` / `trades` 事实语义。

`pnl_snapshots` canonical payload 字段为 `account_id`、`instrument_id`、`position_version`、`trade_id`、`margin_snapshot_id`、`calculation_key`、`price_basis`、`mark_price`、`contract_multiplier`、`realized_pnl`、`unrealized_pnl`、`total_pnl`、`fee_amount`。`calculated_at` 不参与 canonical equality；`raw_payload` 不允许进入 PnL facts；same canonical no-op / duplicate accepted；different canonical 返回 `CONFLICT` / divergence，不静默覆盖历史 snapshot。同一 `account_id + instrument_id + position_version` 不得写入第二条不同 PnL fact；除 `calculation_key` 外经济事实一致时返回 existing，经济事实不一致时 conflict。

### account_snapshots

字段：

- `id`
- `account_id`
- `equity`
- `available_cash`
- `margin_used`
- `frozen_margin`
- `realized_pnl`
- `unrealized_pnl`
- `snapshot_time`

索引：

- `account_id` 索引

快照不是 live source of truth。

### settlement_snapshots

Existing `settlement_snapshots` table is insufficient for Stage F. Stage F migration must extend or replace it without breaking existing history.

字段：

- `id`
- `account_id`
- `trading_day`
- `calculation_key`
- `positions_before`
- `positions_after`
- `settlement_prices`
- `pnl_snapshot_ids`
- `margin_snapshot_ids`
- `account_snapshot_before_id`
- `account_snapshot_after_id`
- `cash_before`
- `cash_after`
- `realized_pnl`
- `unrealized_pnl`
- `margin_used`
- `status`
- `reason`
- `created_at`

约束和索引：

- `UNIQUE(account_id, trading_day)`
- `account_id` 索引
- `trading_day` 索引
- `(account_id, trading_day)` 复合索引
- `calculation_key` 索引

同一 `account_id + trading_day` 只能有一个 final settlement fact。`calculation_key` 参与 canonical payload，但不得允许同一账户同一交易日写入多个 final settlement facts。

Stage F migration 不新增 `settlement_events`、broker reconciliation table 或 risk table，不改变 Stage B / C / D / E facts schema。如历史兼容要求保留 `raw_payload` column，该字段只能作为非事实诊断字段，不参与 canonical payload，不承载缺失的 typed source-of-truth 字段。

### market_ticks

Stage G 已新增 `market_ticks` 表作为 Tick market facts ledger。

字段：

- `id`
- `symbol`
- `instrument_id`
- `trade_instrument_id`
- `exchange`
- `trading_day`
- `ts`
- `price`
- `volume`
- `turnover`
- `open_interest`
- `bid_price_1`
- `ask_price_1`
- `bid_volume_1`
- `ask_volume_1`
- `source`
- `raw_payload`
- `received_at`

约束和索引：

- `UNIQUE(exchange, instrument_id, ts, source)`，名称为 `uq_market_ticks_identity`
- `exchange` 索引
- `instrument_id` 索引
- `trading_day` 索引
- `ts` 索引
- `(exchange, instrument_id, trading_day)` 复合索引

Canonical payload 字段为 `exchange`、`instrument_id`、`trade_instrument_id`、`symbol`、`trading_day`、`ts`、`price`、`volume`、`turnover`、`open_interest`、`bid_price_1`、`ask_price_1`、`bid_volume_1`、`ask_volume_1`、`source`。`raw_payload` 和 `received_at` 不参与 canonical equality。

### market_bars

Stage G 已新增 `market_bars` 表作为 Bar market facts ledger。

字段：

- `id`
- `symbol`
- `instrument_id`
- `trade_instrument_id`
- `exchange`
- `trading_day`
- `timeframe`
- `bar_ts`
- `open`
- `high`
- `low`
- `close`
- `volume`
- `turnover`
- `open_interest`
- `source`
- `quality_status`
- `raw_payload`
- `received_at`

约束和索引：

- `UNIQUE(exchange, instrument_id, timeframe, bar_ts, source)`，名称为 `uq_market_bars_identity`
- `exchange` 索引
- `instrument_id` 索引
- `trading_day` 索引
- `bar_ts` 索引
- `timeframe` 索引
- `(exchange, instrument_id, trading_day)` 复合索引

Canonical payload 字段为 `exchange`、`instrument_id`、`trade_instrument_id`、`symbol`、`trading_day`、`timeframe`、`bar_ts`、`open`、`high`、`low`、`close`、`volume`、`turnover`、`open_interest`、`source`、`quality_status`。`raw_payload` 和 `received_at` 不参与 canonical equality。

### risk_results

Stage J 已新增 `risk_results` 表作为 `TradingRiskResult` persisted facts ledger。

字段：

- `id`
- `risk_result_id`
- `signal_id`
- `evaluation_context_hash`
- `risk_status`
- `risk_reason`
- `risk_level`
- `requested_quantity`
- `approved_quantity`
- `max_quantity`
- `expected_margin`
- `expected_notional`
- `config_hash`
- `evaluation_ts`
- `raw_payload`
- `created_at`

约束和索引：

- `UNIQUE(risk_result_id)`，名称为 `uq_risk_results_risk_result_id`
- `signal_id` 索引

Canonical payload 字段为 `signal_id`、`evaluation_context_hash`、`risk_status`、`risk_reason`、`risk_level`、`requested_quantity`、`approved_quantity`、`max_quantity`、`expected_margin`、`expected_notional` 和 `config_hash`。`risk_result_id` 是该 canonical payload 的 deterministic identity；`raw_payload`、`created_at`、`received_at`、DB id 和非 deterministic `evaluation_ts` 不参与 canonical equality。

### order_intents

Stage J 已新增 `order_intents` 表作为 `OrderIntent` persisted facts ledger。`order_intents` 不写 `orders`，不替代 OMS `OrderState`，不表达 OMS state。

字段：

- `id`
- `intent_id`
- `signal_id`
- `risk_result_id`
- `strategy_name`
- `strategy_version`
- `strategy_config_hash`
- `runtime_id`
- `symbol`
- `instrument_id`
- `trade_instrument_id`
- `exchange`
- `trading_day`
- `timeframe`
- `bar_ts`
- `feature_version`
- `feature_config_hash`
- `side`
- `offset`
- `quantity`
- `price`
- `order_type`
- `tif`
- `expected_margin`
- `expected_notional`
- `intent_reason`
- `raw_payload`
- `created_at`

约束和索引：

- `UNIQUE(intent_id)`，名称为 `uq_order_intents_intent_id`
- `signal_id` 索引
- `risk_result_id` 索引
- `instrument_id` 索引
- `trading_day` 索引

Canonical payload 字段为 `signal_id`、`risk_result_id`、strategy identity、instrument identity、`side`、`offset`、`quantity`、`price`、`order_type`、`tif`、`expected_margin`、`expected_notional` 和 `intent_reason`。`intent_id` 是该 canonical payload 的 deterministic identity；`raw_payload`、`created_at`、`received_at` 和 DB id 不参与 canonical equality。

### execution_commands

Stage K 已新增 `execution_commands` table 作为 `ExecutionCommand` persisted facts / audit ledger。`execution_commands` 不写 `orders` / `order_events`，不替代 OMS `OrderState`，不表达 exchange acceptance / fill / trade。

字段：

- `id`
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

约束和索引：

- `UNIQUE(command_id)`
- `order_id` 索引
- `client_order_id` 索引
- `execution_target` 索引
- `created_at` 索引

Canonical payload 字段为 `order_id`、`client_order_id`、`account_id`、instrument identity、`side`、`offset`、`quantity`、`price`、`order_type`、`tif`、`command_type` 和 `execution_target`。`command_id` 必须 deterministic from `order_id + command_type + execution_target`；`command_payload_hash` 是 canonical payload hash。`raw_payload`、`created_at`、`received_at`、broker response 和 DB id 不参与 canonical equality。

Idempotency：same `command_id` + same canonical -> duplicate / no-op；same `command_id` + different canonical -> conflict / error。同一 OMS order 不得为同一 target 生成多个 submit commands。

### risk_events

字段：

- `id`
- `rule_name`
- `passed`
- `reason`
- `signal_id`
- `order_id`
- `raw_payload`
- `created_at`

索引和外键：

- `rule_name` 索引
- `signal_id` 索引
- `order_id` references `orders.id`

## Environment Validation

环境验证不是 pytest 核心契约测试。

运行：

```bash
uv run which python
uv run python --version
```

预期：

- `uv run which python` 指向 `<project-root>/.venv/bin/python`。
- `uv run python --version` 是 Python 3.12.x。

只有后续新增 `scripts/check_env.py` 后，才可以使用 `uv run python scripts/check_env.py`。当前仓库没有定义 `scripts/check_env.py`。

## Core Contract Tests

运行：

```bash
uv run pytest
```

当前 `order_events` 测试必须验证当前 schema 和本文档一致，不得写死未来幂等规则。如果当前 schema 是 `UNIQUE(event_source, external_event_id)`，测试就验证该实现。

核心契约测试覆盖：

- 当前 schema 契约。
- Decimal 字段和禁止 float 规则。
- Signal 不能直接创建或表示订单。
- `client_order_id` 订单幂等。
- 当前 `order_events` 幂等规则。
- 成交按 `account_id + exchange + exchange_trade_id` 去重。
- 持仓按 `account_id + instrument_id` 单行建模。

只有尚未实现的 Mock Exchange 场景允许使用 `xfail`。

## Domain Freeze Consistency Review

每次 domain migration 都必须审查：

- 文档中的 enum 与 `domain/enums.py` 一致。
- 文档中的 model 字段与 `domain/models.py` 一致。
- 文档中的接口边界与 `interfaces/engines.py`、`interfaces/repositories.py` 一致。
- 文档中的 model 字段不得遗漏当前字段。
- 文档不得定义当前代码中不存在的字段。
- 未来字段只能出现在 Known Deviations 或 Future Migration 中。
- 数据库约束与 ORM 和 Alembic 一致。
- Known Deviations 不得写成当前事实。
- `DOMAIN_FREEZE.md` 只冻结当前事实，不得提前冻结未来设计。

## Static Checks

运行：

```bash
uv run ruff check .
uv run mypy src
```

## Known Deviations

- `domain/models.py` 当前使用 Pydantic `BaseModel`；长期目标是 dataclass-only Domain 字段。
- `domain/models.py` 当前使用 validator 做 Decimal/float 模型校验；长期目标是 Domain 字段定义中不包含 validator。
- `order_events` 当前幂等约束是 `UNIQUE(event_source, external_event_id)`。未来 migration 可以考虑 `UNIQUE(order_id, event_source, external_event_id)`，但这不是当前事实。

## Future Migration Candidates

以下不是当前代码字段，只能通过 domain migration 增加；迁移必须同步更新代码、必要的 ORM/Alembic、测试和本文档：

- `expected_price`

`symbol` 和 `trade_instrument_id` 已随 Stage G 进入 Market Data domain/schema；非 Market Data 事实如需新增这些字段仍必须另走 migration。
