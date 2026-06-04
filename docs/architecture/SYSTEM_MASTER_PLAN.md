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

当前尚未实现为业务能力的部分：

- Application Execution Orchestrator。
- OMS public UNKNOWN entry。
- 类型化 Fill domain 与真实 Trade/Fill 接入。
- Position Manager、Margin Engine、PnL Engine、Settlement Engine。
- Tick / Bar / Kline / MarketContext / FeatureSnapshot。
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
- `positions(account_id, instrument_id)` 是 live position source-of-truth。
- Margin、PnL、Settlement 只能基于类型化 Trade、Position、Market price、Settlement price 和 account context 计算。
- `account_snapshots`、`settlement_snapshots` 是快照与审计，不替代 live source-of-truth。

### Strategy / Market Data Layer

- Market adapter 将外部行情解析为 typed Tick / Bar / Kline。
- Market Data Service 负责去重、排序、数据质量、交易日/session 归属。
- Feature Builder 生成 deterministic `FeatureSnapshot`。
- Strategy 只消费 typed market input 或 `FeatureSnapshot`，只输出 `Signal`。
- Strategy 不创建订单，不调用 OMS，不调用 Execution。
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

1. Market adapter 接收外部行情，解析为 typed Tick / Bar / Kline。
2. Market Data Service 执行 data quality gate，处理缺口、延迟、乱序、异常价格和 session 归属。
3. Feature Builder 基于 typed market facts、calendar、session 和规则版本生成 deterministic `FeatureSnapshot`。
4. Strategy 消费 `FeatureSnapshot`，输出 `Signal`。
5. Application Service 将 `Signal` 转换为 `OrderRequest`，生成稳定 `client_order_id`。
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
18. Trade ledger 去重后进入 Position Manager。
19. Position Manager 更新 live `positions`，处理开仓、平今、平昨、冻结/解冻和 today/yesterday bucket。
20. Margin Engine 基于 Position、instrument rules、account context 计算保证金。
21. PnL Engine 基于 Trade、Position、last price、settlement price 计算 realized / unrealized PnL。
22. Settlement Engine 在交易日边界执行结算、结算价更新、保证金重算、PnL 归集和 today -> yesterday roll。
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
- 真实上下文风控属于 Stage I；Risk -> OMS 自动编排仍由 application layer 负责，Risk 不直接写 OMS、不直接改订单状态。

### Exchange Report Idempotency Key

- Execution report 幂等优先使用 typed `exchange_report_id`。
- 映射后的订单事件继续遵守当前 `event_source + external_event_id` 幂等键。
- Duplicate report / event 不得重复推进 OMS，不得重复累计成交。
- Adapter 和 runtime retry 不得绕过 report/event 幂等。

### Fill / Trade

- 真实成交必须有类型化 `Fill` / `Trade` 事实。
- `Trade` ledger 是会计主链输入。
- 成交去重不能依赖订单状态回报 ID；应使用明确 exchange trade identity。
- 成交价格、成交数量、trade id、fill id、手续费等不得藏在 `raw_payload`。

### Position

- `positions(account_id, instrument_id)` 是 live position source-of-truth。
- Pending、submitted、rejected 或其他未成交订单都不是真实持仓。
- 开仓、平今、平昨、冻结、解冻、today/yesterday roll 必须类型化。
- `account_snapshots` 和 `settlement_snapshots` 不是 live position source-of-truth。

### Margin / PnL / Settlement

- Margin 必须基于 Position、instrument rules、account context 和价格源类型化计算。
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
- Outputs：Fill/Trade contract、schema/repository migration、trade dedupe rule、accounting entry point。
- Allowed changes：Domain / DB / interface / repository / tests 的明确 migration。
- Forbidden changes：不用 `raw_payload` 放成交价、数量、trade id、fill id；不让 mapper 直接更新 position。
- Required tests：domain decimal contract、trade idempotency、duplicate fill、partial fill sequence、full fill, schema round trip, replay fixture。
- Acceptance criteria：真实成交可类型化入账；重复成交不重复生成 Trade；status-only fill 不再承担会计事实。
- Suggested tag：`stage-b-fill-trade-domain-migration`。

### Stage C: Position Manager

- Goal：建立基于 Trade ledger 的 live position 更新链。
- Inputs：typed Trade、current Position model、today/yesterday bucket、offset。
- Outputs：PositionManager、Position repository/UoW、开仓/平今/平昨/冻结/解冻规则。
- Allowed changes：position module、repository、DB tests、position replay tests。
- Forbidden changes：不把 pending/submitted 订单当真实持仓；不让 Risk 自查 Position DB。
- Required tests：open long/short、close today、close yesterday、insufficient bucket、duplicate trade、position replay。
- Acceptance criteria：重复 trade 不重复改仓；positions 与 replay 一致。
- Suggested tag：`stage-c-position-manager`。

### Stage D: Margin Engine

