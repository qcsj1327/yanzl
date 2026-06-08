# 运维文档

当前 operations 目录只作为未来本地开发、验证和排障文档入口。

未来非业务实现类文档应放在本目录。

不得提前新增 live、production、remote、kms、cloud 或真实交易运行流程。

Stage M Runtime / Infrastructure contract freeze 当前记录在：

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
