# Position Contract

本文档记录当前持仓主链契约。Stage L.4 只冻结 Trade-to-Position application contract；不写代码、不改 schema、不改 `src` / `tests`、不实现 Margin / PnL / Settlement / AccountSnapshot / Runtime。

## Stage L.4 Scope

Source-of-truth flow：

```text
typed Trade fact
-> Trade-to-Position application
-> PositionManager.apply_trade(...)
-> Position projection / PositionEvent
```

Stage L.4 只做 Position：

- 输入 typed `Trade` fact。
- 读取 current `Position` / `PositionSnapshot`。
- 使用 typed account identity、typed instrument identity、`trading_day` / calendar context 和 application context。
- 输出 updated `positions` live projection 和 `PositionEvent` audit。

Stage L.4 不做：

- Margin update。
- PnL update。
- Settlement update。
- AccountSnapshot update。
- Broker reconciliation。
- runtime scheduling。
- Kafka / FastAPI / Celery。
- trade correction / cancel flows，除非另开范围。
- cross-account netting。

## Source Of Truth

Position update 只能消费 typed `Trade` fact。

禁止输入：

- `raw_payload` as facts。
- `NormalizedExecutionReport` directly。
- `OrderEventCandidate` directly。
- OMS `OrderState` directly。
- `FeatureSnapshot`。
- `SignalDecision`。
- `TradingRiskResult`。
- `OrderIntent`。
- Broker state。
- Margin / PnL / Settlement。
- Account tables。
- Runtime / Kafka / Celery / FastAPI。

Trade 是唯一成交事实输入。不得从 report、order event、raw payload 或 broker state 直接推 Position。

## Required Gate

Position may update only if：

- Trade identity is stable。
- Trade has `account_id`。
- Trade has `instrument_id` / `trade_instrument_id` and `exchange`。
- Trade has side / `direction` and `offset`。
- Trade `price > 0`。
- Trade `quantity > 0`。
- Trade time / `trading_day` is available or derivable from typed field。
- Trade has not already been applied to Position。

Reject：

- duplicate already-applied trade with different canonical payload。
- missing identity。
- non-positive quantity。
- non-positive price。
- raw_payload-only facts。
- trade without stable source identity。

## Idempotency And Replay

Same `trade_id` / Trade identity：

- same canonical -> duplicate / no-op。
- different canonical -> conflict / error。

Position apply must be idempotent：

- same Trade applied twice must not double-count Position。
- different Trade with same identity but different canonical must conflict before mutation。

Replay：

- consumes ordered Trade facts。
- same trade sequence -> same Position projection。
- duplicate trade -> no-op。
- conflict -> stops and reports typed conflict。
- no Margin / PnL / Settlement update。
- no Accounting mutation。
- no OMS mutation。

## Position Effect Rules

Trade maps to Position as follows：

- BUY open -> increase long。
- SELL open -> increase short。
- SELL close -> reduce long。
- BUY close -> reduce short。

Existing `PositionManager` today/yesterday bucket semantics remain authoritative：

- `CLOSE_TODAY` reduces today bucket。
- `CLOSE_YESTERDAY` reduces yesterday bucket。
- generic `CLOSE` must be resolved by existing contract or typed rejected if ambiguous。

Frozen quantities must not be silently changed. Close more than available must typed reject or conflict; it must not create negative position or reverse the side.

Open trade updates avg price deterministically according to the existing weighted-average contract. Close trade does not rewrite remaining avg price unless a future PositionManager contract migration explicitly changes that behavior.

## PositionEvent Decision

Stage L.4 reuses existing Stage C `PositionEvent`; it does not create another position ledger.

`PositionEvent` must include：

- trade identity。
- `account_id`。
- instrument identity。
- previous position。
- new position。
- changed quantity。
- `event_type`。
- `occurred_at`。

`before_snapshot` / `after_snapshot` remain audit and replay proof. `raw_payload` is diagnostic-only and excluded from canonical equality.

## Repository And Schema Decision

Current schema is sufficient：

- `positions(account_id, instrument_id)` is the live projection。
- `position_events` is the applied-trade audit / idempotency ledger。
- `position_events` already has unique Trade identity via `UNIQUE(account_id, exchange, exchange_trade_id)`。
- `PositionRepository` and `PositionEventRepository` already exist。

