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
  - 当前基线：`stage-i-strategy-signal-lifecycle-core / 780acbd`。
  - 已实现 `StrategyConfig` canonicalization / hash、`StrategyContext`、deterministic `signal_id`、`SignalCandidate`、`SignalDecision`、`TriggerResult`、signal lifecycle、canonical payload、Signal repository protocols、SQLAlchemy repositories、UoW integration、`signal_candidates` / `signal_events` migration、`StrategyService` / `SignalLifecycleService`、deterministic strategy replay 和 tests。
  - Stage I 未实现 Order creation、Risk check、OMS integration、Execution integration、Broker adapter、runtime scheduling、paper / sim / live、portfolio optimization、ML model serving、cross-instrument strategy 或 Accounting mutation。
- Trading Workflow Core 已完成。
  - 当前基线：`stage-j-trading-workflow-core / 2558e55`。
  - 已实现 `SignalDecision -> TradingRiskResult -> OrderIntent` persistence、deterministic canonical/idempotency/replay、repository/UoW 和 tests。
  - Stage J 未调用 OMS / Execution / Broker，不写 `orders` / `order_events`。
- OMS Bridge Core 已完成。
  - 当前基线：`stage-j2-oms-bridge-core / ee4aace`。
  - 已实现 `OrderIntent -> OMSService.create_order` bridge；OMS 已能创建订单记录。
  - Stage J.2 未进入 Execution / Broker / Paper / Sim / Live，不新增 schema。
- Execution Gateway Core 已完成。
  - 当前基线：`stage-k-execution-gateway-core / 94b498e`。
  - 已实现 `ExecutionCommand`、deterministic `command_id`、canonical payload/hash、`ExecutionCommandRepository`、SQLAlchemy repository、UoW integration、`execution_commands` migration、`ExecutionAdapter` Protocol、deterministic `MockExecutionAdapter`、`ExecutionGatewayService`、dry-run replay 和 tests。
  - Stage K only supports `MOCK` target；`PAPER` / `SIM` / `LIVE` typed rejected / deferred。
  - Stage K 不实现 Broker / Exchange / Fill / Trade / Accounting mutation / OMS mutation / ExecutionReport / OrderEvent。
- Execution Report Normalization Core 已完成。
  - 当前基线：`stage-l-execution-report-normalization-core / 37cad40`。
  - 已实现 `RawExecutionReport`、`NormalizedExecutionReport`、`ExecutionReportStatus`、`ExecutionReportNormalizeResult`、`OrderEventCandidate`、deterministic `source_report_hash` / `report_id`、explicit status mapping、candidate builder、`ExecutionReportRepository`、SQLAlchemy repository、UoW integration、`normalized_execution_reports` migration、`ExecutionReportNormalizer`、deterministic replay 和 tests。
  - Stage L may build typed `OrderEvent` candidate；仍不调用 `OMSService.apply_order_event(...)`，不生成 Trade / Fill ledger，不更新 Position / Accounting，不调用 Broker / CTP / SimNow。
- OMS Event Application Core 已完成。
  - 当前基线：`stage-l-execution-report-normalization-core / 37cad40`。
  - 已实现 `OMSEventApplyResultStatus`、`OMSEventApplyResult`、`OMSEventApplyContext`、deterministic `event_id`、canonical payload、candidate -> typed `OrderEvent` mapper、`OMSOrderEventApplier` Protocol、`OMSEventApplicationService`、dry-run default replay 和 tests。
  - Stage L.2 只推进 OMS `OrderStatus`；不生成 Trade，不生成 Fill ledger，不更新 Position / Accounting / Margin / PnL / Settlement，不调用 Broker，不进入 Runtime。
  - Stage L.2 不新增 schema；OMS event ledger 继续使用现有 `order_events`。
- OMS-to-Trade Bridge Core 已完成。
  - 当前基线：`stage-l3-oms-to-trade-bridge-core / 957cf89`。
  - Stage L.3 已实现 `NormalizedExecutionReport / applied OMS OrderEvent proof -> typed Trade fact -> TradeRepository` 桥接边界。
  - 已新增 migration `0014_stage_l3_oms_to_trade_bridge.py`，只扩展 `trades` 和 `normalized_execution_reports` 的 L.3 typed lineage / identity / fee input 字段；未创建第二套 trade ledger。
  - 已实现 deterministic trade identity、`TradeBridgeResult`、OMS-to-Trade bridge service、replay、TradeRepository L.3 aliases 和 canonical conflict checks。
  - Stage L.3 不更新 Position / Margin / PnL / Settlement，不做 broker reconciliation，不进入 Runtime。
- Stage L.4 Trade-to-Position Handoff 已完成。
  - 当前基线：`stage-l4-trade-to-position-handoff / 6c26cbd`。
  - Stage L.4 已实现 `typed Trade fact -> PositionManager.apply_trade(...) -> Position projection / PositionEvent` handoff。
  - Stage L.4 未新增 schema，未创建第二套 position ledger。
  - Stage L.4 不更新 Margin / PnL / Settlement / AccountSnapshot，不进入 Broker / Runtime。
- Stage L.5 Position-to-Accounting Implementation 已完成。
  - 当前基线：`stage-l5-position-to-accounting-handoff / 3f1c5a6`。
  - Stage L.5 已实现 `Trade-applied Position / PositionEvent -> Accounting input snapshot -> MarginEngine / PnLEngine -> MarginSnapshot / PnLSnapshot -> SettlementEngine later` 最小闭环。
  - Stage L.5 新增 migration `0015_stage_l5_position_to_accounting.py`，只扩展 `margin_snapshots` / `pnl_snapshots`；不进入 Broker / Runtime / live。
- Stage M Runtime / Infrastructure Core 已完成。
  - 当前基线：`stage-m-runtime-infrastructure-core / b443249`。
  - Stage M 已实现 thin Runtime / Infrastructure package、runtime config、service graph、lifecycle、disabled-by-default scheduler、dry-run replay coordinator、read-only health checks 和 boundary tests。
  - Stage M 未实现 Broker / CTP / SimNow / live adapter，不新增 schema，不改变 business source-of-truth。

当前尚未实现为业务能力的部分：

- Application Execution Orchestrator。
- RiskContext、portfolio/account risk、intraday limits、kill switch risk。
- Recovery / Replay Framework。
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
5. Trading Workflow application layer 组装 `SignalDecision`、Strategy / Position / Portfolio / Account / Margin / RiskConfig / Calendar typed context。
6. RiskEvaluator deterministic evaluate 并返回 Stage J `TradingRiskResult`。
7. 只有 `ACCEPT` / `REDUCE` 进入 `OrderIntentBuilder`；`REJECT` / `BLOCK` / `UNKNOWN` 不创建 `OrderIntent`，不调用 OMS。
8. `OrderIntentBuilder` 生成 deterministic `OrderIntent` 和 `intent_id`。
9. Stage J 持久化 `OrderIntent`；`OrderIntent` 不是 Order，不承载 OMS state。
10. Stage J.2 OMS bridge adapter 可在显式调用时把 `OrderIntent` 转入 OMS 创建订单。
11. Stage K Execution Gateway 消费 OMS Order / OrderState，生成 deterministic `ExecutionCommand`。
12. Stage K Core 可持久化 `ExecutionCommand`，并只 dispatch 到允许的 execution adapter；contract freeze 不提交真实 broker。
13. Future Execution Adapter 返回 typed `ExecutionCommandResult`；adapter accepted 不表示 exchange accepted。
14. Future broker / exchange report 必须先 normalized 为 typed `ExecutionReport` / `ExchangeReport`，再进入 mapper。
15. ExecutionReportHandler 调用 pure mapper，得到 typed `MappingResult`。
16. 对 `MAPPED_ORDER_EVENT`，Orchestrator 将 `OrderEvent` 交回 `OMSService.apply_order_event(...)`。
17. OMS 根据状态机、幂等、乱序、终态保护和 UNKNOWN 规则应用或拒绝事件。
18. 当 OMS 已应用 `PARTIALLY_FILLED` / `FILLED` 状态且 normalized report 提供成交价格、数量和稳定成交身份时，Stage L.3 OMS-to-Trade Bridge 才能创建 typed `Trade` fact。
19. `TradeRepository` 幂等持久化 Trade ledger；same identity + same canonical no-op，same identity + different canonical conflict。
20. Stage L.4 Trade-to-Position application 只消费去重后的 typed `Trade` fact，并通过 `PositionManager.apply_trade(...)` 更新 live `positions`，处理开仓、平今、平昨和 today/yesterday bucket，并写入 `position_events` 作为 applied-trade audit。
21. Margin Engine 基于 Position、instrument rules、account context 计算保证金。
22. PnL Engine 基于 Trade、Position、last price、settlement price 计算 realized / unrealized PnL。
23. Settlement Engine 在交易日边界执行结算、settlement price finalization、Margin fact finalization、PnL fact finalization 和 today -> yesterday roll。
24. Recovery / Replay Framework 可按 source-of-truth 重放 order events、execution commands、execution reports、trades、positions、market events、settlement snapshots。
25. Monitoring / Audit 记录 metrics、structured logs、control actions、replay divergence、deployment gate 和 incident response。

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
- Position 禁止消费 `OrderStatus`、`OrderEvent`、`ExchangeReport`、`NormalizedExecutionReport`、`OrderEventCandidate`、broker state 或 `raw_payload`。
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
- `MarginSnapshot` canonical payload 字段包括 `account_id`、`instrument_id`、`position_version`、`trading_day`、`config_hash`、`rule_id`、`rule_version`、`long_qty`、`short_qty`、`price`、`contract_multiplier`、`initial_margin`、`maintenance_margin`、`margin_used`、`available_cash`、`equity`、`calculation_key`。`calculated_at` 持久化但不参与 canonical equality；`raw_payload` 不参与 canonical。
- Replay 使用同一 calculator，以 Position projection + MarginRule + AccountContext + typed price input 重算。Stage L.5 后，同一 `account_id + instrument_id + position_version + trading_day + config_hash` 的 existing snapshot 是该 accounting identity 的 margin fact；同一 `calculation_key` canonical same 时 no-op / duplicate snapshot accepted，canonical different 时返回 `CONFLICT` / divergence；`calculation_key` 不同但同一 accounting identity 经济事实一致时 no-op，经济事实不一致时返回 `CONFLICT` / divergence，不得追加第二条 snapshot 或更新 `positions.margin_used`。Replay 不更新 Position qty/avg。

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
- Stage E 已新增 `PnLSnapshotRepository` 和 `pnl_snapshots` table；`pnl_snapshots` canonical payload 使用 deterministic `calculation_key`，不使用 `calculated_at`；`raw_payload` 不允许进入 PnL facts。Stage L.5 后，同一 `account_id + instrument_id + position_version + trading_day + config_hash` 不得写入第二条不同 PnL fact；除 `calculation_key` 外经济事实一致时 no-op，经济事实不一致时 conflict。
- Replay 使用同一 calculator 和 deterministic `calculation_key`。Same canonical no-op，different canonical 返回 `CONFLICT` / divergence；即使 `calculation_key` 不同，同一 accounting identity 的经济事实一致也必须 no-op，经济事实不一致必须 conflict；replay 不得静默覆盖 position PnL fields。Replay divergence 判定必须读取 repository / UoW 内真实 live Position row；调用方传入的 Position 只作为 calculator input。若 live position PnL 与 snapshot divergence，除非当前 transaction 正在更新它，否则必须返回 `CONFLICT`。
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

