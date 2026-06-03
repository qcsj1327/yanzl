# Risk 冻结契约

本文档定义 pure Risk 的冻结契约。Phase 3.0 定义 Risk 职责边界、输入输出、规则范围、配置边界和禁止事项；Phase 3.1 在该契约下实现 pure RiskEngine。

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

非 `Signal` 风控上下文只能通过构造时注入的纯内存配置对象或规则参数提供，不得作为 `check_order` method 参数传入。RiskEngine 本身仍保持 pure computation。

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
- import `futures_mvp.db.*`。
- import `RiskEvent` ORM。
- 通过 `raw_payload`、`metadata`、`raw` 或 `details` 承载 source-of-truth 字段。

## Phase 3.0 Pure Risk Config / Context

以下字段是 Phase 3.0 pure Risk 的最小内存配置 / 上下文形状。

这些字段：

- 不是 Domain 字段。
- 不是 DB schema。
- 不是 interface method 参数。
- 只能通过构造时注入的纯内存配置或规则参数提供。
- 不允许 Risk 通过 DB、OMS、Position、Margin、Calendar 或外部服务自行获取。

| 字段 | 类型 | 默认值 / 缺失行为 | `None` / 缺 key 语义 | 是否启用规则 |
|---|---|---|---|---|
| `disabled_instruments` | `set[str]` | 默认空集合；缺失视为空集合。 | 不适用。空集合表示没有禁用合约。 | 集合非空时启用禁用合约检查。 |
| `max_order_quantity` | `Decimal | None` | 默认 `None`。 | `None` 表示禁用最大单笔数量检查；非 `None` 时 `Signal.quantity` 超过则拒绝。 | 非 `None` 时启用。 |
| `max_notional` | `Decimal | None` | 默认 `None`。 | `None` 表示禁用最大名义金额检查；非 `None` 时必须有对应合约乘数。 | 非 `None` 时启用。 |
| `contract_multiplier_by_instrument` | `dict[str, Decimal]` | 默认空字典；缺失视为空字典。 | 若 `max_notional is None`，缺 key 不使用、不拒绝；若 `max_notional is not None`，缺 key 是配置错误，不得静默通过，不得用 `1` 兜底。 | 不是独立拒绝规则，仅服务名义金额检查。 |
| `limit_up_by_instrument` | `dict[str, Decimal]` | 默认空字典；缺失视为空字典。 | 缺 key 表示禁用该 instrument 的涨停检查；非缺 key 时价格高于涨停价拒绝。 | instrument 有 key 时启用。 |
| `limit_down_by_instrument` | `dict[str, Decimal]` | 默认空字典；缺失视为空字典。 | 缺 key 表示禁用该 instrument 的跌停检查；非缺 key 时价格低于跌停价拒绝。 | instrument 有 key 时启用。 |
| `is_trading_session_allowed` | `bool` | 默认 `True`。 | `True` 表示通过交易时段 flag；`False` 表示拒绝。Phase 3.0 不计算 calendar/session。 | 始终启用，只消费布尔值。 |
| `allowed_offsets` | `set[Offset]` | 默认所有当前 `Offset` enum values；缺失使用默认全量。 | 空集合表示不允许任何 offset；`Signal.offset` 不在集合中时拒绝。 | 始终启用。 |
| `available_margin` | `Decimal | None` | 默认 `None`。 | 与 `required_margin` 同为 `None` 时禁用 margin skeleton；任一单边存在都是配置错误。 | 二者均非 `None` 时启用。 |
| `required_margin` | `Decimal | None` | 默认 `None`。 | 与 `available_margin` 同为 `None` 时禁用 margin skeleton；任一单边存在都是配置错误。 | 二者均非 `None` 时启用。 |
| `current_position` | `Decimal | None` | 默认 `None`。 | 仅作透传 / 诊断。Phase 3.0 不用它推导 `projected_position`。 | 不启用任何规则。 |
| `projected_position` | `Decimal | None` | 默认 `None`。 | 与 `max_position` 同为 `None` 时禁用 max position skeleton；任一单边存在都是配置错误。 | 二者均非 `None` 时启用。 |
| `max_position` | `Decimal | None` | 默认 `None`。 | 与 `projected_position` 同为 `None` 时禁用 max position skeleton；任一单边存在都是配置错误。 | 二者均非 `None` 时启用。 |

Phase 3.2 类型硬化：

- `disabled_instruments` 必须是 `set[str]`。
- `allowed_offsets` 必须是 `set[Offset]`。
- `contract_multiplier_by_instrument`、`limit_up_by_instrument`、`limit_down_by_instrument` 必须是 `dict[str, Decimal]`。
- `is_trading_session_allowed` 必须是 `bool`。
- 所有 Decimal 配置字段必须是 `Decimal | None`。
- 所有配置类型错误统一抛 `RiskConfigurationError`，不得向调用方泄漏 `AttributeError`、`TypeError` 或 `ValueError`。

margin / position 均为 input-only skeleton：

- 不调用 `MarginEngine`。
- 不调用 `PositionManager`。
- 不保证与真实账户、真实仓位一致。
- `required_margin` 和 `projected_position` 的来源不属于 Phase 3.0。
- RiskEngine 不使用 `current_position` 计算 `projected_position`；`projected_position` 必须由构造配置或规则参数直接提供。
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

Phase 3.0 最小配置来源为构造时注入的纯内存配置对象或规则参数。

配置不得作为 `check_order` method 参数传入。

Risk 禁止：

- 读取环境变量。
- 读取文件。
- 查询数据库。
- 调用外部服务。
- 调用 Redis。
- 调用 HTTP / RPC。

## Source-of-Truth 边界

Risk 不得依赖 `raw`、`metadata`、`details` 或 `raw_payload` 作为 source-of-truth 风控字段。

如果未来需要扩展风控字段，必须通过明确配置对象或 Domain migration 进入契约，不得塞入诊断 payload。

现有 DB schema 中即使存在 `risk_events`，也不属于 Phase 3.0 / Phase 3.1 pure Risk 可用依赖。RiskEngine 不得 import `futures_mvp.db.*`，不得 import `RiskEvent` ORM，不得写 `risk_events`。

## Decimal 规则

数量、价格、金额、保证金和名义金额必须使用 `Decimal`。

不允许 `float` 参与核心风控计算。该规则与当前 Domain Decimal 规则一致。

## 错误与拒绝语义

规则未通过时，返回 `RiskDecision.REJECTED`。

正常拒绝路径不得抛异常。

配置错误和系统错误不得通过 `RiskDecision.REJECTED` 掩盖。

Phase 3.0 采用以下错误语义：

- 正常风控拒绝返回 `RiskResult(RiskDecision.REJECTED, rule_name, reason)`。
- 配置错误抛 `RiskConfigurationError`。
- `RiskConfigurationError` 是 Phase 3.0 Risk 实现必须提供的配置错误类型。

异常只用于系统错误，例如：

- 输入缺失。
- 类型错误。
- 配置错误。
- Decimal 约束被破坏。

配置错误包括：

- `max_notional` 启用但缺少 `contract_multiplier_by_instrument[signal.instrument_id]`。
- `available_margin is None` 且 `required_margin is not None`。
- `available_margin is not None` 且 `required_margin is None`。
- `projected_position is None` 且 `max_position is not None`。
- `projected_position is not None` 且 `max_position is None`。
- 非 `Decimal` 数值进入核心风控计算。

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
