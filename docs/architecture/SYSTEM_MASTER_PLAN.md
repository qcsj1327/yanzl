# System Master Implementation Plan

## 1. Executive Summary

本总方案从终态量化交易系统倒推实施路线，目标是把当前本地 deterministic trading core 演进为可进入 paper、sim、live 的期货交易系统。

终态系统必须具备：

- 确定性的领域核心：订单、风控、执行映射、成交、持仓、保证金、PnL、结算均有类型化 source-of-truth。
- 可审计的应用编排：Strategy、Risk、OMS、Execution、Accounting、Recovery、Replay 之间通过明确 port/service 协作。
- 可替换的执行与柜台接入：Mock、paper、SimNow、live broker 只通过 adapter 进入，不污染 Domain、OMS、Risk 或 mapper。
- 可回放的事实流：行情、信号、风控、订单事件、执行回报、成交、持仓、保证金、PnL、结算和审计事件都能按规则重放。
- 可生产运行的安全体系：kill switch、readiness、healthcheck、metrics、audit、runbook、deployment gates 和 disaster recovery。

本文不是当前 sprint 计划，不定义短期闭环，不沿用旧阶段编号继续扩展。本文只定义从终态反推的全局实施路线和约束。

## 2. Current Baseline

当前已完成并可作为后续路线基础的事实：

- OMS / Repository / UoW / Event Semantics 已完成。
  - 当前 tag：`phase-2-complete / a8e0929`。
  - OMS 是订单状态唯一 source-of-truth。
  - `orders.status/version` 与 `order_events` 构成订单状态和审计事实。
  - `OMSService.create_order(...)`、`apply_risk_result(...)`、`apply_order_event(...)`、`recover_order(...)` 是当前订单状态入口。
- Pure Risk Engine 已完成。
  - 当前 tag：`phase-3-complete / 9ec5669`。
  - Risk 保持 pure computation。
  - Risk 不调用 OMS，不查 DB，不写 `risk_events`，不调用 Position / Margin / PnL / Settlement。
  - 终态 Risk 不止 pure config；真实 account / portfolio / position / intraday / kill switch 风控必须在后续 Risk Context / Portfolio Risk Upgrade 中引入。
- Execution mapper 已完成并验收。
  - 当前 tag：`phase-4-execution-mapper-fix2 / 15d35f4`。
  - Mapper 是 pure mapper：`ExchangeReport + MappingContext -> MappingResult`。
  - Mapper 不调用 OMS，不写 DB，不读 `raw_payload` 补 source-of-truth 字段。
  - `PARTIALLY_FILLED -> PARTIALLY_FILLED` 是 OMS 允许迁移，必须保留可映射。
- Execution Command/Report Runtime Layer 已完成并验收。
  - 当前 tag：`phase-4-execution-command-report-runtime / bd6f0d4`。
  - 已有本地 command port、in-memory report sink、EMS command boundary、ConfigurableMockFuturesExchange skeleton 和 report handler。
  - 当前仍不接 OMS，不写 DB，不接 CTP、SimNow、broker adapter、Kafka、Celery 或 FastAPI。
- Accounting Core 已完成并可作为后续路线基础。
  - 当前 tag：`accounting-chain-core-baseline / 83c2948`。
  - 已完成 Trade、Position、Margin、PnL 和 Settlement。
  - Accounting source-of-truth 仍只能来自类型化 Trade、Position、MarginSnapshot、PnLSnapshot、SettlementSnapshot、AccountContext / AccountSnapshot 和结算价格输入。
- Market Data Core 已完成。
  - 当前 tag：`stage-g-market-data-core / 62e3240`。
  - 已实现 typed Tick / Bar / MarketDataEvent / MarketDataSnapshot / DataQualityResult、DataQualityGate、MarketTickRepository / MarketBarRepository、SQLAlchemy repository、UoW integration、`market_ticks` / `market_bars` migration、MarketDataService ingestion 和 deterministic market replay。
  - Stage G 未实现 Tick -> Bar Aggregator、FeatureSnapshot generation、Strategy / Signal、Broker adapter、Kafka ingestion、FastAPI service 或 live market feed。
- Feature Snapshot Core 已完成。
  - 当前基线：`stage-h-feature-snapshot-core / a5c2fbf`。
  - 已实现 typed FeatureSnapshot、FeatureConfig、FeatureBuildResult、pure FeatureBuilder、canonical payload、FeatureSnapshotRepository、SQLAlchemy repository、UoW integration、`feature_snapshots` migration、FeatureService、deterministic feature replay 和 tests。
  - Stage H 未实现 Strategy、Signal、Tick -> Bar Aggregator、Broker adapter、Runtime infra、ML features、portfolio features 或 cross-instrument features。
- Strategy / Signal Lifecycle Core 已完成。
  - 当前基线：`stage-i-strategy-signal-contract-freeze / 0bcbfd8` 后实现。
  - 已实现 `StrategyConfig` canonicalization / hash、`StrategyContext`、deterministic `signal_id`、`SignalCandidate`、`SignalDecision`、`TriggerResult`、signal lifecycle、canonical payload、Signal repository protocols、SQLAlchemy repositories、UoW integration、`signal_candidates` / `signal_events` migration、`StrategyService` / `SignalLifecycleService`、deterministic strategy replay 和 tests。
  - Stage I 未实现 Order creation、Risk check、OMS integration、Execution integration、Broker adapter、runtime scheduling、paper / sim / live、portfolio optimization、ML model serving、cross-instrument strategy 或 Accounting mutation。

当前尚未实现为业务能力的部分：

- Application Execution Orchestrator。
- OMS public UNKNOWN entry。
- RiskContext、portfolio/account risk、intraday limits、kill switch risk。
- Recovery / Replay Framework。
- FastAPI / Celery / Kafka / Runtime control plane。
- CTP / SimNow / live broker adapter。
- Production operations、monitoring、audit、kill switch、deployment gates 和 runbook。

## 3. Target System Architecture

终态系统分为七层。下层不得反向依赖上层，运行时和外部 adapter 不得污染 core。

### Domain / Contract Layer

- 定义 `Signal`、`OrderRequest`、`OrderState`、`RiskResult`、`OrderEvent`、`ExchangeReport`、`Fill`、`Trade`、`Position`、`Margin`、`PnL`、`Settlement`、`MarketTick`、`MarketBar`、`FeatureSnapshot` 等类型化事实。
- 只保留 enum、model、字段、默认值、Decimal 约束和契约边界。
- 禁止业务 orchestration、IO、config、broker、Kafka、Redis、FastAPI、Celery、KMS、cloud SDK。
- `raw_payload`、`metadata`、`raw`、`details` 永远只诊断，不承载 source-of-truth 字段。

### Application Service Layer

- 编排 Strategy、Risk、OMS、Execution、Accounting、Recovery、Replay。
- 负责 `Signal -> OrderRequest -> RiskResult -> OMS -> Execution command -> report mapping -> OMS apply`。
- 负责 RiskContext Builder、MarketContext join、order submit/cancel orchestration、mapping result routing、reconciliation trigger。
- 不直接绕过 OMS 修改订单状态。
- 不把运行时 transport payload 当作事实来源。

### Execution / Broker Adapter Layer

- Execution 保持 command/report 边界。
- EMS 接收 submit/cancel command，不解释 OMS 状态机，不写订单状态。
- Broker adapter 负责 CTP / SimNow / live broker 的连接、登录、心跳、重连、命令投递、回报解析、订单查询、成交查询、账户查询和持仓查询。
- Adapter 输出 typed `ExchangeReport` 或后续 typed query result。
- Adapter 不调用 OMS，不调用 Risk，不更新 Position / Margin / PnL / Settlement。

### Accounting Layer

- Fill / Trade 是会计主链入口。
- `trades` 是成交事实账本；终态成交去重必须基于类型化成交身份，例如 `account_id + exchange + exchange_trade_id`。
- `positions(account_id, instrument_id)` 是 live position projection / current source-of-truth。
- `position_events` 是 Position 幂等、replay 和 audit ledger；只靠 `positions` snapshot 不允许作为重复成交 replay 的幂等依据。
- Margin、PnL、Settlement 只能基于类型化 Trade、Position、Market price、Settlement price 和 account context 计算。
- `account_snapshots`、`settlement_snapshots` 是快照与审计，不替代 live source-of-truth。

### Strategy / Market Data Layer

- Market adapter 将外部行情解析为 typed Tick / Bar。
- Market Data Core 只能消费 external market adapter typed input、instrument identity mapping、trading calendar / trading session、timestamp normalization rule 和 data quality policy。
- Market Data Core 输出 typed `Tick`、typed `Bar`、typed `MarketDataEvent`、typed `MarketDataSnapshot`、`DataQualityResult` 和 replayable market facts。
- Market Data Core 负责去重、排序、数据质量、交易日/session 归属；不得创建订单、调用 OMS / Risk / Execution，或修改 Trade / Position / Margin / PnL / Settlement。
- Market Data Core 不得从 `raw_payload` 补 source-of-truth 字段，不得把 Redis/Kafka message 当作 DB fact。
- Feature Builder 生成 deterministic `FeatureSnapshot`，只消费 typed Bar / MarketDataSnapshot，不修改 Market facts，不创建订单。
- Strategy 只能消费 `FeatureSnapshot`、可选 `MarketDataSnapshot`、由 application layer 注入的 typed PositionContext / PortfolioContext、`StrategyConfig` / `StrategyVersion` 和交易日历 / session context。
- Strategy 只输出 `SignalCandidate`、`SignalDecision`，如包含 lifecycle gate 则只输出 `TriggerResult`；Strategy 不创建订单，不调用 OMS / Risk / Execution，不读取 broker state。
- Risk 不直接查询行情 adapter、行情 DB、Kafka 或 Redis；由 application layer 组装 typed RiskContext。

### Runtime / Infrastructure Layer

