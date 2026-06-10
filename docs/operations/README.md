# 运维文档

当前 operations 目录只作为未来本地开发、验证和排障文档入口。

未来非业务实现类文档应放在本目录。

不得提前新增 live、production、remote、kms、cloud 或真实交易运行流程。

Stage M Runtime / Infrastructure contract freeze、Stage O Operations / Safety / Production Readiness contract freeze 和 Stage P Paper / Sim / Live Rollout Contract Freeze 当前记录在：

- `docs/architecture/SYSTEM_MASTER_PLAN.md`
- `docs/domain/DOMAIN_FREEZE.md`

Operations 文档不得绕过该契约定义 runtime 行为。Runtime 只编排应用服务，不拥有或修改 Position、Margin、PnL、Settlement 或 OMS state。

Stage M implementation 当前新增 `src/futures_mvp/modules/runtime`：

- scheduler 默认 disabled。
- replay coordinator 默认 dry-run。
- replay disabled 时为 no-op，不调用 stage callable。
- live replay allowlist 是 hard gate；未列入 stage 始终 dry-run。
- scheduler 只在 service graph 和 health readiness 预检通过后启动。
- health 状态为 `READY`、`DEGRADED`、`FAILED`。
- Runtime 不引入 FastAPI / Celery / Kafka 硬依赖。
- Runtime 不新增 schema，不拥有业务事实。

Stage O implementation 当前新增 `src/futures_mvp/modules/ops_safety` 并接入 Runtime lifecycle、Scheduler 和 ReplayCoordinator；仍不实现生产 rollout：

- Safety source-of-truth 只能来自 runtime health、typed config、scheduler state、replay report、application service status、DB migration state 和 explicit operator decision。
- `raw_payload`、broker rumor、manual DB edits 和 runtime guessing 不得作为 readiness、live submit 或 recovery 判断依据。
- `SafetyConfig` 挂载在 `RuntimeConfig.safety`；unknown environment reject；production requires explicit flags。
- global kill switch、per-stage kill switch、scheduler pause 和 replay pause 都是 hard gate；live submit 默认 disabled。
- Runtime 和 replay 默认 dry-run；broker live disabled；live submit 需要 explicit operator approval。
- invalid config fail closed；unknown environment reject；production mode requires explicit flags；broker credentials absent means broker disabled。
- app cannot become `READY` if DB migration state is incompatible；when migration readiness is enabled, Runtime lifecycle requires an injected read-only checker and missing checker is `FAILED`；runtime auto-migration forbidden unless explicitly allowed。
- observability objects are typed in-memory only：`OpsEvent`、`OpsHealthReport`、`ReplaySummary`、`SchedulerStatus` and `OpsCounters`。
- recovery playbook must cover replay recovery、conflict recovery、broker post-send uncertain recovery and unresolved callback quarantine handling。
- incident states are `READY`、`DEGRADED`、`FAILED`、`PAUSED` and `KILLED`。
- Stage O does not add schema/Alembic、business fact mutation、real live rollout、CTP/SimNow production integration、external monitoring stack、Kubernetes/systemd deployment、remote server deployment or automatic self-healing trade repair。

Stage P Core 当前实现 typed rollout safety gates，但仍不实现真实 rollout：