### Stage J: Trading Workflow Core

- Goal：实现 Strategy / Signal -> TradingRiskResult -> OrderIntent 的 Trading Workflow Core；本阶段停止在 `OrderIntent` persistence，不调用 OMS / Execution / Broker，不写 `orders` / `order_events`，不进入 Broker / Paper / Sim / Live。
- Inputs：`SignalDecision`、`StrategyConfig`、`PositionContext`、`PortfolioContext`、`AccountContext`、`MarginSnapshot`、`RiskConfig`、`TradingCalendar` / `Session`。
- Forbidden inputs：`OrderStatus`、`OrderEvent`、`ExchangeReport`、`raw_payload`、Broker state、OMS state machine internals。
- Outputs：`TradingRiskResult`、`OrderIntent`、repository/UoW persistence、deterministic replay 和 workflow/idempotency/boundary tests；`OrderIntent` 不是 Order。
- Implemented changes：Stage J domain enums/models、pure `RiskEvaluator` Protocol、pure `OrderIntentBuilder`、canonical payload/id helpers、`TradingRiskResultRepository` / `OrderIntentRepository` Protocol、SQLAlchemy repositories、UoW integration、`0011_stage_j_trading_workflow_core` migration、`TradingWorkflowService`、`TradingWorkflowReplay`、unit/integration/boundary tests 和 docs update。
- Forbidden changes：不改 OMS implementation / state machine，不调用 `OMS.create_order`，不调用 Execution，不接 Broker / Runtime，不写 `orders` / `order_events`，不做 portfolio optimization。
- `RiskResultStatus`：冻结为 `ACCEPT`、`REDUCE`、`REJECT`、`BLOCK`、`UNKNOWN`。
- `TradingWorkflowContext`：必须携带 `requested_quantity`、`risk_config_hash` 和由上层应用基于 typed deterministic inputs 供应的 `evaluation_context_hash`；Stage J 不从 DB 或 `raw_payload` 计算该 hash。
- `TradingRiskResult`：字段冻结为 `signal_id`、`risk_result_id`、`evaluation_context_hash`、`risk_status`、`risk_reason`、`risk_level`、`requested_quantity`、`approved_quantity`、`max_quantity`、`expected_margin`、`expected_notional`、`config_hash`、`evaluation_ts`。`TradingRiskResult` 必须 deterministic；`raw_payload` 和非 deterministic `evaluation_ts` 不参与 canonical/id；same inputs -> same result。
- `OrderIntent`：字段冻结为 `intent_id`、`signal_id`、`risk_result_id`、strategy identity、instrument identity、`side`、`offset`、`quantity`、`price`、`order_type`、`tif`、`expected_margin`、`expected_notional`、`intent_reason`。`intent_id` 必须 deterministic。
- Workflow：`SignalDecision -> RiskEvaluator.evaluate(...) -> TradingRiskResult -> OrderIntentBuilder -> OrderIntent persistence`。只有 `ACCEPT` / `REDUCE` 可进入 `OrderIntent`；`REJECT` / `BLOCK` / `UNKNOWN` 不创建 `OrderIntent`，不调用 OMS。
- Quantity reduction：`ACCEPT` 必须满足 approved quantity 等于 original requested quantity；`REDUCE` 必须满足 reduced quantity `> 0` 且 `< original requested quantity`；若 reduced quantity 等于 requested quantity，normalize 为 `ACCEPT`；若 reduced quantity `<= 0`，normalize 为 `REJECT`；若 approved quantity 大于 requested quantity，返回 `ERROR` 且不持久化。
- Decimal facts：`requested_quantity`、`approved_quantity`、`max_quantity`、`expected_margin`、`expected_notional` 均为 required Decimal。`REJECT` / `BLOCK` / `UNKNOWN` 使用 `Decimal("0")` 表示明确 none/blocked；`None` 不允许进入 Stage J core facts。
- Idempotency：`RiskResult` same canonical -> no-op，different canonical -> conflict/error；`OrderIntent` same canonical -> no-op，different canonical -> conflict/error。`signal_id + config_hash + evaluation_context_hash` 必须得到 deterministic result。
- Replay：same `SignalDecision`、`RiskConfig`、`PositionContext`、`PortfolioContext`、`MarginSnapshot` 得到 same `TradingRiskResult` 和 same `OrderIntent`；replay 不调用 OMS、不调用 Execution、不修改 Accounting。
- Boundaries：Strategy 不创建 `OrderIntent`、不调用 OMS；TradingWorkflowService 依赖 `RiskEvaluator` Protocol，不依赖 concrete RiskEngine；Risk 不知道 Execution；Execution 不知道 Signal；OMS 不消费 `FeatureSnapshot`、不消费 `StrategyConfig`；Broker 不参与 Stage J。
- Repositories：已实现 `TradingRiskResultRepository` 和 `OrderIntentRepository`。唯一键分别为 `risk_result_id`、`intent_id`。Canonical 包含 `evaluation_context_hash` / `requested_quantity`，并排除 `raw_payload`、`created_at`、`received_at`、非 deterministic `evaluation_ts`。
- Tests：覆盖 `ACCEPT`、`REDUCE`、`REJECT`、`BLOCK`、`UNKNOWN`；deterministic TradingRiskResult；deterministic OrderIntent；REDUCE quantity rule；REJECT/BLOCK/UNKNOWN no OMS call；replay deterministic；duplicate same canonical；duplicate different canonical；no OMS/Execution/Broker imports；no raw_payload facts。
- Explicit non-goals：Execution submit、Broker adapter、Paper、Sim、Live、Exchange connectivity、OMS state machine changes、Portfolio optimization、OrderIntent -> OMS bridge。
- Acceptance criteria：Trading Workflow Core 可 deterministic 生成并持久化 `TradingRiskResult` / `OrderIntent`，可 replay，且不越过 OMS / Execution / Broker 边界。
- Suggested tag：`stage-j-trading-workflow-core`。

### Stage J.2: OMS Bridge Core

- Goal：实现 `OrderIntent -> OMS.create_order` bridge；本阶段只进入 OMS create-order boundary，不进入 Execution / Broker / Runtime，不改 schema。
- Baseline：`stage-j-trading-workflow-core / 2558e55`；Stage J 已持久化 `TradingRiskResult` / `OrderIntent`，OMS Core 已存在 `create_order` / `apply_order_event` / `recover_order`，Stage J 本身仍不调用 OMS。
- Implemented changes：`OMSBridgeResultStatus`、`OMSBridgeContext`、`OMSBridgeResult`、deterministic `client_order_id`、bridge canonical payload/hash、`OMSOrderCreator` / `OMSOrderLookup` Protocol、`OMSBridgeService`、dry-run `replay_oms_bridge`、unit/integration/boundary tests 和 docs update。
- Source-of-truth inputs：`OrderIntent`、`TradingRiskResult` reference / `risk_result_id`、从 `OrderIntent` 复制的 Strategy / Signal identity、从 `OrderIntent` 复制的 instrument identity、application layer 提供的 typed account / order config。
- Forbidden inputs：不得直接消费 `FeatureSnapshot`、不得直接消费 `SignalDecision`（除非经 `OrderIntent` lineage）、不得调用 concrete `RiskEngine`、不得消费 `raw_payload`、Broker state、`ExchangeReport`、`OrderEvent`、`ExecutionResult` 或 Accounting tables。
- Outputs：OMS `create_order` input / `OrderRequest` adapter object、`OMSService.create_order(...)` result、`OMSBridgeResult`。
- Forbidden outputs / effects：不得调用 Execution，不得调用 Broker，不得 submit order to exchange，不得修改 Accounting，不得 recompute Risk，不得 mutate Strategy / Signal / Trading Workflow facts。
- Mapping：`OrderIntent.intent_id` deterministic 派生 `client_order_id`；`account_id` 来自 application context / order config；`instrument_id`、`trade_instrument_id`、`exchange`、`side`、`offset`、`quantity`、`price`、`order_type`、`tif` 来自 `OrderIntent`；bridge payload 固定 `source = "oms_bridge"`，`external_ref` / `intent_ref = intent_id`，metadata 仅 diagnostic。
- Idempotency：同一 `intent_id` + same canonical bridge payload -> duplicate/no-op 并返回 existing OMS order reference；同一 `intent_id` + different canonical bridge payload -> typed conflict/error。Duplicate/conflict 判断优先使用 existing bridge `bridge_payload_hash`，hash 缺失时使用 `client_order_id` / `intent_id` / `risk_result_id` lineage + OMS request canonical fallback，不得只比较 OMS request equality。`client_order_id` 必须 deterministic from `intent_id`，不得使用 random UUID 或 timestamp。
- Risk gate boundary：Bridge 必须验证 `OrderIntent` 引用 `ACCEPT` / `REDUCE` 的 `TradingRiskResult`、`risk_result_id` present、`quantity > 0`，且如果未来 `OrderIntent` 存在 status，不得接受 rejected / blocked / unknown intent。Bridge 不得 call RiskEngine、不 rerun risk、不 override approved quantity、不 increase quantity、不修改 side/price 绕过风险。
- OMS boundary：Bridge 只允许调用 `OMSService.create_order`。不得调用 `apply_order_event`、不得调用 Execution / Broker；`apply_risk_result` 也不属于 bridge 常规路径，除非未来 OMS create-order design 明确要求并通过单独验收。Bridge 调用 OMS 时输入已是 upstream risk accepted / reduced，不在本阶段修改 OMS state machine。
- `OMSBridgeResultStatus`：冻结为 `CREATED`、`DUPLICATE`、`REJECTED_INVALID_INTENT`、`REJECTED_RISK_NOT_ACCEPTED`、`CONFLICT`、`ERROR`。
- `OMSBridgeResult`：字段冻结为 `status`、`intent_id`、`client_order_id`、`order_id | None`、`reason`、`bridge_payload_hash`、可选 `created_at` / `bridge_ts` audit。
- Audit / repository：V1 不新增 `OMSBridgeEventRepository` / `OMSBridgeAuditRepository`，不新增 `oms_bridge_events` table，不新增 migration。Bridge 依赖 OMS `orders.client_order_id` 幂等、Order lookup out-of-band bridge lineage metadata 和 `OMSBridgeResult.bridge_payload_hash`；未来如 audit gap 明确，可单独增加 bridge audit repository/table。
- Replay：Bridge replay 消费 ordered `OrderIntent`；same intent -> same `client_order_id`；same canonical -> no-op；different canonical -> typed conflict。Replay 不调用 Execution/Broker，不修改 Accounting；默认应为 dry-run。任何 live replay 调用 OMS 都必须由后续显式 flag / gate 冻结。
- Boundaries：Strategy 不参与；Risk 已在 upstream 完成；TradingWorkflow 只创建 `OrderIntent`；OMS Bridge 只转换并调用 OMS create-order；OMS 在 create-order 后 owns order lifecycle；Execution、Broker、Accounting 不参与。
- Tests：deterministic `client_order_id`、field mapping、missing `risk_result_id` reject、risk not accepted reject、`quantity <= 0` reject、duplicate same canonical no-op、duplicate different OMS payload conflict、OMS creator error -> controlled `ERROR`、no RiskEngine call、no Execution/Broker call、no Accounting mutation、replay dry-run deterministic、`raw_payload` excluded、no bridge migration/table。
- Explicit non-goals：Execution submit、Broker adapter、Paper / Sim / Live、Exchange connectivity、OMS state machine redesign、Risk recalculation、Accounting mutation、Portfolio optimization、Runtime scheduling。
- Acceptance criteria：Bridge 可 deterministic 将 valid `OrderIntent` 映射为 OMS `OrderRequest` 并通过 `OMSOrderCreator` 调用 `create_order`；duplicate same OMS payload no-op；conflict/error typed 返回；dry-run replay 默认不调用 OMS；Execution / Broker / Runtime / Accounting / Risk recalculation 全部出界。
- Suggested tag：`stage-j2-oms-bridge-core`。

