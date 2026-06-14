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
  - Stage L.3 创建 Trade 必须有已应用 OMS `OrderEvent` proof；仅兼容 `OrderState` 的 state-only proof 只能作为 preview / reject context，不能持久化 Trade。
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
- Production rollout automation、external monitoring integration、deployment gates 和 runbook。

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
- Stage U.1 adds a documentation-only Instrument Resolver / Market Data Source contract：future resolver maps `symbol + trading_day` to resolver snapshot fields `symbol`、`instrument_id`、`trade_instrument_id`、`exchange`、`source`、`confidence`、`effective_from/effective_to` and diagnostics；main/continuous contracts are for market data / backtest observation only and must not be used directly for orders；trade contracts must be resolver-derived. U.1 adds no code, schema, live feed, broker, CTP, SimNow or non-`MOCK` target enablement.
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
- Replay：same OMS order + same target -> same `ExecutionCommand`；same canonical -> duplicate / no-op；different canonical -> conflict / error；默认 dry-run 且为 no-write preview，不 append `execution_commands`，不 submit adapter / broker；live replay 默认在首个 `CONFLICT` / `ERROR` 停止下游命令；replay 不 mutate OMS / Accounting。
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
- Source-of-truth flow：`NormalizedExecutionReport / applied OMS OrderEvent proof -> OMS-to-Trade Bridge -> typed Trade fact -> TradeRepository persistence -> PositionManager handoff later`。
- Allowed inputs：`PARTIALLY_FILLED` / `FILLED` 的 `NormalizedExecutionReport`、已应用 OMS `OrderEvent` proof、existing OMS order identity、typed instrument/account identity、typed fee input if available、typed `exchange_trade_id` / fill identity if available。
- Forbidden inputs：`raw_payload` facts、Broker state as truth、`FeatureSnapshot`、`SignalDecision`、`TradingRiskResult`、`OrderIntent` mutation、Position table、Margin / PnL / Settlement、Runtime / Kafka / Celery / FastAPI。
- Required gate：只有 normalized report status 是 `PARTIALLY_FILLED` / `FILLED`、已应用 OMS `OrderEvent` proof 与当前 report 严格绑定、`order_id` / `client_order_id` lineage 匹配、`filled_qty > 0`、`fill_price > 0` 且 trade identity 稳定时，才允许创建 Trade；`ACKED`、`SUBMITTED`、`REJECTED`、`CANCELED`、`ERROR`、adapter accepted only、state-only `OrderState` proof 和 un-applied candidate 都不得创建 Trade。
- OMS proof binding：applied `OrderEvent` proof 必须来自 `EXECUTION_REPORT_NORMALIZER`，且 `report_id`、`execution_status` 映射后的 OMS status、`filled_qty`、`fill_price`、`cumulative_filled_qty`、`report_ts` 和 `order_id` 必须与当前 `NormalizedExecutionReport` 一致；typed proof 字段缺失时拒绝，不从 `raw_payload` 补事实。
- State-only `OrderState` proof：Pre-Stage-P 只可作为 preview / reject context；缺少 matching applied OMS `OrderEvent` proof 时必须返回 `REJECTED_OMS_NOT_APPLIED` 且不持久化 Trade。`source_order_event_id` 必须从 matching applied OMS event proof 填充。
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

- No real broker / CTP / SimNow / live implementation。
- No broker-owned schema or broker ledger table；accepted schema change is limited to normalized report identity strengthening in migration `0016_stage_n_report_identity_conflict`。
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

- Goal：冻结 Operations / Safety / Production Readiness 契约，使 Runtime、Scheduler、Replay、Broker Adapter 和后续 rollout 只能在明确安全门禁下运行。
- Contract baseline：`stage-n-broker-adapter-core / a32b810`。
- Implementation baseline：`stage-o-safety-readiness-contract-freeze / fcd2b0f`。
- Inputs：runtime health、typed config、scheduler state、replay report、application service status、DB migration state、operator decision。
- Outputs：safety source-of-truth、kill switch contract、dry-run/live gate、config validation、migration readiness、observability、recovery playbook、incident states、operator checklist 和 Stage P rollout preflight contract。
- Implemented changes：`ops_safety` typed package、`RuntimeConfig.safety`、kill switch / pause evaluator、live gate validator、read-only migration readiness checker、ops incident / observability models、Runtime lifecycle safety readiness integration、Scheduler safety gate、ReplayCoordinator safety gate and unit / boundary tests。
- Forbidden changes：Stage O 不新增 schema、不直接改业务事实；kill switch 不塞进 OMS 状态机；secret 不进入业务事件；不得把 `raw_payload`、broker rumor、manual DB edits 或 runtime guessing 当作 safety truth。
- Tests：kill switch gate、dry-run/live gate、config fail-closed、migration readiness before scheduler start、structured observability、incident state transitions、scheduler/replay pause、per-stage kill switch、no schema、no business mutation、no Broker/CTP/SimNow/live/network/external monitoring dependency。
- Acceptance criteria：Runtime / Replay / Scheduler / Broker live flow 默认 fail closed；live submit 必须显式 operator approval；DB migration 不兼容时 app 不得 READY；Stage P 只能在 Stage O readiness、kill switch、observability、runbook 和 operator checklist 全部满足后进入。
- Suggested tag：`stage-o-operations-safety-readiness`。

Stage O safety source-of-truth：

- Allowed safety truth：runtime health、typed config、scheduler state、replay report、application service status、DB migration state and explicit operator decision。
- Forbidden safety truth：`raw_payload`、broker rumor、manual DB edits and runtime guessing。

Stage O kill switch / pause contract：

- Global kill switch stops scheduler-triggered work、replay live apply and broker submit。
- Per-stage kill switch stops only the named stage and its downstream unsafe live effects。
- Scheduler pause prevents new scheduled runs without rewriting domain facts。
- Replay pause prevents replay execution；existing persisted facts are not repaired or deleted。
- Live submit is disabled by default。
- Broker adapter is disabled unless explicitly enabled。

Stage O dry-run / live gate：

- Runtime default is dry-run。
- Replay default is dry-run。
- Broker live is disabled。
- Live requires explicit operator approval plus explicit config gates。
- Config typo, missing flag or unknown environment must never imply live。

Stage O readiness / observability / recovery：

- Invalid config fails closed；unknown environment is rejected；production mode requires explicit production flags；missing broker credentials disable broker flow。
- App cannot become `READY` when DB migration state is incompatible；migration check must run before scheduler start；runtime auto-migration is forbidden unless explicitly allowed。
- Required observability：structured logs、health status、replay summary、scheduler status、last successful stage and conflict/error counters。
- Recovery playbook must cover replay recovery、conflict recovery、broker post-send uncertain recovery、unresolved callback quarantine handling and documented operator-only DB repair procedure。
- Incident states are `READY`、`DEGRADED`、`FAILED`、`PAUSED` and `KILLED`。

Stage O current implementation facts：

- Implemented package：`src/futures_mvp/modules/ops_safety`。
- Implemented config objects：`SafetyConfig`、`KillSwitchConfig`、`LiveGateConfig`、`MigrationReadinessConfig` and `ObservabilityConfig`。
- `RuntimeConfig` now carries `safety: SafetyConfig` and rejects unknown environments；`production` requires explicit production flags。
- Kill switch / pause evaluator is pure and returns typed `OpsGateDecision` without mutating business facts。
- `RuntimeLifecycleManager` can run read-only migration readiness and safety readiness before scheduler start；incompatible migration returns `FAILED` and active global kill switch returns incident `KILLED` through `OpsHealthReport`。
- `ApplicationServiceScheduler` blocks `run_once` when scheduler pause / global kill switch / per-job stage kill switch is active and returns typed `RuntimeSchedulerRunResult`。
- `RuntimeReplayCoordinator` blocks all replay when global kill switch / replay pause is active；per-stage kill switch blocks the named stage and stops downstream replay fail-closed。
- Live submit gate requires explicit live flag、broker enabled、live submit enabled、broker credentials handle、compatible migration and typed `OperatorApproval`。
- Migration readiness checker reads only `alembic_version.version_num` and never runs upgrade / downgrade；when migration readiness is enabled, missing checker is `FAILED` with `migration_readiness_checker_missing`。
- Observability is typed in-memory only：`OpsEvent`、`OpsHealthReport`、`ReplaySummary`、`SchedulerStatus` and `OpsCounters`；no external monitoring stack is introduced。
- Stage O does not add Alembic/schema, broker ledger, CTP / SimNow / live adapter, external monitoring dependency or business fact mutation path。