- `SafetyConfig.rollout` carries `RolloutConfig`；default rollout mode is `PAPER`。
- Rollout modes are `PAPER`、`SIM` and `LIVE`；单个 Runtime 任一时刻只能处于一个 mode。`RuntimeConfig.environment` 和 `ExecutionTarget` 都不是 rollout mode。
- Promotion evaluator supports `PAPER -> SIM` and `SIM -> LIVE`；rollback evaluator supports `LIVE -> SIM`、`LIVE -> PAPER`、`SIM -> PAPER`。
- Live is disabled by default and requires explicit live flag、operator approval、broker enabled、credentials present、migration compatible、Runtime `READY`、kill switch released、replay not running、scheduler healthy、capital controls passed and no unresolved critical incidents。
- Stage P capital controls implement max order size、max position size、max daily loss、account whitelist and allowed instrument list；these are safety gates, not OMS source-of-truth。
- Runtime command interaction remains `Runtime -> ExecutionGateway -> BrokerAdapter` only；Runtime must not call Broker directly or mutate OMS / Trade / Position / Accounting directly。
- Mode-aware replay policy allows PAPER / SIM replay, keeps LIVE live apply disabled by default, and requires explicit approval plus `allow_live_apply` for LIVE live apply。
- `FAILED`、`KILLED` and `PAUSED` forbid entering `LIVE`。
- Stage P does not implement real capital deployment、production CTP、production SimNow、broker certification、exchange certification、remote cluster deployment、durable approval/audit table or non-`MOCK` ExecutionGateway support。

Stage P.1 Paper Trading Enablement minimal harness keeps the next phase local and deterministic：

- PAPER allows local deterministic paper execution only；no real broker、CTP、SimNow、live account、external network execution or real capital。
- Paper must continue through `Runtime -> ExecutionGateway -> Paper/Mock adapter -> RawExecutionReport -> NormalizedExecutionReport -> OMS Event -> Trade -> Position -> Accounting`。
- Paper execution owns no order/trade/position/accounting truth；OMS、normalized reports、trade ledger、position and accounting engines keep ownership。
- `ExecutionTarget.MOCK` remains the only enabled target；`ExecutionTarget.PAPER` requires separate implementation and acceptance。
- `PaperExecutionHarness` input is typed `ExecutionCommand`；outputs are typed `ExecutionCommandResult` and `RawExecutionReport` evidence。
- Implemented fill policies are immediate full fill、immediate reject、pre-send timeout and post-send uncertain；partial fill、multi-fill、slippage、market-depth simulation、latency model and timeout recovery are deferred。
- Fill policies are deterministic、config-bound、replayable and must not mutate OMS directly。
- Paper reports must not directly apply OMS, create Trade, update Position or update Accounting。
- Paper still obeys rollout mode `PAPER`、kill switch、scheduler pause、replay pause、migration readiness、capital controls、account whitelist and instrument whitelist。
- Paper replay is allowed, dry-run remains default unless explicitly applying paper facts, conflicts stop downstream, duplicates no-op, and no live apply or broker network is allowed。
- Next implementation should add an approved paper runtime entrypoint that enforces Runtime / Stage O/P safety gates before invoking `PaperExecutionHarness` while keeping `ExecutionTarget.MOCK` until explicit `PAPER` target acceptance。

Stage P.2 Paper Trading End-to-End Flow adds the paper-only coordinator：

- `PaperTradingCoordinator` runs `ExecutionCommand -> PaperExecutionHarness -> RawExecutionReport -> ExecutionReportNormalizer -> OMSEventApplicationService -> OMSToTradeBridgeService -> PositionManager -> Margin/PnL/Settlement engines`。
- `PaperRunContext` carries rollout mode, safety config, migration readiness, capital-control context, order lineage, trading day and accounting config hash。
- Safety preflight requires rollout mode `PAPER`, compatible migration readiness, released kill switch, scheduler/replay not paused and passing capital controls before harness execution。
- Full fill can traverse the accepted service chain and creates Trade only with applied OMS event proof。
- Reject may apply OMS rejection but creates no Trade, Position or Accounting facts。
- Timeout and post-send uncertain produce no report and no downstream mutation。
- Duplicate reports no-op; conflict or error stops downstream。
- `ExecutionTarget.MOCK` remains the only enabled target；`ExecutionTarget.PAPER` / `SIM` / `LIVE` remain disabled and no real broker/network dependency is introduced。

Stage P.3 Paper Runtime Job / Scheduler Wiring is implemented as the minimal paper runtime callable boundary：

