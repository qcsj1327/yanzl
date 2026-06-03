# 项目结构基线

本文档定义当前项目的目录职责和 `docs/` 长期分层规则。除非经过明确确认，不得随意新增顶层目录或 `docs/` 根目录文件。

## 顶层目录约束

- `src/`：项目源码，按 `domain`、`interfaces`、`db`、`modules`、`demo` 分层。
- `tests/`：测试代码，按 `unit` 和 `integration` 分层，并在其下继续按模块职责分组。
- `alembic/`：数据库 migration。
- `docs/`：中文设计契约、测试矩阵和项目规则。
- `docker-compose.yml`：本地 PostgreSQL 和 Redis 基础设施。
- `pyproject.toml`：uv/Python 依赖、测试和静态检查配置。

不得随意新增新的顶层业务目录。确需新增时，必须先说明职责边界、与现有目录的关系，以及是否影响当前冻结契约。

## Tech Stack Roadmap

### Current Core Stack

当前核心栈只包括已经进入项目契约或本地验证链路的技术：

- Python 3.12。
- uv。
- pytest。
- ruff。
- mypy。
- Pydantic Domain Model 当前事实。
- SQLAlchemy。
- Alembic。
- PostgreSQL。
- Protocol 接口。

Redis 目前只作为本地基础设施依赖存在，尚未进入 OMS / Risk / Execution 当前业务实现路径。

### Planned Runtime / Infra Stack

以下不是永久禁止项，而是后续 Runtime / Infrastructure / Adapter 阶段技术栈。它们必须在对应阶段通过契约、测试矩阵和结构审查后引入，不得在当前 Phase 4 Execution pure mapper 阶段提前接入：

- FastAPI：API / Web 控制台服务层。
- Celery：异步任务、定时任务和重试。
- Kafka：行情、订单回报和事件流。
- Redis：缓存、锁、pubsub 和临时状态。
- 云服务：部署、监控和运维。
- KMS：密钥管理。
- CTP / SimNow / broker adapter：真实或仿真柜台适配。
- async framework：行情和交易回报并发处理。
- config system：多环境、多账户和多策略配置。

当前阶段的边界仍然成立：

- OMS 不依赖 EMS / Exchange。
- Risk 不依赖 OMS / DB。
- Execution mapper 不接真实交易接口。

## docs 分类规则

`docs/` 当前只允许以下职能目录：

- `architecture/`：项目结构、分层、目录治理规则。
- `domain/`：Domain 字段冻结契约和领域边界。
- `oms/`：OMS 状态机、Repository / UnitOfWork / Application Service、测试矩阵等 OMS 契约。
- `risk/`：风控模块文档。
- `execution/`：EMS、Mock Exchange、执行链路文档。
- `position/`：持仓、保证金、PnL 相关文档。
- `settlement/`：结算、结算快照、今仓转昨仓相关文档。
- `operations/`：本地开发、验证、排障等非业务实现文档。

除 `docs/README.md` 外，不得随意在 `docs/` 根目录新增文件。新模块文档必须进入对应职能目录。

## tests 分类规则

`tests/` 当前测试目录结构为：

- `tests/unit/domain/`：Domain enum、模型、Decimal 和领域契约测试。
- `tests/unit/environment/`：本地 uv/Python 环境验证测试。
- `tests/unit/interfaces/`：模块接口边界测试。
- `tests/unit/oms/`：OMS 纯函数和后续 OMS 单元测试。
- `tests/unit/risk/`：RiskEngine pure rules、config 语义和边界守卫测试。
- `tests/unit/execution/`：Execution DTO、typed mapping result、pure mapper 和边界守卫测试。
- `tests/integration/db/`：ORM、Alembic 和数据库 schema 契约测试。
- `tests/integration/mock_exchange/`：Mock Exchange 场景契约测试。

不得随意在 `tests/unit/` 或 `tests/integration/` 根目录新增测试文件。新测试必须进入对应模块目录。

不新增空测试模块目录，不使用 `.gitkeep` 占位。只有出现真实测试文件时，才创建对应目录。

## 禁止事项

- 当前阶段不得未经确认新增真实交易接口相关目录。
- 当前阶段不得新增 CTP、SimNow、broker adapter、prod、production、live、remote、kms、cloud 等文档目录或流程；这些属于后续 Runtime / Infrastructure / Adapter 阶段。
- 不得把尚未实现的模块、字段或 schema 写成当前事实。
- 不得把 `raw_payload`、`metadata`、`raw`、`details` 描述为 source-of-truth 字段载体。
- 不得用文档结构变化顺手修改业务实现、ORM、Alembic 或测试断言语义。

## 新文档放置规则

- Domain 字段或枚举变化：更新 `domain/DOMAIN_FREEZE.md`。
- OMS 状态迁移变化：更新 `oms/OMS_STATE_MACHINE.md`。
- OMS Repository / UnitOfWork / Application Service 变化：更新 `oms/OMS_REPOSITORY.md`。
- OMS 测试覆盖变化：更新 `oms/OMS_TEST_MATRIX.md`。
- 风控文档：进入 `risk/`。
- 执行与 Mock Exchange 文档：进入 `execution/`。
- 持仓、保证金、PnL 文档：进入 `position/`。
- 结算文档：进入 `settlement/`。
- 本地开发和验证说明：进入 `operations/` 或根 README 的简短入口。

## OMS 文档收敛规则

OMS 相关文档只维护三份主文档：

- `oms/OMS_STATE_MACHINE.md`
- `oms/OMS_REPOSITORY.md`
- `oms/OMS_TEST_MATRIX.md`

新增 OMS 设计优先并入上述三份文档。除非用户明确批准，不得新增新的 `docs/oms/OMS_*.md` 文件。

## Risk 文档收敛规则

Risk 相关文档只维护两份主文档：

- `risk/RISK_CONTRACT.md`
- `risk/RISK_TEST_MATRIX.md`

`risk/README.md` 只作为入口索引。新增 Risk 设计优先并入上述两份文档。除非用户明确批准，不得为单个 Risk 规则新增独立文档。

## Execution 文档收敛规则

Execution 相关文档只维护两份主文档：

- `execution/EXECUTION_CONTRACT.md`
- `execution/EXECUTION_TEST_MATRIX.md`

`execution/README.md` 只作为入口索引。新增 Execution 设计优先并入上述两份文档。除非用户明确批准，不得为 submit、cancel、fill、reject 等单个执行场景新增独立文档。