- Goal：计算保证金并提供 typed margin context。
- Inputs：Position、instrument rules、account context、order/trade price。
- Outputs：MarginEngine、margin result、RiskContext margin input、margin audit。
- Allowed changes：margin module、context builder、focused tests。
- Forbidden changes：Risk 不直接调用 MarginEngine 或 DB；不把 margin 放入 raw payload。
- Required tests：long/short margin、position margin、order required margin、margin rate missing, Decimal-only, replay consistency。
- Acceptance criteria：`margin_used` 与规则可重放；Risk 只消费 application layer 注入的 typed margin context。
- Suggested tag：`stage-d-margin-engine`。

### Stage E: PnL Engine

- Goal：计算 realized / unrealized PnL。
- Inputs：Trade、Position、last price、settlement price、cost basis。
- Outputs：PnL projection、position PnL update、mark-to-market result。
- Allowed changes：pnl module、price context、tests。
- Forbidden changes：不混用成交价、最新价、结算价；不从行情 raw payload 取价格事实。
- Required tests：realized close PnL、unrealized mark-to-market、settlement price mark、Decimal-only、replay consistency。
- Acceptance criteria：同一 Trade / Position / price input 得到 deterministic PnL。
- Suggested tag：`stage-e-pnl-engine`。

### Stage F: Settlement Engine

- Goal：执行日终结算、结算价更新、PnL 归集和 today -> yesterday roll。
- Inputs：Position、PnL、Margin、settlement price、trading calendar/session。
- Outputs：SettlementEngine、settlement snapshot、idempotent settlement record。
- Allowed changes：settlement module、schema/repository if needed、settlement tests。
- Forbidden changes：不把 settlement 放回 MockExchange；不通过 JSON snapshot 补 live facts。
- Required tests：settlement idempotency、today-to-yesterday roll、PnL carry, margin recompute, duplicate settlement, replay restore。
- Acceptance criteria：同一 `account_id + trading_day` 结算幂等；结算后 positions 与 snapshot 可对账。
- Suggested tag：`stage-f-settlement-engine`。

### Stage G: Market Data / Feature Snapshot

- Goal：建立 typed market data、MarketContext、FeatureSnapshot 和 data quality gate。
- Inputs：instruments、trading calendar/session、external market adapter output、historical data source。
- Outputs：Tick / Bar / Kline、MarketContext、FeatureSnapshot、data quality events、replay fixtures。
- Allowed changes：market data domain/interface/schema/tests、feature builder、replay reader。
- Forbidden changes：不改 OMS 状态机；Risk 不直连行情；Strategy 不创建订单；不使用 raw_payload 补价格或 feature 事实。
- Required tests：tick/bar/kline Decimal contract、session/trading_day attribution、gap/late/out-of-order、stale market, feature deterministic replay。
- Acceptance criteria：同一历史输入可复现 FeatureSnapshot 和 Signal；异常行情可被标记/隔离。
- Suggested tag：`stage-g-market-data-feature-snapshot`。

### Stage H: Strategy / Signal Lifecycle

- Goal：规范 Strategy 输入输出、Signal 幂等和 lifecycle。
- Inputs：FeatureSnapshot、当前 `Signal` model、strategy config。
- Outputs：typed strategy input、Signal idempotency、strategy audit。
- Allowed changes：strategy interface migration、Signal lifecycle tests。
- Forbidden changes：Strategy 不创建 OrderRequest，不调用 OMS / Risk / Execution。
- Required tests：same input same Signal、disabled strategy、duplicate signal、signal timestamp, Decimal-only fields。
- Acceptance criteria：Strategy 只输出 `Signal`，应用层负责后续 order intent。
- Suggested tag：`stage-h-strategy-signal-lifecycle`。

### Stage I: Risk Context / Portfolio Risk Upgrade

- Goal：从 pure Risk 升级到 account / portfolio / position / intraday / kill switch context 风控。
- Inputs：Position、Market Data、Strategy Signal、RiskConfig、account context。
- Outputs：RiskContext、portfolio/account risk checks、intraday limits、kill switch decision/audit。
- Allowed changes：risk module、risk context models、tests、必要文档。
- Forbidden changes：Risk 不直接写 OMS/DB，不直接改订单状态，不绕过 application layer。
- Required tests：account risk、portfolio exposure、position risk、intraday limit、kill switch、first rejection / audit。
- Acceptance criteria：真实上下文风控 deterministic，可 replay，不污染 OMS/Execution。
- Suggested tag：`stage-i-risk-context-portfolio-risk-upgrade`。

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
- Market Data / Feature Snapshot 是 Strategy / Signal Lifecycle 的前置，并应作为并行主线提前规划。
- Risk Context / Portfolio Risk Upgrade 依赖 Position、Market Data、Strategy/Signal，不应提前硬接真实账户上下文。
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
- 没有 Stage I，不把真实 account / portfolio / position / intraday / kill switch 风控写成已完成。
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
- Risk 当前 pure core 不依赖 OMS、DB、Redis、HTTP、PositionManager、MarginEngine；Stage I 只能通过 application layer 注入 typed RiskContext。
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
- Stage G / H 的 Market Data / Strategy 主线应尽早冻结契约，避免后续 Stage I RiskContext 缺少 typed market 和 signal 输入。
- 不应直接跳到 broker adapter 或 runtime infrastructure。