### Stage K: Execution Gateway Core

- Goal：实现 OMS Order -> ExecutionCommand 的 Execution Gateway Core；本阶段只支持 `MOCK` target，不实现 Broker / Paper / Sim / Live。
- Baseline：`stage-j2-oms-bridge-core / ee4aace`；OMS Bridge 已能将 `OrderIntent` 转为 OMS `create_order` 并创建订单记录。
- Implemented changes：`ExecutionCommand`、`ExecutionCommandResult`、`ExecutionGatewayResult`、`ExecutionTarget` / `ExecutionCommandType` / result status enums、deterministic `command_id`、canonical payload/hash、`ExecutionCommandRepository` Protocol、SQLAlchemy repository、UoW integration、`0012_stage_k_execution_gateway_core` migration、`ExecutionAdapter` Protocol、deterministic `MockExecutionAdapter`、`ExecutionGatewayService`、dry-run `replay_execution_gateway`、unit/integration/boundary tests 和 docs update。
- Source-of-truth inputs：OMS Order / `OrderState`、OMS `order_id`、`client_order_id`、从 OMS Order 复制的 instrument identity、`side` / `offset` / `quantity` / `price` / `order_type` / `tif`、typed execution config、trading session / calendar context。
- Forbidden inputs：不得消费 `FeatureSnapshot`、不得消费 `SignalDecision`、不得直接消费 `OrderIntent`（只允许通过 OMS Order metadata lineage 追溯）、不得调用 `RiskEngine`、不得消费 `raw_payload`、不得把 Broker state 当 source-of-truth、不得把未 normalized 的 `ExchangeReport` 当 source-of-truth、不得读取 Accounting tables。
- Outputs：`ExecutionCommand`、`ExecutionCommandResult`；`ExecutionReport` 只作为后续 normalized broker/exchange report 契约。
- Forbidden effects：不得直接 mutate OMS state，除非后续通过 `OMS.apply_order_event` path；不得 mutate Accounting；不得调用 Strategy / Risk；不得读取 Broker state 当事实；Stage K contract 不提交真实 Broker。
- `ExecutionCommand` fields：`command_id`、`order_id`、`client_order_id`、`account_id`、`instrument_id`、`trade_instrument_id`、`exchange`、`side`、`offset`、`quantity`、`price`、`order_type`、`tif`、`command_type`、`execution_target`、`command_payload_hash`、`created_at`。
- `command_type`：`SUBMIT_ORDER`；`CANCEL_ORDER` 为 future / deferred，除非单独实现。
- `execution_target`：冻结为 `MOCK`、`PAPER`、`SIM`、`LIVE`。Stage K Core only supports `MOCK`; `PAPER` / `SIM` / `LIVE` typed rejected / deferred。
- Deterministic identity：`command_id` 必须 deterministic from `order_id + command_type + execution_target`；不得使用 UUID、timestamp 或 DB id。同一 order + same target 必须得到同一 `command_id`。
- Canonical payload：必须包含 `order_id`、`client_order_id`、`account_id`、instrument identity、`side`、`offset`、`quantity`、`price`、`order_type`、`tif`、`command_type`、`execution_target`；必须排除 `raw_payload`、`created_at`、`received_at`、broker response 和 DB id。
- Idempotency：same `command_id` + same canonical -> duplicate / no-op；same `command_id` + different canonical -> conflict / error。同一 OMS order 不得为同一 target 生成多个 submit commands。
- Service boundary：已实现 `ExecutionGatewayService` 接收 OMS Order / `OrderState` 和 typed execution config，验证订单可执行，构造 `ExecutionCommand`，持久化 command，并只在新命令且非 dry-run 时 dispatch 到允许 execution adapter。
- Repository：已实现 `ExecutionCommandRepository` 和 `execution_commands` table，因为 command 是 broker 前的事实 / audit boundary。
- Repository methods：`append_execution_command(command)`、`get_by_command_id(command_id)`、`list_by_order_id(order_id)`、`list_by_target(execution_target, start_ts, end_ts)`。
- Repository uniqueness / indexes：`UNIQUE(command_id)`；索引 `order_id`、`client_order_id`、`execution_target`、`created_at`。
- Adapter boundary：已冻结 `ExecutionAdapter.submit(command) -> ExecutionCommandResult`。Adapter 必须返回 typed result，不得返回 raw broker response 作为事实。
- Stage K Core adapter scope：已实现 deterministic `MockExecutionAdapter`；不得实现 CTP / SimNow / real broker，不得要求网络。
- `ExecutionCommandResult` fields：`command_id`、`order_id`、`status`、`reason`、`adapter_order_ref | None`、`submitted_at | None`、diagnostic-only `raw_payload`。
- `ExecutionCommandResult.status`：`ACCEPTED_BY_ADAPTER`、`REJECTED_BY_ADAPTER`、`DUPLICATE`、`CONFLICT`、`ERROR`。
- OMS relation：Execution Gateway 不直接修改 OMS；后续 `ExecutionReport` 必须先 normalized 为 `OrderEvent`，再由 `OMSService.apply_order_event(...)` 应用。
- Replay：same OMS order + same target -> same `ExecutionCommand`；same canonical -> duplicate / no-op；different canonical -> conflict / error；默认 dry-run；除非显式 live flag，不得 submit adapter / broker；replay 不 mutate OMS / Accounting。
- Boundaries：OMS owns order state；Execution Gateway owns command creation / adapter dispatch；Broker 不在 Stage K；Accounting 不参与；Risk 已 upstream 完成；Strategy 不参与。
- Tests：覆盖 deterministic `command_id`、canonical excludes raw/timestamps、duplicate same canonical、duplicate different canonical conflict、unsupported `execution_target` reject、unsupported `CANCEL_ORDER` reject、OMS order not executable reject、mock adapter submit result、replay dry-run no adapter call、explicit replay submit flag、repository round trip、schema contract、no Broker/CTP/SimNow imports、no Accounting mutation、no OMS direct state mutation。
- Explicit non-goals：real Broker adapter、CTP、SimNow、live trading、exchange connectivity、fill matching、trade generation、accounting update、broker reconciliation、runtime scheduler、Kafka / FastAPI / Celery。
- Acceptance criteria：Execution Gateway contract 可从 eligible OMS Order deterministic 生成 `ExecutionCommand`，可通过 repository 幂等持久化，adapter result 仅为 typed diagnostic/dispatch result，且不越过 OMS / Accounting / Broker / Strategy / Risk 边界。
- Suggested tag：`stage-k-execution-gateway-contract-freeze`。

### Stage L: Execution Report Normalization Core

- Goal：实现 Execution Report Normalizer Core；把 typed adapter report input 归一化为 deterministic `NormalizedExecutionReport`，并构造 optional OMS `OrderEvent` candidate。
- Baseline：`stage-k-execution-gateway-core / 94b498e`；Execution Gateway Core 已完成，Stage K only supports `MOCK` target，`ExecutionCommandResult` 只表示 adapter accepted / rejected，不表示 exchange accepted / fill / trade。
- Implemented changes：domain objects、canonical raw / normalized payload、deterministic `source_report_hash`、deterministic `report_id`、explicit status mapping、`OrderEventCandidate` builder、repository Protocol、SQLAlchemy repository、UoW integration、`0013_stage_l_execution_report_normalization` migration、`ExecutionReportNormalizer` service、`replay_execution_reports`、unit / integration / boundary tests 和 docs update。
- Source-of-truth inputs：`ExecutionCommand`、`ExecutionCommandResult`、typed adapter report input、adapter identity、`command_id` / `order_id` / `client_order_id` lineage、typed timestamp normalization rule。
- Forbidden inputs：不得消费 `FeatureSnapshot`、`SignalDecision`、`TradingRiskResult`、`OrderIntent` mutation、Accounting tables、Position tables、Margin / PnL / Settlement、Broker state as source-of-truth、`raw_payload` as facts。
- RawExecutionReport：冻结 `raw_report_id`、`adapter_name`、`execution_target`、`command_id`、`order_id`、`client_order_id`、`adapter_order_ref`、`exchange_order_id | None`、`report_type`、Decimal `filled_qty`、Decimal `fill_price | None`、Decimal `cumulative_filled_qty`、Decimal `remaining_qty`、`report_ts`、`received_at`、diagnostic-only `raw_payload`；adapter must normalize external ms / us / ns timestamps before domain if possible；no float。
- NormalizedExecutionReport：冻结 deterministic `report_id`、`raw_report_id`、`adapter_name`、`execution_target`、`command_id`、`order_id`、`client_order_id`、`adapter_order_ref`、`exchange_order_id | None`、`execution_status`、Decimal fill fields、`report_ts`、`normalized_at`、`reason | None`、`source_report_hash`。
- `ExecutionReportStatus`：`SUBMITTED`、`ACKED`、`PARTIALLY_FILLED`、`FILLED`、`REJECTED`、`CANCELED`、`ERROR`；它不是 OMS `OrderStatus`。
- OMS mapping：`ACKED -> ACKED`、`PARTIALLY_FILLED -> PARTIALLY_FILLED`、`FILLED -> FILLED`、`REJECTED -> REJECTED_BY_EXCHANGE`、`CANCELED -> CANCELED`；Normalizer may create typed `OrderEvent` candidate，但不得直接调用 `OMSService.apply_order_event(...)`。
- Fill / Trade boundary：fill-like report fields 只是 execution-state facts，不是 Trade facts；Stage L 不创建 Trade ledger、不生成 Fill ledger、不更新 Position、不更新 Margin / PnL / Settlement、不生成 accounting facts。
- Repository / migration：已实现 `ExecutionReportRepository`、SQLAlchemy repository、UoW integration 和 `normalized_execution_reports` table；未创建 `raw_execution_reports`。Methods 为 `append_normalized_report(report)`、`get_by_report_id(report_id)`、`get_by_raw_report_id(raw_report_id)`、`list_by_order_id(order_id)`、`list_by_command_id(command_id)`、`list_by_status(execution_status, start_ts, end_ts)`；unique `report_id` and unique `raw_report_id`；indexes `order_id`、`command_id`、`client_order_id`、`execution_status`、`report_ts`。Stage N forward fix migration `0016_stage_n_report_identity_conflict.py` only strengthens the existing `normalized_execution_reports` ledger source identity and does not create broker tables。
- Replay / idempotency：`raw_report_id` is the first-class source report identity；adapter-provided broker source id is preferred，and deterministic mock-derived identity is allowed only when all identity inputs are typed。`report_id` deterministic；same `raw_report_id` + same canonical -> duplicate / no-op；same `raw_report_id` + different canonical -> conflict before a second normalized report persists；canonical excludes `raw_payload`、`received_at`、`normalized_at`、DB id；report replay consumes ordered `RawExecutionReport` and must not call OMS / Accounting / Trade generation。
- Tests：Decimal-only raw report、deterministic `report_id`、`source_report_hash`、status mapping、candidate mapping、duplicate same canonical、conflict different canonical、`raw_payload` excluded、replay deterministic、repository round trip、UoW exposure、schema contract、no `OMSService.apply_order_event(...)`、no Trade / Fill / Position / Accounting mutation、no Broker / CTP / SimNow dependency。
- Explicit non-goals：Broker adapter、CTP / SimNow / live、Trade ledger generation、Fill ledger generation、Position update、Accounting update、OMS direct mutation unless separately scoped、Runtime scheduler、Kafka / FastAPI / Celery。
- Acceptance criteria：typed adapter report input 可 deterministic normalized；duplicate same canonical no-op；different canonical conflict；candidate-only OMS boundary；no Trade / Fill / Position / Accounting / Broker side effects。
- Suggested tag：`stage-l-execution-report-normalization-core`。

