# Risk 冻结契约

本文档定义 Phase 3.0 pure Risk 的冻结契约。Phase 3.0 只定义 Risk 职责边界、输入输出、规则范围、配置边界和禁止事项，不实现 RiskEngine。

## 当前事实来源

当前 Risk 接口以现有接口为准：

- `src/futures_mvp/interfaces/engines.py`
- `src/futures_mvp/domain/models.py`
- `src/futures_mvp/domain/enums.py`

当前冻结接口：

```python
FuturesRiskEngine.check_order(signal: Signal) -> RiskResult
```

Phase 3.0 不新增 Domain 字段，不新增接口签名，不新增 schema，不写 `risk_events`。

## 职责边界

Risk 只负责：

- 接收领域输入。
- 执行纯风控规则判断。
- 返回 `RiskResult`。
- 不产生订单事件。
- 不修改订单状态。
- 不写数据库。
- 不调用 `OMSService`。

Risk 禁止负责：

- 创建订单。
- 修改 OMS 状态。
- 提交 EMS。
- 撮合。
- 生成成交。
- 更新持仓。
- 计算 PnL。
- 执行结算。
- 写 `risk_events`。
- 连接真实柜台、CTP、SimNow 或 broker。

## Phase 3.0 输入输出

`check_order` 方法参数只接收 `Signal`。

非 `Signal` 风控上下文只能通过构造时注入的纯内存配置或规则参数提供。RiskEngine 本身仍保持 pure computation。

当前不直接消费 `OrderRequest`。如果后续需要 Risk 直接消费 `OrderRequest`，必须先做 domain/interface migration，并同步更新契约、测试和文档。

Phase 3.0 返回 `RiskResult`：

- `RiskResult.decision` 只能是 `RiskDecision.ACCEPTED` 或 `RiskDecision.REJECTED`。
- `RiskResult.rule_name` 表示产生该结果的规则或汇总规则。接受时可使用 `all_pass` 或 `accepted`；拒绝时使用 first rejection rule。
- `RiskResult.reason` 类型为 `str | None`，是可选风控说明。拒绝时建议填写 reason；接受时可为空，也可写 `all_pass` 或 `accepted`。

不得把 future fields 写成当前事实。

## OMS 接入边界

RiskEngine 只返回 `RiskResult`。

未来上层 application/service 可以负责把 `RiskResult` 交给 `OMSService.apply_risk_result(...)`，但 Phase 3.0 不实现该编排。

Risk 禁止：

- import `OMSService`。
- import Repository / UnitOfWork / ORM。
- 查询 DB。
- 调用 OMS、Position、Margin 或 Calendar 模块。
- 读取或写入 `orders`、`order_events`、`risk_events`。
- 通过 `raw_payload`、`metadata`、`raw` 或 `details` 承载 source-of-truth 字段。

## Phase 3.0 Pure Risk Config / Context

以下字段是 Phase 3.0 pure Risk 的最小内存配置 / 上下文形状。

这些字段：

- 不是 Domain 字段。
- 不是 DB schema。
- 不是 interface method 参数。
- 只能通过构造时注入的纯内存配置或规则参数提供。
- 不允许 Risk 通过 DB、OMS、Position、Margin、Calendar 或外部服务自行获取。

| 字段 | 类型 | 用途 |
|---|---|---|
| `disabled_instruments` | `set[str]` | 禁用合约检查。 |
| `max_order_quantity` | `Decimal | None` | 最大单笔数量。 |
| `max_notional` | `Decimal | None` | 最大单笔名义金额。 |
| `contract_multiplier_by_instrument` | `dict[str, Decimal]` | 名义金额计算乘数。 |
| `limit_up_by_instrument` | `dict[str, Decimal]` | 涨停价。 |
| `limit_down_by_instrument` | `dict[str, Decimal]` | 跌停价。 |
| `is_trading_session_allowed` | `bool` | 当前是否允许交易。Phase 3.0 不计算交易日历，只消费布尔值。 |
| `allowed_offsets` | `set[Offset]` | Phase 3.0 offset skeleton 只检查 offset 是否在配置允许集合中。 |
| `available_margin` | `Decimal | None` | 可用保证金输入值。 |
| `required_margin` | `Decimal | None` | 本次请求所需保证金输入值。 |
| `current_position` | `Decimal | None` | 当前输入持仓数量。 |
| `projected_position` | `Decimal | None` | 本次交易后预计持仓数量。 |
| `max_position` | `Decimal | None` | 最大持仓限制。 |

