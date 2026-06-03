# OMS 状态机契约

本文档定义 Phase 2.0 的 OMS 契约。本文档只定义边界、状态机、幂等和事件语义，不实现 OMS 业务逻辑。

## OMS 职责边界

OMS 只负责：

- 订单状态事实来源。
- `client_order_id` 幂等语义。
- 状态迁移规则。
- `order_events` 持久化语义。
- 订单状态查询。

OMS 禁止负责：

- 策略解释。
- 风控计算。
- 撮合。
- 成交生成。
- 持仓更新。
- 保证金计算。
- PnL。
- 结算。
- 真实柜台连接。
- CTP、SimNow、broker adapter 或任何真实交易接口。

`Signal -> OrderRequest` 转换属于 application/service 层，不属于 OMS。OMS 只能消费已经形成的订单请求和风控结果。

## 风控准入边界

- 只有 `RiskDecision.ACCEPTED` 才允许订单进入 `RISK_ACCEPTED` / `SUBMITTING` 链路。
- `RiskDecision.REJECTED` 必须进入 `REJECTED_BY_RISK`。
- OMS 不计算风控，只消费 `RiskResult`。
- 风控拒绝不得调用 EMS、Mock Exchange 或任何提交边界。
- 风控准入结果必须能通过订单状态和事件审计追踪。

## 状态分类

| 状态 | 分类 | 说明 |
|---|---|---|
| `CREATED` | 可迁移 | 订单对象已创建，尚未完成风控。 |
| `RISK_CHECKING` | 可迁移 | 正在执行风控检查。 |
| `REJECTED_BY_RISK` | 终态 | 风控拒绝。 |
| `RISK_ACCEPTED` | 可迁移 | 风控通过，允许进入提交链路。 |
| `SUBMITTING` | 可恢复 | 正在提交到 EMS/Mock Exchange。 |
| `SUBMIT_TIMEOUT` | 可恢复 | 下单提交超时，后续需要查询或回报恢复。 |
| `SUBMIT_FAILED` | 终态 | 本地提交失败，未进入交易所有效订单链路。 |
| `SUBMITTED` | 可恢复 | 已提交，等待交易所 ACK 或拒绝。 |
| `ACKED` | 可迁移 | 交易所已确认订单。 |
| `PARTIALLY_FILLED` | 可迁移 | 部分成交。 |
| `CANCEL_PENDING` | 可恢复 | 撤单请求已发出，等待结果。 |
| `CANCEL_FAILED` | 可恢复 | 撤单失败，订单仍需后续回报确认。 |
| `CANCELED` | 终态 | 已撤单。 |
| `FILLED` | 终态 | 已全部成交。 |
| `REJECTED_BY_EXCHANGE` | 终态 | 交易所拒单。 |
| `EXPIRED` | 终态 | 订单过期。 |
| `UNKNOWN` | 可恢复 | OMS 无法可靠判断当前订单状态。 |

终态包括：

- `REJECTED_BY_RISK`
- `SUBMIT_FAILED`
- `CANCELED`
- `FILLED`
- `REJECTED_BY_EXCHANGE`
- `EXPIRED`

可恢复状态包括：

- `SUBMITTING`
- `SUBMIT_TIMEOUT`
- `SUBMITTED`
- `CANCEL_PENDING`
- `CANCEL_FAILED`
- `UNKNOWN`

## 合法状态迁移矩阵

未列出的迁移均为非法迁移。非法迁移不得改变订单当前状态，不得伪造 `order_events`。