### Stage P: Paper / Sim / Live Rollout Core

- Goal：实现 Paper / Sim / Live rollout typed safety gates；只到 mode / promotion / rollback / capital / live / replay policy decision，不启用真实 Paper / Sim / Live execution。
- Baseline：`pre-stage-p-system-acceptance / c834f7c`；Pre-Stage-P System Acceptance Review = ACCEPT。
- Implemented changes：`RolloutMode`、`RolloutConfig`、`CapitalControlConfig`、capital control evaluator、promotion evaluator、rollback evaluator、Stage P live gate composition helper、mode-aware replay policy、`SafetyConfig.rollout` integration、unit / boundary tests 和 docs update。
- Forbidden changes：不改 schema，不启用 `ExecutionTarget.PAPER` / `SIM` / `LIVE`，不让 ExecutionGateway 支持非 `MOCK` target，不接 CTP / SimNow / live，不接真实 broker/network，不修改 OMS / Trade / Position / Accounting business facts，不实现 durable approval/audit table。

Mode ownership：

- Rollout modes are exactly `PAPER`、`SIM` and `LIVE`。
- The three modes are mutually exclusive；Runtime may run only one rollout mode at any time。
- Mode source-of-truth now enters typed `SafetyConfig.rollout` as `RolloutConfig.mode`；operator approval remains explicit for promotion, live and live replay apply。
- Simultaneous `PAPER + LIVE`、`SIM + LIVE` or `PAPER + SIM` enablement is forbidden and must fail closed。
- Mode must never be inferred from environment typo、broker callback、raw payload、runtime guessing or partial config defaults。
- `RuntimeConfig.environment` is not rollout mode；`ExecutionTarget` is not rollout mode。Default rollout mode is `PAPER`。

Mode source-of-truth：

- Allowed：`RuntimeConfig`、`SafetyConfig` and explicit operator decision。
- Forbidden：`raw_payload`、unknown / misspelled environment values、broker callback、runtime guessing、manual DB edits or untyped logs。
- Runtime may report mode, but must not invent mode。

Promotion path：

```text
PAPER
-> SIM
-> LIVE
```

- `PAPER -> SIM` requires Runtime `READY`、migration compatible、healthy replay result and explicit operator approval。
- `SIM -> LIVE` requires Runtime `READY`、migration compatible、broker enabled、live gate passed、operator approval、kill switch released、no unresolved critical incidents and passed capital controls。
- Promotion may not skip a mode；failed promotion leaves the previous accepted mode intact。
- Same-mode promotion returns typed no-op。

Rollback path：

```text
LIVE -> SIM
LIVE -> PAPER
SIM -> PAPER
```

- Rollback must support operator rollback、kill switch rollback、migration incompatibility rollback and incident rollback。
- Rollback is a safety decision, not a mutation of OMS / Trade / Position / Accounting facts。
- Rollback must preserve evidence：mode decision、incident state、replay summary、broker command/report evidence and operator approval/revocation。
- Rollback evaluator accepts only `LIVE -> SIM`、`LIVE -> PAPER` and `SIM -> PAPER`；it is typed decision-only and does not mutate business facts。

Live gate：

- Live is disabled by default。
- `LIVE` requires explicit live flag、operator approval、broker enabled、credentials present、migration compatible、Runtime `READY`、kill switch released、replay not running、scheduler healthy、passed capital controls and no unresolved critical incidents。
- Any missing, unknown or mismatched input rejects fail-closed。
- `FAILED`、`KILLED` or `PAUSED` incident state forbids entering `LIVE`。

Capital control contract：

- Stage P safety gate must freeze max order size、max position size、max daily loss、account whitelist and allowed instrument list。
- Capital controls are rollout safety gates；they are not OMS source-of-truth and must not rewrite orders, trades, positions or accounting facts。
- Implemented capital controls validate order size、position size、daily loss、account whitelist and instrument whitelist。Empty whitelist is fail-closed for `LIVE`；non-live empty whitelist behavior is explicit in config。

Runtime interaction：

```text
Runtime
-> ExecutionGateway
-> BrokerAdapter
```

- Runtime must not call Broker directly。
- Runtime must not mutate OMS directly。
- Runtime must not mutate Trade、Position、Margin、PnL、Settlement or AccountSnapshot directly。
- Broker callback evidence must re-enter typed report normalization and existing application boundaries。

Replay policy：

- `PAPER`：replay allowed。
- `SIM`：replay allowed by policy。
- `LIVE`：live replay apply disabled by default。
- Live replay apply requires explicit approval、`allow_live_apply` and operator decision together；missing any one condition rejects。
- Replay must not run concurrently with live gate entry。
- Kill switch / replay pause blocks replay policy。`PAPER` / `SIM` replay is allowed by policy；`LIVE` dry-run remains allowed but live apply is gated。

Incident policy：

- Incident states remain `READY`、`DEGRADED`、`FAILED`、`PAUSED` and `KILLED`。
- Entering `LIVE` is forbidden when state is `FAILED`、`KILLED` or `PAUSED`。
- `DEGRADED` may only proceed for non-live work unless a future contract defines an explicit exception。

Recovery contract：

- Post-send uncertain：do not blindly resend；query broker by typed keys, convert proven evidence to typed report/reconciliation input, and re-enter Stage L normalization。
- Unresolved callback：quarantine until lineage is proven；do not mutate OMS / Trade / Position / Accounting from quarantined evidence。
- Replay recovery：start dry-run, stop on conflict, require operator approval before any live apply resumes。
- Operator rollback：must revoke approval, record mode transition and preserve evidence before resuming a lower mode。

Non-goals：

- Stage P Core does not implement real capital deployment。
- No production CTP。
- No production SimNow。
- No broker certification。
- No exchange certification。
- No remote cluster deployment。

Implementation recommendation：

- Keep this Stage P Core as typed preflight/checklist helpers with no business ledger ownership。
- Keep mode validation in typed runtime/safety config before any executable rollout。
- Keep `LIVE` behind explicit operator approval, kill switch release and capital-control gates。
- Future implementation order after acceptance：paper dry-run, paper command path, sim broker adapter path, live read-only preflight, then controlled live enablement only after a separate acceptance review。

- Acceptance criteria：PAPER / SIM / LIVE modes are mutually exclusive；promotion and rollback are typed and auditable；live remains disabled by default；Runtime uses only `Runtime -> ExecutionGateway -> BrokerAdapter`；capital controls and incident policy block unsafe live entry；ExecutionGateway still rejects non-`MOCK` target。
- Suggested tag：`stage-p-paper-sim-live-rollout-core`。

### Stage P.1: Paper Trading Enablement Minimal Harness

- Goal：实现 Paper Trading Enablement 最小 deterministic harness，只生成 local paper execution evidence，不进入 Sim / Live / real broker。
- Baseline：`stage-p1-paper-trading-contract-freeze / 2d07591`；Paper Adapter / Harness Gap Review recommends adding `PaperExecutionHarness` instead of expanding `MockBrokerAdapter` into a paper execution engine。
- Implemented changes：新增 `paper_trading` module、`PaperFillPolicy`、`PaperExecutionHarness`、typed `PaperExecutionResult`、deterministic paper report identity helpers、unit / boundary tests and docs update。
- Forbidden changes preserved：不改 schema，不启用 `ExecutionTarget.PAPER` / `SIM` / `LIVE`，不接 CTP / SimNow / live，不接真实 broker/network，不接 live account，不部署真实资金，不直接 mutate OMS / Trade / Position / Accounting。