No Stage L.4 migration is needed. Do not create a second position ledger. If a later implementation discovers that L.3 deterministic fallback identity cannot be represented by current `position_events.exchange_trade_id`, handle it as a separately scoped migration extending the existing event ledger.

## Accounting Boundary

Stage L.4 must not：

- call `MarginEngine`。
- call `PnLEngine`。
- call `SettlementEngine`。
- update account snapshots。
- update realized / unrealized PnL。
- calculate margin。

Position output becomes input for a later Accounting bridge.

## Future Implementation Tests

Future implementation must cover：

- open long。
- open short。
- close long。
- close short。
- duplicate same trade no-op。
- same trade identity different canonical conflict。
- close more than available reject。
- non-positive qty / price reject。
- missing identity reject。
- raw_payload excluded。
- replay deterministic。
- no Margin / PnL / Settlement mutation。
- no Accounting mutation。

## Stage L.5 Accounting Handoff

Stage L.5 freezes how Trade-applied Position / PositionEvent becomes accounting input. It does not change `PositionManager` and does not implement Margin, PnL, Settlement, Broker, Runtime, or live workflows.

Source-of-truth flow：

```text
Trade-applied Position / PositionEvent
-> Accounting input snapshot
-> MarginEngine
-> PnLEngine
-> MarginSnapshot / PnLSnapshot
-> SettlementEngine later
```

Allowed accounting inputs：

- typed Position / PositionEvent after Trade application。
- typed Trade facts when realized PnL needs close input。
- typed MarketDataSnapshot / settlement price / last price input。
- typed account config / margin config / pnl config。
- trading_day / calendar context。

Forbidden accounting inputs：

- `raw_payload` facts。
- Broker state。
- OMS `OrderState` directly。
- `NormalizedExecutionReport` directly。
- `OrderEventCandidate` directly。
- SignalDecision / Strategy output。
- Runtime scheduler。
- external account balance unless first represented as typed account snapshot input。

Ownership boundaries：

- `PositionManager` owns position quantity projection and `PositionEvent` audit。
- `MarginEngine` owns `MarginSnapshot`。
- `PnLEngine` owns `PnLSnapshot`。
- `SettlementEngine` owns settlement snapshot。
- AccountSnapshot update may happen only through Settlement / Accounting service, not directly by `PositionManager`。

Required gate for accounting handoff：

- stable Position `account_id` / `instrument_id`。
- known `position.version`。
- typed Decimal market / settlement price input。
- available trading_day。
- deterministic config hash / calculation key。
- known source PositionEvent / Position version lineage。

Reject：

- missing position identity。
- missing price。
- non-Decimal price。
- stale position version unless explicitly replaying that historical version。
- raw_payload-only facts。

Position -> Margin contract：

- `MarginSnapshot` must bind to `account_id`、`instrument_id`、`position_version`、`trading_day` and deterministic `calculation_key` / config hash。
- same account + instrument + position_version + config + typed price input -> same margin fact。
- duplicate same canonical -> no-op。
- same identity + different canonical -> conflict。
- no direct Position qty / avg mutation by Margin。

Position / Trade -> PnL contract：

- `PnLSnapshot` must bind to `account_id`、`instrument_id`、`position_version`、`trading_day` and deterministic `calculation_key` / config hash。
- realized PnL source is typed Trade / PositionEvent close data only。
- unrealized PnL source is typed Position plus typed market / settlement price。
- no raw report / broker state / OMS state / execution report input。

Repository / schema decision：

- Existing Margin / PnL / Settlement repositories already exist。
- Existing schema is partially sufficient for position accounting lineage through `account_id`、`instrument_id`、`position_version` and `calculation_key`。
- Existing `margin_snapshots` and `pnl_snapshots` do not persist first-class `trading_day`; config lineage is not uniformly represented as `config_hash`。
- Future implementation requires `0015_stage_l5_position_to_accounting.py` unless it explicitly encodes `trading_day` and config hash in deterministic `calculation_key` and passes review。
- Do not create a second accounting ledger。

Stage L.5 replay：

- same position_version + same config + same typed price input -> duplicate / no-op。
- same identity + different canonical -> conflict。
- ordered PositionEvents / Positions replay deterministic。
- replay must not call Broker / Runtime。
- replay must not mutate OMS / Trade ledger。