| 当前状态 | 允许迁移到 |
|---|---|
| `CREATED` | `RISK_CHECKING`, `REJECTED_BY_RISK`, `UNKNOWN` |
| `RISK_CHECKING` | `RISK_ACCEPTED`, `REJECTED_BY_RISK`, `UNKNOWN` |
| `REJECTED_BY_RISK` | 无 |
| `RISK_ACCEPTED` | `SUBMITTING`, `SUBMIT_FAILED`, `UNKNOWN` |
| `SUBMITTING` | `SUBMITTED`, `ACKED`, `SUBMIT_TIMEOUT`, `SUBMIT_FAILED`, `REJECTED_BY_EXCHANGE`, `UNKNOWN` |
| `SUBMIT_TIMEOUT` | `SUBMITTED`, `ACKED`, `REJECTED_BY_EXCHANGE`, `SUBMIT_FAILED`, `UNKNOWN` |
| `SUBMIT_FAILED` | 无 |
| `SUBMITTED` | `ACKED`, `REJECTED_BY_EXCHANGE`, `CANCEL_PENDING`, `EXPIRED`, `UNKNOWN` |
| `ACKED` | `PARTIALLY_FILLED`, `FILLED`, `CANCEL_PENDING`, `CANCELED`, `EXPIRED`, `UNKNOWN` |
| `PARTIALLY_FILLED` | `PARTIALLY_FILLED`, `FILLED`, `CANCEL_PENDING`, `CANCELED`, `EXPIRED`, `UNKNOWN` |
| `CANCEL_PENDING` | `CANCELED`, `CANCEL_FAILED`, `FILLED`, `PARTIALLY_FILLED`, `UNKNOWN` |
| `CANCEL_FAILED` | `PARTIALLY_FILLED`, `FILLED`, `CANCEL_PENDING`, `CANCELED`, `EXPIRED`, `UNKNOWN` |
| `CANCELED` | 无 |
| `FILLED` | 无 |
| `REJECTED_BY_EXCHANGE` | 无 |
| `EXPIRED` | 无 |
| `UNKNOWN` | `SUBMITTED`, `ACKED`, `PARTIALLY_FILLED`, `CANCELED`, `FILLED`, `REJECTED_BY_EXCHANGE`, `EXPIRED` |

## 非法迁移规则

- 终态不得迁移到任何状态。
- `REJECTED_BY_RISK` 不得进入 `SUBMITTING`、`SUBMITTED`、`ACKED` 或任何成交相关状态。
- `SUBMIT_FAILED` 不得进入交易所确认或成交状态。
- `CANCELED` 不得进入成交状态。
- `FILLED` 不得进入撤单或拒单状态。
- `REJECTED_BY_EXCHANGE` 不得进入成交或撤单状态。
- `EXPIRED` 不得进入成交或撤单状态。
- `previous_status` 与当前状态不一致时，不得直接按普通事件应用。
- `apply_order_event` 收到 `previous_status` 与当前状态一致、但目标状态不在合法迁移矩阵内的事件时，必须返回 `MISMATCH_REJECTED`，不得泄漏状态机异常。
- 非法迁移不得更新订单状态，不得 append 成功状态事件，不得自动进入 `UNKNOWN`，除非事件语义另有明确 UNKNOWN 进入规则。

## UNKNOWN 进入条件

OMS 在无法可靠判断订单当前状态时进入 `UNKNOWN`。典型条件：

- 收到无法归类的交易所回报。
- 收到与当前状态矛盾且无法判断是否重复或旧事件的回报。
- 提交超时后又收到不完整或缺少关键字段的回报。
- 重启恢复时 `orders` 与 `order_events` 无法一致重放。
- `previous_status` 与当前状态不一致，且事件既不能判定为重复，也不能判定为旧事件。
- 事件顺序缺口导致无法确认累计成交或撤单结果。

进入 `UNKNOWN` 必须写入 `order_events`，并保留诊断 `raw_payload`。`raw_payload` 不得承载 source-of-truth 字段。

## UNKNOWN 恢复条件

`UNKNOWN` 只能通过可验证的权威信息恢复：