- FastAPI、Celery、Kafka、Redis、async runtime、cloud、KMS 都属于后续 runtime / infra stage。
- Runtime 通过 adapter/port 接入 Application Service，不进入 Domain、OMS、Risk 或 pure mapper。
- Kafka 是传输和回放入口，不是 DB source-of-truth 的替代。
- Redis 可用于 cache、lock、pubsub、临时状态，不作为订单、成交、持仓、资金或结算事实来源。
- KMS / secrets provider 只处理 secret retrieval 和 redaction，不进入业务事件字段。

### Operations / Safety Layer

- 提供 monitoring、metrics、audit、kill switch、readiness、healthcheck、deployment gates、runbook 和 disaster recovery。
- Operations 不直接改 Domain、OMS、Risk、Execution mapper 或 Accounting source-of-truth。
- 所有人工控制和系统控制动作必须生成结构化 audit。
- Live 前必须通过 paper、sim、live preflight 的递进验收。

## 4. End-to-End Trading Flow

终态交易链路如下：

1. Market adapter 接收外部行情，解析为 typed Tick / Bar。
2. Market Data Service 执行 data quality gate，处理缺口、延迟、乱序、异常价格和 session 归属。
3. Feature Builder 基于 typed market facts、calendar、session 和规则版本生成 deterministic `FeatureSnapshot`。
4. Strategy 消费 `FeatureSnapshot` 和允许的 typed context，输出 `SignalCandidate` / `SignalDecision`。
5. Application Service 将 `SignalDecision` 转换为后续 OrderIntent / `OrderRequest`，生成稳定 `client_order_id`。
6. RiskContext Builder 组装 account、portfolio、position、margin、market、intraday、kill switch 等 typed context。
7. Pure Risk Core 计算并返回 `RiskResult`。
8. Application Service 将 `RiskResult` 交给 `OMSService.apply_risk_result(...)`。
9. OMS 推进 `OrderState` 到 `RISK_ACCEPTED` 或 `REJECTED_BY_RISK`，并写入 `order_events`。
10. Application Execution Orchestrator 对 `RISK_ACCEPTED` 订单发起 submit。
11. Orchestrator 先通过 OMS 事件让订单进入 `SUBMITTING`，再调用 EMS command port。
12. EMS 调用 Mock / paper / SimNow / live broker adapter 的 command port。
13. Execution / Broker adapter 产生 typed `ExchangeReport`。
14. ExecutionReportHandler 调用 pure mapper，得到 typed `MappingResult`。
15. 对 `MAPPED_ORDER_EVENT`，Orchestrator 将 `OrderEvent` 交回 `OMSService.apply_order_event(...)`。
16. OMS 根据状态机、幂等、乱序、终态保护和 UNKNOWN 规则应用或拒绝事件。
17. 当回报包含真实成交事实时，必须先经 Fill / Trade domain migration 形成 typed `Fill` / `Trade`。
18. Trade ledger 去重后作为 Position Manager 的唯一输入事实。
19. Position Manager 更新 live `positions`，处理开仓、平今、平昨和 today/yesterday bucket，并写入 `position_events` 作为 applied-trade audit。
20. Margin Engine 基于 Position、instrument rules、account context 计算保证金。
21. PnL Engine 基于 Trade、Position、last price、settlement price 计算 realized / unrealized PnL。
22. Settlement Engine 在交易日边界执行结算、settlement price finalization、Margin fact finalization、PnL fact finalization 和 today -> yesterday roll。
23. Recovery / Replay Framework 可按 source-of-truth 重放 order events、execution reports、trades、positions、market events、settlement snapshots。
24. Monitoring / Audit 记录 metrics、structured logs、control actions、replay divergence、deployment gate 和 incident response。

关键边界：

- OMS 决定订单状态；Execution、Adapter、Runtime 不得绕过 OMS。
- 当前 status-only fill 不能作为真实成交事实；真实成交必须类型化。
- Broker query reconciliation 不能静默覆盖本地事实；必须进入 recovery/replay 或明确恢复事件。
- `raw_payload` 永远只诊断。

## 5. Source-of-Truth Rules

### Order State

- 订单状态 source-of-truth 是 `orders.status/version` 与 `order_events`。
- 唯一状态入口是 OMS service。
- 每次订单状态变化必须有对应 `OrderEvent`。
- 终态订单不得回退。
- `UNKNOWN` 只能按 OMS 冻结原因进入，并只能恢复到允许目标。

### Risk Result

- 当前 source-of-truth 是 typed `RiskResult`。
- Risk 只返回 `RiskDecision.ACCEPTED` 或 `RiskDecision.REJECTED`，并提供 `rule_name`、`reason`。
- 未来 `risk_events` 只能作为审计或可追溯事实，不允许让 pure RiskEngine 依赖 DB。
- Risk context 必须由 application layer 结构化注入。
- Pure Risk 当前已完成，但终态 Risk 需要 account、portfolio、position、intraday、kill switch 等真实上下文风控。
- 真实上下文风控属于后续 Risk Context / Portfolio Risk Upgrade；Risk -> OMS 自动编排仍由 application layer 负责，Risk 不直接写 OMS、不直接改订单状态。

### Exchange Report Idempotency Key

- Execution report 幂等优先使用 typed `exchange_report_id`。
- 映射后的订单事件继续遵守当前 `event_source + external_event_id` 幂等键。
- Duplicate report / event 不得重复推进 OMS，不得重复累计成交。
- Adapter 和 runtime retry 不得绕过 report/event 幂等。

### Fill / Trade

- 真实成交必须拆分为类型化 `FillEvent` / `Trade` 事实。
- `FillEvent` 是 execution report typed fact，不直接更新 Position，不替代 Trade ledger。
- `Trade` ledger 是 accounting source-of-truth，也是会计主链输入。
- 成交去重不能依赖订单状态回报 ID；应使用明确 exchange trade identity。
- 成交价格、成交数量、trade id、fill id、手续费等不得藏在 `raw_payload`。
- `OrderStatus.FILLED` / `OrderStatus.PARTIALLY_FILLED` 不是成交账本事实。
- Position、Margin、PnL、Settlement 只能基于去重后的 `Trade` ledger。
- Stage B 选择扩展 `MappingResult` 为 `OrderEvent + FillEvent + Trade` bundle；mapper 仍只产出类型化事实，不写 DB。

### Position

- `trades` ledger 是 Position 更新的唯一输入事实。
- `positions(account_id, instrument_id)` 是 live position projection / current source-of-truth。
- `position_events` 是幂等和 replay audit ledger，记录 trade 是否已应用、应用前后 position snapshot 和 conflict 判定依据。
- Position 禁止消费 `OrderStatus`、`OrderEvent`、`ExchangeReport` 或 `raw_payload`。
- Pending、submitted、rejected 或其他未成交订单都不是真实持仓。
- 开仓、平今、平昨、冻结、解冻、today/yesterday roll 必须类型化；Stage C 只冻结 trade-driven position bucket 更新，不实现冻结/解冻或结算滚动。
- `account_snapshots` 和 `settlement_snapshots` 不是 live position source-of-truth。

### Margin / PnL / Settlement

- Margin 必须基于 Position、typed MarginRule、typed AccountContext 和 typed price input / price basis 计算。
- Margin 禁止消费 `OrderStatus`、`OrderEvent`、`ExchangeReport`、`raw_payload` 或 broker adapter query；Risk 不得直接查 DB 或直接调用 MarginEngine。
- Realized PnL 与 unrealized PnL 必须分离。
- `Trade.price`、`Position.last_price`、`Position.settlement_price` 不得混用。
- Settlement 以 `account_id + trading_day` 为边界，必须可幂等执行和重放。
- 结算后的 live source-of-truth 仍是类型化 positions/accounting state，不是 JSON 快照。

### raw_payload

`raw_payload` 永远只用于诊断。它不得承载以下 source-of-truth：

- 订单状态。
- `previous_status` / `new_status`。
- 成交价格、数量、trade id、fill id。
- 持仓数量、今昨仓、冻结数量。
- 保证金、资金、手续费、PnL。
- 结算价、交易日、结算结果。
- 风控上下文、规则版本、kill switch 状态。
- broker secret、环境、账户配置。

## 6. Implementation Roadmap

### Stage A: Application Execution Orchestrator

- Goal：把已完成的 Risk、OMS、EMS、report handler 和 mapper 编排为应用层执行链路。
- Inputs：OMS service、pure Risk result、Execution runtime layer、ExchangeReport mapper、Mock Exchange report sink。
- Outputs：submit/cancel orchestrator、mapping result routing、typed failure handling、report-to-OMS handoff。
- Allowed changes：新增 application service / orchestrator、focused unit/integration tests、必要接口 wiring。
- Forbidden changes：不改 mapper purity、不改 RiskEngine、不改 DB schema、不新增真实 broker、不用 runtime transport 替代 service boundary。
- Required tests：submit success、submit reject、cancel success、timeout、exchange unavailable、duplicate report、mapping error、insufficient context、OMS terminal protection。
- Acceptance criteria：`MAPPED_ORDER_EVENT` 可经 OMS 安全应用；非 mapped result 有 typed 分流；orchestrator 不直接写 DB 或订单状态。
- Suggested tag：`stage-a-application-execution-orchestrator`。

### Stage B: Fill / Trade Domain Migration

- Goal：把真实成交事实从 status-only fill 迁移为类型化 Fill / Trade。
- Inputs：Execution fill report、当前 `Trade` model、status-only fill 限制、account/exchange/order identity。
- Outputs：`FillEvent` contract、扩展后的 `Trade` contract、typed fill `ExchangeReport` fields、扩展 `MappingResult`、`TradeRepository`、schema migration、trade dedupe rule、accounting entry point。
- Allowed changes：Domain / execution DTO / mapper result / DB / interface / repository / UoW / tests 的明确 migration。
- Forbidden changes：不用 `raw_payload` 放成交价、数量、trade id、fill id、fee；不让 mapper 直接写 DB；不让 repository 更新 Position；不改 OMS 状态机；不接 broker/runtime。
- Required tests：FillEvent decimal contract、Trade decimal contract、raw_payload forbidden、typed fill extraction、status-only compatibility、duplicate trade same payload、duplicate trade conflict payload、repository/UoW、schema round trip、partial fill sequence、full fill、no Position mutation。
- Acceptance criteria：真实成交可类型化入账；重复成交不重复生成 Trade；status-only fill 不再承担会计事实；`PARTIALLY_FILLED -> PARTIALLY_FILLED` 继续允许；`UNIQUE(account_id, exchange, exchange_trade_id)` 保留。
- Suggested tag：`stage-b-fill-trade-domain-migration`。