Paper scope：

- PAPER allows local deterministic paper execution only。
- PAPER must not use real broker、CTP、SimNow、live account、external network execution or real capital。
- PAPER must continue through the accepted main chain：

```text
Runtime
-> ExecutionGateway
-> Paper/Mock adapter
-> RawExecutionReport
-> NormalizedExecutionReport
-> OMS Event
-> Trade
-> Position
-> Accounting
```

Paper source-of-truth：

- Paper execution owns no order truth、trade truth、position truth or accounting truth。
- OMS owns order truth。
- `NormalizedExecutionReport` owns normalized execution report facts。
- Trade ledger owns trade facts。
- Position owns position projection。
- Accounting engines own margin / pnl / settlement / account snapshots。

Execution target policy：

- `ExecutionTarget.MOCK` remains the only enabled target at this baseline。
- `ExecutionTarget.PAPER` must not be automatically enabled by PAPER rollout mode。
- Any future `PAPER` target enablement requires separate implementation and acceptance review。
- Paper Enablement may reuse `MockBrokerAdapter` or a deterministic paper harness, but it must not claim to be a live broker。

Paper adapter / harness contract：

- Input：typed `ExecutionCommand`。
- Output：typed `ExecutionCommandResult` plus `RawExecutionReport` evidence。
- `PaperExecutionHarness` reuses the `MockBrokerAdapter` submit boundary and keeps `ExecutionTarget.MOCK` as the only supported target。
- `ExecutionTarget.PAPER` / `SIM` / `LIVE` remain disabled in `ExecutionGateway` and are rejected by the paper harness。
- Adapter order reference must be deterministic。
- Fill identity must be deterministic；no random fill id。
- Fact identity must not use timestamp-now。
- `raw_payload` remains diagnostic-only and must not be source-of-truth。

P.1 fill policy：

- Implemented policies：immediate full fill、immediate reject、pre-send timeout and post-send uncertain。
- Immediate full fill and immediate reject produce `RawExecutionReport` evidence through `BrokerCallbackEvidence` and `translate_callback_to_raw_execution_report(...)`。
- Pre-send timeout and post-send uncertain return typed command failure / uncertain results and produce no report in P.1。
- Deferred：partial fill sequence、multi-fill、price slippage policy、market-depth/order-book simulation、latency model and timeout recovery workflow。
- Every implemented policy is deterministic、config-bound and replayable。
- Fill policy does not call OMS directly or mutate Trade / Position / Accounting。

Paper reports：

- Paper reports may enter only through:

```text
RawExecutionReport
-> ExecutionReportNormalizer
-> OMSEventApplication
-> OMSToTrade
-> Position
-> Accounting
```

- Direct OMS apply is forbidden。
- Direct Trade creation is forbidden。
- Direct Position update is forbidden。
- Direct Accounting update is forbidden。
- `PaperExecutionHarness` stops at typed `RawExecutionReport` evidence；normalization、OMS event application、OMS-to-Trade、Position and Accounting remain owned by their existing services。

Paper safety gates：

- Paper still obeys rollout mode `PAPER`、kill switch、scheduler pause、replay pause、migration readiness、capital controls、account whitelist and instrument whitelist。
- Paper has no real money exemption from capital controls。

Paper replay：

- Paper replay is allowed。
- Dry-run remains default unless explicitly applying paper facts。
- Conflict stops downstream。
- Duplicate same canonical is no-op。
- No live replay apply。
- No broker network。

Runtime interaction：

```text
Runtime
-> ExecutionGateway
-> adapter / harness
```

- Runtime must not call adapter directly。
- Runtime must not mutate OMS directly。
- Runtime must not mutate Trade / Position / Accounting directly。

Stage P.1 non-goals：

- No SIM。
- No LIVE。
- No real broker。
- No CTP。
- No SimNow。
- No non-`MOCK` gateway target enablement unless separately approved。
- No real capital。
- No remote deployment。

Implementation recommendation：

- Next implementation should wire the harness through an approved paper runtime entrypoint with Stage O/P safety gates upstream。
- Keep `ExecutionTarget.MOCK` until explicit `PAPER` target implementation and acceptance review。
- Treat Paper Enablement as local deterministic evidence generation, not as broker integration。

- Acceptance criteria：Paper execution can be expressed without weakening source-of-truth ownership；paper reports enter only through `RawExecutionReport -> NormalizedExecutionReport -> OMS Event -> Trade -> Position -> Accounting`；non-`MOCK` gateway target remains disabled。
- Suggested tag：`stage-p1-paper-trading-enablement-contract-freeze`。

### Stage P.2: Paper Trading End-to-End Flow

- Goal：实现 paper-only E2E coordinator，将 Stage P.1 harness evidence 串入现有 accepted main chain，不进入 SIM / LIVE / real broker。
- Baseline：`stage-p1-paper-trading-minimal-harness / 1a2089f`；Stage P.1 Paper Harness Integration Gate Review = ACCEPT。
- Implemented changes：新增 `PaperRunContext`、`PaperAccountingContext`、`PaperRunResult`、`PaperRunStatus` and `PaperTradingCoordinator`；新增 safety preflight、report application sequence、full fill / reject / timeout / uncertain paths、duplicate / conflict stop tests、boundary tests and docs update。
- Forbidden changes preserved：不改 schema，不启用 `ExecutionTarget.PAPER` / `SIM` / `LIVE`，不接 CTP / SimNow / live，不接真实 broker/network，不直接 mutate OMS / Trade / Position / Accounting repositories，不把 paper coordinator 变成 source-of-truth。

P.2 paper E2E sequence：

```text
ExecutionCommand
-> PaperExecutionHarness
-> RawExecutionReport
-> ExecutionReportNormalizer
-> OMSEventApplicationService
-> OMSToTradeBridgeService
-> PositionManager
-> MarginEngine / PnLEngine / SettlementEngine
```

P.2 safety preflight：

- Requires rollout mode `PAPER` and `SafetyConfig.rollout.mode == PAPER`。
- Requires compatible migration readiness。
- Blocks on global kill switch、scheduler pause and replay pause。
- Requires capital controls to pass, including account whitelist and instrument whitelist policy。
- Safety reject stops before harness execution and has no downstream side effect。

P.2 report and fact ownership：

- The coordinator calls existing services in order；it does not own order、trade、position or accounting truth。
- Full fill uses applied OMS event proof before `OMSToTradeBridgeService` creates a Trade。
- Reject reports may apply OMS rejection through `OMSEventApplicationService` but do not create Trade、Position or Accounting facts。
- Pre-send timeout and post-send uncertain produce no report and no downstream mutation。
- Duplicate report no-ops; conflict / error stops downstream。

P.2 target policy：

- `ExecutionTarget.MOCK` remains the only enabled execution target。
- `ExecutionTarget.PAPER` / `SIM` / `LIVE` remain rejected and require separate implementation / acceptance。
- Rollout mode `PAPER` still does not imply `ExecutionTarget.PAPER`。

- Acceptance criteria：paper full fill can traverse the existing service chain through typed boundaries；reject / timeout / uncertain do not create downstream facts；safety preflight blocks before execution；no schema、real broker、SIM / LIVE or non-`MOCK` target enablement。
- Suggested tag：`stage-p2-paper-trading-e2e-flow`。

### Stage P.3: Paper Runtime Job / Scheduler Wiring

