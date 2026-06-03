# OMS 测试矩阵

本文档定义 Phase 2 后续必须落地的非 xfail OMS 测试矩阵。本文档只定义测试计划，不新增测试代码。

## 测试分类

Phase 2 OMS 测试分为：

- 状态迁移测试。
- 幂等测试。
- 事件处理测试。
- 风控准入测试。
- 持久化与恢复测试。
- 边界禁止测试。

除 Mock Exchange 尚未实现的撮合场景外，OMS 核心契约测试不得使用 `xfail`。

## Phase 2.2 最小非 xfail 测试矩阵

Phase 2.2 只覆盖 OMS Repository / UnitOfWork / `order_events` 持久化边界，不进入 OMSService、撮合、风控计算、持仓、保证金、PnL 或结算。

### Repository 单元测试

| 场景 | 预期 | 状态 |
|---|---|---|
| 订单创建 + 初始事件 | 订单记录和初始 `order_event` 在同一事务内提交。 | Done |
| 状态更新 + 事件 append | `orders.status` 更新和 `order_events` append 在同一事务内提交。 | Done |
| 写事件失败 | 事务 rollback，不留下已更新订单状态。 | Done |
| 更新订单失败 | 事务 rollback，不留下半条事件。 | Done |
| 相同 `client_order_id` + 相同 canonical payload | 返回已有订单，不创建第二笔订单。 | Done |
| 相同 `client_order_id` + 不同 canonical payload | 返回类型化幂等冲突，不创建第二笔订单。 | Done |
| `IntegrityError` 后查询已有订单 | 唯一约束冲突后重新查询，并按 canonical payload 判断幂等或冲突。 | Done |
| `order_id` str/int 映射成功 | Domain `order_id` 与 DB `orders.id` 由 Repository 统一转换。 | Done |
| 非法 `order_id` 字符串 | 拒绝查询，不得查询错误订单。 | Done |
| duplicate `order_event` | 不重复 append，不重复应用。 | Done |
| open/recovery query | 返回 `SUBMITTING`, `SUBMIT_TIMEOUT`, `SUBMITTED`, `ACKED`, `PARTIALLY_FILLED`, `CANCEL_PENDING`, `CANCEL_FAILED`, `UNKNOWN`。 | Done |
| 终态订单恢复查询 | `REJECTED_BY_RISK`, `SUBMIT_FAILED`, `CANCELED`, `FILLED`, `REJECTED_BY_EXCHANGE`, `EXPIRED` 不进入自动恢复集合。 | Done |
| event replay ordering | 按 `id` 或 `created_at, id` 稳定重放，禁止只按 `created_at`。 | Done |
| `raw_payload` | 不承载 source-of-truth 字段。 | Done |
| `occurred_at` 持久化 | `order_events.occurred_at` 必须写入业务事件发生时间，不能用 `created_at` 冒充。 | Done |

### PostgreSQL 集成测试

| 场景 | 预期 | 状态 |
|---|---|---|
| `orders.client_order_id` 唯一约束 | 真实 PostgreSQL 触发唯一约束。 | Done |
| `order_events(event_source, external_event_id)` 唯一约束 | 真实 PostgreSQL 触发唯一约束。 | Done |
| `raw_payload` JSON round-trip | JSON 能完整写入和读出。 | Done |
| 订单 + 事件同事务提交 | 真实 PostgreSQL 中二者同时可见。 | Done |
| 事件插入失败 rollback | `orders.status` 不变。 | Done |
| 订单更新失败 rollback | `order_events` 不残留。 | Done |

### Phase 2.3+ 后续项

以下进入 OMSService 后继续验收：

- OMSService 调用 Repository 后的状态迁移与事件写入编排。
- OMSService 对乱序事件、`previous_status` mismatch 和 `UNKNOWN` 的策略。
- OMSService 从 `orders + order_events` 重放恢复。

## 状态迁移测试

