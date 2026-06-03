# 执行文档

Phase 4.0 Exchange / Execution Contract Gate 已冻结执行契约。Phase 4.1 已实现 DTO、MappingContext、MappingResult、MappingError 和 pure ExchangeReport mapper；当前 Execution Command/Report Runtime Layer 已实现本地 in-memory report surface、EMS command boundary、ConfigurableMockFuturesExchange skeleton 和 mapper wrapper。不连接真实交易接口。

## 文档入口

- `EXECUTION_CONTRACT.md`：EMS、MockFuturesExchange command port、exchange report、OrderEvent 映射和执行回报语义。
- `EXECUTION_TEST_MATRIX.md`：Execution 契约测试矩阵和后续阶段范围。

Execution 只维护上述两份主文档。后续新增执行设计优先合并进这两份文档，不为 submit、cancel、fill、reject 等单独新增文档。

## 当前边界

- Phase 4.0 定义 EMS / MockFuturesExchange command port、ExchangeReport / OrderEvent 映射契约。
- Phase 4.1 已实现 DTO、typed result 和 pure mapper。
- Execution runtime layer 已实现 `ExchangeCommandPort`、本地 `ExecutionReportSink`、EMS command boundary、ConfigurableMockFuturesExchange 和 `ExecutionReportHandler`。
- 当前 `MockFuturesExchange` Protocol 只承载 submit / cancel command port，方法返回 `None`；report surface 通过独立 `ExecutionReportSink` 承载。
- `ExecutionReportSink` 是当前 local / in-memory report surface，不是 Kafka / Redis / Celery，也不是生产事件总线；后续 runtime/infra event bus 必须另开 adapter。
- Phase 4 可实现的 MockFuturesExchange 不包含 settlement 方法；每日结算属于后续 Settlement 阶段。
- EMS / Exchange 不直接修改 OMS 状态，不直接写订单状态。
- `OMSService.apply_order_event(...)` 是订单状态变更入口。
- 后续 Exchange report 必须先映射为 `OrderEvent` 或 typed mapping result 后进入 OMS。
- 乱序不是独立 report type；由普通 report 的 `previous_status` mismatch 交给 OMS 处理。
- `UNKNOWN_REPORT` 应用等待后续 OMS public UNKNOWN entry，不属于当前 runtime layer 实现范围。
- 不得提前把 Application Execution Orchestrator、真实交易接口、CTP、SimNow 或 broker adapter 写成当前事实。