### Stage L.2: OMS Event Application Core

- Goal：实现 `OrderEventCandidate -> OMS.apply_order_event` 应用契约；只推进 OMS `OrderStatus`，不进入成交、会计、broker 或 runtime。
- Baseline：`stage-l-execution-report-normalization-core / 37cad40`；Stage L 已能从 `NormalizedExecutionReport` deterministic 构造 optional `OrderEventCandidate`，但不调用 OMS。
- Implemented changes：`OMSEventApplyResultStatus`、`OMSEventApplyResult`、`OMSEventApplyContext`、deterministic `event_id`、canonical payload、candidate -> typed `OrderEvent` mapper、`OMSOrderEventApplier` Protocol、`OMSOrderEventLookup` read-only Protocol、`OMSEventApplicationService`、dry-run default `replay_oms_order_events`、unit / boundary tests 和 docs update。
- Source-of-truth flow：`NormalizedExecutionReport -> OrderEventCandidate -> typed OrderEvent -> OMSService.apply_order_event(...) -> OMS OrderState transition`。
- Allowed inputs：`NormalizedExecutionReport`、`OrderEventCandidate`、current OMS `OrderState`、typed application context。
- Forbidden inputs：`FeatureSnapshot`、`SignalDecision`、`TradingRiskResult`、`OrderIntent` mutation、`raw_payload` facts、Broker state、Accounting tables、Position tables、Margin / PnL / Settlement。
- Event identity：`event_id` deterministic from `report_id + order_id + execution_status + cumulative_filled_qty + report_ts`。禁止 UUID、timestamp-now 或 DB id。
- Candidate mapping：Stage L normalizer normally emits candidates only for `ACKED`、`PARTIALLY_FILLED`、`FILLED`、`REJECTED` 和 `CANCELED`。Stage L.2 defensively maps manually supplied `SUBMITTED -> NO_OP` and `ERROR -> REJECTED_NO_EVENT` without calling OMS。
- OMS boundary：只有 Stage L.2 application service may call `OMSService.apply_order_event(...)`。不得调用 `OMSService.create_order(...)`、Execution adapter、Broker、Accounting、PositionManager 或 TradeRepository。
- Idempotency：same candidate -> same `OrderEvent` -> same OMS transition / no-op；before live OMS apply, Stage L.2 performs deterministic event-key lookup and typed canonical precheck；existing same canonical -> `DUPLICATE` / no-op；different candidate same `event_id` or missing existing typed canonical -> `CONFLICT` before OMS apply；terminal order protection remains owned by OMS state machine。
- Replay：same normalized report -> same candidate -> same `OrderEvent`。Replay may call OMS only in explicit OMS replay mode；default review recommendation is dry-run first，live apply requires explicit flag。Live replay must complete full batch canonical preflight before any OMS apply；batch conflict returns `CONFLICT` and performs no OMS apply。
- Repository decision：Stage L.2 不新增 table，不新增 migration；复用现有 `order_events` 作为 OMS event ledger。如果后续需要额外 audit，必须另开 contract amendment。
- Explicit non-goals：No Trade ledger，No Fill ledger，No Position update，No Margin / PnL / Settlement update，No Broker / CTP / SimNow，No Runtime / Kafka / Celery / FastAPI。
- Acceptance criteria：application boundary 能 deterministic 把 mappable candidate 应用到 OMS；no-op status 不调用 OMS；duplicate same candidate no-op；same `event_id` different payload typed conflict；所有非 OMS 状态副作用均出界。
- Suggested tag：`stage-l2-oms-event-application-core`。

### Stage L.3: OMS-to-Trade Bridge Core

- Goal：实现 OMS confirmed filled event / `NormalizedExecutionReport` -> typed `Trade` fact 的桥接边界，只到 `TradeRepository` persistence。
- Baseline：`stage-l2-oms-event-application-core / 54d6fc8`；Stage L.2 已闭合 Strategy -> OMS OrderState，但 Strategy -> Trade / Accounting 尚未闭环。
- Migration：`0014_stage_l3_oms_to_trade_bridge.py`（revision `0014_stage_l3_oms_trade_bridge`）只扩展 existing `trades` ledger 和 `normalized_execution_reports` typed report input；不新增第二套 trade ledger，不改 OMS / Position / Margin / PnL / Settlement schema。
- Source-of-truth flow：`NormalizedExecutionReport / OrderEventCandidate / applied OMS OrderEvent -> OMS-to-Trade Bridge -> typed Trade fact -> TradeRepository persistence -> PositionManager handoff later`。
- Allowed inputs：`PARTIALLY_FILLED` / `FILLED` 的 `NormalizedExecutionReport`、已应用 OMS `OrderEvent` 或兼容 `OrderState` proof、existing OMS order identity、typed instrument/account identity、typed fee input if available、typed `exchange_trade_id` / fill identity if available。
- Forbidden inputs：`raw_payload` facts、Broker state as truth、`FeatureSnapshot`、`SignalDecision`、`TradingRiskResult`、`OrderIntent` mutation、Position table、Margin / PnL / Settlement、Runtime / Kafka / Celery / FastAPI。
- Required gate：只有 normalized report status 是 `PARTIALLY_FILLED` / `FILLED`、OMS proof 与当前 report 严格绑定或 `OrderState` 可证明兼容 filled state、`order_id` / `client_order_id` lineage 匹配、`filled_qty > 0`、`fill_price > 0` 且 trade identity 稳定时，才允许创建 Trade；`ACKED`、`SUBMITTED`、`REJECTED`、`CANCELED`、`ERROR`、adapter accepted only 和 un-applied candidate 都不得创建 Trade。
- OMS proof binding：applied `OrderEvent` proof 必须来自 `EXECUTION_REPORT_NORMALIZER`，且 `report_id`、`execution_status` 映射后的 OMS status、`filled_qty`、`fill_price`、`cumulative_filled_qty`、`report_ts` 和 `order_id` 必须与当前 `NormalizedExecutionReport` 一致；typed proof 字段缺失时拒绝，不从 `raw_payload` 补事实。
- Compatible `OrderState` proof：无 applied event 时，只允许 typed `OrderState` 证明 eligibility，不证明具体 `source_order_event_id`。`source_order_event_id` 必须 absent / `None`，且只能从 matching applied OMS event proof 填充。`FILLED` report 必须对应 `FILLED` state；`PARTIALLY_FILLED` report 可对应 `PARTIALLY_FILLED` / `FILLED` state；`order_state.filled_quantity` 必须大于等于 report `cumulative_filled_qty`，否则拒绝。
- Trade identity：优先 `account_id + exchange + exchange_trade_id`，`identity_source=exchange_trade_id`。无 `exchange_trade_id` 时使用 deterministic fallback `derived_` identity，payload 为 `account_id + exchange + order_id + report_id + cumulative_filled_qty + fill_price + report_ts`，并设置 `identity_source=derived_from_report`；无法构造稳定 fallback 时 typed reject。禁止 UUID、timestamp-now、DB id 或 raw-payload-only identity。
- Trade fields：implemented `Trade` fact 包含 `id`、`account_id`、`exchange`、`exchange_trade_id` 或 fallback identity、`identity_source`、`order_id`、`client_order_id`、`instrument_id`、`trade_instrument_id`、`symbol`、`direction`、`offset`、Decimal `price` / `quantity`、`fee_amount | None`、`fee_currency | None`、`fee_source | None`、`trade_time`、`trading_day | None`、`source_report_id`、兼容字段 `source_exchange_report_id`、`source_order_event_id` 和 diagnostic-only `raw_payload`。
- Fee semantics：`fee_amount is None` 表示 unknown；`fee_amount == Decimal("0")` 表示 known zero；`fee_amount is not None` 时必须有 `fee_currency` 和 typed `fee_source`。Stage L.3 不计算 fee。
- Result contract：`TradeBridgeResultStatus` 已实现为 `CREATED`、`DUPLICATE`、`REJECTED_NOT_FILLED`、`REJECTED_OMS_NOT_APPLIED`、`REJECTED_MISSING_TRADE_IDENTITY`、`REJECTED_LINEAGE_MISMATCH`、`CONFLICT`、`ERROR`；`TradeBridgeResult` 字段为 `status`、`trade | None`、`source_report_id`、`source_order_event_id | None`、`reason | None`。
- Repository / schema：复用 existing `TradeRepository`，未创建第二套 trade ledger。`trades` 已扩展 `identity_source`、`client_order_id`、`trade_instrument_id`、`symbol`、`source_report_id`、`source_order_event_id`；`normalized_execution_reports` 已扩展 typed `exchange_trade_id`、`fill_id`、`fee_amount`、`fee_currency`、`fee_source`。Existing `UNIQUE(account_id, exchange, exchange_trade_id)` 继续作为 exchange id 和 fallback id 的 trade identity 约束。
- Repository API：保留 `create_or_get_trade(trade)`；新增 `append_trade(trade)`、`get_by_trade_identity(account_id, exchange, exchange_trade_id)` 和 `list_by_order_id(order_id)`，用于 L.3 bridge / replay。
- Canonical payload：包含 account/exchange/trade identity、`identity_source`、order lineage、instrument identity、direction、offset、price、quantity、fee fields、trade time、trading day、`source_report_id`、`source_order_event_id`；排除 `raw_payload`、`created_at`、`updated_at` 和 DB id。Fees 参与 canonical，并区分 unknown vs zero。
- Replay / idempotency：ordered eligible normalized reports + applied OMS proof -> same Trade；same canonical duplicate/no-op；different canonical conflict；replay 不 mutate OMS，不更新 Position / Accounting。
- OMS boundary：Stage L.3 只能通过 typed read-only port 读取 OMS `OrderState` / applied `OrderEvent` proof；不得调用 `OMS.apply_order_event`、`OMS.create_order`、修改订单状态，或只凭 OMS status 推导 fill economics。
- Position / Accounting boundary：Stage L.3 不调用 `PositionManager.apply_trade`，不更新 positions、margin、pnl、settlement 或 account snapshot；只允许产出 typed Trade fact 供后续 PositionManager handoff。
- Explicit non-goals：Position update、Margin update、PnL update、Settlement update、broker reconciliation、runtime scheduling、Kafka / FastAPI / Celery、CTP / SimNow / live broker、fee calculation、trade correction / cancel flows。
- Acceptance criteria：eligible filled report + OMS proof 可 deterministic 创建 typed Trade；same canonical duplicate/no-op；different canonical conflict；fallback identity deterministic；raw_payload excluded；fee unknown vs zero preserved；replay deterministic；无 OMS / Position / Accounting / Broker / Runtime side effects。
- Suggested tag：`stage-l3-oms-to-trade-bridge-core`。