- Paper runtime job may run only under rollout mode `PAPER`, call `PaperTradingCoordinator` through typed `PaperRunContext`, and return typed `PaperRunResult` / `PaperJobResult`。
- `PaperJobConfig` defaults are disabled and fail-closed：`enabled = False`, explicit `job_name`, `rollout_mode = PAPER`, dry-run default where applicable, `max_commands_per_run`, `stop_on_first_error`, `stop_on_conflict`, and required migration / capital / scheduler-pause / replay-pause gates。
- Runtime service graph may hold `PaperTradingCoordinator`, a paper job callable and `PaperJobConfig`; Runtime must not call `PaperExecutionHarness`, BrokerAdapter, or OMS / Trade / Position / Accounting repositories directly。
- Scheduler may call only the injected paper job callable and record typed result/status; it must not construct commands from raw payload, mutate business facts, bypass the coordinator, call the harness directly or call broker directly。
- Before job execution, rollout mode `PAPER`, scheduler enabled, paper job enabled, kill switch released, scheduler not paused, replay not paused, migration compatible, capital controls passed, account allowed and instrument allowed must all pass。
- Any failed gate returns a typed blocked/rejected job result, does not call the coordinator and creates no business side effect。
- Dry-run must not mutate ledgers; paper apply may mutate only through the accepted Stage P.2 service chain after all gates pass；no live apply is allowed。
- `PaperJobStatus` is frozen as `DISABLED`, `BLOCKED`, `DRY_RUN`, `COMPLETED`, `DUPLICATE`, `CONFLICT`, `ERROR`。
- `PaperJobResult` is observability only, not business source-of-truth, and carries job name, status, reason, paper run result, diagnostic timestamps, processed command count and conflict/error counters。
- Command source is explicit typed `ExecutionCommand` input or an injected typed command provider；raw payload commands, broker callbacks as commands, runtime guessing and strategy direct bypass are forbidden。
- P.3 non-goals：strategy live loop, market data scheduler, SIM, LIVE, non-`MOCK` gateway target, real broker, remote deployment, durable job/audit table and external monitoring stack。

Stage P.4 Paper Runbook / Local Paper Session completes the local Paper Trading MVP：

- `PaperLocalSession` accepts explicit typed `ExecutionCommand` values or an injected typed command provider and orchestrates `PaperRuntimeJob` only。
- `PaperSessionConfig` carries session name, runtime id, trading day, account id, dry-run mode, max command count, clean-start flag, stop-on-error/conflict policy and explicit apply confirmation。
- `PaperSessionResult` is observability only and is not a business source-of-truth。
- Dry-run is default；apply requires explicit `apply_confirmed=True` and still goes through `PaperRuntimeJob -> PaperTradingCoordinator`。
- Stage P.1 minimal harness, Stage P.2 paper E2E, Stage P.3 runtime job wiring and Stage P.4 local session/runbook are complete。
- Paper Trading local MVP is complete；SIM / LIVE / non-`MOCK` execution target support remain not implemented。

Paper Trading Local MVP stable baseline：

- Status：STABLE BASELINE。
- Baseline commit：`dde3e66` on `main`。
- Previous tag：`stage-p4-paper-local-session-complete`。
- Current soak evidence：Day 0 rerun passed、Day 1 passed、10x passed、Day-long 30-run passed、Multi-day 3 trading days passed。

Stable Paper chain：

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

Stable Paper safety invariants：

- dry-run no mutation。
- apply completed。
- duplicate no-op。
- conflict stop。
- `ExecutionTarget.MOCK` only。
- no `ExecutionTarget.PAPER` / `SIM` / `LIVE` enablement。
- no broker / CTP / SimNow / live / network dependency。
- settlement snapshot created。
- created trade has `source_order_event_id`。

Stable Paper soak evidence summary：

