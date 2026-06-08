# 结算文档

当前 Stage F Settlement Engine 已实现。

当前能力：

- typed `SettlementPrice` / `SettlementContext` / `SettlementSnapshot` / `SettlementResult`。
- `SettlementEngine` 执行日终 fact finalization、account snapshot、today -> yesterday roll。
- Settlement 消费 Position live projection、PnLSnapshot、MarginSnapshot、AccountContext / AccountSnapshot、typed SettlementPrice 和 TradingCalendar / trading_day。
- 同一 `account_id + trading_day` 只有一个 final settlement fact；same canonical 返回 `DUPLICATE` no-op，different canonical 返回 `CONFLICT`。
- Rejected settlement 不 append snapshot、不 roll position、不写 account snapshot。
- Replay 复用同一 settlement calculator / engine，并检查 live position / account projection divergence。

明确不实现：

- Broker reconciliation。
- 真实 exchange settlement file ingestion。
- CTP / SimNow。
- Risk direct integration。
- runtime infra。
- 修改历史 trades / position_events / pnl_snapshots / margin_snapshots。
- raw_payload settlement facts。
- Settlement file parser。

## Stage L.5 Margin / PnL To Settlement Contract

Stage L.5 freezes the accounting-chain handoff into Settlement. It does not implement Runtime, Broker, live feeds, external account sync, or calendar automation.

Settlement may consume `MarginSnapshot` + `PnLSnapshot` only when the following lineage matches exactly for each settled instrument / position lineage：

- `account_id`。
- `instrument_id`。
- `position_version`。
- `trading_day`。

Mismatch must return typed reject / conflict. Settlement must not fall back to `instrument_id` alone. This preserves the Stage F fact-lineage fix that prevented account / position-version ambiguity.

Settlement source-of-truth remains：

- typed Position live projection。
- `MarginSnapshot`。
- `PnLSnapshot`。
- typed AccountContext / AccountSnapshot。
- typed SettlementPrice。
- TradingCalendar / trading_day。

Settlement forbidden inputs：

- `raw_payload` facts。
- Broker state。
- OMS `OrderState`。
- `NormalizedExecutionReport`。
- `OrderEventCandidate`。
- SignalDecision / Strategy output。
- Runtime scheduler。

Settlement must not recompute Stage D Margin or Stage E PnL. If settlement-price margin or settlement-compatible PnL is required, those facts must already exist as typed `MarginSnapshot` / `PnLSnapshot` before settlement finalization.

Stage L.5 idempotency / replay：

- same position_version + same config + same typed price input -> duplicate / no-op upstream accounting facts。
- same identity + different canonical -> conflict。
- ordered PositionEvents / Positions replay deterministic。
- replay must not call Broker / Runtime。
- replay must not mutate OMS / Trade ledger。

Repository / schema decision：

- Current Margin / PnL / Settlement repositories already exist。
- Current snapshot tables are partially sufficient：they carry account / instrument / position_version / calculation identity, and settlement references margin / PnL snapshot ids。
- Current `margin_snapshots` and `pnl_snapshots` do not persist first-class `trading_day`; config lineage is not uniformly represented as `config_hash`。
- Future implementation requires `0015_stage_l5_position_to_accounting.py` unless it explicitly encodes `trading_day` and config hash inside deterministic `calculation_key` and passes review。
- Any migration must extend existing accounting snapshot ledgers only; do not create parallel accounting tables。
- Do not create a second accounting ledger。