### Stage L.4: Trade-to-Position Contract Freeze

- Goal：冻结当前 L.3 typed Trade 主链到既有 PositionManager 的应用契约。
- Inputs：typed `Trade` fact、current `Position` / `PositionSnapshot`、typed instrument identity、typed account identity、`trading_day` / calendar context、application context。
- Outputs：Position application result、updated `positions` live projection、`PositionEvent` applied-trade audit。
- Allowed changes：只改文档；冻结 source-of-truth、gate、idempotency、position effect、replay、repository/schema 和 accounting boundary。
- Forbidden changes：不写代码；不改 schema；不改 `src` / `tests`；不实现 Margin / PnL / Settlement / AccountSnapshot / Runtime。
- Required future tests：open long、open short、close long、close short、duplicate same trade no-op、same trade identity different canonical conflict、close more than available reject、non-positive qty/price reject、missing identity reject、raw_payload excluded、replay deterministic、no Margin/PnL/Settlement mutation、no Accounting mutation。
- Acceptance criteria：Position update 只能消费 typed Trade fact；same Trade 重放不 double-count；same identity different canonical mutation 前 conflict；PositionEvent 可证明 trade 已应用和应用前后 position；Stage M 仍保留 Runtime / Infrastructure。
- Suggested tag：`stage-l4-trade-to-position-contract-freeze`。

Stage L.4 source-of-truth：

- `Trade` 是 Position application 唯一成交事实输入。
- 不允许从 `raw_payload`、`NormalizedExecutionReport`、`OrderEventCandidate`、OMS `OrderState`、`OrderEvent`、Broker state、FeatureSnapshot、SignalDecision、TradingRiskResult 或 OrderIntent 直接推 Position。
- Stage L.3 的 typed Trade ledger 是本阶段上游；Stage L.4 的输出是 Position projection / PositionEvent，供后续 accounting bridge 使用。

Stage L.4 required gate：

- Trade identity 必须稳定，且包含 `account_id`、`instrument_id` / `trade_instrument_id`、`exchange`、direction / side、offset、positive Decimal `price`、positive Decimal `quantity`、typed `trade_time` 和可用或可从 typed 字段推导的 `trading_day`。
- Trade 必须尚未被应用到 Position；已应用同 canonical 为 duplicate / no-op，已应用但 canonical 不同为 conflict。
- 必须 reject：duplicate already-applied conflict、missing identity、non-positive quantity、non-positive price、raw_payload-only facts、without stable source identity。

Stage L.4 position effect rules：

- BUY + OPEN -> increase long。
- SELL + OPEN -> increase short。
- SELL + CLOSE / CLOSE_TODAY / CLOSE_YESTERDAY -> reduce long according to existing offset bucket semantics。
- BUY + CLOSE / CLOSE_TODAY / CLOSE_YESTERDAY -> reduce short according to existing offset bucket semantics。
- 必须尊重现有 `PositionSide` / direction、today/yesterday bucket 和 frozen quantity 语义；Stage L.4 不从订单状态推导冻结，也不得静默修改 frozen quantities。
- close 数量超过可用 bucket / side 时必须 typed reject 或 conflict，不得生成负持仓，不得自动转成反向开仓。
- open trade 按现有 PositionManager contract deterministic 更新同侧 avg price；close trade 不改写剩余 avg price，除非未来单独迁移 PositionManager contract。

Stage L.4 idempotency / replay：

- 幂等键沿用 Trade identity：`account_id + exchange + exchange_trade_id`，或 L.3 已标记的 deterministic fallback identity。
- same trade identity + same canonical -> duplicate / no-op。
- same trade identity + different canonical -> conflict / error，且必须发生在任何 Position mutation 之前。
- 同一 Trade 应用两次不得 double-count Position。
- Replay 只消费 ordered Trade facts；同一 trade sequence 必须得到同一 Position projection；duplicate no-op；conflict stops。
- Replay 不更新 Margin / PnL / Settlement / Accounting，不 mutate OMS / Trade ledger / Broker state。

Stage L.4 PositionEvent decision：

- 复用现有 Stage C `PositionEvent`，不新增第二套 applied-trade ledger。
- `PositionEvent` 必须包含 trade identity、`account_id`、instrument identity、previous position、new position、changed quantity、`event_type`、`occurred_at`。
- 现有 `before_snapshot` / `after_snapshot` 是 replay 和 audit 必需事实；`raw_payload` 仍只诊断，不参与 canonical。

Stage L.4 repository / schema decision：

- 当前 `PositionRepository`、`PositionEventRepository`、`positions` 和 `position_events` schema 对 L.4 契约足够。
- `position_events` 已有 `UNIQUE(account_id, exchange, exchange_trade_id)`，可作为 applied Trade tracking。
- Stage L.4 不需要 migration；后续实现应避免新增第二个 position ledger。
- 只有在后续实现发现 L.3 fallback identity 无法被 `position_events.exchange_trade_id` 稳定表达时，才允许另开 schema migration；迁移也必须扩展现有 `position_events`，不得创建平行 ledger。

Stage L.4 accounting boundary：

- 不调用 `MarginEngine`。
- 不调用 `PnLEngine`。
- 不调用 `SettlementEngine`。
- 不更新 account snapshots。
- 不更新 realized / unrealized PnL。
- 不计算 margin。
- Position output 只作为后续 Accounting bridge 输入。

Stage L.4 explicit non-goals：

- Margin update。
- PnL update。
- Settlement update。
- AccountSnapshot update。
- Broker reconciliation。
- runtime scheduling。
- Kafka / FastAPI / Celery。
- trade correction / cancel flows，除非另开范围。
- cross-account netting。

### Stage L.5: Position-to-Accounting Implementation

- Goal：实现 Trade-applied Position / PositionEvent 到 Margin / PnL / Settlement / AccountSnapshot 会计链连接契约的最小闭环。
- Baseline：`stage-l4-trade-to-position-handoff / 6c26cbd`；Strategy -> OMS OrderState、OMS State -> Trade Fact、Trade -> Position 均已闭环。
- Inputs：typed Position / PositionEvent after Trade application、typed Trade facts if needed for realized PnL、typed MarketDataSnapshot / settlement price / last price input、typed account config / margin config / pnl config、TradingCalendar / trading_day。
- Outputs：Accounting input snapshot、MarginSnapshot、PnLSnapshot、later SettlementSnapshot / AccountSnapshot through Settlement / Accounting service。
- Allowed changes：migration `0015_stage_l5_position_to_accounting.py`、`MarginSnapshot` / `PnLSnapshot` domain、snapshot repositories、Margin/PnL gates、Settlement matching、focused tests/docs。
- Forbidden changes：不接 Broker / Runtime / Kafka / Celery / FastAPI；不修改 orders / order_events / trades / positions schema；不修改 PositionManager；不改 OMS / Trade ledger；不让 Margin/PnL 成为 Position quantity source。
- Required future tests：margin binds to position_version、pnl binds to position_version、settlement rejects margin/pnl mismatch、duplicate same accounting fact no-op、different canonical conflict、replay deterministic、missing price rejected、stale position version rejected、raw_payload excluded、no Position mutation by Margin/PnL、no OMS/Trade mutation by Accounting。
- Acceptance criteria：会计链只从 typed Position / PositionEvent / Trade / typed price / typed config 形成 accounting facts；MarginSnapshot / PnLSnapshot 以 first-class `trading_day` / `config_hash` 绑定 position_version 和 deterministic calculation identity；Settlement 不再按 instrument-only fallback 匹配；Stage M 仍保留 Runtime / Infrastructure。
- Suggested tag：`stage-l5-position-to-accounting-contract-freeze`。

Stage L.5 source-of-truth：

- Allowed inputs：typed Position / PositionEvent after Trade application、typed Trade facts for realized PnL close input、typed MarketDataSnapshot / settlement price / last price input、typed account config / margin config / pnl config、trading_day / calendar context。
- Forbidden inputs：`raw_payload` facts、Broker state、OMS `OrderState` directly、`NormalizedExecutionReport` directly、`OrderEventCandidate` directly、SignalDecision / Strategy output、Runtime scheduler、external account balance unless first represented as typed account snapshot input。
- Position output from Stage L.4 becomes the accounting input; accounting facts must not be reconstructed from broker query, OMS state, execution reports, raw payload, or strategy/risk facts.

Accounting ownership boundaries：

- `PositionManager` owns position quantity projection and `PositionEvent` applied-trade audit。
- `MarginEngine` owns margin calculation and `MarginSnapshot`。
- `PnLEngine` owns realized / unrealized PnL calculation and `PnLSnapshot`。
- `SettlementEngine` owns settlement finalization and `SettlementSnapshot`。
- AccountSnapshot update may happen only through Settlement / Accounting service; `PositionManager` must not update AccountSnapshot directly。

Stage L.5 required gate：

- Margin / PnL calculation may run only if Position has stable `account_id` / `instrument_id`, known `position.version`, typed Decimal market / settlement price input, available `trading_day`, deterministic `config_hash` / `calculation_key`, and known source PositionEvent / Position version lineage。
- Must reject：missing position identity、missing price、non-Decimal price、stale position version unless explicitly replaying against that historical version、raw_payload-only facts。