Stage B 冻结说明：

- `FillEvent` 字段包括 `id`、`order_id`、`account_id`、`exchange`、`instrument_id`、`exchange_report_id`、`exchange_trade_id`、`fill_id | None`、`direction`、`offset`、`price`、`quantity`、`fee_amount | None`、`fee_currency | None`、`fee_source | None`、`traded_at`、`trading_day | None`、diagnostic-only `raw_payload`。
- `Trade` 字段包括 `id`、`account_id`、`exchange`、`exchange_trade_id`、`order_id`、`instrument_id`、`direction`、`offset`、`price`、`quantity`、`fee_amount | None`、`fee_currency | None`、`fee_source | None`、`trade_time`、`trading_day | None`、`source_exchange_report_id`、diagnostic-only `raw_payload`。
- `fee_amount is None` 表示未知；`fee_amount == Decimal("0")` 表示明确为零；`fee_currency` 在 `fee_amount is not None` 时必填；Stage B 不计算 PnL。
- `allow_status_only_fill=True` 保留旧行为，只映射 OrderStatus；`allow_status_only_fill=False` 且 typed fields 完整时产出 typed fill/trade fact；typed fields 缺失时返回 typed unsupported/error。
- `TradeRepository.create_or_get_trade(trade)` 按 `account_id + exchange + exchange_trade_id` 幂等；same payload 返回 existing，different payload 抛 `TradeIdempotencyConflictError`。
- 当前 `trades` 表已有基础字段和 `UNIQUE(account_id, exchange, exchange_trade_id)`，但 Stage B 冻结字段需要 Alembic migration 补充 fee、`trading_day`、`source_exchange_report_id` 和 `raw_payload`。
- 如 broker 无 `exchange_trade_id`，不能用随机 id；必须先冻结稳定替代键，否则不允许入账。

### Stage C: Position Manager

- Goal：建立基于 Trade ledger 的 live position 更新链。
- Inputs：typed Trade、current Position model、today/yesterday bucket、offset、`position_events` idempotency/audit ledger。
- Outputs：PositionManager、Position repository/UoW、PositionEvent repository/UoW、开仓/平今/平昨规则、applied-trade audit、position replay contract。
- Allowed changes：position domain / service、position repository、position event repository、DB migration、DB tests、position replay tests。
- Forbidden changes：不把 pending/submitted 订单当真实持仓；不让 Position 消费 `OrderStatus`、`OrderEvent`、`ExchangeReport` 或 `raw_payload`；不让 Risk 自查 Position DB；不实现 Margin / PnL / Settlement / today->yesterday roll / order freeze reservation。
- Required tests：OPEN LONG、OPEN SHORT、CLOSE TODAY LONG、CLOSE YESTERDAY LONG、CLOSE TODAY SHORT、CLOSE YESTERDAY SHORT、partial close、insufficient today/yesterday bucket、duplicate trade no-op、duplicate trade conflict、replay deterministic、position event unique trade key、DB round trip、UoW exposes positions/events、no OMS/Risk/Execution mapper/Broker/Runtime import、no Margin/PnL/Settlement mutation。
- Acceptance criteria：重复 trade replay no-op；same trade key + different canonical payload typed conflict；positions 与 ordered Trade replay 一致；PositionEvent 可回答哪笔 trade 已应用、应用前后 position 是什么、replay 是否重复。
- Suggested tag：`stage-c-position-manager`。

Stage C 当前实现说明：

- Stage C 选择 `PositionEvent`，不选择仅 `position_applied_trades`，因为 replay 和 audit 需要 before/after snapshot。
- Stage C Position 负责字段为 `account_id`、`instrument_id`、`long_today_qty`、`long_yesterday_qty`、`short_today_qty`、`short_yesterday_qty`、`long_avg_price`、`short_avg_price`、`version`、`updated_at`。
- 已存在的 `frozen_long_qty` / `frozen_short_qty` 可保留为字段，但 Stage C 不从订单状态推导冻结；冻结/解冻后续必须由 typed reservation event 驱动。
- Stage C 不更新 `realized_pnl`、`unrealized_pnl`、`margin_used`、settlement roll、today -> yesterday roll。
- 更新规则：BUY + OPEN 增加 `long_today_qty` 并按同侧 today + yesterday 总量加权平均更新 `long_avg_price`；SELL + OPEN 增加 `short_today_qty` 并按同侧 today + yesterday 总量加权平均更新 `short_avg_price`；SELL + CLOSE_TODAY 扣 `long_today_qty`；SELL + CLOSE_YESTERDAY 扣 `long_yesterday_qty`；BUY + CLOSE_TODAY 扣 `short_today_qty`；BUY + CLOSE_YESTERDAY 扣 `short_yesterday_qty`。
- Partial close 只扣成交数量；close 数量超过对应 bucket 时返回 typed rejection 且不修改 position；unsupported offset 返回 typed error；任何 resulting quantity 不得为负；数量和价格必须使用 Decimal。
- 平仓不在 Stage C 计算 realized PnL；平仓不改变剩余 open avg price。
- 幂等键沿用 Trade identity：`account_id + exchange + exchange_trade_id`。已存在且 canonical payload 一致时，live `positions` projection 必须与 `PositionEvent.after_snapshot` 一致才返回 `DUPLICATE_IGNORED`；projection diverged 或 payload 不一致时返回 `CONFLICT`；未存在时在同一 UoW 内更新 `positions` 并写入 `position_events`。
- `PositionEvent` 字段包括 `id`、`account_id`、`instrument_id`、`exchange`、`exchange_trade_id`、`trade_id`、`position_id`、`direction`、`offset`、`price`、`quantity`、`before_snapshot`、`after_snapshot`、`event_type`、`occurred_at`、`created_at`、diagnostic-only `raw_payload`。
- `PositionManager.apply_trade(trade)` 返回 typed result，状态包括 `APPLIED`、`DUPLICATE_IGNORED`、`REJECTED_INSUFFICIENT_POSITION`、`CONFLICT`、`ERROR`。
- `PositionManager.replay_trades(...)` 按 `trade_time` 和稳定 secondary key 排序后逐笔 `apply_trade`，已应用 no-op。Replay divergence 不得静默覆盖，必须返回 typed conflict/report。
- Stage C DB migration 已包含 `positions.version INTEGER NOT NULL DEFAULT 0`、`position_events` table、`UNIQUE(account_id, exchange, exchange_trade_id)`、`position_id` FK，以及 `account_id`、`instrument_id`、`account_id + instrument_id`、`trade_id` / `exchange_trade_id` 索引。

### Stage D: Margin Engine

- Goal：计算保证金并提供 typed margin context。
- Inputs：Position、typed MarginRule、typed AccountContext、typed price input / price basis。
- Outputs：MarginEngine、MarginRequirement、MarginSnapshot、MarginResult、RiskContext margin input、margin audit。
- Allowed changes：margin domain / module、MarginSnapshot repository、margin_snapshots migration、context builder、focused tests。
- Forbidden changes：Risk 不直接调用 MarginEngine 或 DB；不把 margin 放入 raw payload；不消费 `OrderStatus`、`OrderEvent`、`ExchangeReport`、broker adapter query 或 raw payload；不实现 PnL / Settlement / today-to-yesterday roll / order freeze reservation / broker reconciliation / CTP / SimNow / runtime infra。
- Required tests：long margin、short margin、mixed margin、today+yesterday qty、multiplier、initial vs maintenance、insufficient cash、missing rule、missing price、Decimal-only、snapshot persistence、replay deterministic、replay divergence、`positions.margin_used` update boundary and rollback、canonical duplicate snapshot no-op、canonical conflict、no PnL/Settlement mutation、no `OrderStatus` / `OrderEvent` / `ExchangeReport` / `raw_payload` consumption。
- Acceptance criteria：`margin_used` 与规则可重放；Risk 只消费 application layer 注入的 typed margin context；MarginSnapshot canonical same replay no-op，canonical different 返回 conflict/divergence 且不静默覆盖。
- Suggested tag：`stage-d-margin-engine`。

Stage D 当前实现说明：