- `uv run pytest`：892 passed, 11 xfailed。
- `uv run ruff check .`：passed。
- `uv run mypy src`：passed。
- `uv run alembic current`：`0016_stage_n_report_identity`。
- 3-day soak：30/30 dry-run ok；30/30 apply completed；30/30 duplicate no-op。
- 3-day row growth：`normalized_execution_reports +60`, `trades +30`, `positions +30`, `position_events +30`, `margin_snapshots +30`, `pnl_snapshots +30`, `settlement_snapshots +30`。
- 3-day targets：`MOCK` only。

Paper stable baseline non-goals remain：

- SIM。
- LIVE。
- `ExecutionTarget.PAPER` / `SIM` / `LIVE` enablement。
- real broker。
- CTP。
- SimNow。
- remote deployment。
- production rollout。

SIM Gap Review result：ACCEPT。

Next allowed gate：Stage Q.1 SIM Trading Contract Freeze。

Not allowed before that gate：SIM implementation, LIVE work or real broker work。

Stage Q.1 SIM Trading Contract Freeze：

- Baseline：`paper-local-mvp-stable-baseline / 73a9f39`。
- Scope：documentation-only contract freeze；no code, no schema, no `ExecutionTarget.SIM`, no SimNow / CTP / LIVE / broker / network。
- SIM is an independent rollout mode；it is not a PAPER alias and not a shortcut rehearsal for LIVE。
- SIM currently does not connect to real broker, SimNow, CTP, live account or broker network。
- Future SIM may implement local or controlled simulated exchange behavior, deterministic or configured simulated reports and richer execution behavior than Paper, but Stage Q.1 implements none of it。

SIM mode boundary：

- `RolloutMode.SIM` is mutually exclusive with PAPER and LIVE。
- One runtime instance may run only one mode。
- Paper stable baseline does not automatically upgrade to SIM。
- SIM must not enable LIVE gates, LIVE credentials, live apply or live broker credential access。

SIM execution target policy：

- `ExecutionTarget.MOCK` remains the only enabled target。
- Stage Q.1 does not enable `ExecutionTarget.SIM`。
- Future `ExecutionTarget.SIM` enablement requires separate implementation and acceptance review。
- `ExecutionTarget.SIM` is not `RolloutMode.SIM`; `RolloutMode.SIM` does not automatically allow `ExecutionTarget.SIM`。

SIM harness / adapter boundary：

- Future SIM must add a `SimExecutionHarness` or `SimAdapter` contract。
- SIM must not directly reuse `PaperExecutionHarness` as the SIM execution engine。
- A shared deterministic evidence builder may be extracted only if Paper and SIM boundaries remain explicit。
- Input must be typed `ExecutionCommand`。
- Output must be typed `ExecutionCommandResult` plus `RawExecutionReport` evidence。
- The harness / adapter must not mutate OMS, Trade, Position or Accounting state。
- `raw_payload` remains diagnostic-only and never source-of-truth。

SIM source-of-truth and report path：

- SIM harness does not own order, trade, position or accounting truth。
- OMS owns order truth；`NormalizedExecutionReport` owns execution report facts；Trade ledger owns trade facts；Position owns position facts；Accounting owns margin, PnL and settlement snapshots。
- All SIM evidence must flow through `RawExecutionReport -> ExecutionReportNormalizer -> OMSEventApplicationService -> OMSToTradeBridgeService -> PositionManager -> MarginEngine / PnLEngine / SettlementEngine`。
- Direct OMS apply, direct Trade creation, direct Position update and direct Accounting update are forbidden。

SIM identity / idempotency：

- SIM `raw_report_id` and `adapter_order_ref` must be deterministic。
- SIM `fill_id` / `exchange_trade_id` must be deterministic or sourced from a typed simulated exchange event。
- UUID, timestamp-now and DB id must not be business fact identity。
- same identity + same canonical payload means duplicate / no-op。
- same identity + different canonical payload means conflict。

SIM safety and replay policy：