- Goal：实现最小 paper runtime job and scheduler wiring，将 Stage P.2 coordinator 放入 Runtime / Scheduler callable 边界。
- Baseline：`stage-p2-paper-trading-e2e-flow / 041014a`；Stage P.2 Post-Acceptance Gate Review = ACCEPT。
- Implemented changes：新增 `PaperJobConfig`、`PaperJobStatus`、`PaperJobResult` and `PaperRuntimeJob`；Runtime service graph 新增 `PaperTradingCoordinator` slot and default disabled `PaperJobConfig`；Scheduler 继续只通过 injected `RuntimeJob` callable 调用 paper job。
- Scope：Paper runtime job may trigger `PaperTradingCoordinator` only under rollout mode `PAPER`, using typed `PaperRunContext`, and returning typed `PaperRunResult` / `PaperJobResult`。
- Forbidden changes：不实现 SIM / LIVE，不启用 `ExecutionTarget.PAPER` / `SIM` / `LIVE`，不接 real broker / CTP / SimNow / network broker，不新增 schema，不实现 durable job/audit table，不让 runtime 或 scheduler 拥有业务事实。

P.3 allowed path：

```text
Runtime Scheduler
-> Paper Runtime Job
-> PaperTradingCoordinator
-> existing application services
```

P.3 runtime and scheduler boundaries：

- Runtime service graph may hold `PaperTradingCoordinator`, a paper job callable and `PaperJobConfig`。
- Runtime must not call `PaperExecutionHarness` directly。
- Runtime must not call BrokerAdapter directly。
- Runtime must not call OMS / Trade / Position / Accounting repositories directly。
- Scheduler may call only the injected paper job callable and record typed job status/result。
- Scheduler must not construct `ExecutionCommand` from raw payload, mutate business facts, bypass the coordinator, call the harness directly or call broker directly。

P.3 `PaperJobConfig` contract：

- `enabled: bool = False`。
- `job_name`。
- `rollout_mode` must be `PAPER`。
- dry-run default if applicable。
- `max_commands_per_run`。
- `stop_on_first_error`。
- `stop_on_conflict`。
- `require_migration_ready`。
- `require_capital_controls`。
- `require_scheduler_not_paused`。
- `require_replay_not_paused`。
- Defaults are disabled and fail-closed。

P.3 safety gates before job execution：

- Rollout mode `PAPER`。
- Scheduler enabled。
- Paper job enabled。
- Kill switch released。
- Scheduler not paused。
- Replay not paused。
- Migration compatible。
- Capital controls pass。
- Account and instrument allowed。
- Any failed gate returns typed blocked/rejected result, does not call the coordinator and creates no business side effect。

P.3 dry-run / apply semantics：

- Default behavior is disabled or dry-run by config。
- Apply path is allowed only after all safety gates pass。
- Dry-run must not mutate ledgers。
- Paper apply may mutate ledgers only through the accepted Stage P.2 service chain。
- No live apply is allowed。

P.3 job result / reporting contract：

- `PaperJobStatus`: `DISABLED`, `BLOCKED`, `DRY_RUN`, `COMPLETED`, `DUPLICATE`, `CONFLICT`, `ERROR`。
- `PaperJobResult`: `job_name`, `status`, `reason`, `paper_run_result`, `started_at`, `finished_at`, processed command count, conflict counter and error counter。
- Result is observability only and is not a business source-of-truth。

P.3 command source contract：

- Current P.3 command source is explicit typed `ExecutionCommand` input or an injected command provider returning a typed `ExecutionCommand` list。
- Raw payload commands, broker callbacks as commands, runtime guessing and strategy direct bypass are forbidden。
- Strategy-originated commands must arrive through the already accepted workflow / OMS / Execution command path。

P.3 replay / conflict policy：

- Duplicate no-op。
- Conflict stops downstream。
- `stop_on_conflict` default true。
- `stop_on_first_error` default true。
- No downstream execution after conflict or error。

P.3 non-goals：

- No strategy live loop。
- No market data scheduler。
- No SIM。
- No LIVE。
- No non-`MOCK` gateway target。
- No real broker。
- No remote deployment。
- No durable job/audit table。
- No external monitoring stack。

Implementation recommendation：

- Next implementation should run Stage P.3 acceptance review before considering paper command-provider hardening or broader paper runtime workflows。
- No schema migration was added or expected。

### Stage P.4: Paper Runbook / Local Paper Session

- Goal：实现最小 local paper session helper、smoke tests and operations runbook，完成本地 Paper Trading MVP 收官。
- Baseline：`stage-p3-paper-runtime-job-wiring / 50edc23`；Stage P.3 Post-Acceptance Gate Review = ACCEPT。
- Implemented changes：新增 `PaperSessionConfig`、`PaperSessionStatus`、`PaperSessionResult`、`PaperLocalSession` and `run_paper_local_session`；新增 dry-run / apply / blocked / conflict smoke tests；更新 operations runbook and completion docs。
- Scope：Paper local session accepts explicit typed `ExecutionCommand` list or injected typed command provider, then orchestrates `PaperRuntimeJob` only。
- Forbidden changes preserved：不实现 SIM / LIVE，不启用 `ExecutionTarget.PAPER` / `SIM` / `LIVE`，不接 real broker / CTP / SimNow / network broker，不新增 schema，不实现 durable audit table，不绕过 `PaperRuntimeJob` / `PaperTradingCoordinator`，不让 session result 成为业务 source-of-truth。

P.4 local paper session flow：

```text
typed ExecutionCommand list / typed command provider
-> PaperLocalSession
-> PaperRuntimeJob
-> PaperTradingCoordinator
-> accepted paper E2E chain
```

P.4 session contract：

- `PaperSessionConfig` carries `session_name`, `runtime_id`, `trading_day`, `account_id`, `dry_run`, `max_commands`, `require_clean_start`, `stop_on_first_error`, `stop_on_conflict` and explicit `apply_confirmed`。
- `dry_run=True` remains the default local session mode。
- `dry_run=False` requires `apply_confirmed=True` before any job call。
- Empty commands, missing command source, duplicate command sources or non-`MOCK` execution target return typed blocked result before job execution。
- `PaperSessionResult` is observability only and is not a business source-of-truth。
- Conflict and error aggregation preserve stop-on-conflict and stop-on-first-error behavior from `PaperRuntimeJob`。

Paper completion status：

- Stage P.1 minimal harness complete。
- Stage P.2 paper E2E complete。
- Stage P.3 runtime job wiring complete。
- Stage P.4 local paper session / runbook complete。
- Paper Trading local MVP complete。
- Paper Trading Local MVP = STABLE BASELINE。
- Stability baseline commit：`dde3e66` on `main`。
- Previous tag：`stage-p4-paper-local-session-complete`。
- Current soak evidence：Day 0 rerun passed、Day 1 passed、10x passed、Day-long 30-run passed、Multi-day 3 trading days passed。
- SIM / LIVE remain not implemented。
- non-`MOCK` execution target remains not implemented。

Paper stable chain：

```text
ExecutionCommand
-> PaperExecutionHarness
-> RawExecutionReport
-> ExecutionReportNormalizer
-> OMSEventApplicationService
-> OMSToTradeBridgeService
-> PositionManager
-> MarginEngine
-> PnLEngine
-> SettlementEngine
-> PaperRuntimeJob
-> PaperLocalSession
```

Paper stability invariants：

- dry-run no mutation。
- apply completed。
- duplicate no-op。
- conflict stop。
- `ExecutionTarget.MOCK` only。
- no `ExecutionTarget.PAPER` / `SIM` / `LIVE` enablement。
- no broker / CTP / SimNow / live / network dependency。
- settlement snapshot created。
- `source_order_event_id` present on created trade。

Paper stability evidence summary：

- `uv run pytest`：892 passed, 11 xfailed。
- `uv run ruff check .`：passed。
- `uv run mypy src`：passed。
- `uv run alembic current`：`0016_stage_n_report_identity`。
- Multi-day 3 trading days soak：30/30 dry-run ok, 30/30 apply completed, 30/30 duplicate no-op。
- Multi-day row growth：`normalized_execution_reports +60`, `trades +30`, `positions +30`, `position_events +30`, `margin_snapshots +30`, `pnl_snapshots +30`, `settlement_snapshots +30`。
- Multi-day targets：`MOCK` only。

Paper explicit non-goals remain：

