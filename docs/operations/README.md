# 运维文档

当前 operations 目录只作为未来本地开发、验证和排障文档入口。

未来非业务实现类文档应放在本目录。

不得提前新增 live、production、remote、kms、cloud 或真实交易运行流程。

Stage M Runtime / Infrastructure contract freeze 和 Stage O Operations / Safety / Production Readiness contract freeze 当前记录在：

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
