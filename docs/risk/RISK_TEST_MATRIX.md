# Risk 测试矩阵

本文档定义 Phase 3.0 pure Risk 的测试矩阵。Phase 3.0 只覆盖纯风控计算，不接 OMS，不写 DB，不写 `risk_events`。

状态列只允许：

- `Done`
- `Pending`
- `Phase 3.1+`

Phase 3.0 进入实现前，以下 Phase 3.0 项默认为 `Pending`。实现完成并有真实测试覆盖后，才能标记为 `Done`。

## Phase 3.0 必测项

| 场景 | 预期 | 状态 |
|---|---|---|
| accepted happy path | 所有规则通过，返回 `RiskDecision.ACCEPTED`。 | Pending |
| disabled instrument reject | 合约禁用时返回 `RiskDecision.REJECTED`。 | Pending |
| max single order quantity reject | `Signal.quantity` 超过最大单笔手数时拒绝。 | Pending |
| max notional amount reject | 名义金额超过最大单笔名义金额时拒绝。 | Pending |
| price above limit up reject | 委托限价高于涨停价时拒绝。 | Pending |
| price below limit down reject | 委托限价低于跌停价时拒绝。 | Pending |
| trading session closed reject | 输入上下文标记不可交易时拒绝。 | Pending |
| offset invalid reject skeleton | `Signal.offset` 不在 `allowed_offsets` 时拒绝。 | Pending |
| margin insufficient reject skeleton | `available_margin < required_margin` 时拒绝。 | Pending |
| max position reject skeleton | `projected_position > max_position` 时拒绝。 | Pending |
| first rejection wins | 多条规则同时失败时，返回第一条拒绝规则。 | Pending |
| Decimal no float | 风控计算不得接受或产生 `float`。 | Pending |
| pure config/context 字段存在性与默认值 | 内存配置包含 Phase 3.0 最小字段表，并按契约提供默认值。 | Pending |
| None disabled semantics | `None` 按契约禁用对应 skeleton 规则，不得被误判为拒绝。 | Pending |
| dict missing key semantics | 字典缺 key 按契约禁用单 instrument 检查或触发配置错误。 | Pending |
| config error raises `RiskConfigurationError` | 配置错误抛 `RiskConfigurationError`，不得返回普通 `REJECTED` 掩盖系统错误。 | Pending |
| RiskEngine 不 import OMS/db/repository | RiskEngine 不依赖 `OMSService`、Repository / UnitOfWork / ORM / DB。 | Pending |
| RiskEngine 不写 `risk_events` | Phase 3.0 不写 `risk_events`，不触碰 DB。 | Pending |

## Config / Context 语义测试

| 场景 | 预期 | 状态 |
|---|---|---|
| `disabled_instruments` 默认值 | 缺失时视为空集合，表示没有禁用合约。 | Pending |
| `max_order_quantity is None` | 禁用最大单笔数量检查。 | Pending |
| `max_notional is None` | 禁用最大名义金额检查。 | Pending |
| `max_notional` 启用但缺 multiplier | 缺少 `contract_multiplier_by_instrument[signal.instrument_id]` 时抛 `RiskConfigurationError`。 | Pending |
| multiplier 缺 key 且 `max_notional is None` | 不使用乘数，不拒绝，不抛配置错误。 | Pending |
| `limit_up_by_instrument` 缺 key | 禁用该 instrument 的涨停检查。 | Pending |
| `limit_down_by_instrument` 缺 key | 禁用该 instrument 的跌停检查。 | Pending |
| `is_trading_session_allowed` 默认值 | 默认 `True`，Phase 3.0 不计算 calendar/session。 | Pending |
| `allowed_offsets` 默认值 | 默认包含所有当前 `Offset` enum values。 | Pending |
| `allowed_offsets` 为空集合 | 表示不允许任何 offset，所有 offset 均拒绝。 | Pending |
| `available_margin` 与 `required_margin` 同为 `None` | 禁用 margin skeleton。 | Pending |
| `available_margin` without `required_margin` | 抛 `RiskConfigurationError`。 | Pending |
| `projected_position` 与 `max_position` 同为 `None` | 禁用 max position skeleton。 | Pending |
| `max_position` without `projected_position` | 抛 `RiskConfigurationError`。 | Pending |
| `current_position` diagnostic only | 不使用 `current_position` 推导 `projected_position`，只允许透传 / 诊断。 | Pending |