- SIM。
- LIVE。
- `ExecutionTarget.PAPER` / `SIM` / `LIVE` enablement。
- real broker。
- CTP。
- SimNow。
- remote deployment。
- production rollout。

SIM Gap Review result：ACCEPT。

Next allowed stage：Stage Q.1 SIM Trading Contract Freeze。

Not allowed before that gate：SIM implementation、LIVE work or real broker work。

### Stage Q.1: SIM Trading Contract Freeze

- Goal：冻结 SIM Trading 契约，作为后续 SIM implementation 前置基线。
- Baseline：`paper-local-mvp-stable-baseline / 73a9f39`；SIM Gap Review = ACCEPT。
- Scope：documentation-only contract freeze；不写代码，不改 schema，不启用 `ExecutionTarget.SIM`，不接 SimNow / CTP / live / broker / network。

SIM scope：

- SIM is an independent rollout mode and is not a PAPER alias。
- SIM is not a shortcut rehearsal for LIVE。
- SIM currently does not connect to real broker、SimNow、CTP、live account or network broker。
- Future SIM implementation may provide local or controlled simulated exchange behavior, deterministic or configured simulated reports, richer execution behavior than Paper and still feed the existing report / accounting pipeline。
- Stage Q.1 implements none of that behavior；it freezes only the contract。

Mode boundary：

- `RolloutMode.SIM` is mutually exclusive with `PAPER` and `LIVE`。
- One runtime instance may run under only one rollout mode。
- The Paper stable baseline does not automatically upgrade to SIM。
- SIM must not enable LIVE gates, LIVE credentials, live apply or live broker access。
- SIM must not read or use live broker credentials。

Execution target policy：

- Stage Q.1 does not enable `ExecutionTarget.SIM`。
- `ExecutionTarget.MOCK` remains the only enabled execution target。
- Future `ExecutionTarget.SIM` enablement requires a separate implementation stage and acceptance review。
- `ExecutionTarget.SIM` is not `RolloutMode.SIM`。
- `RolloutMode.SIM` does not automatically allow `ExecutionTarget.SIM`。

SIM harness / adapter boundary：

- Future SIM must add a `SimExecutionHarness` or `SimAdapter` contract。
- SIM must not directly reuse `PaperExecutionHarness` as its execution engine。
- A shared deterministic evidence builder may be extracted only if it preserves Paper and SIM boundaries。
- SIM harness input must be typed `ExecutionCommand`。
- SIM harness output must be typed `ExecutionCommandResult` plus `RawExecutionReport` evidence。
- SIM harness must not mutate OMS, Trade, Position or Accounting state。
- `raw_payload` is diagnostic only and must not become source-of-truth。

SIM source-of-truth：

- SIM harness does not own order truth, trade truth, position truth or accounting truth。
- OMS owns order truth。
- `NormalizedExecutionReport` owns execution report facts。
- Trade ledger owns trade facts。
- Position owns position facts。
- Accounting owns margin, PnL and settlement snapshots。

SIM report path：

```text
RawExecutionReport
-> ExecutionReportNormalizer
-> OMSEventApplicationService
-> OMSToTradeBridgeService
-> PositionManager
-> MarginEngine / PnLEngine / SettlementEngine
```

Forbidden report-path shortcuts：

- No direct OMS apply。
- No direct Trade creation。
- No direct Position update。
- No direct Accounting update。

SIM identity / idempotency：

- SIM `raw_report_id` must be deterministic。
- SIM `adapter_order_ref` must be deterministic。
- SIM `fill_id` / `exchange_trade_id` must be deterministic or sourced from a typed simulated exchange event。
- UUID, timestamp-now and DB id must not be used as business fact identity。
- same identity + same canonical payload means duplicate / no-op。
- same identity + different canonical payload means conflict。
- `raw_payload` remains diagnostic-only。

SIM safety gates：

- SIM requires Runtime READY。
- SIM requires `RolloutMode.SIM`。
- SIM requires migration compatible。
- SIM requires kill switch released。
- SIM requires scheduler and replay not paused。
- SIM requires explicit operator approval for PAPER -> SIM promotion。
- SIM requires configured capital controls。
- SIM requires account whitelist and instrument whitelist。
- SIM requires no unresolved critical incident。
- SIM still forbids live flag, live credentials, live apply and real broker access。

SIM replay policy：

- SIM replay defaults to dry-run。
- SIM apply requires explicit SIM approval。
- Duplicate replay must no-op。
- Conflict replay must stop。
- SIM replay must not perform live apply。
- SIM replay must not use broker network。
- SIM replay must not repair business ledgers manually。

SIM fill / execution behavior contract：

- Future SIM may support immediate fill, partial fill sequence, reject, timeout, post-send uncertain, latency simulation, slippage and order book / depth simulation。
- Stage Q.1 implements none of those behaviors。
- Each future behavior must be deterministic or config-bound。
- Each future behavior must produce typed `RawExecutionReport` evidence。
- No future behavior may mutate OMS, Trade, Position or Accounting facts directly。

Migration decision：

- Stage Q.1 adds no schema or Alembic migration。
- Future SIM implementation should reuse existing ledgers unless a durable SIM session / audit table is separately frozen and reviewed。

Paper stability protection：

- Paper remains the stable baseline。
- Paper local MVP remains complete。
- SIM work must not regress Paper invariants：dry-run no mutation, apply completed, duplicate no-op, conflict stop, `MOCK` only and no broker / live dependency。

Stage Q.1 explicit non-goals：

- SIM runtime。
- SimNow。
- CTP。
- LIVE。
- real capital。
- remote deployment。
- production broker certification。
- `ExecutionTarget.SIM` enablement。
- schema changes。

Next recommendation：

- Run SIM Harness Gap Review。
- Decide `SimExecutionHarness` versus shared execution evidence builder。
- Do not implement SIM until that review is accepted。

### Stage Q.2: SIM Harness Contract Freeze

- Goal：冻结 `SharedExecutionEvidenceBuilder + SimExecutionHarness` 契约，作为未来 SIM harness implementation 前置基线。
- Baseline：`stage-q1-sim-trading-contract-freeze / b459f2d`；SIM Harness Gap Review = ACCEPT。
- Route decision：采用 `SharedExecutionEvidenceBuilder` plus independent `SimExecutionHarness`。
- Rejected routes：不直接复用 `PaperExecutionHarness` 作为 SIM engine；不把 Paper harness 改成 generic execution engine；不启用 `ExecutionTarget.SIM`。
- Scope：documentation-only contract freeze；不写代码，不改 schema，不改 `src` / tests，不接 broker / SimNow / CTP / live / network。

Shared builder scope：

- May construct deterministic evidence identities。
- May construct typed `BrokerCallbackEvidence`。
- May construct report sequences。
- May validate canonical typed inputs。
- May calculate cumulative and remaining quantity。
- Must not hold rollout mode。
- Must not decide PAPER / SIM safety gates。
- Must not call adapters。
- Must not call OMS, Trade, Position or Accounting services。
- Must not write DB。
- Must not own order, trade, position or accounting source-of-truth。

Namespace / prefix rules：

- Paper prefix remains `paper_*`。
- SIM prefix must be `sim_*`。
- Paper `adapter_name` remains `paper_harness`。
- SIM `adapter_name` must be `sim_harness`。
- `raw_report_id`, `fill_id`, `exchange_trade_id` and `exchange_order_id` must include the mode namespace。
- Paper and SIM identity domains must not collide。

Paper regression contract：

- Paper wrapper must preserve `ExecutionTarget.MOCK` only。
- Paper wrapper must preserve `adapter_name = paper_harness`。
- Paper wrapper must preserve `paper_*` identity prefixes。
- Paper full fill must remain deterministic `ACKED -> FILLED`。
- Paper reject, timeout and post-send uncertain behavior must remain unchanged。
- Paper must still avoid direct OMS / Trade / Position / Accounting mutation。
- Paper must still avoid broker / network dependencies。
- Paper stable baseline invariants must remain unchanged。

SimExecutionHarness contract：