| 场景 | 预期 |
|---|---|
| `CREATED -> RISK_CHECKING` | 合法迁移，写入 `order_events`。 |
| `RISK_CHECKING -> RISK_ACCEPTED` | 仅当 `RiskDecision.ACCEPTED` 时合法。 |
| `RISK_CHECKING -> REJECTED_BY_RISK` | 仅当 `RiskDecision.REJECTED` 时合法。 |
| `RISK_ACCEPTED -> SUBMITTING` | 合法迁移。 |
| `SUBMITTING -> SUBMITTED` | 合法迁移。 |
| `SUBMITTING -> SUBMIT_TIMEOUT` | 合法迁移，可恢复。 |
| `SUBMITTING -> SUBMIT_FAILED` | 合法迁移，进入终态。 |
| `SUBMITTING -> REJECTED_BY_EXCHANGE` | 合法迁移，进入终态。 |
| `SUBMITTED -> ACKED` | 合法迁移。 |
| `SUBMITTED -> REJECTED_BY_EXCHANGE` | 合法迁移，进入终态。 |
| `ACKED -> PARTIALLY_FILLED` | 合法迁移，累计成交数量增加。 |
| `ACKED -> FILLED` | 合法迁移，进入终态。 |
| `ACKED -> CANCEL_PENDING` | 合法迁移。 |
| `PARTIALLY_FILLED -> PARTIALLY_FILLED` | 合法迁移，成交累计单调增加。 |
| `PARTIALLY_FILLED -> FILLED` | 合法迁移，累计成交数量等于订单数量。 |
| `PARTIALLY_FILLED -> CANCEL_PENDING` | 合法迁移。 |
| `CANCEL_PENDING -> CANCELED` | 合法迁移，进入终态。 |
| `CANCEL_PENDING -> CANCEL_FAILED` | 合法迁移，可恢复。 |
| `CANCEL_PENDING -> PARTIALLY_FILLED` | 合法迁移，表示撤单期间发生部分成交。 |
| `CANCEL_PENDING -> FILLED` | 合法迁移，表示撤单期间全部成交。 |
| `CANCEL_FAILED -> CANCEL_PENDING` | 合法迁移，表示再次撤单。 |
| `CANCEL_FAILED -> PARTIALLY_FILLED` | 合法迁移。 |
| `CANCEL_FAILED -> FILLED` | 合法迁移，进入终态。 |
| `UNKNOWN -> 已验证状态` | 仅通过权威查询、重放或恢复事件合法恢复。 |

## 非法状态迁移测试

| 场景 | 预期 |
|---|---|
| `REJECTED_BY_RISK -> SUBMITTING` | 非法；不得提交；不得改变状态。 |
| `SUBMIT_FAILED -> SUBMITTED` | 非法；不得改变状态。 |
| `CANCELED -> FILLED` | 非法；不得改变状态。 |
| `FILLED -> CANCELED` | 非法；不得改变状态。 |
| `REJECTED_BY_EXCHANGE -> ACKED` | 非法；不得改变状态。 |
| `EXPIRED -> PARTIALLY_FILLED` | 非法；不得改变状态。 |
| `FILLED -> ACKED` | 非法；不得回退。 |
| `CANCELED -> CANCEL_PENDING` | 非法；终态不可再迁移。 |

非法迁移必须满足：

- 不改变 `orders.status`。
- 不生成伪造的成功状态事件。
- 记录诊断或拒绝原因。

## 终态不可再迁移测试

以下状态均为终态，必须测试无法再迁移：

- `REJECTED_BY_RISK`
- `SUBMIT_FAILED`
- `CANCELED`
- `FILLED`
- `REJECTED_BY_EXCHANGE`
- `EXPIRED`

## UNKNOWN 测试

| 场景 | 预期 |
|---|---|
| 收到无法归类的事件 | 进入 `UNKNOWN` 或拒绝应用，并记录诊断。 |
| 收到与当前状态矛盾且无法判断的新事件 | 进入 `UNKNOWN`。 |
| 重启恢复时 `orders` 与 `order_events` 无法一致重放 | 进入 `UNKNOWN`。 |
| `UNKNOWN` 收到权威终态恢复事件 | 恢复到对应终态。 |
| `UNKNOWN` 收到重复旧事件 | 不恢复，不重复应用。 |
| 从 `UNKNOWN` 恢复到终态后再收到旧事件 | 终态不得回退。 |
| `UNKNOWN -> CANCEL_PENDING` | 禁止；`CANCEL_PENDING` 是撤单过程态，不是权威恢复态。 |
| `UNKNOWN -> CANCEL_FAILED` | 禁止；`CANCEL_FAILED` 是撤单失败过程异常，不是权威恢复终态。 |

## client_order_id 幂等测试

| 场景 | 预期 |
|---|---|
| 相同 `client_order_id` + 相同 payload 创建两次 | 返回已有订单，只存在一笔订单。 |
| 相同 `client_order_id` + 不同 payload | 拒绝并记录冲突，不创建新订单。 |
| 并发重复创建相同 payload | 最终只创建一笔订单。 |
| 幂等冲突后继续查询 | 返回原订单或明确冲突结果，不产生第二笔订单。 |
| 幂等冲突 | 不调用 EMS，不调用 Mock Exchange。 |