- 从交易所或 Mock Exchange 查询到订单最终状态。
- 通过完整且幂等的事件重放恢复出一致状态。
- 人工或系统对账生成明确恢复事件。
- 恢复事件必须带有新的 `external_event_id`，并符合当前 `order_events` 幂等规则。
- 显式 `OrderEvent` 恢复 `UNKNOWN` 时，`previous_status` 必须等于 `UNKNOWN`。
- 显式恢复事件的 `previous_status` 不是 `UNKNOWN` 时，不得恢复，返回 `MISMATCH_REJECTED`。

从 `UNKNOWN` 恢复到终态后，终态规则继续生效。

`UNKNOWN` 不允许恢复到 `CANCEL_PENDING` 或 `CANCEL_FAILED`：

- `CANCEL_PENDING` 是撤单过程态，不是权威恢复态。
- `CANCEL_FAILED` 是撤单失败过程异常，不是权威恢复终态。
- `UNKNOWN` 恢复只能来自权威查询、重放或恢复事件确认的稳定状态。

## client_order_id 幂等语义

`client_order_id` 是订单创建幂等键。

- 同 `client_order_id` + 相同 payload：返回已有订单，不创建新订单。
- 同 `client_order_id` + 不同 payload：拒绝创建，并记录幂等冲突。
- 并发重复创建：只能创建一笔订单。
- 幂等冲突不得创建新订单。
- 幂等冲突不得调用 EMS 或 Mock Exchange。
- 当前数据库约束为 `orders.client_order_id` 全局唯一。未来如需账户内唯一，必须通过 domain/schema migration 明确迁移。

用于比较的 payload 至少包含：

- `account_id`
- `instrument_id`
- `exchange`
- `direction`
- `offset`
- `order_type`
- `limit_price`
- `quantity`

## order_events 语义

当前 DB 幂等键是：

```text
event_source + external_event_id
```

事件处理规则：

- 重复事件不得重复应用。
- 重复事件必须先按 `event_source + external_event_id` 查询；若既有事件属于同一订单，返回 `DUPLICATE`。
- 若既有事件属于其他订单，返回 `EVENT_KEY_COLLISION`，不得返回其他订单状态，不得修改当前订单。
- 重复事件不得重复累计成交数量。
- 重复事件不得重复写入同语义状态变化。
- `previous_status` 与当前状态一致：按状态迁移矩阵正常应用。
- `previous_status` 与当前状态不一致，且能判断为重复事件或旧事件：忽略并记录诊断。
- `previous_status` 与当前状态不一致，且无法判断：进入 `UNKNOWN` 或拒绝应用。
- 旧事件不得回退订单状态，返回 `OLD_IGNORED`。
- 终态订单不得自动恢复或回退，恢复入口返回 `IGNORED_TERMINAL`。
- 乱序事件不得破坏订单状态单调性。
- 乱序事件不得让终态订单回退。
- `raw_payload` 只用于诊断，不承载 source-of-truth 字段。

时间语义：

- `occurred_at` 是业务事件发生时间。
- `created_at` 是本地入库时间。
- 当前 DB `order_events.occurred_at` 是类型化业务事件时间列，不得用 `created_at` 冒充。

## 乱序事件处理策略

乱序事件按以下优先级处理：

1. 如果事件已按 `event_source + external_event_id` 处理过，视为重复事件，忽略。
2. 如果事件对应状态已经被当前状态覆盖，且不会改变成交累计、终态或审计事实，视为旧事件，忽略并记录诊断。
3. 如果事件可以合法推进当前状态，正常应用。
4. 如果事件与当前状态矛盾但可通过权威查询或重放恢复，进入 `UNKNOWN`。
5. 如果事件非法且无恢复价值，拒绝应用并记录诊断，不改变订单状态。

## Future Migration Candidates

以下不是当前 schema 事实，只是 Phase 2 后续候选：

- 将事件幂等键评估为 `UNIQUE(order_id, event_source, external_event_id)`。
- 为 `orders` 增加最后事件 ID、外部订单号、提交/确认/终态时间、恢复来源等恢复辅助字段。