- Future SIM harness input is typed `ExecutionCommand`。
- Future SIM harness output is typed `ExecutionCommandResult` plus `RawExecutionReport` evidence。
- Future SIM harness uses `SharedExecutionEvidenceBuilder`。
- Future SIM harness owns no business facts。
- Future SIM harness must not directly mutate OMS, Trade, Position or Accounting。
- Future SIM harness must not connect to real broker, SimNow, CTP, live account or network。
- Future SIM harness adds no schema。
- Stage Q.2 does not enable `ExecutionTarget.SIM`。

SIM policy / scenario contract：

- Future SIM policies may include immediate full fill, reject, timeout, post-send uncertain, partial fill sequence, latency simulation, slippage and order book / depth simulation。
- Stage Q.2 implements none of these policies。
- Future policies must be deterministic or config-bound。

Partial fill contract：

- `ACKED` must precede `PARTIALLY_FILLED` / `FILLED` when required by the OMS state machine。
- `cumulative_filled_qty` must be monotonic increasing。
- Per-report `filled_qty` must be positive for fill reports。
- `remaining_qty` must be non-negative。
- Final `FILLED` cumulative quantity must equal order quantity。
- Overfill is forbidden。
- Report identity must be deterministic per sequence index。
- Duplicate same report must no-op。
- Conflict must stop。

Safety gate boundary：

- SIM harness does not own safety gates。
- SIM runtime / job / session layer must enforce `RolloutMode.SIM`, PAPER -> SIM promotion approval, Runtime READY, migration compatible, kill switch released, scheduler and replay not paused, capital controls, account whitelist, instrument whitelist, no live credentials and no live apply。

Execution target policy：

- Stage Q.2 does not enable `ExecutionTarget.SIM`。
- Gateway still rejects non-`MOCK` targets。
- SIM harness may exist only as a local controlled evidence generator after implementation。
- `RolloutMode.SIM` does not imply `ExecutionTarget.SIM`。

Source-of-truth and report path：

```text
RawExecutionReport
-> ExecutionReportNormalizer
-> OMSEventApplicationService
-> OMSToTradeBridgeService
-> PositionManager
-> MarginEngine / PnLEngine / SettlementEngine
```

- SIM harness and shared builder never own facts。
- Direct OMS, Trade, Position or Accounting mutation remains forbidden。

Migration decision：

- No schema or Alembic migration in Stage Q.2。
- Durable SIM session / audit storage requires a separate contract freeze and acceptance review。

Future test matrix：

- Paper regression outputs unchanged after shared builder extraction。
- SIM immediate fill emits `ACKED -> FILLED`。
- SIM partial fill emits `ACKED -> PARTIALLY_FILLED -> FILLED`。
- SIM reject, timeout and post-send uncertain。
- deterministic SIM identities with `sim_*` prefix。
- no Paper / SIM identity collision。
- duplicate no-op。
- conflict stop。
- no direct OMS / Trade / Position / Accounting mutation。
- no broker / network imports。
- gateway still rejects `ExecutionTarget.SIM`。
- no schema / Alembic migration。

Stage Q.2 explicit non-goals：

- shared builder code。
- sim harness code。
- SIM runtime / job / session。
- `ExecutionTarget.SIM`。
- SimNow / CTP / live。
- schema changes。

Next recommendation：

- Implement shared builder extraction。
- Wrap Paper reports through the shared builder without changing Paper output。
- Run Paper regression review before implementing minimal `SimExecutionHarness`。

### Stage Q.5: SIM E2E Contract Freeze

- Goal：冻结 SIM E2E coordinator 契约，作为后续 SIM E2E implementation 前置基线。
- Baseline：`stage-q4-minimal-sim-execution-harness / 48a62ab`。
- Scope：documentation-only contract freeze；不写代码，不改 schema，不改 `src` / tests，不启用 `ExecutionTarget.SIM`，不接 SimNow / CTP / live / broker / network。

SIM E2E scope：

- SIM E2E may use local controlled SIM evidence only。
- SIM E2E input must be typed `ExecutionCommand`。
- SIM E2E must consume `SimExecutionHarness` output。
- SIM E2E may reuse the existing report / OMS / trade / position / accounting pipeline。
- SIM E2E must not use real broker, external exchange, live capital or `ExecutionTarget.SIM` enablement。

Coordinator boundary：

- Future implementation must add `SimTradingCoordinator`, `SimRunContext` and `SimRunResult`。
- SIM E2E must not reuse `PaperTradingCoordinator` as the SIM coordinator。
- A shared orchestration helper may be extracted only if it does not own PAPER / SIM mode semantics。
- Coordinator may only orchestrate:

```text
SimExecutionHarness
-> RawExecutionReport
-> ExecutionReportNormalizer
-> OMSEventApplicationService
-> OMSToTradeBridgeService
-> PositionManager
-> MarginEngine / PnLEngine / SettlementEngine
```

Source-of-truth：

- SIM coordinator and harness do not own order truth。
- SIM coordinator and harness do not own execution report facts。
- SIM coordinator and harness do not own trade truth。
- SIM coordinator and harness do not own position truth。
- SIM coordinator and harness do not own accounting truth。
- Facts remain owned by OMS, `NormalizedExecutionReport`, Trade ledger, Position and Accounting snapshots。

Safety preflight：

- SIM E2E must run safety preflight before invoking `SimExecutionHarness`。
- Required gates：`RolloutMode.SIM`, explicit operator approval for PAPER -> SIM, Runtime READY, migration compatible, kill switch released, scheduler and replay not paused, capital controls pass, account whitelist, instrument whitelist and no unresolved critical incident。
- SIM E2E must not allow live credentials or live apply。

Report sequence：

- SIM full fill must emit `ACKED -> FILLED`。
- SIM reject must emit `REJECTED` report and create no Trade。
- SIM timeout and post-send uncertain must return command result only, with no report and no downstream processing。
- Future partial fill must emit `ACKED -> PARTIALLY_FILLED* -> FILLED`, keep cumulative quantity monotonic, forbid overfill, make duplicate no-op and stop on conflict。

Duplicate / conflict policy：

- duplicate normalized report no-ops。
- duplicate OMS event no-ops。
- duplicate trade no-ops。
- Any conflict or error stops downstream。
- No later Position or Accounting mutation may occur after stop。

Accounting contract：

- SIM E2E accounting must use consistent `position_version`, `trading_day` and `config_hash`。
- Settlement must consume run-local margin and PnL snapshots。
- Settlement identity checks must be preserved。
- SIM E2E must not fake settlement facts。
- SIM E2E must not use instrument-only fallback。

Target and runtime policy：

- `ExecutionTarget.MOCK` remains the only enabled target。
- `ExecutionTarget.SIM` remains disabled。
- `RolloutMode.SIM` does not imply `ExecutionTarget.SIM`。
- `SimExecutionHarness` may continue to reject non-`MOCK` target until target enablement is separately frozen and accepted。
- Stage Q.5 does not implement `SimRuntimeJob`, `SimLocalSession`, scheduler wiring or target enablement。

Migration decision：

- No schema or Alembic migration in Stage Q.5。
- Durable SIM session / audit storage requires a separate contract freeze and acceptance review。

Future SIM E2E test matrix：

- non-SIM mode rejected。
- safety gate blocks。
- full fill E2E completes。
- reject creates no Trade。
- timeout / post-send uncertain produce no downstream mutation。
- duplicate no-op。
- report conflict stops。
- OMS duplicate stops。
- trade duplicate stops。
- accounting settlement identity remains consistent。
- no non-`MOCK` gateway enablement。
- no broker / network / schema。

Stage Q.5 explicit non-goals：

- SIM E2E code。
- SIM runtime / job / session。
- `ExecutionTarget.SIM`。
- SimNow / CTP / live。
- real broker。
- partial fill implementation。
- slippage / depth / latency implementation。
- schema changes。

### Stage Q.7: SIM Runtime + Local Session Finalization