Position -> Margin contract：

- `MarginSnapshot` binds to `account_id`、`instrument_id`、`position_version`、first-class `trading_day`、first-class `config_hash` and deterministic `calculation_key`。
- Same account + instrument + position_version + trading_day + config_hash + typed price input -> same margin fact。
- Duplicate same canonical -> no-op / existing snapshot。
- Same identity + different canonical -> conflict。
- Stage L.5 does not allow direct Position qty / avg mutation by Margin. Existing Stage D margin projection may update cached `positions.margin_used` only as a snapshot-backed derived cache and never as position quantity source-of-truth.

Position / Trade -> PnL contract：

- `PnLSnapshot` binds to `account_id`、`instrument_id`、`position_version`、first-class `trading_day`、first-class `config_hash` and deterministic `calculation_key`。
- Realized PnL source is typed Trade / PositionEvent close data only。
- Unrealized PnL source is typed Position plus typed market / settlement price。
- No raw report, broker state, OMS state, execution report, or raw payload may drive PnL。

Margin / PnL -> Settlement contract：

- `SettlementEngine` may consume `MarginSnapshot` + `PnLSnapshot` only when `account_id`、`instrument_id`、`position_version` and `trading_day` match exactly for the settled instrument / position lineage。
- Mismatch returns typed reject / conflict。
- No fallback by `instrument_id` alone is allowed; this preserves the Stage F fact-lineage P1 fix。
- Settlement consumes existing accounting facts; it must not recompute Stage D margin or Stage E PnL.

Stage L.5 idempotency / replay：

- Same position_version + same trading_day + same config_hash + same typed price input -> duplicate / no-op。
- Same identity + different canonical -> conflict。
- Replay ordered PositionEvents / Positions deterministically。
- Replay must not call Broker / Runtime。
- Replay must not mutate OMS / Trade ledger。

Stage L.5 repository / schema decision：

- Current MarginSnapshotRepository、PnLSnapshotRepository、SettlementSnapshotRepository、AccountSnapshotRepository and related tables already exist。
- Migration `0015_stage_l5_position_to_accounting.py` extends only `margin_snapshots` and `pnl_snapshots` with NOT NULL `trading_day` and NOT NULL `config_hash` plus L.5 accounting identity indexes。
- Existing `calculation_key` uniqueness remains. Repository append checks same calculation key canonical no-op/conflict and strict accounting identity `account_id + instrument_id + position_version + trading_day + config_hash` no-op/conflict。
- Legacy `get_by_position_version(...)` no longer drives L.5 writes and must not be used to choose among multiple trading_day / config_hash contexts。
- Do not create a second accounting ledger.

Stage L.5 explicit non-goals：

- Runtime scheduler。
- Broker reconciliation。
- live market feed。
- settlement calendar automation。
- external broker account sync。
- order / event / trade mutation。
- strategy / risk recomputation。

### Stage M: Runtime / Infrastructure Core

- Goal：冻结 Runtime / Infrastructure process lifecycle、startup / shutdown、dependency wiring、scheduler、replay orchestration、health、failure recovery、service ownership 和 source-of-truth boundary。
- Baseline：`stage-l5-position-to-accounting-handoff / 3f1c5a6`；Strategy -> OMS OrderState、OMS State -> Trade Fact、Trade -> Position、Position -> Accounting 均已闭合。
- Inputs：已冻结的 Application Services、repositories/UoW ports、typed config、typed replay inputs、health dependency checks。
- Outputs：Runtime dependency graph、startup order、shutdown order、replay order、health model、failure model、service ownership、thin Runtime implementation。
- Allowed changes：Runtime package、runtime unit tests and docs updates only。
- Forbidden changes：不改 schema；不改 business domain fields；不改 OMS / Trade / Position / Accounting services；不让 Runtime 改 Position / Margin / PnL / Settlement / OMS state；不把 Kafka / Redis / scheduler payload 当作业务事实。
- Acceptance criteria：Runtime 只编排 Market、Feature、Strategy、Workflow、OMS、Execution、Trade、Position、Accounting 应用服务；Runtime 不拥有业务事实；Runtime 只调用应用服务，不直接调用 repository mutation 或 domain engine mutation。
- Suggested tag：`stage-m-runtime-infrastructure-contract-freeze`。

Stage M runtime dependency graph：

```text
Runtime Process
-> Config / Secrets Provider
-> DB / UoW Factory
-> MarketDataService
-> FeatureService
-> StrategyService / SignalLifecycleService
-> TradingWorkflowService
-> OMSBridgeService / OMSService
-> ExecutionGatewayService
-> ExecutionReportNormalizer / OMSEventApplicationService
-> TradeBridgeService
-> PositionManager
-> MarginEngine / PnLEngine / SettlementEngine through Accounting application service
-> Replay Orchestrator
-> Health / Readiness Reporter
```

Runtime only orchestrates：

- Market。
- Feature。
- Strategy。
- Workflow。
- OMS。
- Execution。
- Trade。
- Position。
- Accounting。

Runtime source-of-truth rule：

- Runtime owns process state only：process id、runtime id、component lifecycle、scheduler trigger status、task attempt、retry metadata、lock ownership、health/readiness state 和 structured logs。
- Runtime does not own business facts。
- DB business ledgers remain source-of-truth：market facts、feature snapshots、signals、risk results、order intents、orders / order_events、execution commands、normalized execution reports、trades、positions / position_events、margin snapshots、pnl snapshots、settlement snapshots 和 account snapshots。
- Kafka / Redis / Celery / FastAPI payloads are transport, cache, task envelope or control input only；they never replace DB facts。
- Runtime must not recover missing business fields from `raw_payload`、message headers、task kwargs、cache values、logs or metrics。

Startup order：

1. Load typed config and secrets; redact secrets before logging。
2. Initialize process identity / `runtime_id` for lineage only; it must not enter deterministic business identity。
3. Initialize DB engine and UoW factory。
4. Run migration/version compatibility check in read-only mode。
5. Wire repositories and application service ports。
6. Wire Market -> Feature -> Strategy -> Workflow -> OMS -> Execution -> Trade -> Position -> Accounting application services。
7. Initialize replay orchestrator in disabled / explicit-trigger mode。
8. Initialize scheduler in paused mode。
9. Initialize health/readiness reporter。
10. Mark readiness only after dependency checks and service wiring checks pass。
11. Start scheduler/consumers only after readiness is true and kill switch policy allows execution。

Shutdown order：

1. Stop accepting new API commands, scheduler ticks and consumer messages。
2. Mark readiness false while liveness can remain true。
3. Drain in-flight application service calls with timeout。
4. Stop scheduler and consumers。
5. Flush structured logs, metrics and audit events。
6. Close UoW sessions / DB connections。
7. Release runtime locks。
8. Mark process terminated。

Scheduler boundary：

- Scheduler may trigger application service methods only。
- Scheduler may pass typed request/context objects, not raw transport payloads as facts。
- Scheduler must not directly update `positions`、`margin_snapshots`、`pnl_snapshots`、`settlement_snapshots`、`orders` or `order_events`。
- Scheduler retries must preserve deterministic idempotency keys already owned by the application service。
- Scheduler failure does not imply business failure unless the called application service returned a typed business result。

Replay order：

```text
Market facts
-> FeatureSnapshot replay
-> Strategy / Signal replay
-> Trading Workflow replay
-> OMS Bridge replay
-> Execution Gateway replay
-> Execution Report normalization replay
-> OMS Event application replay
-> Trade bridge replay
-> Position replay
-> Accounting replay
```

Replay orchestration rules：

- Runtime may coordinate replay order, batch size, dry-run/live-apply flags and reporting。
- Runtime must call each stage's existing replay/application boundary。
- Runtime must not directly mutate OMS state, Trade ledger, Position, Margin, PnL, Settlement or AccountSnapshot。
- Replay default is dry-run / preview where a stage supports it；live apply requires explicit operator intent and preflight conflict check。
- Disabled replay is an explicit no-op。
- Live apply is a hard per-stage allowlist；non-allowlisted stages remain dry-run regardless of global replay defaults。
- Any conflict / divergence stops the dependent downstream replay segment unless an explicit recovery contract says otherwise。

Health model：

- Liveness：process event loop / worker is alive and can report。
- Readiness：config, DB/UoW, migration compatibility, service wiring, scheduler policy and kill switch state allow work。
- Dependency health：DB reachable, required queues/brokers reachable if enabled, Redis/Kafka available if configured, secrets provider reachable if configured。
- Business health：latest successful service call, replay divergence count, idempotency conflict count and pending retry/dead-letter count are reported as metrics/audit, not as business source-of-truth。
- Health endpoints / probes must not repair business state。

Failure model：

- Startup failure before readiness：fail closed; no scheduler/consumer execution。
- Dependency failure after readiness：mark readiness false, stop new work, drain or fail typed attempts。
- Application service typed reject/conflict：preserve result, do not retry blindly, route to replay/recovery report。
- Runtime exception before service commit：retry only through the same application service idempotency boundary。
- Runtime exception after service commit but before ack/log：repeat may only become duplicate/no-op through service idempotency；Runtime must not manually patch DB state。
- Poison message / repeated task failure：dead-letter with redacted envelope and correlation id；business facts remain unchanged unless already committed by an application service。
- Recovery must be replay/service driven, never direct table mutation。

Service ownership：

- MarketDataService owns market fact ingestion/replay。
- FeatureService owns FeatureSnapshot generation/replay。
- StrategyService / SignalLifecycleService own SignalCandidate / SignalDecision and lifecycle events。
- TradingWorkflowService owns TradingRiskResult / OrderIntent creation。
- OMSBridgeService owns OrderIntent -> OMS create-order bridge。
- OMSService owns OMS `orders.status/version` and `order_events` state application。
- ExecutionGatewayService owns ExecutionCommand creation/dispatch boundary。
- ExecutionReportNormalizer owns NormalizedExecutionReport and OrderEventCandidate creation。
- OMSEventApplicationService owns candidate -> typed OrderEvent mapping and guarded OMS event apply。
- TradeBridgeService owns typed Trade fact creation from eligible report + OMS proof。
- PositionManager owns Position projection and PositionEvent applied-trade audit。
- Accounting application service owns calls into MarginEngine、PnLEngine、SettlementEngine and snapshot persistence。
- Runtime owns process lifecycle, wiring, scheduling, retries, health, metrics, locks and transport envelope only。

Runtime explicitly must not：

- 改 Position quantity、avg price、today/yesterday bucket、frozen qty、version or `position_events`。
- 改 Margin facts or cached `positions.margin_used`。
- 改 PnL facts or cached `positions.realized_pnl` / `positions.unrealized_pnl`。
- 改 Settlement facts、today->yesterday roll 或 AccountSnapshot。
- 改 OMS `orders.status/version` 或 `order_events`。
- 直接调用 repository mutation 绕过 application service。
- 直接调用 pure Domain engine 并自行落库。
- 通过 Redis/Kafka/Celery/FastAPI payload 补业务事实。

