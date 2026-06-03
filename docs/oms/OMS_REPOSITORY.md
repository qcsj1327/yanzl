# OMS Repository / UnitOfWork 设计契约

本文档定义 OMS Repository、UnitOfWork 与 OMS Application Service 设计契约。Phase 2.3A 已落地最小 OMSService 编排，但仍不实现风控计算、EMS 接入、Mock Exchange、持仓、保证金、PnL 或结算。

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
- 如果不存在，使用 nested transaction / savepoint 写入新事件并 `flush`。
- 如果 DB unique constraint 抛出 `IntegrityError`，只回滚当前 insert savepoint。
- `IntegrityError` 后重新查询 `event_source + external_event_id`；查到既有事件时统一抛出 `EventAlreadyExistsError`，仍查不到时抛出 `RepositoryError`。
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

当前 Repository 状态更新使用 `version` 做乐观并发控制：

- `expected_version is not None` 时，使用单条条件 `UPDATE`。
- 条件为 `orders.id = :id AND orders.version = :expected_version`。
- 写入成功后 `version = version + 1`。
- affected rows 为 `0` 时抛出 `OptimisticLockError`。
- `expected_version is None` 时保留直接更新语义，但没有并发保护。
- 生产状态更新路径应传入 `expected_version`。

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
- 并发相同 `client_order_id` + 相同 payload 只创建一笔订单。
- 并发相同 `client_order_id` + 不同 payload 抛出 `IdempotencyConflictError`。
- `order_id` str/int 映射成功。
- `order_id` 非法字符串拒绝。
- duplicate `order_event` 不重复 append。
- 并发 duplicate `order_event` 统一转换为 `EventAlreadyExistsError`。
- open/recovery query 状态集合正确。
- 终态订单不进入恢复集合。
- event replay ordering by `id` 或 `created_at, id`。
- `raw_payload` 不承载 source-of-truth 字段。
- `occurred_at` 必须持久化业务事件发生时间。

当前 Phase 2.2G 已覆盖稳定的双 Session / barrier 并发创建测试，并覆盖真实 `IntegrityError` 后重新查询分支。

## OMS Application Service

本节定义 Phase 2.3A 已落地的最小 OMS Application Service 边界。OMSService 只做应用层编排，不修改 Repository、Domain、Alembic 或状态机矩阵。

### Service 职责

`OMSService` 是 OMS 应用层编排器，只负责把订单请求、风控结果、订单事件和恢复流程放进同一个事务边界内执行。

允许职责：

- `create_order`：创建订单状态事实，并写入初始审计事件。
- `apply_risk_result`：消费外部风控结果，推进到 `RISK_ACCEPTED` 或 `REJECTED_BY_RISK`。
- `apply_order_event`：消费 EMS、Exchange、System 或 OMS 事件，执行去重、乱序判断、`previous_status` 校验、状态迁移和事件持久化。
- `recover_order`：基于 `orders + order_events` 对单笔订单做重放、校验和恢复。

禁止职责：

- 风控计算。
- 撮合。
- 生成成交。
- 提交到 EMS、Mock Exchange 或真实柜台。
- 更新持仓。
- 计算保证金。
- 计算 PnL。
- 结算。
- Paper Trading。

`OMSService` 只消费已经形成的 `OrderRequest`、`RiskResult` 和 `OrderEvent`。任何 `Signal -> OrderRequest` 转换、Risk Engine 调用、EMS 调用、Mock Exchange 查询、Position/Margin/PnL/Settlement 处理都不属于 Phase 2.3。

### Repository / OMSService / 状态机三层职责

Repository 负责持久化事实：

- `OrderRepository` 创建订单、查询订单、更新订单状态、查询 open/recovery orders。
- `OrderEventRepository` 追加事件、按 `event_source + external_event_id` 查询重复事件、按 `order_id` 返回事件流。
- Repository 只保存上层已确认的状态结果，不判断状态迁移是否合法。
- Repository 不判断重复应用、乱序、`previous_status` mismatch 或 `UNKNOWN`。
- Repository 不自行 `commit` / `rollback`。

`OMSService` 负责应用层决策与事务编排：