- Margin source-of-truth 只能是 `Position`、typed `MarginRule`、typed `AccountContext` 和 typed price input / price basis。
- `Instrument.margin_rate` 不是完整规则，只能作为兼容数据来源之一；完整规则必须由 typed `MarginRule` 表达。
- `MarginRule.price_basis` 冻结为 `LAST_PRICE | SETTLEMENT_PRICE | AVG_PRICE | MANUAL`。`LAST_PRICE` 使用 typed latest price input；`SETTLEMENT_PRICE` 使用 typed settlement price input；`AVG_PRICE` 使用 Position avg price；`MANUAL` 使用 `MarginRule.price`。缺少所需价格返回 `REJECTED_MISSING_PRICE`。
- `AVG_PRICE` mixed position 下，long notional 使用 `long_avg_price`，short notional 使用 `short_avg_price`，分别计算后相加；对应方向 qty > 0 但 avg price 缺失或为 0 时返回 `REJECTED_MISSING_PRICE`。
- 计算规则：`long_qty = long_today_qty + long_yesterday_qty`；`short_qty = short_today_qty + short_yesterday_qty`；initial margin 和 maintenance margin 分别按 qty * price * contract multiplier * rate 计算；`margin_used = total_initial`；`required_cash = total_initial`；`is_sufficient = account.available_cash >= required_cash`。
- Insufficient cash 返回 `REJECTED_INSUFFICIENT_CASH` typed result，不抛业务异常，不 append `MarginSnapshot`，不更新 `positions.margin_used`。所有金额、价格、数量、rate、multiplier 必须 Decimal-only；rate `>= 0`，contract multiplier `> 0`，`available_cash` 可为 0。
- Margin calculation 必须校验 typed identity：`position.account_id == account.account_id`，`rule.instrument_id == position.instrument_id`。Mismatch 返回 typed `ERROR`，不 append `MarginSnapshot`，不更新 `positions.margin_used`。
- Stage D 允许更新 `positions.margin_used`，但必须和 `MarginSnapshot` 在同一 UoW / transaction。固定顺序为：先计算 `MarginRequirement` / `MarginSnapshot`，再 append `MarginSnapshot`，最后用 `expected_version=position.version` 更新 `positions.margin_used`。任一步失败则整个 transaction rollback。
- 不允许只更新 `positions.margin_used` 而没有 snapshot；不允许只写 snapshot 但声称 live `margin_used` 已更新；更新 `positions.margin_used` 时必须使用 margin-only repository method，不得复用会写 qty / avg price 的通用 position update；不得修改 qty、avg price、realized/unrealized PnL 或 settlement fields。
- Stage D 需要 `MarginSnapshotRepository` 和 `margin_snapshots` table；本阶段不建 `margin_rules` table，`MarginRule` 由 application layer 注入，`MarginSnapshot` 记录 `rule_id | None` 和 `rule_version | None`。
- `MarginSnapshot` canonical payload 字段包括 `account_id`、`instrument_id`、`position_version`、`rule_id`、`rule_version`、`long_qty`、`short_qty`、`price`、`contract_multiplier`、`initial_margin`、`maintenance_margin`、`margin_used`、`available_cash`、`equity`、`calculation_key`。`calculated_at` 持久化但不参与 canonical equality；`raw_payload` 不参与 canonical。
- Replay 使用同一 calculator，以 Position projection + MarginRule + AccountContext + typed price input 重算。同一 `account_id + instrument_id + position_version` 的 existing snapshot 已是该 position version 的 margin fact；同一 `calculation_key` canonical same 时 no-op / duplicate snapshot accepted，canonical different 时返回 `CONFLICT` / divergence；`calculation_key` 不同但同一 position version 经济事实一致时 no-op，经济事实不一致时返回 `CONFLICT` / divergence，不得追加第二条 snapshot 或更新 `positions.margin_used`。Replay 不更新 Position qty/avg。

### Stage E: PnL Engine

- Goal：计算 realized / unrealized PnL。
- Inputs：Trade、Position 或 typed pre/post position snapshot、typed price input、typed Trade fee；MarginSnapshot 只可用于 audit correlation，不参与 PnL 公式。
- Outputs：PnLEngine、RealizedPnL、UnrealizedPnL、PnLSnapshot、PnLResult、position PnL projection update。
- Allowed changes：pnl domain / module、PnLSnapshot repository、pnl_snapshots migration、pnl-only position update boundary、focused tests。
- Forbidden changes：不消费 `OrderStatus`、`OrderEvent`、`ExchangeReport`、broker adapter query 或 `raw_payload`；不让 Risk 直接 DB lookup；不实现 Settlement / today-yesterday roll / Margin recompute / broker reconciliation / CTP / SimNow / runtime infra / account equity mutation。
- Required tests：long close realized PnL、short close realized PnL、open trade no realized PnL、fee known / zero / unknown、long unrealized、short unrealized、mixed unrealized、LAST_PRICE / SETTLEMENT_PRICE / MANUAL、missing price、missing multiplier、Decimal-only、pre-close position required、snapshot persistence、duplicate no-op、canonical conflict、replay deterministic、no Margin mutation、no Settlement mutation、no `OrderStatus` / `OrderEvent` / `ExchangeReport` / `raw_payload` consumption。
- Acceptance criteria：同一 Trade / typed Position context / price input / multiplier / fee 得到 deterministic PnL；PnLSnapshot canonical same replay no-op，canonical different 返回 conflict/divergence 且不静默覆盖；Stage E 只通过 pnl-only repository method 更新 `positions.realized_pnl` / `positions.unrealized_pnl`。
- Suggested tag：`stage-e-pnl-engine`。

Stage E 当前实现说明：

- PnL source-of-truth 只能是 `Trade`、`Position` 或 typed pre/post position snapshot、typed price input、typed Trade fee。`MarginSnapshot` 只用于 audit correlation，不参与 realized / unrealized PnL 公式。
- `PnLPriceBasis` 冻结为 `LAST_PRICE | SETTLEMENT_PRICE | MANUAL`。缺少所需 price 返回 `REJECTED_MISSING_PRICE`；不得从 `raw_payload` 或 broker query 取价。
- `PnLResultStatus` 冻结为 `CALCULATED`、`REJECTED_MISSING_POSITION`、`REJECTED_MISSING_PRICE`、`REJECTED_MISSING_MULTIPLIER`、`REJECTED_MISSING_FEE`、`DOMAIN_FIELD_UNSUPPORTED`、`CONFLICT`、`ERROR`。
- Contract multiplier 必须来自 typed input 或 typed rule object，必须 Decimal 且 `> 0`；缺失返回 `REJECTED_MISSING_MULTIPLIER`。
- Realized PnL 只处理 close trade：`SELL + CLOSE_*` closes long，`BUY + CLOSE_*` closes short。Long close gross = `(trade.price - avg_cost) * quantity * contract_multiplier`；short close gross = `(avg_cost - trade.price) * quantity * contract_multiplier`。Open trade 不产生 realized PnL。
- Realized PnL 必须消费 typed pre-close position snapshot/context，或显式 `avg_cost`。不得用历史 close 后的 current live Position 推导 avg_cost，不得从 `raw_payload` 或 `OrderEvent` 推导 avg_cost。
- Fee policy：`fee_amount` 为 Decimal 时 `net_realized_pnl = gross_realized_pnl - fee_amount`；`Decimal("0")` 表示明确零手续费；`fee_amount is None` 时 calculator 可返回 `CALCULATED` 和 `reason="fee_unknown"` 以保留 gross 诊断信息，但 PnLEngine 持久化 projection 必须返回 `REJECTED_MISSING_FEE`，不 append snapshot，不更新 position PnL。
- Unrealized PnL 使用 typed mark price：long = `(mark_price - long_avg_price) * long_qty * contract_multiplier`；short = `(short_avg_price - mark_price) * short_qty * contract_multiplier`；`long_qty = long_today_qty + long_yesterday_qty`，`short_qty = short_today_qty + short_yesterday_qty`。
- Stage E 可更新 `positions.realized_pnl` / `positions.unrealized_pnl`，但必须先 append `PnLSnapshot`，再用 pnl-only repository method 更新 position PnL fields，并且二者处于同一 UoW / transaction。不得更新 qty、avg price、`margin_used` 或 settlement fields；snapshot append 失败不得更新 position，position update 失败必须 rollback。
- Stage E 已新增 `PnLSnapshotRepository` 和 `pnl_snapshots` table；`pnl_snapshots` canonical payload 使用 deterministic `calculation_key`，不使用 `calculated_at`；`raw_payload` 不允许进入 PnL facts。同一 `account_id + instrument_id + position_version` 不得写入第二条不同 PnL fact；除 `calculation_key` 外经济事实一致时 no-op，经济事实不一致时 conflict。
- Replay 使用同一 calculator 和 deterministic `calculation_key`。Same canonical no-op，different canonical 返回 `CONFLICT` / divergence；即使 `calculation_key` 不同，同一 position version 的经济事实一致也必须 no-op，经济事实不一致必须 conflict；replay 不得静默覆盖 position PnL fields。Replay divergence 判定必须读取 repository / UoW 内真实 live Position row；调用方传入的 Position 只作为 calculator input。若 live position PnL 与 snapshot divergence，除非当前 transaction 正在更新它，否则必须返回 `CONFLICT`。
- PnL 不使用 `margin_used` 参与公式，不触发 Margin recompute，MarginEngine 不调用 PnLEngine。Stage E 不实现 settlement snapshots、settlement price finalization、daily PnL carry、today -> yesterday roll 或 account equity mutation。

### Stage F: Settlement Engine

Stage F 当前实现说明：

- 已实现 Settlement domain objects、SettlementCalculator / planner、SettlementEngine、replay path、SettlementSnapshotRepository、AccountSnapshotRepository、settlement-only position roll method、UoW integration 和 `0007_stage_f_settlement_engine` migration。
- Successful settlement 在同一 UoW 内创建 / 引用 account before snapshot、创建 account after snapshot、append SettlementSnapshot、roll today -> yesterday；任一步失败 rollback。
- Duplicate same canonical 返回 `DUPLICATE` no-op；different canonical 返回 `CONFLICT`；replay 会读取 live position / account row 检查 divergence。
- Rejected settlement 不落库、不 roll、不更新 account。Stage F 仍不接 Broker / Risk / Execution / Runtime，不消费 `OrderStatus` / `OrderEvent` / `ExchangeReport` / `raw_payload` facts，不修改历史 Trade / PositionEvent / PnLSnapshot / MarginSnapshot。

