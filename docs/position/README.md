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