- SIM requires Runtime READY, `RolloutMode.SIM`, migration compatible, kill switch released, scheduler and replay not paused, explicit operator approval for PAPER -> SIM promotion, configured capital controls, account whitelist, instrument whitelist and no unresolved critical incident。
- SIM still forbids live flag, live credentials, live apply and real broker。
- SIM replay defaults to dry-run；apply requires explicit SIM approval。
- Duplicate replay must no-op；conflict replay must stop。
- SIM replay must not perform live apply, use broker network or repair business ledgers manually。

SIM fill / execution behavior contract：

- Future SIM may support immediate fill, partial fill sequence, reject, timeout, post-send uncertain, latency simulation, slippage and order book / depth simulation。
- Each future behavior must be deterministic or config-bound, produce typed `RawExecutionReport` evidence and avoid direct fact mutation。
- Stage Q.1 implements none of those behaviors。

SIM migration decision：

- No schema or Alembic migration in Contract Freeze。
- Future SIM implementation should reuse existing ledgers unless a durable SIM session / audit table is separately frozen and accepted。

SIM non-goals remain：

- SIM runtime。
- SimNow。
- CTP。
- LIVE。
- real capital。
- remote deployment。
- production broker certification。
- `ExecutionTarget.SIM` enablement。
- schema changes。

Next recommendation：run SIM Harness Gap Review, decide `SimExecutionHarness` versus shared execution evidence builder and do not implement SIM until that review is accepted。

Stage Q.2 SIM Harness Contract Freeze：

- Baseline：`stage-q1-sim-trading-contract-freeze / b459f2d`。
- SIM Harness Gap Review：ACCEPT。
- Route decision：adopt `SharedExecutionEvidenceBuilder + SimExecutionHarness`。
- Rejected：directly reusing `PaperExecutionHarness` as SIM engine, changing Paper harness into a generic execution engine and enabling `ExecutionTarget.SIM`。
- Scope：documentation-only；no code, no `src` / tests, no schema, no broker / SimNow / CTP / LIVE / network。

Shared builder boundary：

- Allowed：deterministic evidence identity construction, typed `BrokerCallbackEvidence` construction, report sequence construction, canonical input validation and cumulative / remaining quantity calculation。
- Forbidden：holding rollout mode, deciding PAPER / SIM safety gates, calling adapters, calling OMS / Trade / Position / Accounting, writing DB or owning order / trade / position / accounting source-of-truth。

Namespace / prefix rules：

- Paper prefix remains `paper_*`。
- SIM prefix must be `sim_*`。
- Paper `adapter_name` remains `paper_harness`。
- SIM `adapter_name` must be `sim_harness`。
- `raw_report_id`, `fill_id`, `exchange_trade_id` and `exchange_order_id` must include mode namespace。
- Paper and SIM identity domains must not collide。

Paper regression contract：

- Paper wrapper must preserve `ExecutionTarget.MOCK` only, `adapter_name = paper_harness`, `paper_*` identity prefix, full-fill `ACKED -> FILLED`, reject / timeout / uncertain behavior, no direct mutation, no broker / network and Paper stable baseline invariants。

SimExecutionHarness contract：

- Future SIM harness input is typed `ExecutionCommand`。
- Future SIM harness output is typed `ExecutionCommandResult` plus `RawExecutionReport` evidence。
- Future SIM harness uses `SharedExecutionEvidenceBuilder`。
- Future SIM harness owns no business facts and must not directly mutate OMS, Trade, Position or Accounting。
- Future SIM harness must not connect to real broker, SimNow, CTP, live account or network。
- Stage Q.2 adds no schema and does not enable `ExecutionTarget.SIM`。

SIM policy / scenario contract：

- Future SIM may support immediate full fill, reject, timeout, post-send uncertain, partial fill sequence, latency simulation, slippage and order book / depth simulation。
- Stage Q.2 implements none of these policies。
- Future behavior must be deterministic or config-bound。

Partial fill contract：

