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
- `symbol` 当前不是 Domain 字段。
- `trade_instrument_id` 当前不是 Domain 字段。
- 未来如果要分离 `symbol`、`instrument_id`、`trade_instrument_id`，必须通过 domain migration。在此之前，不得通过 `raw_payload` 或 JSON 字段偷带缺失的身份字段。

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

## 当前接口边界

- `MarketDataMock.latest_price(instrument_id: str) -> Decimal`：Mock 行情价格查询。
- `StrategyEngine.on_market_data(...) -> list[Signal]`：策略代码只能输出信号。
- `FuturesRiskEngine.check_order(signal: Signal) -> RiskResult`：pure Risk 风控计算边界；OMS 不调用该接口。
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
- `MarginEngine.margin_required(order: OrderRequest) -> Decimal`：保证金计算边界。
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

字段：

- `id`
- `trading_day`
- `account_id`
- `cash_before`
- `cash_after`
- `positions_before`
- `positions_after`
- `settlement_prices`
- `raw_payload`
- `created_at`

索引：

- `trading_day` 索引
- `account_id` 索引

快照不是 live source of truth。`raw_payload` 不得承载缺失的类型化 source-of-truth 字段。

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

以下不是当前冻结字段：

- `symbol`
- `trade_instrument_id`
- `expected_price`

它们只能通过 domain migration 增加；迁移必须同步更新代码、必要的 ORM/Alembic、测试和本文档。