- Goal：执行日终结算、settlement price finalization、PnL / Margin fact finalization、account snapshot、today -> yesterday roll。
- Inputs：Position live projection、PnLSnapshot、MarginSnapshot、AccountContext / AccountSnapshot、typed SettlementPrice input、TradingCalendar / trading_day。Trade / PositionEvent 只可用于 audit / replay proof，不作为 primary live settlement path。
- Outputs：SettlementEngine、SettlementSnapshot、SettlementResult、SettlementSnapshotRepository、account snapshot after-state、settlement-only position roll。
- Allowed changes：settlement module、settlement domain models、settlement repository / UoW port、account snapshot repository if needed、migration extending `settlement_snapshots`、settlement tests。
- Forbidden changes：不把 settlement 放回 MockExchange；不通过 JSON snapshot 补 live facts；不消费 `OrderStatus` / `OrderEvent` / `ExchangeReport` / `raw_payload` / broker adapter query / Risk direct DB lookup；不改历史 Trade / PositionEvent / PnLSnapshot / MarginSnapshot；不实现 broker reconciliation、真实交易所结算单解析、CTP、SimNow 或 runtime infra。
- Required tests：domain Decimal validation、non-trading day reject、missing position / PnL / Margin / settlement price、frozen qty reject、today-to-yesterday roll、avg price unchanged、PnL / Margin snapshots not mutated、account after formula、duplicate same canonical no-op、same account/day different canonical conflict、replay live position/account divergence conflict、rejected result no persistence、settlement-only position update boundary、schema unique account/day、no OMS / Risk / Execution / Broker / raw_payload dependency。
- Acceptance criteria：同一 `account_id + trading_day` 只有一个 final settlement fact；same canonical duplicate returns `DUPLICATE` / existing no-op；different canonical returns `CONFLICT`；successful settlement appends SettlementSnapshot, creates/references account after snapshot, and rolls positions in one UoW; rejected settlement does not persist or roll.
- Suggested tag：`stage-f-settlement-engine`。

Stage F contract freeze：

- Settlement source-of-truth 只能是 typed Position live projection、PnLSnapshot、MarginSnapshot、AccountContext / AccountSnapshot、typed SettlementPrice input、TradingCalendar / trading_day。Trade / PositionEvent 只提供 audit / replay proof，不驱动 primary live settlement。
- `SettlementResultStatus` 冻结为 `SETTLED`、`DUPLICATE`、`REJECTED_NON_TRADING_DAY`、`REJECTED_MISSING_POSITION`、`REJECTED_MISSING_PNL`、`REJECTED_MISSING_MARGIN`、`REJECTED_MISSING_SETTLEMENT_PRICE`、`REJECTED_FROZEN_POSITION`、`CONFLICT`、`ERROR`。
- Today -> yesterday roll：`long_yesterday_qty += long_today_qty`，`short_yesterday_qty += short_today_qty`，`long_today_qty = 0`，`short_today_qty = 0`。Stage F 不改 avg price，不重算 realized / unrealized PnL，不重算 `margin_used`。如 `frozen_long_qty > 0` 或 `frozen_short_qty > 0`，返回 `REJECTED_FROZEN_POSITION`，不 roll、不 append settlement snapshot、不更新 account。
- PnL finalization：Settlement 消费 `PnLSnapshot` facts，不重新计算 Stage E PnL；必须校验每个 settled instrument 有 relevant PnLSnapshot，`PnLSnapshot.price_basis == SETTLEMENT_PRICE` 或明确 settlement-compatible，且 `PnLSnapshot.mark_price == SettlementPrice.price`；不 mutate historical `pnl_snapshots`。
- Margin finalization：Settlement 消费 `MarginSnapshot.margin_used`，不重新计算 Stage D margin；如需要 settlement-price margin，Stage D 必须先生成 MarginSnapshot；Settlement 不 mutate historical `margin_snapshots`。
- Account formula 冻结为 typed formula：`cash_after = cash_before + realized_pnl`；`equity_after = cash_after + unrealized_pnl`；`available_cash_after = cash_after - margin_used`；`frozen_cash_after = account_before.frozen_cash`。不做 fee recomputation，realized PnL 来自 already-net PnLSnapshot，unrealized PnL 来自 PnLSnapshot，margin_used 来自 MarginSnapshot；不查 broker cash，不读 raw payload。
- Stage F creates or references `account_snapshot_after`; `account_snapshot_before` may be referenced or constructed from typed AccountContext. SettlementSnapshot stores account before/after ids and typed cash/equity/PnL/margin values. Account update, settlement snapshot append, and position roll must be in the same UoW; any failure rolls back all.
- `SettlementSnapshotRepository` freezes: `append_settlement_snapshot(snapshot)`、`get_by_account_trading_day(account_id, trading_day)`、`get_by_calculation_key(account_id, trading_day, calculation_key)`、`list_by_account(account_id)`、`list_by_trading_day(trading_day)`。
- Migration: existing `settlement_snapshots` is insufficient. Stage F must extend or replace it without breaking history, adding `calculation_key`、`status`、`reason`、`positions_before`、`positions_after`、`settlement_prices`、`pnl_snapshot_ids`、`margin_snapshot_ids`、`account_snapshot_before_id`、`account_snapshot_after_id`、`cash_before`、`cash_after`、`realized_pnl`、`unrealized_pnl`、`margin_used`; add `UNIQUE(account_id, trading_day)`, indexes on `account_id`, `trading_day`, `(account_id, trading_day)`, and `calculation_key`. Do not add `settlement_events`, broker reconciliation table, or risk table in Stage F.
- Canonical payload includes `account_id`、`trading_day`、`calculation_key`、`positions_before`、`positions_after`、`settlement_prices`、`pnl_snapshot_ids`、`margin_snapshot_ids`、`cash_before`、`cash_after`、`realized_pnl`、`unrealized_pnl`、`margin_used`、`status`; `calculated_at` / `created_at` and `raw_payload` are not canonical facts.
- Replay uses the same settlement calculator / engine. Existing same canonical returns `DUPLICATE` / no-op; existing different canonical returns `CONFLICT`; live position/account projection divergence from snapshot after-state returns `CONFLICT`. Replay must not mutate historical trades, position_events, pnl_snapshots, or margin_snapshots.
- Settlement position roll must use a settlement-only repository method such as `PositionRepository.roll_today_to_yesterday_for_settlement(...)` with `expected_version`. It may update only `long_today_qty`, `long_yesterday_qty`, `short_today_qty`, `short_yesterday_qty`, `version`, and `updated_at`; it must not update avg price, realized/unrealized PnL, `margin_used`, or settlement price fields.
- Non-trading day returns `REJECTED_NON_TRADING_DAY`; trading day must come from typed input or TradingCalendar repository, never inferred from system date.

### Stage G: Market Data / Feature Snapshot

- Goal：实现 Market Data Core，建立 typed Tick / Bar / MarketDataEvent / MarketDataSnapshot、data quality gate、repository contract、DB market facts、ingestion service、replay contract 和 FeatureSnapshot 边界。
- Inputs：external market adapter typed input、instrument identity mapping、trading calendar / trading session、timestamp normalization rule、data quality policy。
- Outputs：typed `Tick`、typed `Bar`、typed `MarketDataEvent`、typed `MarketDataSnapshot`、`DataQualityResult`、replayable market facts。
- Implemented changes：market data domain objects、DataQualityGate、MarketTickRepository / MarketBarRepository Protocol、SQLAlchemy repository、UoW integration、`0008_stage_g_market_data_core` migration、MarketDataService ingestion、deterministic market replay、unit/integration/boundary tests、docs update。
- Forbidden changes：不改 OMS / Risk / Execution / Accounting 行为；不实现 Broker adapter、CTP、SimNow、live feed、Kafka ingestion、FastAPI、Celery、Strategy、Signal、Feature indicators 或 Tick -> Bar Aggregator。
- Source-of-truth：Market Data 只能消费 typed adapter input、typed identity mapping、calendar/session、timestamp normalization rule 和 data quality policy；`raw_payload` 只诊断，Redis/Kafka 只可作为未来 transport/cache，不是 DB fact。
- Instrument identity：冻结 `symbol`、`instrument_id`、`trade_instrument_id`、`exchange`、`trading_day`、calendar/session 归属；不得混用主力连续合约、行情合约、交易合约和 base symbol；Adapter 负责 normalized typed identity；Market Data Core 不猜测合约映射。
- Timestamp：external ts 可以是 ms/us/ns，但 adapter 必须 normalize；Domain 时间必须使用已有 Domain 契约一致的 typed `datetime` / `date`；`bar_ts` 冻结为 bar start timestamp；`trading_day` 必须由 calendar/session rule 给出，不得从系统日期推断。
- Data quality：missing identity、bad timestamp、out-of-session、bad price、bad OHLC、non-monotonic timestamp 均返回 typed rejected；duplicate same canonical 返回 `DUPLICATE` no-op；duplicate different canonical 返回 `CONFLICT` 或 `ERROR`；gap 返回 `GAP_DETECTED`，只有显式 policy `allow_gap=True` 时才可继续接受。
- Price / volume validation：price 必须为 `Decimal > 0`；volume / turnover / open_interest 必须 `>= 0`；OHLC 必须满足 high/low 边界；bid/ask 同时存在时必须 `bid <= ask`；zero-volume bar 只有显式 policy 允许时可接受；非法事实必须 typed reject，不得静默修正。
- Bar aggregation：Stage G 不实现 aggregator。后续 `Tick -> Bar` aggregator 必须按 `instrument_id + timeframe + bar_ts` deterministic；same canonical no-op；different canonical conflict；不得创建订单或生成 strategy signal。
- Repository / DB contract：已实现 `MarketTickRepository`、`MarketBarRepository`、`market_ticks` table、`market_bars` table。Tick idempotency 为 `exchange + instrument_id + ts + source`，如未来 exchange tick id 存在则优先使用；Bar idempotency 为 `exchange + instrument_id + timeframe + bar_ts + source`。Canonical 排除 `raw_payload`、`received_at`、`calculated_at`。
- Replay：Market replay 使用 ordered typed market facts；same canonical no-op；different canonical conflict；replay 必须 deterministic；不得直接调用 Strategy，除非后续 Strategy Replay stage 另行定义；不得 mutate Accounting。
- FeatureSnapshot boundary：`FeatureSnapshot` 消费 typed Bar / MarketDataSnapshot，是 deterministic derived fact；不修改 Market facts，不创建订单；Strategy 后续消费 FeatureSnapshot；Stage G 不实现 indicators。
- Tests：Tick decimal validation、Bar OHLC validation、missing identity reject、bad timestamp reject、out-of-session reject、duplicate same canonical、duplicate different canonical conflict/error、raw_payload diagnostic only、non-monotonic reject、gap detection、bar idempotency、repository round trip、replay deterministic、no OMS/Risk/Execution/Accounting mutation/import。
- Acceptance criteria：Market Data Core 可独立接收 typed Tick / Bar，执行 data quality gate，持久化 accepted market facts，幂等处理 duplicate，typed 返回 conflict/error，并可 deterministic replay；不得污染 Strategy、Risk、OMS、Execution、Accounting、Broker 或 Runtime。
- Suggested tag：`stage-g-market-data-contract-freeze`。