- `ACKED` must precede `PARTIALLY_FILLED` / `FILLED` when required by OMS state machine。
- `cumulative_filled_qty` must be monotonic increasing。
- per-report `filled_qty` must be positive for fill reports。
- `remaining_qty` must be non-negative。
- final `FILLED` cumulative quantity must equal order quantity。
- overfill is forbidden。
- report identity must be deterministic per sequence index。
- duplicate same report must no-op。
- conflict must stop。

Safety boundary：

- SIM harness does not own safety gates。
- SIM runtime / job / session must enforce `RolloutMode.SIM`, PAPER -> SIM promotion approval, Runtime READY, migration compatible, kill switch released, scheduler and replay not paused, capital controls, account whitelist, instrument whitelist, no live credentials and no live apply。

Execution target policy：

- Stage Q.2 does not enable `ExecutionTarget.SIM`。
- Gateway still rejects non-`MOCK` targets。
- SIM harness may exist as a local controlled evidence generator only after implementation。
- `RolloutMode.SIM` does not imply `ExecutionTarget.SIM`。

Source-of-truth / report path：

- All SIM evidence must enter `RawExecutionReport -> ExecutionReportNormalizer -> OMSEventApplicationService -> OMSToTradeBridgeService -> PositionManager -> MarginEngine / PnLEngine / SettlementEngine`。
- SIM harness and shared builder never own facts。
- Direct OMS, Trade, Position or Accounting mutation remains forbidden。

Migration decision：

- No schema or Alembic migration。
- Durable SIM session / audit storage requires a separate contract freeze and acceptance review。

Future test matrix：

- Paper regression outputs unchanged after shared builder extraction。
- SIM immediate fill `ACKED -> FILLED`。
- SIM partial fill `ACKED -> PARTIALLY_FILLED -> FILLED`。
- SIM reject / timeout / post-send uncertain。
- deterministic identities with `sim_*` prefix。
- no Paper / SIM identity collision。
- duplicate no-op。
- conflict stop。
- no direct mutation。
- no broker / network imports。
- gateway still rejects `ExecutionTarget.SIM`。
- no schema / Alembic migration。

Stage Q.2 non-goals：

- shared builder code。
- sim harness code。
- SIM runtime / job / session。
- `ExecutionTarget.SIM`。
- SimNow / CTP / live。
- schema changes。

Next recommendation：implement shared builder extraction, wrap Paper reports through shared builder without changing output and implement minimal `SimExecutionHarness` only after Paper regression review。

Stage Q.5 SIM E2E Contract Freeze：

- Baseline：`stage-q4-minimal-sim-execution-harness / 48a62ab`。
- Scope：documentation-only；no code, no `src` / tests, no schema, no `ExecutionTarget.SIM`, no broker / SimNow / CTP / LIVE / network。
- SIM E2E may only use local controlled SIM evidence, typed `ExecutionCommand` input, `SimExecutionHarness` output and the existing report / accounting pipeline。
- SIM E2E must not use real broker, external exchange, live capital or `ExecutionTarget.SIM` enablement。

SIM E2E coordinator boundary：

- Future implementation must add `SimTradingCoordinator`, `SimRunContext` and `SimRunResult`。
- SIM E2E must not reuse `PaperTradingCoordinator` as SIM coordinator。
- Shared orchestration helpers are allowed only if they do not own PAPER / SIM mode semantics。
- Coordinator may only orchestrate `SimExecutionHarness -> RawExecutionReport -> ExecutionReportNormalizer -> OMSEventApplicationService -> OMSToTradeBridgeService -> PositionManager -> MarginEngine / PnLEngine / SettlementEngine`。

SIM E2E source-of-truth：

- SIM coordinator / harness do not own order truth, execution report facts, trade truth, position truth or accounting truth。
- Facts remain owned by OMS, `NormalizedExecutionReport`, Trade ledger, Position and Accounting snapshots。

SIM E2E safety preflight：

- Must run before `SimExecutionHarness`。
- Required gates：`RolloutMode.SIM`, explicit operator approval for PAPER -> SIM, Runtime READY, migration compatible, kill switch released, scheduler / replay not paused, capital controls pass, account whitelist, instrument whitelist, no live credentials, no live apply and no unresolved critical incident。

