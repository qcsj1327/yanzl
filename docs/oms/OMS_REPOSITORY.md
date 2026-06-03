# OMS Repository / UnitOfWork 设计契约

本文档定义 OMS Repository 与 UnitOfWork 设计契约。Phase 2.2D 已提供 SQLAlchemy Repository skeleton、UnitOfWork skeleton 和 ORM <-> Domain mapper，但仍不实现 OMSService、风控接入或事件乱序处理。

## Repository 边界

### OrderRepository

`OrderRepository` 只负责持久化相关操作：

- 创建订单记录。
- 按 `client_order_id` 查询订单。
- 按 DB `id` 查询订单。
- 按 Domain `order_id` 查询订单。
- 更新订单状态。
- 查询 open/recovery orders。

`OrderRepository` 禁止负责：

- 执行状态迁移判断。
- 计算风控。
- 生成成交。
- 更新持仓。
- 调用 EMS、Mock Exchange 或任何真实交易接口。
- 处理 PnL、保证金或结算。

状态迁移判断属于 OMS application/service 层，应调用 `state_machine.validate_transition(...)`。Repository 只保存已经由上层确认的结果。

当前抽象端口签名：

```python
class OrderRepository(Protocol):
    def create_order(self, order_request: OrderRequest, *, client_order_id: str) -> OrderState: ...
    def get_by_id(self, order_id: str) -> OrderState | None: ...
    def get_by_client_order_id(self, client_order_id: str) -> OrderState | None: ...
    def update_status(
        self,
        order_id: str,
        new_status: OrderStatus,
        *,
        expected_version: int | None = None,
    ) -> OrderState: ...
    def list_open_orders(self) -> list[OrderState]: ...
```

### OrderEventRepository

`OrderEventRepository` 只负责事件持久化相关操作：

- append `order_event`。
- 按 `event_source + external_event_id` 查询重复事件。
- 按 `order_id` 查询事件流。

`OrderEventRepository` 禁止负责：

- 判断事件是否乱序。
- 判断事件是否重复应用。
- 判断是否进入 `UNKNOWN`。
- 决定状态迁移是否合法。
- 把 source-of-truth 字段藏进 `raw_payload`。

重复事件、乱序事件、`previous_status` mismatch 和 `UNKNOWN` 策略属于 OMS application/service 层。

当前 SQLAlchemy skeleton 对重复 `order_event` 的处理策略：

- `append_event(...)` 先按 `event_source + external_event_id` 查询。
- 如果已存在，抛出 `EventAlreadyExistsError`。
- 如果不存在，写入新事件并 `flush`。
- Repository 不自动 `commit` 或 `rollback`。
- Repository 写入 Domain `OrderEvent.occurred_at`，`created_at` 由 DB/ORM 生成。
- Repository 透传 `raw_payload` 诊断信息，不解释 `raw_payload`。
- Repository 不判断乱序，不处理 `previous_status` mismatch，不决定 `UNKNOWN`。
- `list_by_order_id(...)` 必须按 `order_events.id` 升序返回，不得只按 `created_at` 排序。

当前抽象端口签名：

```python
class OrderEventRepository(Protocol):
    def append_event(self, event: OrderEvent) -> OrderEvent: ...
    def get_by_event_key(
        self,
        event_source: EventSource,
        external_event_id: str,
    ) -> OrderEvent | None: ...
    def list_by_order_id(self, order_id: str) -> list[OrderEvent]: ...
```

## UnitOfWork / Transaction Boundary

Phase 2.2 后续实现必须使用统一事务边界：

- 订单创建 + 初始 `order_event` 必须在同一事务内提交。
- 订单状态更新 + `order_event` append 必须在同一事务内提交。
- 幂等冲突审计若落库，也必须与冲突判断在同一事务内完成。
- rollback 后不得留下半条订单或半条事件。
- Repository 不自行 `commit`。
- Repository 不自行 `rollback`。
- `commit` / `rollback` 由 UnitOfWork 统一控制。

建议边界：