- Goal：complete the local controlled SIM runtime and local session loop without enabling `ExecutionTarget.SIM` or external broker connectivity。
- Baseline：`stage-q6-minimal-sim-e2e-coordinator / 1c1d595`。
- Implemented changes：新增 `SimJobConfig`、`SimJobStatus`、`SimJobResult`、`SimRuntimeJob`、`SimSessionConfig`、`SimSessionStatus`、`SimSessionResult`、`SimLocalSession` and `run_sim_local_session`；新增 SIM runtime job and local session tests；更新 SIM operations runbook。
- Scope：SIM runtime/session accepts typed local `ExecutionCommand` sources with `ExecutionTarget.MOCK` and orchestrates only `SimRuntimeJob -> SimTradingCoordinator -> existing report / OMS / trade / position / accounting pipeline`。
- Forbidden changes preserved：不启用 `ExecutionTarget.SIM`，不改 ExecutionGateway 非 `MOCK` 拒绝逻辑，不接 SimNow / CTP / live / broker / network，不新增 schema / Alembic，不实现 partial / slippage / latency / depth，不复用 Paper runtime/session/coordinator as SIM implementation，不直接写 OMS / Trade / Position / Accounting repositories，不实现 live credentials or live apply。

SIM runtime job boundary：

- `SimJobConfig` defaults are fail closed：disabled, dry-run, scheduler disabled, stop-on-conflict, stop-on-first-error, migration readiness required, capital controls required and rollout mode `SIM`。
- `SimRuntimeJob` is callable and returns observability-only `SimJobResult`。
- Dry-run validates typed contexts and safety gates but does not call `SimTradingCoordinator`。
- Apply requires explicit confirmation and calls `SimTradingCoordinator` only after all safety gates pass。
- Aggregate statuses are `DISABLED`, `DRY_RUN`, `COMPLETED`, `DUPLICATE`, `BLOCKED`, `CONFLICT` and `ERROR`。

SIM runtime safety gates：

- `RolloutMode.SIM` and `SafetyConfig.rollout.mode == SIM`。
- SIM operator approval bound to environment `sim`, account id, adapter target `mock`, stage `sim_trading` and command surface。
- Runtime READY。
- Migration compatible。
- Kill switch released。
- Scheduler and replay not paused。
- Capital controls passed with account and instrument allowed。
- No live credentials, no live flags and no live apply。
- No unresolved critical incident。
- Command target `ExecutionTarget.MOCK` only。

SIM local session boundary：

- `SimLocalSession` accepts explicit typed `ExecutionCommand` values or an injected typed provider only。
- Raw payloads and broker callbacks are rejected as command sources。
- Apply requires `apply_confirmed=True`。
- Session calls only the injected job factory and does not own business facts。
- Session result is observability only。
- Conflict and error stop later commands through `SimRuntimeJob` policy。

SIM Q.7 runbook and validation：

- Operators must run dry-run first, inspect `SimSessionResult` and nested `SimJobResult`, then apply only with explicit confirmation。
- After apply, facts must be inspected through normalized reports, OMS events, trades, positions and accounting snapshots。
- Duplicate rerun must no-op；conflict/error must stop downstream。
- Rollback / halt uses kill switch, scheduler pause or replay pause。
- Basic validation covers unit SIM runtime/session, execution evidence, full test suite, ruff, mypy and diff-check。

Stage Q.7 explicit non-goals：

- `ExecutionTarget.SIM` enablement。
- Gateway target policy changes。
- SimNow / CTP / live / broker / network。
- partial fill, slippage, latency or depth simulation。
- schema / Alembic changes。
- durable SIM audit/session table。
- production rollout。

### SIM Stability Freeze

- Baseline：`b894ce6 / stage-q7-sim-runtime-local-session`。
- SIM Local MVP = STABLE BASELINE。
- `ExecutionTarget.SIM` remains disabled。
- `ExecutionTarget.MOCK` remains the only enabled target。
- No SimNow / CTP / live / broker / network integration is present。
- No schema / Alembic change is part of the SIM stability freeze。

Stable SIM local chain：

```text
ExecutionCommand
-> SimExecutionHarness
-> RawExecutionReport
-> ExecutionReportNormalizer
-> OMSEventApplicationService
-> OMSToTradeBridgeService
-> PositionManager
-> MarginEngine / PnLEngine / SettlementEngine
-> SimRuntimeJob
-> SimLocalSession
```

Frozen SIM safety invariants：

- dry-run no mutation。
- apply completed。
- duplicate no-op。
- conflict stop。
- command target `ExecutionTarget.MOCK` only。
- no `ExecutionTarget.SIM` enablement。
- no `ExecutionTarget.PAPER` / `ExecutionTarget.LIVE` target use。
- no SimNow / CTP / live / broker / network。
- settlement snapshot created on completed full-fill apply。
- `source_order_event_id` present on created trade。

SIM local soak evidence：

- SIM Day 0 passed。
- SIM 10x passed。
- SIM Day-long 30-run passed。
- Day-long evidence：30/30 dry-run ok、30/30 apply completed、30/30 duplicate no-op。
- Day-long row growth matched expected：`normalized_execution_reports +60`、`order_events +60`、`trades +30`、`positions +30`、`position_events +30`、`margin_snapshots +30`、`pnl_snapshots +30`、`settlement_snapshots +30`。
- Targets remained `MOCK` only。

Known P3：

- Duplicate rerun outer session status remains `COMPLETED` while nested job/run status is `DUPLICATE` and DB delta is zero。
- This is an observability enum limitation only and does not affect idempotency or ledger safety。

### Stage R.1: Operator Console Contract Freeze

- Goal：freeze the local Operator Console UX, functions, configuration, safety boundary and forbidden actions for non-code / non-CLI local operators。
- Baseline：`sim-local-mvp-stable-baseline / 5f28114`。
- Scope：documentation-only；no code, no schema, no `src` / tests, no FastAPI, no public network, no broker / CTP / SimNow / LIVE, no `ExecutionTarget.PAPER` / `SIM` / `LIVE` enablement。
- Console positioning：local Streamlit-first control panel for Paper/SIM run control, Runtime/Ops status viewing, safety control, result inspection and read-only diagnostics。
- Console is not a strategy developer, database editor, LIVE console, broker console, CTP console or SimNow console。

Stage R.1 page layout：

- Dashboard。
- Paper Session。
- SIM Session。
- Safety Controls。
- Configuration。
- Results / History。
- Diagnostics。
- Live Locked Page。

Stage R.1 Dashboard must display Runtime status, rollout mode, ExecutionTarget status, migration status, kill switch, scheduler pause, replay pause, latest Paper/SIM result and `MOCK only / no live` notice。

Stage R.1 allowed actions：

- `Run Paper Dry-run`。
- `Run Paper Apply` with explicit confirmation。
- `View Paper Result`。
- `Run SIM Dry-run`。
- `Run SIM Apply` with explicit confirmation。
- `View SIM Result`。
- Toggle Kill Switch。
- Toggle Scheduler Pause。
- Toggle Replay Pause。
- Read-only configuration preview, result/history inspection and diagnostics inspection。

Stage R.1 forbidden actions：

- Live Enable。
- Broker Enable。
- CTP Enable。
- SimNow Enable。
- Manual DB edit。
- Force Order。
- Force Trade。
- Force Position。
- `ExecutionTarget.PAPER` / `ExecutionTarget.SIM` / `ExecutionTarget.LIVE` selection or enablement。

Stage R.1 safety rules：

- apply buttons default disabled。
- apply requires second confirmation and impact explanation。
- UI must distinguish dry-run from apply。
- UI must state whether DB rows may be written。
- UI must state `MOCK only`。
- Paper apply may mutate local ledgers only through `PaperLocalSession -> PaperRuntimeJob -> PaperTradingCoordinator`。
- SIM apply may mutate local ledgers only through `SimLocalSession -> SimRuntimeJob -> SimTradingCoordinator`。
- dry-run must not mutate business ledgers。