SIM E2E report sequence：

- Full fill：`ACKED -> FILLED`。
- Reject：`REJECTED` report, no Trade。
- Timeout / post-send uncertain：command result only, no report, no downstream。
- Future partial fill：`ACKED -> PARTIALLY_FILLED* -> FILLED`, cumulative monotonic, no overfill, duplicate no-op and conflict stop。

SIM E2E duplicate / conflict policy：

- duplicate normalized report no-ops。
- duplicate OMS event no-ops。
- duplicate trade no-ops。
- any conflict / error stops downstream。
- no later Position or Accounting mutation after stop。

SIM E2E accounting contract：

- Use consistent `position_version`, `trading_day` and `config_hash`。
- Settlement must consume run-local margin and PnL snapshots。
- Preserve settlement identity checks。
- Do not fake settlement facts。
- Do not use instrument-only fallback。

SIM E2E target / runtime policy：

- `ExecutionTarget.MOCK` remains the only enabled target。
- `ExecutionTarget.SIM` remains disabled。
- `RolloutMode.SIM` does not imply `ExecutionTarget.SIM`。
- `SimExecutionHarness` may reject non-`MOCK` until target enablement is separately frozen。
- Stage Q.5 does not implement `SimRuntimeJob`, `SimLocalSession`, scheduler wiring or target enablement。

SIM E2E migration decision：

- No schema or Alembic migration。
- Durable SIM session / audit storage requires a separate contract freeze and acceptance review。

Future SIM E2E test matrix：

- non-SIM mode rejected。
- safety gate blocks。
- full fill E2E completes。
- reject no trade。
- timeout / post-send uncertain no downstream。
- duplicate no-op。
- report conflict stop。
- OMS duplicate stop。
- trade duplicate stop。
- accounting settlement identity consistency。
- no non-`MOCK` gateway enablement。
- no broker / network / schema。

Stage Q.5 non-goals：

- SIM E2E code。
- SIM runtime / job / session。
- `ExecutionTarget.SIM`。
- SimNow / CTP / live。
- real broker。
- partial fill implementation。
- slippage / depth / latency implementation。
- schema changes。

Paper local session runbook：

1. Confirm branch/tag：verify the working branch and expected tag before any local paper session.
2. Run validation commands：`uv run pytest`、`uv run ruff check .`、`uv run mypy src`。
3. Confirm DB migration visibility：`uv run alembic heads` and `uv run alembic current`。
4. Confirm safety：rollout mode `PAPER`, broker disabled, live disabled, kill switch released, scheduler not paused, replay not paused, migration compatible, capital controls configured, account allowed and instrument allowed。
5. Run dry-run session first：use typed `ExecutionCommand` input or an injected typed command provider; do not use raw payload commands。
6. Inspect `PaperSessionResult`：confirm status, reason, processed command count, duplicate count, conflict count, error count and nested `PaperJobResult`。
7. Run apply session only after dry-run is clean：set explicit apply confirmation and keep `ExecutionTarget.MOCK`。For immediate full-fill paper commands, the paper harness emits deterministic ACKED evidence before FILLED evidence; OMS transition rules must still accept each event in order。
8. Inspect paper facts through accepted ledgers/services：normalized reports, OMS order state, trades, positions, margin snapshots, PnL snapshots and settlement snapshots。Paper settlement must consume the margin and PnL snapshots generated by the same paper run and their `account_id + instrument_id + position_version + trading_day` identity must match the settled position。
9. Rollback/stop by safety controls：activate kill switch, scheduler pause or replay pause; do not edit business ledgers manually。
10. Forbidden during Paper local session：no SIM, no LIVE, no real broker, no CTP, no SimNow, no network broker, no manual DB edits, no raw payload command source and no `ExecutionTarget.PAPER` / `SIM` / `LIVE` enablement。