- OMS application/service 打开 UnitOfWork。
- UnitOfWork 在具体实现内部管理同一个事务上下文。
- 抽象端口不暴露 SQLAlchemy session 或具体 DB session。
- `OrderRepository` 和 `OrderEventRepository` 共享同一个 UnitOfWork 事务边界。
- application/service 完成状态机判断、幂等判断和事件语义判断。
- UnitOfWork 原子提交或回滚。
- 当前 `SQLAlchemyUnitOfWork.__exit__` 遇异常必须 `rollback`。
- 当前 `SQLAlchemyUnitOfWork.__exit__` 无异常不自动 `commit`，必须由调用方显式 `commit`，避免隐式提交。
- 事务原子性测试必须以数据库查询事实为准，不得依赖当前 Session 的 ORM identity map。
- 未 `commit` 不可见必须使用第二个独立 Session 验证。
- rollback 后结果必须使用新的独立 Session 验证。

当前抽象端口签名：

```python
class UnitOfWork(Protocol):
    orders: OrderRepository
    order_events: OrderEventRepository

    def commit(self) -> None: ...
    def rollback(self) -> None: ...
    def __enter__(self) -> UnitOfWork: ...
    def __exit__(self, exc_type, exc, tb) -> bool | None: ...
```

## order_id 映射

当前短期方案：

- DB `orders.id` 是 `int` 主键。
- Domain `order_id` 是 `str`。
- Repository 统一执行 `str(db_order.id)` 暴露给 Domain。
- 输入 Domain `order_id` 时，Repository 负责解析为 `int`。
- 解析失败必须拒绝，不得查询错误订单。
- 业务层不得直接依赖 ORM `Order.id`。

Future Migration Candidate：

- 未来可增加 `orders.oms_order_id` 作为稳定字符串订单 ID。
- 当前阶段不做该 migration。

## client_order_id 幂等

`client_order_id` 是当前全局唯一幂等键。

canonical payload 字段固定为：

- `account_id`
- `instrument_id`
- `exchange`
- `direction`
- `offset`
- `order_type`
- `limit_price`
- `quantity`

比较规则：

- Enum 按 `.value` 比较。
- Decimal 直接按 `Decimal` 等值语义比较。
- 禁止用 `str(Decimal)` 比较，避免 `Decimal("1.0")` 与 `Decimal("1.00")` 被误判为不同。
- 只比较上述类型化字段，不依赖 `raw_payload`。
- 不比较 `metadata`、`created_at`、`status`、`filled_quantity`。

幂等规则：

- 同 `client_order_id` + canonical payload 相同：返回已有订单。
- 同 `client_order_id` + canonical payload 不同：抛出 `IdempotencyConflictError`。
- 幂等冲突不得创建第二笔订单。
- 幂等冲突不得修改已有订单。
- 幂等冲突不得伪造 `order_event` 表达冲突。
- 幂等冲突不得调用 EMS、Mock Exchange 或真实交易接口。

当前 SQLAlchemy Repository 实现语义：

- `create_order(...)` 先按 `client_order_id` 查询已有订单。
- 已有订单 payload 相同时直接返回已有订单，不修改订单状态，不新增 `order_event`。
- 已有订单 payload 不同时抛出 `IdempotencyConflictError`。
- 新订单 insert 使用 nested transaction / savepoint 捕获 DB unique constraint 的 `IntegrityError`。
- `IntegrityError` 只回滚当前 insert savepoint，不回滚 UnitOfWork 外层事务。
- `IntegrityError` 后必须重新查询 `client_order_id`。
- 重新查询到相同 payload 时返回已有订单；payload 不同时抛出 `IdempotencyConflictError`；仍查不到时抛出 `RepositoryError`。

## 幂等冲突审计

当前阶段策略：

- 当前 schema 没有专用 conflict/audit 表。
- 不允许伪造 `order_event` 状态事件表达幂等冲突。
- Phase 2.2 只返回类型化错误或结果。
- 幂等冲突事实不得只写入 `raw_payload` 当作 source-of-truth。

Future Migration Candidate：

- 新增 `audit_events` 表。
- 或新增 `oms_conflicts` 表。
- 或扩展 `order_events`，增加类型化 `event_type` / `outcome` / `reason` 字段。

## order_events 事件时间

时间语义：