margin / position 均为 input-only skeleton：

- 不调用 `MarginEngine`。
- 不调用 `PositionManager`。
- 不保证与真实账户、真实仓位一致。
- `required_margin` 和 `projected_position` 的来源不属于 Phase 3.0。
- Phase 3.1+ 再接真实上下文。

## Phase 3.0 最小规则范围

Phase 3.0 只定义纯规则。所有上下文必须通过纯输入对象或内存配置对象传入，不允许 Risk 自己查询 DB 或调用其他模块。

最小规则范围：

- disabled instrument。
- max single order quantity。
- max notional amount。
- price limit up / down。
- trading session allowed flag。
- close_today / close_yesterday basic offset validation skeleton。
- input-only margin availability skeleton。
- input-only max position skeleton。

保证金、持仓、交易时段如需上下文，必须通过纯输入对象或配置传入。

Risk 不允许调用 PositionManager，因为 PositionManager 尚未实现。

### 规则说明

disabled instrument：

- 输入配置标记合约禁用时，返回 `RiskDecision.REJECTED`。

max single order quantity：

- `Signal.quantity` 超过配置上限时，返回 `RiskDecision.REJECTED`。

max notional amount：

- 名义金额由 `Signal.limit_price * Signal.quantity * multiplier` 等纯输入字段计算。
- 超过配置上限时，返回 `RiskDecision.REJECTED`。

price limit up / down：

- `Signal.limit_price` 高于涨停价或低于跌停价时，返回 `RiskDecision.REJECTED`。

trading session allowed flag：

- 输入上下文标记当前不可交易时，返回 `RiskDecision.REJECTED`。

close_today / close_yesterday basic offset validation skeleton：

- 只验证 `Signal.offset` 是否在 `allowed_offsets` 配置集合中。
- 不验证今仓 / 昨仓可用数量。
- 不处理交易所平今 / 平昨优先级。
- 交易所特定平今 / 平昨细则进入 Phase 3.1+。

input-only margin availability skeleton：

- 只比较调用方提供的 Decimal 值，例如 `available_margin >= required_margin`。
- 不计算真实 margin。
- 不读取 `margin_rate`。
- 不接真实账户资金引擎。

input-only max position skeleton：

- 只比较调用方提供的 Decimal 值，例如 `projected_position <= max_position`。
- 不更新或推导真实持仓。
- 不接 PositionManager。

## 配置边界

Phase 3.0 最小配置来源为纯内存配置对象或规则参数。

Risk 禁止：

- 读取环境变量。
- 读取文件。
- 查询数据库。
- 调用外部服务。
- 调用 Redis。
- 调用 HTTP / RPC。

## Decimal 规则

数量、价格、金额、保证金和名义金额必须使用 `Decimal`。

不允许 `float` 参与核心风控计算。该规则与当前 Domain Decimal 规则一致。

## 错误与拒绝语义

规则未通过时，返回 `RiskDecision.REJECTED`。

正常拒绝路径不得抛异常。

异常只用于系统错误，例如：

- 输入缺失。
- 类型错误。
- 配置错误。
- Decimal 约束被破坏。

多规则命中策略：

- Phase 3.0 采用 first rejection wins。
- 第一个拒绝规则决定 `RiskResult.decision` 和 `rule_name`，并建议填写 `reason`。
- 聚合多个拒绝原因属于 Phase 3.1+。

## Phase 3 禁止事项

Phase 3.0 禁止：

- OMS 集成。
- DB 写入。
- `risk_events`。
- EMS / Exchange。
- Position / Margin / PnL / Settlement。
- 真实交易接口。
- CTP。
- SimNow。
- broker adapter。
- live / production / remote / KMS / cloud 流程。

## Phase 3.1+ 后续候选

以下不是 Phase 3.0 当前事实：

- real position context。
- real margin engine。
- exchange-specific close_today / close_yesterday。
- trading calendar integration。
- `risk_events` repository。
- Risk -> OMS application orchestration。
- 多规则拒绝原因聚合。