## 输入输出契约测试

| 场景 | 预期 | 状态 |
|---|---|---|
| `FuturesRiskEngine.check_order` 输入 | 方法签名只接收 `Signal`；非 Signal 上下文通过构造时注入。 | Pending |
| `FuturesRiskEngine.check_order` 输出 | 当前接口只返回 `RiskResult`。 | Pending |
| `RiskResult.decision` | 只能是 `ACCEPTED` 或 `REJECTED`。 | Pending |
| accepted rule_name | 接受路径允许 `all_pass` 或 `accepted`。 | Pending |
| rejected rule_name | 拒绝路径使用 first rejection rule。 | Pending |
| `RiskResult.reason` 可选 | `reason` 类型为 `str | None`；接受路径可为空，拒绝路径建议填写。 | Pending |
| 正常拒绝不抛异常 | 规则拒绝通过 `RiskResult` 表达。 | Pending |
| 系统错误才抛异常 | 输入缺失、类型错误或配置错误可抛异常。 | Pending |
| 非 Decimal 核心数值 | 非 `Decimal` 数值进入核心计算时抛系统错误，不参与风控计算。 | Pending |

## 边界禁止测试

| 场景 | 预期 | 状态 |
|---|---|---|
| 不调用 `OMSService` | RiskEngine 不 import、不实例化、不调用 `OMSService`。 | Pending |
| 不调用 Repository / UnitOfWork | RiskEngine 不访问持久化端口。 | Pending |
| 不调用 ORM / DB | RiskEngine 不 import SQLAlchemy，不读写数据库。 | Pending |
| 不调用 EMS / Mock Exchange | RiskEngine 不提交订单，不撮合，不查询交易接口。 | Pending |
| 不调用 MarginEngine | margin skeleton 只比较 input-only Decimal 值。 | Pending |
| 不调用 PositionManager | position skeleton 只比较 input-only Decimal 值。 | Pending |
| 不调用 Position / Margin / PnL / Settlement | Phase 3.0 只消费纯输入上下文。 | Pending |
| 不调用真实交易接口 / CTP / SimNow / broker adapter | RiskEngine 不 import、不实例化、不调用任何真实交易接入或适配器。 | Pending |
| 不读取环境变量 / 文件 | 配置来自纯内存对象或规则参数。 | Pending |
| 不调用外部服务 | 不调用 HTTP / RPC / Redis / broker。 | Pending |
| 不 import `futures_mvp.db.*` | RiskEngine 不 import DB 包或 ORM model。 | Pending |
| 不 import `RiskEvent` ORM | 现有 `risk_events` schema 不属于 pure Risk 可用依赖。 | Pending |
| 不新增 Domain 字段 | Phase 3.0 Risk 实现不得为规则上下文新增 Domain 字段。 | Pending |
| 不新增 DB schema / migration | Phase 3.0 Risk 实现不得新增 schema 或 Alembic migration。 | Pending |
| 不依赖 raw / metadata / details | Risk 不得把 `raw`、`metadata`、`details` 或 `raw_payload` 当作 source-of-truth。 | Pending |
| 不新增 live / production / remote / KMS / cloud 文件 | Phase 3.0 不新增生产、远程、密钥或云流程文档 / 配置。 | Pending |

## Phase 3.1+ 后续项

以下不是 Phase 3.0 当前事实，不阻塞 Phase 3.0 pure Risk：

| 场景 | 预期 | 状态 |
|---|---|---|
| real position context | 引入真实持仓上下文前必须先定义输入契约。 | Phase 3.1+ |
| real margin engine | 引入真实保证金引擎前必须先定义模块边界。 | Phase 3.1+ |
| exchange-specific close_today / close_yesterday | 交易所特定平今 / 平昨细则后续实现。 | Phase 3.1+ |
| trading calendar integration | 如需接交易日历，必须先定义纯输入或独立集成边界。 | Phase 3.1+ |
| `risk_events` repository | 持久化 risk_events 前必须先设计 Repository / UnitOfWork。 | Phase 3.1+ |
| Risk -> OMS application orchestration | 未来上层编排负责把 `RiskResult` 交给 `OMSService.apply_risk_result`。 | Phase 3.1+ |
| 多规则拒绝聚合 | first rejection wins 之外的聚合策略后续定义。 | Phase 3.1+ |