- Domain `OrderEvent.occurred_at` 是业务事件发生时间。
- DB 当前已具备 `order_events.occurred_at DateTime(timezone=True) NOT NULL`。
- `created_at` 是本地入库时间。
- `created_at` 不能冒充 `occurred_at`。
- `occurred_at` 不得只塞进 `raw_payload` 当作 source-of-truth。

Phase 2.2B 当前事实：

- `order_events.occurred_at DateTime(timezone=True) NOT NULL`

Repository 后续写入 `order_events` 时必须显式提供 `occurred_at`。

## order_events 幂等键

当前 schema：

```text
UNIQUE(event_source, external_event_id)
```

Repository 后续实现必须按当前 schema 处理重复事件。

已知风险：

- 该约束作用域过宽。
- 如果外部事件 ID 只在订单、账户、交易日或会话内唯一，可能误杀不同订单的同源事件。

Future Migration Candidate：

```text
UNIQUE(order_id, event_source, external_event_id)
```

如果不迁移，必须要求 `external_event_id` 在 `event_source` 内全局唯一。

## orders.version

当前事实：

- 当前 DB 已具备 `orders.version int not null default 0`。
- `version` 是 Repository 后续状态更新的乐观并发控制字段，不是业务订单状态。

Phase 2.2B 当前事实：

- `orders.version int not null default 0`

后续 Repository 状态更新必须使用 `version` 或等价锁机制：

- 读取订单当前版本。
- 更新时校验版本。
- 写入成功后版本递增。
- 版本不匹配时拒绝当前更新或交由上层进入恢复流程。

## open/recovery query

open/recovery 状态集合：

- `SUBMITTING`
- `SUBMIT_TIMEOUT`
- `SUBMITTED`
- `ACKED`
- `PARTIALLY_FILLED`
- `CANCEL_PENDING`
- `CANCEL_FAILED`
- `UNKNOWN`

这些状态表示订单仍可能需要恢复、查询、重放或继续接收交易所/Mock Exchange 回报。

终态必须排除自动恢复：

- `REJECTED_BY_RISK`
- `SUBMIT_FAILED`
- `CANCELED`
- `FILLED`
- `REJECTED_BY_EXCHANGE`
- `EXPIRED`

`RISK_ACCEPTED` 是本地已过风控但尚未提交的状态，不属于交易所 open order。是否恢复该状态属于 OMS application/service 的本地任务恢复策略，不属于 exchange open query。

## 事件重放排序

事件重放必须使用稳定顺序：

- 最小方案：按 `order_events.id` 升序重放。
- 或按 `created_at, id` 升序重放。

禁止：

- 只按 `created_at` 重放。
- 用 `created_at` 冒充业务事件发生顺序。
- 用 `raw_payload` 中的时间字段作为唯一排序事实来源。

当前 `occurred_at` 已是类型化业务事件时间列：

- `created_at, id` 仍表示本地入库顺序。
- `occurred_at` 可辅助判断旧事件或乱序事件。
- 不得只按 `occurred_at` 覆盖状态机单调性。

## Phase 2.2 测试矩阵

后续 Phase 2.2 非 xfail 测试必须覆盖：

- 订单创建 + 初始事件同事务。
- 状态更新 + 事件同事务。
- rollback 不留半条订单或半条事件。
- 未 `commit` 不可见必须用第二个独立 Session 验证。
- rollback 结果必须用新的独立 Session 验证。
- 事务原子性测试必须以数据库事实为准，不得依赖 ORM identity map。
- `client_order_id` 相同 payload 幂等。
- `client_order_id` 不同 payload 冲突。
- `IntegrityError` 后查询已有订单。
- `order_id` str/int 映射成功。
- `order_id` 非法字符串拒绝。
- duplicate `order_event` 不重复 append。
- open/recovery query 状态集合正确。
- 终态订单不进入恢复集合。
- event replay ordering by `id` 或 `created_at, id`。
- `raw_payload` 不承载 source-of-truth 字段。
- `occurred_at` 必须持久化业务事件发生时间。

并发创建测试仍是后续项；后续验收必须证明并发相同 `client_order_id` 最终只创建一笔订单，并覆盖真实 `IntegrityError` 后重新查询分支。