Stage M explicit non-goals：

- Broker / CTP / SimNow / live adapter。
- Paper / sim / live trading。
- New business schema。
- New business domain models。
- OMS state-machine change。
- Position / Accounting algorithm change。
- Settlement calendar automation。
- Broker reconciliation。
- Portfolio risk upgrade。
- Kill switch risk rule implementation；Stage M only wires runtime readiness/stop policy boundary。

Stage M implementation recommendation：

- Implement Stage M as a thin runtime package around existing application services。
- Start with in-process dependency wiring and CLI/local process lifecycle before FastAPI/Celery/Kafka。
- Keep scheduler disabled by default and require explicit config to enable each job。
- Add health/readiness as read-only probes。
- Add replay orchestrator as dry-run first, with explicit live-apply flags per stage。
- Add no business tables in Stage M；if runtime task audit is later needed, freeze a separate infrastructure-only contract before migration。
- Validate with tests that monkeypatch application services and assert Runtime never imports repository implementations for direct mutation and never mutates Position / Margin / PnL / Settlement / OMS state directly。

Stage M current implementation facts：

- Implemented package：`src/futures_mvp/modules/runtime`。
- Implemented config objects：`RuntimeConfig`、`SchedulerConfig`、`ReplayConfig` and `RuntimeConfigError`。
- Scheduler is disabled by default. Enabled scheduler requires explicit job names and only calls injected application service callables。
- Replay is dry-run by default. `RuntimeReplayCoordinator` fixes stage order as Market -> Feature -> Strategy -> Workflow -> OMS Bridge -> Execution Gateway -> Execution Reports -> OMS Event Application -> OMS-to-Trade -> Position -> Margin -> PnL -> Settlement。
- Disabled replay is a typed no-op and calls no stage callable。
- Live replay apply is not global；it is a hard gate allowed only for explicitly listed replay stages。
- Replay conflict / divergence is represented as coordinator conflict and should degrade health; Runtime does not auto-repair business facts。
- Health model is implemented as `RuntimeHealthStatus.READY / DEGRADED / FAILED` with `RuntimeHealthChecker` and typed check/report objects。
- Service graph builder wires current application service slots and requires external `RiskEvaluator` and `TradeRepository` dependencies instead of inventing business logic。
- Lifecycle manager validates service graph before readiness, starts scheduler only after health precheck passes and stops scheduler before DB close hooks。
- Runtime tests live under `tests/unit/runtime` and include config、health、service graph、lifecycle、scheduler、replay and boundary guards。
- Stage M adds no Alembic migration, no schema, no business domain fields, no Broker / CTP / SimNow / live adapter, and no FastAPI / Celery / Kafka hard dependency。

### Stage N: Broker / Adapter Layer

- Goal：冻结 Broker / Adapter Layer contract；只定义 adapter command/report/query、identity、canonical、replay/idempotency、failure recovery、Runtime interaction 和 OMS ownership boundary。
- Baseline：`stage-m-runtime-infrastructure-core / b443249`；Runtime 已能 wire application services、scheduler disabled by default、replay dry-run by default，但没有 Broker / CTP / SimNow / live adapter。
- Inputs：`ExecutionCommand`、typed broker config / secrets handle、Runtime service graph、adapter session context、external broker command acknowledgements、external broker order/trade/account/position query records。
- Outputs：typed broker command result、typed `RawExecutionReport` input for Stage L normalizer、typed broker query snapshots for reconciliation/recovery、adapter health/session status、redacted diagnostics。
- Allowed changes for this freeze：只改文档；冻结 dependency graph、adapter boundary、OMS ownership rules、replay contract 和 implementation recommendation。
- Forbidden changes for this freeze：不写代码；不改 schema；不新增 Alembic；不新增 broker table；不改变 OMS / Execution / Trade / Position / Accounting contracts。
- Suggested tag：`stage-n-broker-adapter-contract-freeze`。

Stage N dependency graph：

```text
Runtime Process / Scheduler
-> Broker Adapter Port
-> Broker Session Manager
-> Broker Command Adapter
-> External Broker / SimNow / CTP
-> Broker Report Adapter
-> RawExecutionReport typed input
-> ExecutionReportNormalizer
-> OMSEventApplicationService
-> TradeBridgeService
-> PositionManager
-> Accounting application service

Broker Query Adapter
-> typed Order / Trade / Account / Position query snapshots
-> Reconciliation / Recovery report
-> existing replay / application boundaries
```

Stage N adapter boundary：

- Adapter owns broker connectivity：connect、login、logout、heartbeat、reconnect、session state、command transport、report subscription / polling、query transport and redacted diagnostics。
- Adapter consumes persisted `ExecutionCommand` and typed broker config only；it must not consume Strategy、Risk、OrderIntent、OMS internals、Accounting tables or `raw_payload` facts。
- Adapter returns typed command result and typed report/query records；raw broker message is diagnostic-only and must be redacted before logs / metrics。
- Adapter must not call `OMSService`、`RiskEngine`、`TradeRepository`、`PositionManager`、Margin / PnL / Settlement services or repository mutation methods。
- Adapter accepted / broker transport accepted is not exchange accepted；exchange/order/fill truth still enters through Stage L typed report normalization and later OMS / Trade / Position / Accounting boundaries。

OMS ownership rules：

- OMS remains the only owner of `orders.status/version` and `order_events`。
- Broker report must become typed `RawExecutionReport` / `NormalizedExecutionReport` before any OMS event candidate exists。
- Only `OMSEventApplicationService` may route a candidate into `OMSService.apply_order_event(...)` under its existing dry-run/live-apply gates。
- Broker query result must not overwrite OMS status。Query mismatch creates typed reconciliation / recovery evidence, then recovery must use existing OMS recovery / replay path。
- Adapter, Runtime and reconciliation code must not patch `orders` or append `order_events` directly。

Stage N broker source-of-truth：

- Broker is source-of-truth only for external broker-observed facts before they enter the local typed pipeline：external order id / order ref、exchange order status、exchange trade id、fill price / quantity、broker account snapshot、broker position snapshot and broker timestamps。
- Local system source-of-truth remains the persisted business ledgers after typed ingestion：`execution_commands`、`normalized_execution_reports`、`orders` / `order_events`、`trades`、`positions` / `position_events`、accounting snapshots。
- Broker query data is reconciliation evidence, not direct local truth。It can prove recovery inputs only after typed normalization and explicit recovery contract handling。
- `raw_payload` / raw broker message never carries hidden source-of-truth fields; all business fields needed downstream must be first-class typed fields.

Stage N broker command contract：

- Submit / cancel commands originate from existing `ExecutionCommand` only。
- Command identity remains `ExecutionCommand.command_id`; adapter may add broker lineage such as `adapter_name`、`adapter_instance_id`、`session_id` and `adapter_order_ref` for audit only。
- Adapter must preserve `order_id`、`client_order_id`、`account_id`、instrument identity、side、offset、quantity、price、order_type、tif、command_type and execution target exactly as typed command input。
- Same `command_id` + same canonical broker command is duplicate / no-op or idempotent retry。
- Same `command_id` + different canonical broker command is conflict before broker send。
- Pre-send failure returns typed adapter failure and does not imply broker accepted。
- Post-send uncertain must not blindly resend as a new order；it must query/recover through broker order query and existing replay/recovery boundaries。

Stage N broker report contract：

- Broker order / trade notifications must be converted to typed `RawExecutionReport` before Stage L normalizer。
- Required report lineage includes adapter identity、execution target、`command_id` when known、`order_id` / `client_order_id` when known、`adapter_order_ref`、`exchange_order_id | None`、broker status、filled quantity、fill price when applicable、cumulative filled quantity、remaining quantity、report timestamp and diagnostic-only raw payload。
- If `command_id` or OMS lineage is missing, adapter may emit typed unresolved report evidence for reconciliation, but it must not invent local order identity。
- Report timestamp units and timezone must be normalized before domain entry where possible。
- Decimal quantities/prices are mandatory；float facts are forbidden。

Stage N adapter identity and canonical payload：

- Adapter identity includes `adapter_name`、`execution_target`、`broker_environment`、`account_id`、`adapter_instance_id` and optional `session_id`。
- `session_id` and `runtime_id` are lineage / audit only and must not participate in deterministic business identity。
- Broker command canonical payload includes `command_id`、OMS lineage、account/instrument identity、side、offset、quantity、price、order_type、tif、command_type、execution target、adapter name and broker environment。
- Broker report canonical payload includes adapter identity、broker report identity or deterministic fallback key、OMS/command lineage when known、exchange order/trade identity、typed status、Decimal fill fields and normalized broker report timestamp。
- Canonical payload excludes raw broker message、logs、metrics、received_at、runtime_id、session_id、DB id and secrets。

Stage N replay contract：

- Broker command replay defaults to dry-run and must not send to broker unless an explicit live-send gate is enabled for the adapter and command type。
- Report replay consumes typed captured report/query evidence and re-enters Stage L normalizer / existing downstream replay order；it must not call OMS / Trade / Position / Accounting directly。
- Same command/report canonical -> duplicate / no-op；same identity + different canonical -> conflict and stop dependent downstream replay。
- Reconnect replay must query broker state first for post-send uncertain commands; it must not generate a second submit command for the same OMS order / target。
- Query reconciliation is evidence-to-recovery, not direct table mutation。

Stage N failure recovery：

- Pre-send adapter failure：return typed failure, keep OMS recovery through existing command/report path, no broker state assumed。
- Post-send uncertain：mark adapter result uncertain, stop blind retry, query broker by adapter order ref / exchange order id / client order id, then emit typed report or reconciliation evidence。
- Disconnect/reconnect：re-login, resubscribe reports, query open orders/trades since last known typed checkpoint, feed typed reports into normalization/replay。
- Duplicate broker callback：same canonical no-op; different canonical conflict。
- Missing lineage：quarantine as unresolved typed evidence; do not mutate OMS or create Trade until lineage is proven。
- Secret/config failure：fail closed and mark Runtime readiness false; never log secret values or put them into `raw_payload`。

Stage N Runtime interaction：

- Runtime wires adapter ports and session lifecycle, but Runtime still owns only process lifecycle, scheduling, health, locks and transport envelope。
- Scheduler may trigger adapter commands only through the existing Execution Gateway / adapter port boundary。
- Runtime health may report broker connectivity/session state, but health probes must not repair business state。
- Runtime readiness must be false when required broker session/config is unavailable for enabled live/paper/sim command flow。
- Live command flow is disabled by default; paper/sim/live enablement requires explicit config, explicit adapter target, readiness checks and later Operations gates。

Stage N explicit non-goals：

- No code implementation in this freeze。
- No schema migration or broker ledger table。
- No OMS state-machine change。
- No direct Trade / Position / Accounting mutation。
- No broker reconciliation auto-overwrite。
- No portfolio risk upgrade。
- No kill switch risk rule implementation。
- No production rollout or live enablement。
- No FastAPI / Celery / Kafka hard dependency。