### Stage H: Feature Snapshot Core

- Goal：实现 `FeatureSnapshot` source-of-truth、identity、字段、计算规则、warmup / missing data、repository、builder/service、replay 和 Strategy 边界；本阶段不进入 Strategy / Signal。
- Inputs：typed `Bar`、typed `MarketDataSnapshot`、trading calendar / session、instrument identity、deterministic feature config / rule version。
- Outputs：typed `FeatureSnapshot` / `FeatureConfig` / `FeatureBuildResult`、pure FeatureBuilder、canonical payload、`FeatureSnapshotRepository`、`feature_snapshots` table、FeatureService、deterministic replay 和 tests。
- Implemented changes：domain enum/model、feature builder/canonical/service/replay module、repository Protocol、SQLAlchemy repository、UoW integration、`0009_stage_h_feature_snapshot_core` migration、unit/integration/boundary tests、docs update。
- Forbidden changes：不实现 Strategy / Signal、OMS / Risk / Execution / Accounting integration、Tick -> Bar Aggregator、Broker adapter、Runtime infra、ML features、portfolio features 或 cross-instrument features；FeatureService 不查询 MarketBarRepository；Redis/Kafka 不作为 source-of-truth。
- Source-of-truth：`FeatureSnapshot` 只能消费 typed Bar、MarketDataSnapshot、trading calendar/session、instrument identity、deterministic feature config / rule version；不得消费 `raw_payload`、OrderStatus、OrderEvent、ExchangeReport、Trade / Position / Margin / PnL / Settlement、Broker query，或把 Redis/Kafka 当 source-of-truth。
- Identity：必须携带 `symbol`、`instrument_id`、`trade_instrument_id`、`exchange`、`trading_day`、`timeframe`、`bar_ts`、`feature_version`、`feature_config_hash`、`source_bar_ids` 或 `source_bar_keys`；instrument identity 和 timeframe 必须与 source bars 一致；`bar_ts` 使用 bar start timestamp；`feature_version` 不是完整 config identity，`feature_config_hash` 必须由 deterministic config 派生；FeatureSnapshot 不猜合约映射。
- Fields：冻结 `returns`、`bar_return`、`price_range`、`range`、`atr`、`volume_ratio`、`moving_average`、`bias`、`breakout_level`、`volatility`、`momentum`、`source_window_start`、`source_window_end`、`warmup_complete`、`quality_status`、`missing_bar_count`、`gap_count`；`raw_payload` 如存在仅 diagnostic。Numeric features 必须为 `Decimal | None`，禁止 float；insufficient warmup 时 affected features 为 `None` 且 `warmup_complete=False`；不得静默用 0 填补缺失值。
- Calculation rules：`returns` / `bar_return` 使用 typed close prices；`range` / `price_range = high - low`；ATR 使用 configured window 和 typed OHLC；MA 使用 configured window 和 close；`bias = close - moving_average`，ratio 后续如需要另增 `bias_ratio`；`volume_ratio` 使用 configured window average volume；`breakout_level` 使用 configured window high/low；`volatility` / `momentum` 必须在实现前另行冻结 window 和 formula。
- Warmup / missing data：source bars 少于 required window 时 `warmup_complete=False`、affected features 为 `None`、不得 fake 0；gap detected 时 `quality_status` 反映 gap、`gap_count > 0`，仅当 policy `allow_gap=True` 时可继续 emit；missing bars 必须由 `missing_bar_count` 记录。
- Repository / DB contract：已实现 `FeatureSnapshotRepository` 和 `feature_snapshots` table；方法为 `append_feature_snapshot(snapshot)`、`get_by_identity(exchange, instrument_id, timeframe, bar_ts, feature_version, feature_config_hash)`、`list_by_instrument(exchange, instrument_id, timeframe, start_bar_ts, end_bar_ts)`、`list_by_trading_day(exchange, instrument_id, timeframe, trading_day)`；唯一键为 `exchange + instrument_id + timeframe + bar_ts + feature_version + feature_config_hash`；canonical 排除 `raw_payload`、`calculated_at`、`received_at`。
- Builder / Service boundary：`FeatureBuilder` 是从 typed bars + config 到 FeatureSnapshot 的 pure calculation；`FeatureService` 负责持久化 snapshots；rejected / insufficient input 不创建 fake facts；不得调用 Strategy、创建 Signal、直接查 Risk 或 mutate Accounting。
- Replay：Feature replay 消费 ordered Bars，并按 `exchange + instrument_id + timeframe + feature_version + feature_config_hash` grouping；same inputs/config 必须生成 same FeatureSnapshot；same canonical no-op；different canonical conflict/error；replay 不调用 Strategy，不修改 Market facts 或 Accounting。
- Strategy relation：Strategy 后续消费 `FeatureSnapshot`；`FeatureSnapshot` 不是 `Signal`；`FeatureBuilder` 不做交易决策；Strategy 不得为了补缺失 feature 直接读取 raw bars，除非后续 Strategy replay contract 显式允许。
- Tests：FeatureSnapshot Decimal validation、warmup/gap/quality invariant validation、FeatureConfig deterministic config hash、insufficient warmup -> `None` 且 no zero-fill、MA calculation、ATR calculation、bias formula、volume_ratio、breakout_level、volatility、momentum、source identity mismatch reject、timeframe mismatch reject、gap handling、duplicate same canonical、duplicate different canonical、replay deterministic、no Strategy/Risk/Accounting mutation、raw_payload excluded。
- Explicit non-goals：Stage H 不实现 Strategy、Signal、OMS/Risk integration、Tick -> Bar Aggregator、Broker adapter、live feed、Kafka/FastAPI/Celery runtime、ML features、portfolio features、cross-instrument features 或 execution/accounting mutation。
- Acceptance criteria：FeatureSnapshot Core 可从 caller-supplied ordered Bars deterministic 生成、持久化、幂等 duplicate、typed conflict/error，并可 replay；不得污染 Strategy、Risk、OMS、Execution、Accounting、Broker、Runtime 或 Market facts。
- Suggested tag：`stage-h-feature-snapshot-core`。

### Stage I: Strategy / Signal Lifecycle Core

