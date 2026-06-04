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