- 打开 `UnitOfWork`。
- 在同一事务内完成订单状态更新与 `order_events` append。
- 调用状态机校验合法迁移。
- 执行 `client_order_id` 创建幂等语义。
- 执行 `event_source + external_event_id` 事件幂等语义。
- 判断 duplicate event、old event、`previous_status` mismatch 和 `UNKNOWN` 策略。
- 显式 `commit` 成功路径，异常路径依赖 UnitOfWork rollback。

状态机负责纯状态规则：

- 定义 `ALLOWED_TRANSITIONS`。
- 定义终态、可恢复状态和 `UNKNOWN` 恢复目标。
- 校验 `from_status -> to_status` 是否允许。
- 判断已知 `UNKNOWN` 进入原因是否有效。

状态机不访问 Repository，不开启事务，不写事件，不处理幂等，不解释外部事件 payload。

### OMSService 接口草案

以下是 Phase 2.3A 已落地的最小服务 API。

```python
from collections.abc import Callable
from datetime import datetime

from futures_mvp.domain.models import (
    OrderEvent,
    OrderEventApplicationResult,
    OrderRequest,
    OrderState,
    RiskResult,
)
from futures_mvp.interfaces.repositories import UnitOfWork


class OMSService:
    def __init__(
        self,
        uow_factory: Callable[[], UnitOfWork],
        *,
        clock: Callable[[], datetime],
    ) -> None: ...

    def create_order(
        self,
        request: OrderRequest,
        *,
        client_order_id: str,
    ) -> OrderState: ...

    def apply_risk_result(
        self,
        order_id: str,
        risk_result: RiskResult,
        *,
        external_event_id: str,
        occurred_at: datetime | None = None,
    ) -> OrderEventApplicationResult: ...

    def apply_order_event(self, event: OrderEvent) -> OrderEventApplicationResult: ...

    def recover_order(self, order_id: str) -> OrderEventApplicationResult: ...

    def get_by_client_order_id(self, client_order_id: str) -> OrderState | None: ...
```

命名与依赖约束：

- 事件入口使用 `apply_order_event`，避免与旧 `OMS.apply_event` Protocol 混淆。
- 恢复入口使用 `recover_order`，只恢复单笔订单。
- 构造函数只允许依赖 `UnitOfWork` factory 和时间源。
- 不允许依赖 Risk Engine、EMS、Mock Exchange、Position Manager、Margin Engine、PnL Engine 或 Settlement Engine。
- 本阶段不暴露批量提交、撤单、撮合、成交、持仓或结算接口。
- Phase 2.4 起，`OrderState.version` 暴露 `orders.version`，OMSService 生产状态更新路径必须向 `update_status` 传 `expected_version=order.version`。
- 多段状态迁移必须使用上一次 `update_status` 返回的新 `OrderState.version`，不得复用旧版本。
- `apply_risk_result`、`apply_order_event`、`recover_order` 返回 `OrderEventApplicationResult`，用 `EventApplicationStatus` 表达事件应用结果。
- `EventApplicationStatus` 不得写成裸字符串，不得塞进 `raw_payload` 作为 source-of-truth。

### create_order 契约

输入：

- `OrderRequest`

处理：

- 打开 UnitOfWork。
- 调用 `OrderRepository.create_order(request, client_order_id=request.client_order_id)`。
- 如果 Repository 返回既有相同 payload 订单，直接返回，不重复写初始事件。
- 如果 Repository 抛出幂等冲突，直接向上返回类型化错误，不写伪造状态事件。
- 新订单默认状态必须是 `CREATED`。
- 新订单必须在同一事务内写入初始 `order_events`，事件来源为 `OMS`，`previous_status=None`，`new_status=CREATED`。
- 显式 `commit`。

禁止：

- 不调用 Risk Engine。
- 不自动进入 `RISK_CHECKING`，除非未来有明确应用层风控编排阶段。
- 不调用 EMS 或 Mock Exchange。

### apply_risk_result 契约

输入：

- `order_id`
- 外部已计算好的 `RiskResult`
- `external_event_id`
- `occurred_at`

处理：