## order_event 幂等测试

| 场景 | 预期 |
|---|---|
| 重复 `(event_source, external_event_id)` | 不重复应用。 |
| 重复成交事件 | 不重复累计成交数量。 |
| 重复状态事件 | 不重复写入同语义状态变化。 |
| 不同 `external_event_id` 的合法后续事件 | 正常应用。 |
| 当前 schema 幂等键检查 | 验证 `UNIQUE(event_source, external_event_id)`。 |

## previous_status mismatch 测试

| 场景 | 预期 |
|---|---|
| `previous_status` 与当前状态一致 | 正常按矩阵迁移。 |
| `previous_status` 与当前状态不一致，但事件已处理过 | 视为重复，忽略。 |
| `previous_status` 与当前状态不一致，且事件明显旧于当前状态 | 视为旧事件，忽略并记录诊断。 |
| `previous_status` 与当前状态不一致且无法判断 | 进入 `UNKNOWN` 或拒绝应用。 |

## 乱序事件测试

| 场景 | 预期 |
|---|---|
| 先收到成交，后收到 ACK | 不得让状态回退；策略必须明确为应用、忽略或进入 `UNKNOWN`。 |
| 先收到撤单成功，后收到部分成交 | 终态不得回退；无法判断时进入 `UNKNOWN`。 |
| 先收到部分成交，后收到提交确认 | 不得重复事件；不得减少累计成交。 |
| 乱序事件缺少可验证上下文 | 进入 `UNKNOWN` 或拒绝应用。 |

## 部分成交测试

| 场景 | 预期 |
|---|---|
| 首次部分成交 | 状态进入 `PARTIALLY_FILLED`。 |
| 多次部分成交 | `filled_quantity` 单调增加。 |
| 部分成交累计到订单数量 | 状态进入 `FILLED`。 |
| 成交数量超过订单数量 | 拒绝应用或进入 `UNKNOWN`。 |
| 重复部分成交事件 | 不重复累计。 |

## 撤单失败测试

| 场景 | 预期 |
|---|---|
| `CANCEL_PENDING -> CANCEL_FAILED` | 合法迁移，写入事件。 |
| `CANCEL_FAILED` 后再次撤单 | 可进入 `CANCEL_PENDING`。 |
| `CANCEL_FAILED` 后收到成交 | 可进入 `PARTIALLY_FILLED` 或 `FILLED`。 |
| 重复撤单失败事件 | 不重复应用。 |

## 风控准入测试

| 场景 | 预期 |
|---|---|
| `RiskDecision.ACCEPTED` | 允许进入 `RISK_ACCEPTED`，后续可进入 `SUBMITTING`。 |
| `RiskDecision.REJECTED` | 必须进入 `REJECTED_BY_RISK`。 |
| `RiskDecision.REJECTED` | 不得调用 EMS 或 Mock Exchange。 |
| 风控拒绝 | 保留 `rule_name` 和 `reason` 供审计。 |
| OMS 处理风控结果 | 不计算风控规则本身。 |

## order_events 写入测试

| 场景 | 预期 |
|---|---|
| 每次有效状态变化 | 必须写入一条 `order_events`。 |
| 状态未变化的重复事件 | 不得重复写入成功迁移事件。 |
| 非法迁移 | 不得写入伪造成功事件。 |
| 进入 `UNKNOWN` | 必须写入诊断事件。 |

## raw_payload 测试

| 场景 | 预期 |
|---|---|
| 状态事实字段只存在于 `raw_payload` | 测试应失败或拒绝该事件语义。 |
| `raw_payload` 包含诊断信息 | 允许保留。 |
| source-of-truth 字段缺少类型化字段 | 不得靠 `raw_payload` 补足。 |

## 持久化与恢复测试

| 场景 | 预期 |
|---|---|
| 从 `orders + order_events` 重放恢复 | 恢复出一致订单状态。 |
| 重复重放 | 不产生副作用。 |
| 恢复后继续处理新事件 | 幂等规则仍生效。 |
| 恢复发现不一致 | 进入 `UNKNOWN`。 |

## 当前允许继续 xfail 的范围

以下仍可留在 Mock Exchange 后续阶段：

- 撮合引擎价格匹配细节。
- Mock Exchange 生成部分成交的具体算法。
- Mock Exchange 生成乱序/重复回报的模拟器细节。
- 每日结算和今仓转昨仓的完整实现。

但 OMS 层对这些回报的状态处理契约不得继续只依赖 xfail。