- Goal：实现 Strategy / Signal Lifecycle Core，明确 Strategy source-of-truth、输出边界、SignalCandidate / SignalDecision 字段、Trigger lifecycle、repository / migration、replay / idempotency 以及 Risk / OMS 关系。
- Inputs：`FeatureSnapshot`；可选 `MarketDataSnapshot`；可选且必须由 application layer 注入的 typed PositionContext / PortfolioContext；`StrategyConfig` / `StrategyVersion`；trading calendar / session context。
- Outputs：`SignalCandidate`、`SignalDecision`；如包含 lifecycle gate，则输出 `TriggerResult` / application-level intent。
- Implemented changes：domain enum/model、`StrategyConfig` deterministic hash、`build_signal_id(...)`、pure Strategy Protocol、signal lifecycle rule、canonical payload、`SignalCandidateRepository` / `SignalEventRepository` Protocol、SQLAlchemy repositories、UoW integration、`0010_stage_i_strategy_signal_lifecycle` migration、`StrategyService` / `SignalLifecycleService`、strategy replay、unit/integration/boundary tests、docs update。
- Forbidden changes：不创建 Order / `OrderRequest`；不做 Risk check；不接 OMS / Execution / Broker / Runtime；不做 runtime scheduling、paper / sim / live、portfolio optimization、ML model serving、cross-instrument strategy 或 Accounting mutation；`raw_payload` 不作为 decision source。
- Source-of-truth：Strategy 不得消费 `raw_payload`、DB、Repository / UoW、`OMSService`、`RiskEngine`、Execution / Broker、`OrderStatus`、`OrderEvent`、`ExchangeReport`，也不得直接读取 Trade / Position / Margin / PnL / Settlement tables。
- Output boundary：Strategy 不创建 Order，不调用 OMS / Risk / Execution，不 mutate Position / Accounting，不 submit / cancel order，不读取 broker state。
- Identity：Strategy / Signal 必须携带 `strategy_name`、`strategy_version`、`strategy_config_hash`、`runtime_id`、deterministic `signal_id` policy、`symbol`、`instrument_id`、`trade_instrument_id`、`exchange`、`trading_day`、`timeframe`、`bar_ts`、`feature_version`、`feature_config_hash`。`runtime_id` 是 runtime lineage / audit 字段，不参与 `signal_id` hash。
- SignalCandidate：字段冻结为 `signal_id`、`strategy_name`、`strategy_version`、`strategy_config_hash`、`runtime_id`、`symbol`、`instrument_id`、`trade_instrument_id`、`exchange`、`trading_day`、`timeframe`、`bar_ts`、`feature_version`、`feature_config_hash`、`decision`、`side`、`position_side`、`confidence`、`strength`、`reason`、`expected_price`、`stop_loss`、`take_profit`、`holding_period_hint`、`tags`、`features_ref`、`raw_payload` diagnostic only。`signal_id` 必须由 strategy identity、feature identity 和 decision params deterministic 派生，且排除 `runtime_id`；`confidence` 是 0 到 1 的 Decimal；非 HOLD 时 `expected_price` 必须为 Decimal > 0；HOLD 不得携带 BUY / SELL side；`raw_payload` 不参与 source-of-truth。
- SignalDecision：字段冻结为 `decision`、`side`、`strength`、`confidence`、`reason`、`signal_id`、`strategy_name`、`strategy_version`、`strategy_config_hash`、`runtime_id`、`symbol`、`instrument_id`、`trade_instrument_id`、`exchange`、`trading_day`、`timeframe`、`bar_ts`、`feature_version`、`feature_config_hash`、`position_side`、`expected_price`、`stop_loss`、`take_profit`、`tags`、`raw_payload` diagnostic only。
- Trigger lifecycle：如包含 lifecycle gate，状态冻结为 `CANDIDATE`、`CONFIRMED`、`TRIGGERED`、`DUPLICATE`、`BLOCKED`、`EXPIRED`。同 canonical duplicate 返回 `DUPLICATE` / no-op；不同 canonical duplicate 返回 `CONFLICT` / `ERROR`；expired / blocked signal 不得 trigger；已 `TRIGGERED` signal 再 trigger 返回 `DUPLICATE` / no-op 且不再产生 actionable intent；trigger 不创建 Order，只产生 `TriggerResult` / application-level intent。
- StrategyConfig：字段冻结为 `strategy_name`、`strategy_version`、`feature_version`、`feature_config_hash`、`timeframe`、`params`、`allow_position_context`、`allow_market_snapshot`、`enabled`。`strategy_version` deterministic 且 required；`params` 必须 canonicalized，mapping key 只允许 `str`，value 只允许 stable JSON-like values：`None`、`bool`、`int`、`str`、`Decimal`、`date`、`datetime`、enum、list/tuple、dict；不得接受 float、set、object 或 arbitrary class instance；推荐生成 `strategy_config_hash`；不得使用 runtime random version；`raw_payload` 不是 source-of-truth。
- StrategyResult：`GENERATED` 必须携带 `SignalDecision`；`REJECTED_*` / `ERROR` 不得携带 `SignalDecision`；非法组合由 `StrategyService` 返回 typed `ERROR` 且不持久化 candidate/event。
- Repository / DB contract：已实现 `SignalCandidateRepository`、`SignalEventRepository`、`signal_candidates` table、`signal_events` table。`signal_id` 唯一；实现复合唯一键 `strategy_name + strategy_version + strategy_config_hash + instrument_id + timeframe + bar_ts + feature_version + feature_config_hash`。`signal_events.event_key` 是由 `signal_id + lifecycle_status + event_ts + event_reason` deterministic 生成的 sha256 幂等键，并具备唯一约束。Canonical 排除 `raw_payload`、`calculated_at`、`received_at`、`created_at` 和 DB id。
- Replay / idempotency：Strategy replay 消费 ordered `FeatureSnapshot`；same strategy config + same feature snapshot 必须得到 same `signal_id`；same canonical duplicate no-op；different canonical conflict / error；replay 不调用 OMS / Risk / Execution，不 mutate Accounting，不创建 orders。
- Risk / OMS relation：Signal 是 pre-risk intent；Risk 后续只能经 application orchestration 消费 `SignalDecision` / OrderIntent；Strategy 不知道 `RiskResult`，不理解 OMS state machine；OMS 不直接消费 `FeatureSnapshot`。
- Tests：deterministic `signal_id`、HOLD side NONE、非 HOLD required `expected_price`、confidence range、feature identity propagation、strategy config hash、duplicate same canonical、duplicate different canonical、lifecycle confirm / block / expire / trigger、replay deterministic、repository round trip、schema contract、no OMS / Risk / Execution / Accounting imports、no OrderRequest creation、`raw_payload` excluded。
- Explicit non-goals：Stage I 不实现 Order creation、Risk check、OMS integration、Execution integration、Broker adapter、runtime scheduling、paper / sim / live、portfolio optimization、ML model serving、cross-instrument strategy unless separately scoped。
- Acceptance criteria：Strategy / Signal Lifecycle Core 可 deterministic 生成、持久化、幂等 duplicate、typed conflict/error、执行 lifecycle gate 和 replay；不得越过 Strategy source-of-truth、output boundary、replay/idempotency 和 Risk / OMS 隔离规则。
- Suggested tag：`stage-i-strategy-signal-lifecycle-core`。

### Stage J: OMS Public UNKNOWN Entry

- Goal：为 UNKNOWN candidate / UNKNOWN_REPORT 提供公开、类型化、可审计的 OMS entry。
- Inputs：OMS UNKNOWN 契约、mapper `UNKNOWN_REPORT_REQUIRES_OMS_UNKNOWN_ENTRY`、orchestrator 分流结果。
- Outputs：typed UNKNOWN entry、diagnostic event、recovery handoff。
- Allowed changes：OMS service contract、UNKNOWN entry tests、docs/test matrix update。
- Forbidden changes：不新增非法状态迁移，不扩大 UNKNOWN 恢复目标，不让 adapter 自行进入 UNKNOWN。
- Required tests：UNKNOWN entry reason validation、duplicate unknown event、terminal order protection、recoverable/unrecoverable UNKNOWN、raw_payload diagnostic-only。
- Acceptance criteria：UNKNOWN_REPORT 可以被安全诊断进入或拒绝；UNKNOWN 恢复仍只走冻结目标。
- Suggested tag：`stage-j-oms-public-unknown-entry`。

### Stage K: Recovery / Replay Framework

- Goal：统一订单、执行、成交、持仓、行情、结算的重放与对账。
- Inputs：order_events、exchange reports、trades、positions、market events、settlement snapshots、UNKNOWN 语义。
- Outputs：replay runner、divergence reports、reconciliation events、recovery workflow。
- Allowed changes：replay services、fixtures、regression tests。
- Forbidden changes：不静默覆盖事实；不手工 SQL 改 OMS 状态；不通过 raw_payload 补账。
- Required tests：order replay、trade replay、position replay、market replay、settlement replay、divergence detection、duplicate event idempotency。
- Acceptance criteria：replay 与 source-of-truth 一致；分歧被 typed report 捕获。
- Suggested tag：`stage-k-recovery-replay-framework`。

### Stage L: Runtime / Infrastructure

- Goal：通过 port/adapter 引入 runtime/control plane/event bus/task system。
- Inputs：stable orchestrator、replay framework、accounting source-of-truth。
- Outputs：FastAPI control plane、Celery task workers、Kafka/Redis adapters、config/secrets provider boundary。
- Allowed changes：runtime adapter、event envelope、task config、health/readiness endpoints。
- Forbidden changes：不让 FastAPI/Celery/Kafka/Redis/KMS 污染 Domain、OMS、Risk、mapper；Redis/Kafka payload 不做 source-of-truth。
- Required tests：API command boundary、consumer idempotency、retry/dead-letter、config version, health/readiness, secret redaction。
- Acceptance criteria：runtime retry 幂等；core 可在无 runtime adapter 下继续测试。
- Suggested tag：`stage-l-runtime-infrastructure`。

### Stage M: Broker / Adapter Layer

- Goal：接入 CTP / SimNow / broker adapter。
- Inputs：runtime ports、replay/reconciliation、orchestrator、UNKNOWN entry、Fill/Trade migration。
- Outputs：broker command/query/report adapter、heartbeat/reconnect/session manager、typed query result。
- Allowed changes：adapter module、broker config/secrets requirements、sim tests、query reconciliation tests。
- Forbidden changes：adapter 不调用 OMS/Risk/DB，不改 mapper 语义，不用 raw broker message 补事实。
- Required tests：connect/login/logout、heartbeat、submit/cancel, pre-send failure, post-send uncertain, reconnect, query order/trade/account/position, SimNow dry-run。
- Acceptance criteria：SimNow 可对账；live command port 默认不启用；query reconciliation 进入 replay/recovery。
- Suggested tag：`stage-m-broker-adapter-layer`。

### Stage N: Operations / Safety / Production Readiness

- Goal：建立生产门禁、安全控制、监控、审计、runbook 和 DR。
- Inputs：runtime、broker adapter、replay framework、accounting source-of-truth。
- Outputs：metrics、audit trail、kill switch、readiness、healthcheck、deployment gates、runbook。
- Allowed changes：ops control/audit schema if needed、metrics/logging adapters、readiness/preflight tests。
- Forbidden changes：ops 不直接改业务事实；kill switch 不塞进 OMS 状态机；secret 不进入业务事件。
- Required tests：kill switch gate、audit event、health/readiness、deployment preflight、incident replay、secret redaction。
- Acceptance criteria：safety gates 可审计；UNKNOWN/recovery/position mismatch 有 runbook 和 typed workflow。
- Suggested tag：`stage-n-operations-safety-readiness`。

### Stage O: Paper / Sim / Live Rollout

- Goal：按 local -> paper -> sim -> live 递进验收。
- Inputs：Stage A-N 验收结果、runtime config、broker config、runbook、preflight checklist。
- Outputs：paper trading run、SimNow run、live preflight、controlled live enablement。
- Allowed changes：rollout config、environment gates、runbook updates、preflight automation。
- Forbidden changes：不跳级 live；不绕过 paper/sim；不以手工配置暗示环境；不在 live 前启用真实 submit/cancel。
- Required tests：paper trading tests、simulation tests、live read-only preflight、dry-run command validation、rollback drill。
- Acceptance criteria：paper/sim 通过后才可 live；live preflight 全绿且 kill switch 默认安全。
- Suggested tag：`stage-o-paper-sim-live-rollout`。

## 7. Stage Dependency Graph

核心执行与会计链：

```text
Stage A -> Stage B -> Stage C -> Stage D -> Stage E -> Stage F
```

市场与策略链：

```text
Stage G -> Stage H
Stage C + Stage G + Stage H -> Stage I
```

UNKNOWN / Recovery / Runtime / Broker / Production 主线：

```text
Stage A -> Stage J
Stage A + Stage B + Stage C + Stage F + Stage G + Stage J -> Stage K
Stage K -> Stage L
Stage K + Stage L -> Stage M
Stage M -> Stage N
Stage N -> Stage O
```

依赖说明：

