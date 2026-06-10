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

Paper local session runbook：

1. Confirm branch/tag：verify the working branch and expected tag before any local paper session.
2. Run validation commands：`uv run pytest`、`uv run ruff check .`、`uv run mypy src`。
3. Confirm DB migration visibility：`uv run alembic heads` and `uv run alembic current`。
4. Confirm safety：rollout mode `PAPER`, broker disabled, live disabled, kill switch released, scheduler not paused, replay not paused, migration compatible, capital controls configured, account allowed and instrument allowed。
5. Run dry-run session first：use typed `ExecutionCommand` input or an injected typed command provider; do not use raw payload commands。
6. Inspect `PaperSessionResult`：confirm status, reason, processed command count, duplicate count, conflict count, error count and nested `PaperJobResult`。
7. Run apply session only after dry-run is clean：set explicit apply confirmation and keep `ExecutionTarget.MOCK`。
8. Inspect paper facts through accepted ledgers/services：normalized reports, OMS order state, trades, positions, margin snapshots, PnL snapshots and settlement snapshots。
9. Rollback/stop by safety controls：activate kill switch, scheduler pause or replay pause; do not edit business ledgers manually。
10. Forbidden during Paper local session：no SIM, no LIVE, no real broker, no CTP, no SimNow, no network broker, no manual DB edits, no raw payload command source and no `ExecutionTarget.PAPER` / `SIM` / `LIVE` enablement。
