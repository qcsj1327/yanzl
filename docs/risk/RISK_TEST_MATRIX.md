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
| offset invalid reject skeleton | 基础 offset 校验失败时拒绝。 | Pending |
| margin insufficient reject skeleton | 可用保证金输入不足时拒绝。 | Pending |
| max position reject skeleton | 输入持仓超过上限时拒绝。 | Pending |
| first rejection wins | 多条规则同时失败时，返回第一条拒绝规则。 | Pending |
| Decimal no float | 风控计算不得接受或产生 `float`。 | Pending |
| RiskEngine 不 import OMS/db/repository | RiskEngine 不依赖 `OMSService`、Repository / UnitOfWork / ORM / DB。 | Pending |
| RiskEngine 不写 `risk_events` | Phase 3.0 不写 `risk_events`，不触碰 DB。 | Pending |

## 输入输出契约测试

| 场景 | 预期 | 状态 |
|---|---|---|
| `FuturesRiskEngine.check_order` 输入 | 当前接口只接收 `Signal`。 | Pending |
| `FuturesRiskEngine.check_order` 输出 | 当前接口只返回 `RiskResult`。 | Pending |
| `RiskResult.decision` | 只能是 `ACCEPTED` 或 `REJECTED`。 | Pending |
| `RiskResult.rule_name` | 返回命中的规则名。 | Pending |
| `RiskResult.reason` | 返回接受或拒绝原因。 | Pending |
| 正常拒绝不抛异常 | 规则拒绝通过 `RiskResult` 表达。 | Pending |
| 系统错误才抛异常 | 输入缺失、类型错误或配置错误可抛异常。 | Pending |

## 边界禁止测试

| 场景 | 预期 | 状态 |
|---|---|---|
| 不调用 `OMSService` | RiskEngine 不 import、不实例化、不调用 `OMSService`。 | Pending |
| 不调用 Repository / UnitOfWork | RiskEngine 不访问持久化端口。 | Pending |
| 不调用 ORM / DB | RiskEngine 不 import SQLAlchemy，不读写数据库。 | Pending |
| 不调用 EMS / Mock Exchange | RiskEngine 不提交订单，不撮合，不查询交易接口。 | Pending |
| 不调用 Position / Margin / PnL / Settlement | Phase 3.0 只消费纯输入上下文。 | Pending |
| 不读取环境变量 / 文件 | 配置来自纯内存对象或规则参数。 | Pending |
| 不调用外部服务 | 不调用 HTTP / RPC / Redis / broker。 | Pending |

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
