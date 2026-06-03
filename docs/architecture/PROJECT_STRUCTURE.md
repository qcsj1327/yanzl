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
- `tests/integration/db/`：ORM、Alembic 和数据库 schema 契约测试。
- `tests/integration/mock_exchange/`：Mock Exchange 场景契约测试。

不得随意在 `tests/unit/` 或 `tests/integration/` 根目录新增测试文件。新测试必须进入对应模块目录。

不新增空测试模块目录，不使用 `.gitkeep` 占位。只有出现真实测试文件时，才创建对应目录。

## 禁止事项

- 不得未经确认新增真实交易接口相关目录。
- 不得新增 CTP、SimNow、broker adapter、production、live、remote、kms、cloud 等文档目录或流程。
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
