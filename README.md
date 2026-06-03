# 系统 MVP

当前项目已完成基础骨架、核心领域模型、模块接口、数据库表设计、Phase 2 OMS 最小 Application Service、Phase 3 pure Risk Engine，以及 Phase 4.1 Execution DTO / pure mapper。当前阶段不连接真实期货柜台、CTP、SimNow 或任何真实交易接口，只允许使用 `MockFuturesExchange` command port / pure mapper 边界。

目标链路：

```text
MarketDataMock -> StrategyEngine -> FuturesRiskEngine -> OMS -> EMS -> MockFuturesExchange -> Trade -> FuturesPositionManager -> MarginEngine -> PnLEngine -> SettlementEngine
```

## macOS Apple Silicon 初始化

要求：

- 禁止使用 macOS 系统 Python
- 禁止使用 conda、pyenv、poetry
- 使用 uv 管理 Python 和依赖
- Python 固定为 3.12
- 虚拟环境必须位于项目根目录 `.venv`
- 所有命令通过 `uv run ...` 执行

初始化：

```bash
uv python install 3.12
uv sync
```

验证：

```bash
uv run which python
uv run python --version
```

验收标准：

```text
uv run which python -> <project-root>/.venv/bin/python
uv run python --version -> Python 3.12.x
```

## 技术栈路线图

Current Core Stack：

- Python 3.12
- uv
- pytest
- ruff
- mypy
- Pydantic Domain Model 当前事实
- SQLAlchemy
- Alembic
- PostgreSQL
- Protocol 接口

Planned Runtime / Infra Stack：

- FastAPI：API / Web 控制台服务层
- Celery：异步任务、定时任务和重试
- Kafka：行情、订单回报和事件流
- Redis：缓存、锁、pubsub 和临时状态
- 云服务：部署、监控和运维
- KMS：密钥管理
- CTP / SimNow / broker adapter：真实或仿真柜台适配
- async framework：行情和交易回报并发处理
- config system：多环境、多账户和多策略配置

这些不是永久禁止项，但不属于当前 Phase 4 Execution Contract / pure mapper 阶段。当前阶段仍保持：OMS 不依赖 EMS / Exchange；Risk 不依赖 OMS / DB；Execution mapper 不接真实交易接口。

## 启动基础设施

```bash
docker compose up -d postgres redis
```

如果本机尚未安装 Docker Desktop，请先安装 Apple Silicon 版本的 Docker Desktop。当前项目仍会生成 `docker-compose.yml`，但容器启动需要本机 Docker CLI 可用。

## 数据库迁移

```bash
uv run alembic upgrade head
```

数据库连接默认读取 `.env` 中的 `DATABASE_URL`，可参考 `.env.example`。

## 验证分类

### Environment Validation

环境验证不归类为 pytest 核心契约测试：

```bash
uv run which python
uv run python --version
```

当前项目尚未包含 `scripts/check_env.py`。只有后续新增该脚本后，才可运行：

```bash
uv run python scripts/check_env.py
```

### Core Contract Tests

核心契约测试覆盖当前 schema 契约、Decimal/float 禁止规则、Signal 不能直接下单、`client_order_id` 幂等、`order_events` 当前幂等规则、`trades` 去重规则和 `positions` 单行模型规则：

```bash
uv run pytest
```

核心契约测试不使用 `xfail`。只有尚未实现的 Mock Exchange 场景测试允许 `xfail`。

测试目录按职能分层：

- `tests/unit/domain`
- `tests/unit/environment`
- `tests/unit/interfaces`
- `tests/unit/oms`
- `tests/unit/risk`
- `tests/unit/execution`
- `tests/integration/db`
- `tests/integration/mock_exchange`

### Domain Freeze Consistency Review

每次 Domain 字段或 schema 变更都必须审查：

- `docs/domain/DOMAIN_FREEZE.md` 中的 enum 与 `src/futures_mvp/domain/enums.py` 一致
- 文档模型字段与 `src/futures_mvp/domain/models.py` 一致
- 文档接口边界与 `src/futures_mvp/interfaces/engines.py` 一致
- 文档数据库约束与 ORM/Alembic 一致
- 文档不得遗漏当前字段，也不得定义当前不存在字段
- Known Deviations 不得写成当前事实

### Static Checks

```bash
uv run ruff check .
uv run mypy src
```

### Phase 2 OMS Contract Gate

Phase 2 OMS 实现前必须先阅读：

- `docs/oms/OMS_STATE_MACHINE.md`
- `docs/oms/OMS_TEST_MATRIX.md`
- `docs/oms/OMS_REPOSITORY.md`

Phase 2.3A 已引入最小 OMS Application Service 编排。OMS 仍只负责订单状态、幂等、事件持久化和恢复边界，不实现风控计算、EMS、Mock Exchange、持仓、保证金、PnL 或结算。

### Phase 3 Risk Contract Gate

Phase 3 Risk 实现前必须先阅读：

- `docs/risk/RISK_CONTRACT.md`
- `docs/risk/RISK_TEST_MATRIX.md`

Phase 3 pure Risk Engine 已实现并完成 hardening。Risk 仍不接 `OMSService`，不写 `risk_events`，不访问 DB / Repository / UnitOfWork，不进入 EMS、Mock Exchange、Position、Margin、PnL 或 Settlement。

### Phase 4 Exchange / Execution Contract Gate

Phase 4 Execution 实现前必须先阅读：

- `docs/execution/EXECUTION_CONTRACT.md`
- `docs/execution/EXECUTION_TEST_MATRIX.md`

Phase 4.0 冻结 EMS、MockFuturesExchange command port、ExchangeReport、ExchangeReport -> OrderEvent 映射和执行回报语义。Phase 4.1 已实现 DTO、MappingContext、MappingResult、MappingError 和 pure mapper。当前 Execution Command/Report Runtime Layer 已实现 `ExchangeCommandPort`、本地 in-memory `ExecutionReportSink`、EMS command boundary、ConfigurableMockFuturesExchange 和 mapper wrapper。当前 `MockFuturesExchange` Protocol 只承载 submit / cancel command port，方法返回 `None`；report surface 与 command port 分离，不连接真实交易接口，不进入 Position、Margin、PnL 或 Settlement。

## Demo 策略

当前 demo 只提供骨架入口，不执行完整交易链路：

```bash
uv run futures-demo
```

## 当前阶段范围

已规划但当前仍未实现完整业务逻辑：

- 撮合与成交模拟
- Application Execution Orchestrator
- OMS public UNKNOWN entry / UNKNOWN_REPORT application
- 生产事件总线或 Kafka / Redis / Celery adapter
- 真实上下文风控 / Position / Margin / Risk -> OMS 集成
- PnL 和保证金计算
- 每日结算
- 今仓转昨仓
- 真实交易接口
# yanzl