Stage R.1 configuration contract：

- Normal configuration：`account_id`, `trading_day`, instrument whitelist, max order size, max position size, max daily loss, Paper/SIM mode and dry-run/apply intent。
- Advanced configuration：`runtime_id`, `config_hash`, migration revision and capital control details。
- Initial sources：typed config object, local TOML/YAML file, environment variables and UI session state。
- Persistent Console configuration, durable approvals, durable audit/session table, auth, remote access or UI profiles require a separate contract freeze。

Stage R.1 architecture boundary：

- Console may call only `PaperLocalSession`, `SimLocalSession`, Runtime/Ops health and read-only diagnostics。
- Console must not directly call OMS / Trade / Position / Accounting repository mutation。
- Console must not bypass RuntimeJob / LocalSession, directly write ledger, call harnesses directly, construct commands from raw payloads, use broker callbacks as commands, connect to broker/live or modify schema。
- Console result objects are observability only and never replace DB business ledgers as source-of-truth。

Stage R.1 future implementation recommendation：

- `src/futures_mvp/modules/operator_console/app.py` for Streamlit layout/navigation。
- `src/futures_mvp/modules/operator_console/view_models.py` for display-only view models。
- `src/futures_mvp/modules/operator_console/actions.py` for calls to `PaperLocalSession` and `SimLocalSession` only。
- `src/futures_mvp/modules/operator_console/diagnostics.py` for read-only diagnostics。
- `src/futures_mvp/modules/operator_console/safety.py` for allowed safety controls and forbidden enable-path guards。

Stage R.1 future tests should assert actions do not bypass sessions, forbidden actions do not exist, live buttons do not exist, Paper/SIM apply requires confirmation and non-`MOCK` target cannot be selected。

Stage R.1 validation：

- `git diff --check`。

### Stage T.1: Local Operator Workflow Hardening Contract Freeze

- Goal：freeze the next local Operator Console workflow hardening scope so
  non-code / non-CLI operators can assemble Paper/SIM dry-run config, preview
  typed commands/config, inspect in-memory result history, view known soak
  evidence and read diagnostics from the UI。
- Baseline：`stage-r51-console-blocked-result-ux / b7c6035`。
- Scope：documentation-only；no code, no schema, no `src` / tests, no commit,
  no tag。
- Future implementation may add Console dry-run config assembly, typed command
  fixture preview, account/trading-day/instrument-whitelist/capital-controls UI,
  Paper/SIM dry-run provider construction from typed UI config, in-memory result
  history, read-only soak evidence display and read-only diagnostics。
- Future implementation must not add Paper/SIM apply, DB/ledger/repository
  writes, durable result/history tables, broker / CTP / SimNow / LIVE / network
  integration, schema changes or `ExecutionTarget.PAPER` / `SIM` / `LIVE`
  enablement。

Stage T.1 configuration workflow：

- UI fields：`account_id`, `trading_day`, `instrument_id`,
  `trade_instrument_id`, `symbol`, `exchange`, `quantity`, `price`,
  `max_order_size`, `max_position_size`, `max_daily_loss` and allowed
  instruments。
- UI may generate typed dry-run command/config previews only。
- UI must not write DB rows, ledgers, repositories, durable config, approvals or
  audit/session tables。
- Missing or invalid config must produce `BLOCKED` with Chinese guidance。

Stage T.1 dry-run provider assembly：

- Providers may be constructed only from typed UI config。
- `dry_run=True`, `apply_confirmed=False`, `apply_requested=False` and target
  is `MOCK` only。
- non-`MOCK` target is impossible；if observed, result is `BLOCKED`。
- nonzero DB delta is `BLOCKED`。
- Every dry-run result must display 是否写库, target, reason and next step。

Stage T.1 result history, evidence and diagnostics：

- Result history is in-memory / session-state only and observability only；it is
  not a source-of-truth and does not add schema。
- Soak evidence display is read-only known baseline evidence display only；it
  must not execute commands or mutate DB。
- Diagnostics remain read-only；running shell commands from the UI requires a
  separate acceptance。

Stage T.1 forbidden actions：

- Paper/SIM apply from this workflow。
- Live Enable, Broker Enable, CTP Enable, SimNow Enable。
- Manual DB edit。
- Force Order, Force Trade, Force Position, Force Accounting。
- Broker/live/CTP/SimNow/network imports or execution paths outside accepted
  dry-run wiring。

Stage T.1 future tests should assert valid config builds a `MOCK` dry-run
provider, invalid config blocks, non-`MOCK` is impossible, dry-run writes no DB
rows, apply remains disabled, history stays in memory, forbidden buttons do not
exist, no forbidden imports are introduced and no schema changes exist。

Stage T.1 validation：

- `git diff --check`。

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
Stage P -> Stage P.1 -> Stage P.2 -> Stage P.3 -> Stage P.4
Stage P.4 -> Stage Q.1 -> Stage Q.2 -> Stage Q.5 -> Stage Q.7 -> SIM Stability Freeze
SIM Stability Freeze -> Stage R.1
Stage R.1 -> Future Production Rollout
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
- Stage P 只冻结 Paper / Sim / Live rollout 契约；Future Production Rollout 才能讨论真实资金部署、生产 CTP / SimNow、broker / exchange certification 或 remote cluster deployment。
- Stage P.3 只允许 paper runtime job / scheduler wiring；不得借机进入 SIM / LIVE / non-`MOCK` execution / real broker。
- Stage P.4 completes local Paper Trading MVP only；不得借机进入 SIM / LIVE / non-`MOCK` execution / real broker。
- Stage R.1 only freezes a local Operator Console contract；it is not live enablement, not broker enablement, not FastAPI, not public network and not schema work。

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

下一步是在 `pre-stage-p-system-acceptance / c834f7c` 基线上执行 Stage P Paper / Sim / Live Rollout Core acceptance review：

```text
Stage P Paper / Sim / Live Rollout
```

Stage N Broker Adapter Core、Stage O Operations / Safety Core、Pre-Stage-P System Acceptance Review 和 Stage P typed rollout safety gates 已完成；Stage P Core 不实现 live enablement。进入任何可执行 Paper / Sim / Live rollout 前必须保持：

- legacy Execution orchestrator 不再作为当前 OMS apply path。
- Trade source-of-truth 只能来自 `NormalizedExecutionReport + applied OMS OrderEvent proof -> OMSToTradeBridgeService -> TradeRepository`。
- ExecutionGateway replay dry-run 为 no-write preview；live replay 冲突默认停止下游。
- Broker / Adapter 不拥有 OMS / Trade / Position / Accounting facts，且 live submit/cancel 默认不启用。
- PAPER / SIM / LIVE 互斥，`LIVE` 默认禁用，并受 operator approval、kill switch、migration readiness、Runtime READY、broker credentials、scheduler/replay policy 和 capital controls 共同约束。

## 13. Stage U.4.1 Resolver Consumer Baseline

Baseline：`stage-u31-static-registry-metadata-coverage / e76811a`。

Stage U.4.1 freezes the local resolver consumer contract in
`docs/market_data/RESOLVER_CONSUMER_CONTRACT.md`. It is documentation-only and
does not add schema, code, tests, DB writes, live feed, quote API, CTP, SimNow,
broker, network integration or non-`MOCK` targets.

Backtest, Paper, SIM and Operator Console dry-run must consume the same
resolver-derived identity from `symbol + trading_day + mode`. They must not
guess `instrument_id`, `trade_instrument_id` or `exchange` independently.

Only `InstrumentResolution.status == RESOLVED` may continue to command, order,
report or trade generation. `NOT_FOUND`, `INVALID_INPUT`, `EXPIRED`,
`AMBIGUOUS` and `METADATA_INVALID` fail closed.

Future implementation stages should route identity through a shared resolver
consumer boundary and preserve resolver lineage on downstream objects. Durable
resolver snapshots remain a separate future schema decision and require a
`Resolver Snapshot Persistence Contract Freeze`.