Stage N implementation recommendation：

- Implement first as a port-driven adapter package with a deterministic fake / SimNow-like adapter before any live CTP integration。
- Keep command send, report normalization input and query reconciliation as three separate adapter surfaces。
- Persist no new broker facts until a separate schema contract is frozen; reuse existing `execution_commands` and `normalized_execution_reports` for business pipeline facts。
- Add boundary tests for no OMS/Risk/DB mutation, command canonical conflicts, post-send uncertain recovery, report Decimal normalization, duplicate callbacks and query mismatch evidence。
- Keep live target disabled by default and require Runtime readiness plus future Stage O safety gates before real submit/cancel can be enabled。

Stage N current implementation facts：

- Implemented package：`src/futures_mvp/modules/broker_adapter`。
- Implemented `MockBrokerAdapter` as an `ExecutionAdapter` implementation for deterministic Stage N tests；it consumes existing `ExecutionCommand` and returns existing `ExecutionCommandResult`。
- Implemented submit modes：accepted、pre-send timeout、post-send uncertain and duplicate same canonical no-op。
- Implemented deterministic `adapter_order_ref` from `command_id`；no UUID、timestamp-now or DB id is used as fact identity。
- Implemented adapter-internal `BrokerCallbackEvidence` and translator to existing `RawExecutionReport`；it is not a business fact ledger and is not persisted。
- Missing `command_id`、`order_id`、`client_order_id`、`adapter_order_ref` or stable non-mock `raw_report_id` is quarantined in `InMemoryUnresolvedBrokerCallbackQuarantine` for tests only；missing lineage / source identity is not invented from `raw_payload`。
- Mock callback evidence without broker source id may derive deterministic `raw_report_id` only from typed evidence fields；non-mock evidence must supply stable `raw_report_id`。
- Valid translated reports enter the existing `RawExecutionReport -> ExecutionReportNormalizer -> NormalizedExecutionReport` pipeline；the normalizer now enforces `raw_report_id` source identity duplicate / conflict before any second normalized report can persist。
- Runtime code was not changed；adapter remains injectable through existing `ExecutionGatewayService` / `ServiceGraphDependencies.execution_adapter` boundary。
- Stage N keeps cancel unsupported / deferred；`ExecutionCommandType.CANCEL_ORDER` remains reserved by current domain validation。
- Stage N core does not introduce a broker ledger. The only schema change is 0016, which strengthens the existing normalized_execution_reports ledger with raw_report_id source identity uniqueness. Stage N adds no broker table, no CTP / SimNow / live adapter, and no network dependency。

### Stage O: Operations / Safety / Production Readiness

- Goal：建立生产门禁、安全控制、监控、审计、runbook 和 DR。
- Inputs：runtime、broker adapter、replay framework、accounting source-of-truth。
- Outputs：metrics、audit trail、kill switch、readiness、healthcheck、deployment gates、runbook。
- Allowed changes：ops control/audit schema if needed、metrics/logging adapters、readiness/preflight tests。
- Forbidden changes：ops 不直接改业务事实；kill switch 不塞进 OMS 状态机；secret 不进入业务事件。
- Required tests：kill switch gate、audit event、health/readiness、deployment preflight、incident replay、secret redaction。
- Acceptance criteria：safety gates 可审计；UNKNOWN/recovery/position mismatch 有 runbook 和 typed workflow。
- Suggested tag：`stage-o-operations-safety-readiness`。

### Stage P: Paper / Sim / Live Rollout

- Goal：按 local -> paper -> sim -> live 递进验收。
- Inputs：Stage A-O 验收结果、runtime config、broker config、runbook、preflight checklist。
- Outputs：paper trading run、SimNow run、live preflight、controlled live enablement。
- Allowed changes：rollout config、environment gates、runbook updates、preflight automation。
- Forbidden changes：不跳级 live；不绕过 paper/sim；不以手工配置暗示环境；不在 live 前启用真实 submit/cancel。
- Required tests：paper trading tests、simulation tests、live read-only preflight、dry-run command validation、rollback drill。
- Acceptance criteria：paper/sim 通过后才可 live；live preflight 全绿且 kill switch 默认安全。
- Suggested tag：`stage-p-paper-sim-live-rollout`。

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

Trading Workflow / Execution Gateway / Recovery / Runtime / Broker / Production 主线：

```text
Stage I + Stage C + Stage D + Stage F -> Stage J
Stage J.2 -> Stage K
Stage K -> Stage L
Stage L -> Stage L.2
Stage L.2 -> Stage L.3
Stage L.3 -> Stage L.4
Stage L.4 -> Stage L.5
Stage L.5 -> Stage M
Stage M -> Stage N
Stage N -> Stage O
Stage O -> Stage P
```

依赖说明：

- Market Data / Feature Snapshot 是 Strategy / Signal Lifecycle 的前置，并应作为并行主线提前规划；Stage H 只冻结 FeatureSnapshot，不进入 Strategy / Signal。
- Stage I 实现 Strategy / Signal Lifecycle Core，但不实现 Order creation、Risk check、OMS integration 或 Execution integration。
- Stage J 实现 Trading Workflow Core，只到 SignalDecision -> TradingRiskResult -> OrderIntent persistence；不改 OMS state machine，不接 Execution，不进入 Broker/Runtime。
- Stage J.2 实现 OMS Bridge Core，只到 `OrderIntent -> OMS.create_order`；不接 Execution / Broker。
- Stage K 实现 Execution Gateway command boundary，只消费 OMS Order / `OrderState` 和 typed execution config，只输出 `ExecutionCommand` / `ExecutionCommandResult`，只支持 `MOCK` target，不提交真实 broker。
- Stage L 实现 Execution Report Normalization Core，只生成 persisted `NormalizedExecutionReport` 和 optional `OrderEventCandidate`，不调用 OMS。
- Stage L.2 实现 OMS event application core，只允许 application service 将 `OrderEventCandidate` 映射为 typed `OrderEvent` 后调用 `OMSService.apply_order_event(...)`，并只推进 OMS OrderStatus。
- Stage L.3 实现 OMS-to-Trade Bridge core，只允许已成交 normalized report 加已应用 OMS proof 创建 typed Trade fact 并持久化到 existing `TradeRepository`；不更新 Position / Accounting，不进入 Runtime。
- Risk Context / Portfolio Risk Upgrade 依赖 Position、Margin、Accounting、Market Data、FeatureSnapshot、Strategy / Signal，不应提前硬接 broker state 或 raw payload。
- Recovery / Replay 依赖订单、执行命令、成交、持仓、结算、行情、Strategy / Signal 和 Trading Workflow 语义。
- Broker / Adapter 必须在 Execution Gateway、Recovery / Replay 和 Runtime 边界稳定后进入；Stage N 只冻结 adapter 合约，不代表 live enablement。
- Operations / Safety / Production Readiness 是 Paper / Sim / Live Rollout 的硬前置。
- Broker / Adapter 完成后不得直接进入 rollout。
- Stage P 必须依赖 Stage O 的 readiness、kill switch、monitoring、audit、deployment gate、runbook 和 DR 验收。
- Paper / Sim / Live 不允许跳级。

不可跳级规则：

- 没有 Stage A，不接 OMS execution orchestration。
- 没有 Stage B，不处理真实成交事实。
- 没有 Stage C，不把持仓写成真实 source-of-truth。
- 没有 Stage G，不冻结 Strategy 所需 typed market input。
- 没有 Stage H，不冻结 Strategy 所需 FeatureSnapshot。
- 没有 Stage I，不把 Strategy / Signal Lifecycle 写成已完成。
- 没有 Stage J，不把 SignalDecision 接入 Risk -> OrderIntent -> OMS workflow。
- 没有 Stage J.2，不把 `OrderIntent` 转入 OMS Order。
- 没有 Stage K，不生成 ExecutionCommand，不接 adapter dispatch。
- 没有 Stage L，不接 broker report normalization。
- 没有 Stage N，不接 broker query reconciliation。
- 没有 Stage M/N/O，不进入 sim/live。
- 没有 Stage O，不进入 Stage P。
- Stage P 只能按 paper -> sim -> live 递进。

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
- OMS state machine、recovery target。
- Risk pure rules、RiskContext input validation、account risk、portfolio exposure、position risk、intraday limit、kill switch context rule。
- Execution DTO、mapper、mapping result、report handler。
- Accounting calculation：Trade、Position、Margin、PnL、Settlement。
- Market Data data quality、FeatureSnapshot deterministic generation。
- Strategy deterministic signal id、SignalCandidate / SignalDecision validation、Signal lifecycle gate。
- Trading Workflow TradingRiskResult / OrderIntent deterministic contract。

### Integration Tests

- OMS repository/UoW transaction。
- Orchestrator submit/cancel + OMS + Execution runtime。
- Risk -> OMS application orchestration。
- Trading Workflow no-OMS-call gates for `REJECT` / `BLOCK` / `UNKNOWN`。
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
- Trading Workflow replay。
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
- Full strategy -> signal -> risk -> OrderIntent -> OMS -> execution simulation -> accounting chain。
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
2. Stage K 已先冻结并实现 Execution Gateway command boundary，确保 OMS Order -> ExecutionCommand 的 source-of-truth、idempotency 和 dry-run replay 稳定。
3. Stage L.2 稳定 OMS event application、Stage L.3 稳定 OMS-to-Trade Bridge core、Stage L.4 稳定 Trade-to-Position handoff 且 Stage L.5 冻结 Position-to-Accounting contract 后，Stage M 才引入 event envelope、task boundary、control plane、config/secrets provider。
4. Kafka 只传输 typed events，不替代 DB source-of-truth。
5. Celery 只调度任务，不承载领域判断。
6. Redis 只做 cache/lock/pubsub/临时状态，不做事实来源。
7. FastAPI 只做 control plane，不直接写业务事实。
8. KMS / secrets provider 只服务 secret retrieval，不把 secret 写进业务模型、事件、raw payload、logs 或 metrics。
9. Cloud deployment 必须在 Operations gates 和 live preflight 之后进入。

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

下一步是在 `stage-m-runtime-infrastructure-core / b443249` 基线上执行 Stage N Broker / Adapter Layer Contract Freeze：

```text
Stage N Broker / Adapter Layer Contract Freeze
```

Stage N 只改文档，不写代码，不改 schema。冻结输出必须包括：

- dependency graph。
- adapter boundary。
- OMS ownership rules。
- replay contract。
- implementation recommendation。

Stage N 必须保持：

- Broker / Adapter 不调用 OMS / Risk / DB mutation。
- Broker query reconciliation 不静默覆盖本地事实。
- Broker report 必须先进入 typed report normalization，再由现有 OMS / Trade / Position / Accounting 边界处理。
- Runtime 只 wire adapter lifecycle / scheduling / health，不拥有业务事实。
- Live submit/cancel 默认不启用；生产 rollout 仍依赖 Stage O / Stage P。