- 查询当前订单。
- 先按 `event_source=RISK + external_event_id` 查询既有事件；既有事件属于同一订单时返回 `DUPLICATE`，属于其他订单时返回 `EVENT_KEY_COLLISION`。
- 若 `RiskDecision.ACCEPTED`，目标状态为 `RISK_ACCEPTED`。
- 若 `RiskDecision.REJECTED`，目标状态为 `REJECTED_BY_RISK`。
- 当前状态为 `CREATED` 且风控通过时，必须先确认 `can_transition(CREATED, RISK_CHECKING)` 和 `can_transition(RISK_CHECKING, RISK_ACCEPTED)`，再执行桥接更新。
- 当前状态为 `RISK_CHECKING` 且风控通过时，必须先确认 `can_transition(RISK_CHECKING, RISK_ACCEPTED)`。
- 当前状态为 `CREATED` 或 `RISK_CHECKING` 且风控拒绝时，必须先确认 `can_transition(..., REJECTED_BY_RISK)`。
- 风控目标迁移非法时，返回 `MISMATCH_REJECTED`，不调用 `update_status`，不 append 成功风控事件，不泄漏 `InvalidOrderTransition`。
- 在同一事务内更新订单状态并 append 风控事件。
- 如果风控通过路径需要从 `CREATED` 桥接到 `RISK_CHECKING`，必须在同一事务内 append `RISK_CHECKING` 事件和 `RISK_ACCEPTED` 事件，且最终返回 `RISK_ACCEPTED`。
- 事件来源为 `RISK`。
- 显式 `commit`。
- 成功应用返回 `OrderEventApplicationResult(status=APPLIED, order=...)`。
- duplicate 风控事件返回 `DUPLICATE`。
- event key 属于其他订单时返回 `EVENT_KEY_COLLISION`，不得返回其他订单状态。

禁止：

- 不计算风控规则。
- 风控拒绝不得触发 EMS、Mock Exchange 或任何提交边界。
- 不把 `RiskResult.reason` 当作新的 source-of-truth 状态字段，只允许作为诊断 payload。

### apply_order_event 契约

输入：

- `OrderEvent`

处理顺序：

1. 打开 UnitOfWork。
2. 按 `event_source + external_event_id` 查询已处理事件。
3. 已存在且属于当前请求订单时返回 `DUPLICATE`，不重复 append，不重复更新状态。
4. 已存在但属于其他订单时返回 `EVENT_KEY_COLLISION`，不得返回其他订单状态，不得修改当前订单。
5. 查询当前订单。
6. 校验 `previous_status`。
7. 判断 old event、合法推进、UNKNOWN 或拒绝应用。
8. 对合法推进调用 `validate_transition(current.status, event.new_status)`。
9. 在同一事务内更新订单状态并 append 原始事件。
10. 显式 `commit`。

非法目标迁移：

- `event.previous_status == current.status` 但 `can_transition(current.status, event.new_status)` 为 false 时，返回 `MISMATCH_REJECTED`。
- 不调用 `update_status`。
- 不 append 成功事件。
- 不泄漏 `InvalidOrderTransition` 给正常事件应用调用方。
- 不自动进入 `UNKNOWN`，除非事件语义符合明确的 UNKNOWN 进入规则。

禁止：

- 不生成成交。
- 不累计成交数量，除非后续 Domain 明确提供类型化字段和规则。
- 不更新持仓、保证金、PnL 或结算。
- 不用 `raw_payload` 承载 source-of-truth 字段。

### duplicate event 策略

判定条件：

- `OrderEventRepository.get_by_event_key(event.event_source, event.external_event_id)` 返回既有事件。

策略：

- 既有事件属于同一订单时，不调用 `append_event`，不调用 `update_status`，返回 `DUPLICATE` 和当前请求订单状态。
- 既有事件属于其他订单时，返回 `EVENT_KEY_COLLISION` 和当前请求订单状态。
- 不因 duplicate event 进入 `UNKNOWN`。
- 不得返回其他订单状态。
- 如当前订单不存在，返回订单不存在错误；不得仅凭旧事件重建订单。

原因：

- 当前 DB 幂等键是 `event_source + external_event_id`。
- 重复事件不得重复应用，不得重复累计成交，不得重复写入同语义状态变化。
- 当前阶段不修改 DB unique key。未来若要改为订单维度唯一，必须单独 schema migration。

### previous_status mismatch 策略