- OMS Public UNKNOWN Entry 是异常回报治理能力，不是 Fill / Trade Domain Migration 的硬前置。
- Market Data / Feature Snapshot 是 Strategy / Signal Lifecycle 的前置，并应作为并行主线提前规划；Stage H 只冻结 FeatureSnapshot，不进入 Strategy / Signal。
- Stage I 实现 Strategy / Signal Lifecycle Core，但不实现 Order creation、Risk check、OMS integration 或 Execution integration。
- Risk Context / Portfolio Risk Upgrade 依赖 Position、Market Data、Strategy / Signal，不应提前硬接真实账户上下文。
- Recovery / Replay 依赖订单、成交、持仓、结算、行情和 UNKNOWN 语义。
- Broker / Adapter 必须在 Recovery / Replay 和 Runtime 边界稳定后进入。
- Operations / Safety / Production Readiness 是 Paper / Sim / Live Rollout 的硬前置。
- Broker / Adapter 完成后不得直接进入 rollout。
- Stage O 必须依赖 Stage N 的 readiness、kill switch、monitoring、audit、deployment gate、runbook 和 DR 验收。
- Paper / Sim / Live 不允许跳级。

不可跳级规则：

- 没有 Stage A，不接 OMS execution orchestration。
- 没有 Stage B，不处理真实成交事实。
- 没有 Stage C，不把持仓写成真实 source-of-truth。
- 没有 Stage G，不冻结 Strategy 所需 typed market input。
- 没有 Stage H，不冻结 Strategy 所需 FeatureSnapshot。
- 没有 Stage I，不把 Strategy / Signal Lifecycle 写成已完成。
- 没有后续 Risk Context / Portfolio Risk Upgrade，不把真实 account / portfolio / position / intraday / kill switch 风控写成已完成。
- 没有 Stage J，不应用 UNKNOWN_REPORT。
- 没有 Stage K，不接 broker query reconciliation。
- 没有 Stage L/M/N，不进入 sim/live。
- 没有 Stage N，不进入 Stage O。
- Stage O 只能按 paper -> sim -> live 递进。

## 8. Contract Amendment Policy

实现任一 stage 时，如发现冻结契约冲突，必须先停下做 Contract Amendment。

Contract Amendment 必须包含：

- 冲突的现有契约、代码、schema 或测试证据。
- 新行为的 source-of-truth 定义。
- Domain / interface / DB / OMS state machine / test matrix 是否受影响。
- 是否需要 migration。
- 旧事实如何回放或迁移。
- 明确验收测试。

禁止事项：

- 不允许通过修改测试绕过契约。
- 不允许通过 `raw_payload`、JSON、metadata、details 补 source-of-truth。
- 不允许实现偷偷改 Domain 字段、DB schema、OMS state machine。
- 不允许 adapter、runtime、ops 工具直接写订单状态。
- 不允许把未来能力写成当前事实。

允许事项：

- 明确迁移后更新 Domain freeze、module contract、schema tests、unit tests、integration tests。
- 在 stage 范围内增加必要 port/interface，只要不破坏既有边界。
- 对确实需要的 public entry 增加 typed API，但必须有测试和文档同步。

## 9. Testing Strategy

### Unit Tests

- Domain enum/model/Decimal contract。
- OMS state machine、UNKNOWN entry、recovery target。
- Risk pure rules、RiskContext input validation、account risk、portfolio exposure、position risk、intraday limit、kill switch context rule。
- Execution DTO、mapper、mapping result、report handler。
- Accounting calculation：Trade、Position、Margin、PnL、Settlement。
- Market Data data quality、FeatureSnapshot deterministic generation。
- Strategy deterministic signal id、SignalCandidate / SignalDecision validation、Signal lifecycle gate。

### Integration Tests

- OMS repository/UoW transaction。
- Orchestrator submit/cancel + OMS + Execution runtime。
- Risk -> OMS application orchestration。
- Fill/Trade -> Position -> Margin/PnL。
- Runtime adapter command boundary。

### DB Tests

- Alembic migration。
- Schema contract。
- Repository idempotency。
- Trade dedupe。
- Position live source-of-truth。
- Settlement idempotency。
- Audit schema if introduced.

### Replay Tests

- Order event replay。
- Exchange report replay。
- Trade / Position replay。
- Market data / FeatureSnapshot replay。
- Strategy / Signal replay。
- Settlement replay。
- Divergence detection and typed reconciliation result。

### Simulation Tests

- Mock exchange deterministic scenarios。
- SimNow adapter query reconciliation。
- Reconnect and heartbeat behavior。
- Post-send uncertain recovery。
- Duplicate/out-of-order reports。

### Paper Trading Tests

- No live broker submit/cancel。
- Full strategy -> signal -> risk -> OMS -> execution simulation -> accounting chain。
- Runtime worker retry idempotency。
- Metrics, audit and kill switch gate。

### Live Preflight Tests

- Read-only broker connection。
- Read-only order/trade/account/position query。
- Market data freshness。
- Secret loading and redaction。
- Clock drift。
- DB/Redis/Kafka health。
- Dry-run command validation。
- Kill switch default safe state。

### Regression Gates

每个 stage 完成后至少运行：

```bash
uv run pytest
uv run ruff check .
uv run mypy src
```

如 stage 引入 runtime、broker、market data、accounting 或 replay，还必须运行对应 stage 的专项 replay/simulation/paper/preflight tests。

### xfail Policy

- 未实现能力不得用 xfail 包装成已验收。
- xfail 只能用于已记录的外部依赖限制或明确待迁移 contract gap。
- 每个 xfail 必须有原因、解除条件和关联 stage。
- 不允许用 xfail 掩盖 source-of-truth、state machine、idempotency、raw_payload 违规。

## 10. Runtime / Infra Adoption Plan

FastAPI、Celery、Kafka、Redis、async runtime、cloud、KMS 是后续 Runtime / Infrastructure 阶段技术栈。

当前 core 不应提前依赖这些技术：

- Domain 不 import runtime/config/broker/cloud。
- OMS 不依赖 EMS、Kafka、Redis、FastAPI 或 broker。
- Risk 当前 pure core 不依赖 OMS、DB、Redis、HTTP、PositionManager、MarginEngine；后续 Risk Context / Portfolio Risk Upgrade 只能通过 application layer 注入 typed RiskContext。
- Strategy 不依赖 OMS、Risk、Execution、Broker、DB、Redis、Kafka 或 HTTP；Stage I 的 StrategyContext 和 pure Strategy interface 不携带 Repository / UoW，只有 application service 使用 signal repositories 持久化候选和 lifecycle event。
- Execution mapper 不接 broker，不写 DB，不调 OMS。
- Repository/UoW 不判断 Kafka ordering，不读取 KMS，不调用 broker。

采用顺序：

1. Stage A 先稳定 application execution boundary。
2. Stage K 稳定 recovery / replay 后，Stage L 引入 event envelope、task boundary、control plane、config/secrets provider。
3. Kafka 只传输 typed events，不替代 DB source-of-truth。
4. Celery 只调度任务，不承载领域判断。
5. Redis 只做 cache/lock/pubsub/临时状态，不做事实来源。
6. FastAPI 只做 control plane，不直接写业务事实。
7. KMS / secrets provider 只服务 secret retrieval，不把 secret 写进业务模型、事件、raw payload、logs 或 metrics。
8. Cloud deployment 必须在 Operations gates 和 live preflight 之后进入。

## 11. Risk Register

- State machine drift：adapter/orchestrator/runtime 绕过 OMS 或暗改状态机。
- Duplicate / out-of-order reports：重复回报或乱序回报导致重复状态推进或终态回退。
- Fill/trade modeling gaps：真实成交价量、trade id、fill id 被塞入 `raw_payload`。
- Position mismatch：重复成交、漏成交、平今/平昨扣减错误导致 live position 分歧。
- Margin mismatch：合约乘数、保证金率、价格源或账户资金上下文不一致。
- Settlement mismatch：结算价、交易日、夜盘归属、today/yesterday roll 不一致。
- Broker reconnect：断线重连后 post-send uncertain 被错误重试为重复下单。
- Replay divergence：生产事实流与重放结果不一致且缺少 typed divergence report。
- Config/secrets leakage：broker credential、API key、KMS 明文进入 logs、metrics、raw_payload 或 business event。
- Runtime event ordering：Kafka/Celery retry、dead-letter、late event 破坏幂等或顺序假设。
- Production safety：kill switch、readiness、deployment gate 或 runbook 缺失导致 live 风险不可控。

## 12. Immediate Next Step

本总方案没有发现 P0/P1 blocker。

下一步不是继续写文档，而是进入：

```text
Stage A: Application Execution Orchestrator Scope/Implementation
```

Stage A 的实施入口应聚焦：

- 定义 orchestrator 的 submit/cancel public API。
- 明确 orchestrator 如何读取当前 `OrderState` 并构造 `MappingContext`。
- 明确 submit 前进入 `SUBMITTING`、cancel 前进入 `CANCEL_PENDING` 的 OMS event 语义。
- 明确 `MAPPED_ORDER_EVENT`、`DUPLICATE_REPORT`、`IGNORED_REPORT`、`INSUFFICIENT_CONTEXT`、`MAPPING_ERROR`、`DOMAIN_FIELD_UNSUPPORTED`、`ENTER_UNKNOWN_CANDIDATE` 的分流行为。
- 保持 mapper pure，保持 Risk pure，不修改 DB schema，不接真实 broker。

Stage A 完成后：

- 主会计链可进入 Stage B: Fill / Trade Domain Migration。
- Stage J: OMS Public UNKNOWN Entry 可并行准备，但它是异常回报治理能力，不阻塞 Fill / Trade。
- Stage I 完成后，下一步建议进入后续 Risk Context / Portfolio Risk Upgrade 或 application orchestration 边界设计；仍不应直接跳到 Broker adapter 或 runtime infrastructure。
- 不应直接跳到 broker adapter 或 runtime infrastructure。
