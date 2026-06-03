# Risk 文档

当前进入 Phase 3.0 Risk Contract Gate。本阶段只冻结 pure Risk 契约，不实现 RiskEngine，不接 OMS，不写 DB，不写 `risk_events`。

## 文档入口

- `RISK_CONTRACT.md`：Risk 职责边界、输入输出、规则范围、配置边界和禁止事项。
- `RISK_TEST_MATRIX.md`：Phase 3.0 必测矩阵和 Phase 3.1+ 后续项。

Risk 只维护上述两份主文档。后续新增 Risk 设计优先合并进这两份文档，不为单个规则新增独立文档。

## 当前边界

- Phase 3.0 只允许 pure Risk Engine。
- 当前冻结接口为 `FuturesRiskEngine.check_order(signal: Signal) -> RiskResult`。
- Risk 不调用 `OMSService`，不访问 Repository / UnitOfWork / ORM / DB。
- Risk 不写 `order_events` 或 `risk_events`。
- Risk 不进入 EMS、Mock Exchange、Position、Margin、PnL 或 Settlement。
- 不得新增真实交易接口、CTP、SimNow 或 broker adapter。

不得提前把 Phase 3.1+ 风控规则、字段、接口或行为写成当前事实。