`event.previous_status is None`：

- 仅允许用于初始、诊断或明确恢复类事件。
- 对普通状态推进事件，应拒绝应用或进入 `UNKNOWN`，由事件来源和上下文决定。

`event.previous_status == current.status`：

- 按状态机矩阵正常处理。

`event.previous_status != current.status`：

- 如果事件已按幂等键处理过，按 duplicate event 忽略。
- 如果事件目标状态已经被当前状态覆盖，且不会改变终态、成交事实或审计事实，按 old event 忽略并记录诊断。
- 如果无法判断为 duplicate 或 old event，且 `should_enter_unknown("previous_status_mismatch_unresolved")` 为真，进入 `UNKNOWN`。
- 如果事件非法且无恢复价值，拒绝应用并记录诊断，不改变订单状态。
- old event 返回 `OLD_IGNORED`。
- 无法恢复的 mismatch 返回 `MISMATCH_REJECTED` 或进入 `UNKNOWN` 后返回 `ENTERED_UNKNOWN`。

进入 `UNKNOWN` 时必须 append 诊断事件，`raw_payload` 保留 mismatch 诊断信息。

### old event 策略

old event 是已经被当前订单状态覆盖、不会改变事实的迟到事件。

可忽略条件：

- 当前订单已在终态，事件目标状态等于当前终态。
- 当前订单状态已经位于事件目标状态之后，且事件不携带新的类型化事实。
- `previous_status` 指向较早状态，事件目标状态不会改变当前状态、终态或恢复判断。

策略：

- 不回退订单状态。
- 不重复 append 原业务事件作为状态变更事件。
- 可以在未来审计表或诊断事件中记录；当前没有专用 audit schema 时，不得伪造状态事件。

终态订单事件分类：

- 目标状态等于当前终态：返回 `OLD_IGNORED`。
- 目标状态是另一个终态：返回 `MISMATCH_REJECTED`。
- 目标状态是非终态：返回 `IGNORED_TERMINAL`。
- 终态订单不得进入 `UNKNOWN`，不得回退，不得 append 新状态事件。

无法证明为 old event 时，不得强行忽略；应进入 `UNKNOWN` 或拒绝应用。

### UNKNOWN 进入与恢复策略

`OMSService` 只能按 `OMS_STATE_MACHINE.md` 已冻结原因进入 `UNKNOWN`，不得新增状态机矩阵项。

允许进入条件：

- `unclassified_exchange_report`：收到无法归类的交易所回报。
- `contradictory_report`：收到与当前状态矛盾且无法判断是否重复或旧事件的回报。
- `incomplete_report_after_submit_timeout`：提交超时后收到不完整或缺少关键字段的回报。
- `replay_inconsistent`：重启恢复时 `orders` 与 `order_events` 无法一致重放。
- `previous_status_mismatch_unresolved`：`previous_status` 与当前状态不一致，且既不能判定重复，也不能判定旧事件。
- `event_sequence_gap`：事件顺序缺口导致无法确认累计成交或撤单结果。

进入要求：

- 必须调用 `validate_transition(current.status, UNKNOWN)`。
- 必须写入 `order_events`。
- `raw_payload` 只保留诊断信息，不承载 source-of-truth 字段。
- 不调用外部查询或撮合组件。

`UNKNOWN` 只能恢复到状态机允许目标：

- `SUBMITTED`
- `ACKED`
- `PARTIALLY_FILLED`
- `CANCELED`
- `FILLED`
- `REJECTED_BY_EXCHANGE`
- `EXPIRED`

恢复来源：

- 完整且幂等的事件重放恢复出一致状态。
- 人工或系统对账生成明确恢复事件；显式 `OrderEvent` 恢复必须满足 `previous_status == UNKNOWN`。
- 未来交易所或 Mock Exchange 权威查询结果；但该查询不属于 Phase 2.3 实现。

禁止恢复目标：

- `CREATED`
- `RISK_CHECKING`
- `REJECTED_BY_RISK`
- `RISK_ACCEPTED`
- `SUBMITTING`
- `SUBMIT_TIMEOUT`
- `SUBMIT_FAILED`
- `CANCEL_PENDING`
- `CANCEL_FAILED`
- `UNKNOWN`

### recover_order 契约

恢复输入只允许来自：

- `orders`
- `order_events`

重启恢复流程候选：

1. Phase 2.7 当前批量重启恢复入口由调用方通过 `OrderRepository.list_open_orders()` 找到 open/recovery orders 后逐笔调用 `recover_order(order_id)`。
2. 当前阶段不新增 `OMSService.recover_open_orders()` 批量 API。
3. `recover_order` 读取当前订单和按 `order_events.id` 升序排列的事件流。
4. 从订单创建事件开始重放状态迁移。
5. 每一步使用状态机校验迁移。
6. 重放结果与 `orders.status` 一致时，返回当前订单。
7. `UNKNOWN` 订单如能从事件流恢复到 `UNKNOWN_RECOVERY_TARGETS` 中的稳定状态，写入恢复事件并更新订单状态。
8. 重放结果与 `orders.status` 不一致且无法证明为可接受恢复差异时，进入或保持 `UNKNOWN`。
9. 终态订单恢复返回 `IGNORED_TERMINAL`，不自动恢复、不回退。

open/recovery 状态集合沿用 Repository 契约，批量入口由调用方逐笔调用 `recover_order` 并对每笔结果进行判断：

- `SUBMITTING`
- `SUBMIT_TIMEOUT`
- `SUBMITTED`
- `ACKED`
- `PARTIALLY_FILLED`
- `CANCEL_PENDING`
- `CANCEL_FAILED`
- `UNKNOWN`

处理约束：

- `SUBMITTING`、`SUBMIT_TIMEOUT`、`SUBMITTED`、`ACKED`、`PARTIALLY_FILLED`、`CANCEL_PENDING`、`CANCEL_FAILED` 只能通过本地事件重放确认当前状态。
- 事件流一致时返回 `APPLIED`，不新增恢复事件，不降级到 `UNKNOWN`。
- `UNKNOWN` 事件流一致时保持 `UNKNOWN` 并返回 `APPLIED`；可重放到稳定允许目标时才写恢复事件并返回 `RECOVERED_FROM_UNKNOWN`。
- 本阶段不发起 EMS 或 Mock Exchange 查询。
- 需要外部权威查询时，只保留为后续阶段接口，不在 Phase 2.3 实现。

UNKNOWN 恢复流程：

1. 读取 `UNKNOWN` 订单事件流。
2. 按 `order_events.id` 升序重放。
3. 如果能恢复到 `UNKNOWN_RECOVERY_TARGETS` 中的稳定状态，写入恢复事件并更新订单状态。
4. 如果只能恢复到过程态或仍不一致，保持 `UNKNOWN`。
5. 如果恢复事件重复，按 duplicate event 忽略，不重复恢复。
6. 显式恢复事件 `previous_status` 不是 `UNKNOWN` 时，不恢复，返回 `MISMATCH_REJECTED`。

约束：

- `UNKNOWN` 不恢复到 `CANCEL_PENDING` 或 `CANCEL_FAILED`。
- `UNKNOWN` 恢复到终态后，终态不可回退。
- 恢复事件必须带新的 `external_event_id`。

### OMSService 事务边界

每个 public method 独立打开 UnitOfWork。

必须同事务提交：

- 新订单 + 初始事件。
- 风控结果状态更新 + 风控事件。
- 外部订单事件状态更新 + 事件 append。
- UNKNOWN 诊断状态更新 + 诊断事件。
- UNKNOWN 恢复状态更新 + 恢复事件。

失败规则：

- 状态更新失败时不得留下事件。
- 事件 append 失败时不得留下状态更新。
- duplicate event 已存在时不得再次 append。
- 乐观锁失败时不得伪造事件。

### Phase 3 Risk 边界

Phase 3 Risk 仍是后续阶段，不是当前 OMS 当前事实。

- Phase 3 最小版只允许实现 pure Risk Engine。
- Phase 3 最小版不写 `risk_events`。
- Phase 3 最小版不接 `OMSService`。
- Phase 3 最小版不调用 Repository、UnitOfWork、ORM 或 DB。
- 未来如果需要持久化 `risk_events`，必须先设计 `RiskEventRepository` / UnitOfWork 端口，再进入实现。
