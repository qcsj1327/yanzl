# Stage W.1 组合研究层契约冻结

基线：`stage-v19-local-research-backtest-mvp-baseline / b410f68`。

Stage W.1 只改文档。本文冻结研究专用组合层契约，为后续多品种、多持仓、多策略 Backtest 定义边界。本文不新增代码、测试、schema、Alembic migration、DB write、broker 连接、live feed、network 集成或 execution target enablement。

`ResearchPortfolio` 只属于 Backtest 研究 / 观测对象。它不是生产组合、会计账本、broker 账户或 live position 事实来源。

## ResearchPortfolio 契约

未来 `ResearchPortfolio` 必须是类型化、确定性的对象。

必需字段：

- `portfolio_id`。
- `strategy_name`。
- `run_id`。
- `initial_cash`。
- `cash`。
- `total_market_value`。
- `total_equity`。
- `positions`。
- `pnl_points`。
- `diagnostics`。

身份规则：

- 同一 `strategy_name`、`run_id`、初始资金、resolver lineage 集合和已接受 Backtest 配置必须生成确定性的 `portfolio_id`。
- `strategy_name` 和 `run_id` 必须参与组合身份。
- 即使消费相同 market data，不同 `strategy_name` 或 `run_id` 的两次运行也必须生成隔离的 portfolio 对象。
- `positions` 必须按 resolver-derived instrument identity 建模，不得按 UI label、filename、raw payload 或人工猜测的合约字符串建模。

`ResearchPortfolio` 可以汇总模拟订单、模拟成交、研究持仓和研究 PnL points。这些汇总仍只是 Backtest 输出视图；不得成为 OMS、Trade、Position、Accounting、broker 或 live account 事实。

## ResearchPosition 契约

Stage W.1 冻结一个研究组合内可包含多个 `ResearchPosition` 对象。

每个 `ResearchPosition` 必须携带：

- `symbol`。
- `instrument_id`。
- `trade_instrument_id`。
- `exchange`。
- `trading_day` 或生效交易日窗口。
- `side`。
- `quantity`。
- `avg_price`。
- `market_value`。
- resolver lineage。
- diagnostics。

resolver lineage 必须包含：

- resolver source。
- resolver confidence。
- resolver 生效窗口或 diagnostics summary。
- resolver status。
- 本次 Backtest run 使用的数据源摘要。

同一个研究组合允许跨不同 `symbol`、`instrument_id` 和 `trade_instrument_id` 持有多个 position。resolver-derived identity 不同的两个 position 不得被合并。

当前冻结方向范围仍为 long-only：

- 接受研究专用模拟成交后可以 long open。
- 禁止 short。
- 禁止 close / exit，直到后续单独接受 close / exit contract。
- 禁止 partial fill。

resolver identity 为 unresolved、expired、ambiguous 或 metadata-invalid 时，必须在创建或更新任何 `ResearchPosition` 前 fail closed。

## 资金分配规则

Stage W.1 冻结单一组合资金池。

cash 规则：

- `initial_cash` 是一次 Backtest run 的起始研究资金。
- `cash` 从 `initial_cash` 开始。
- 每笔 accepted research trade 都从单一资金池扣减 notional。
- buy notional 按已接受研究成交契约下的 `fill_price * fill_qty` 计算。
- `cash` 不得为负。
- 会导致 `cash` 为负的 trade 必须 fail closed，且不得创建或更新 `ResearchPosition`。

负资金、leverage、margin 和 borrowing 都不是已冻结能力。实现前必须先单独冻结 leverage / margin contract。

研究资金不代表生产资金变动。研究资金不得写入 account balance、broker balance、margin snapshot、settlement snapshot 或 accounting ledger。

## 组合权益曲线

组合权益是研究专用曲线。

每个 portfolio PnL point 的计算规则：

```text
total_market_value = sum(position market value)
total_equity = cash + total_market_value
```

必须能观测每个品种的贡献。未来每个 `pnl_points` entry 必须能按组合内每个 symbol / resolver identity 识别对应 position market value 及其对 total equity 的贡献。

equity 规则：

- position market value 只能使用计算点之前或当时可用的、无前视的标准化历史行情数据。
- 禁止使用未来 bar、未来 tick、未来 quote 和最终运行汇总。
- `total_market_value` 是 research position market value 的总和，不是 broker valuation。
- `total_equity` 只是研究权益，不是账户权益。
- portfolio PnL point 必须保留复现该点所需的 `strategy_name`、`run_id` 和 resolver lineage。

组合权益曲线输出不是生产会计事实。没有单独接受的 promotion contract 前，不得用于 settlement、reconciliation、broker account display、live risk 或 production replay。

## 策略隔离

Stage W.1 冻结单策略组合隔离。

隔离规则：

- 每个 `ResearchPortfolio` 只属于一个 `strategy_name` 和一个 `run_id`。
- `strategy_name` 和 `run_id` 必须参与组合身份、position grouping 和 PnL point lineage。
- 两个 strategy 不得共享可变研究资金、positions、PnL points、diagnostics 或 simulated trade state。
- 一个 failed 或 blocked strategy run 不得污染另一个 strategy run。
- multi-strategy portfolio aggregation 不在 W.1 冻结范围内，必须另开阶段。

未来 multi-strategy portfolio work 必须先定义明确的 ownership、allocation、aggregation 和 conflict rules，才能进入实现。

## Fail-Closed 能力列表

Stage W.1 继续禁止以下能力：

- close。
- short。
- partial fill。
- commission。
- slippage。
- leverage。
- margin。
- multi-currency。

任何 request、strategy decision、simulated order、simulated trade 或 portfolio update 只要需要上述能力，都必须 fail closed，并保持研究资金、positions 和 PnL points 不变。

## 安全边界

`ResearchPortfolio` 不是：

- production portfolio。
- accounting ledger。
- broker account。
- live position。
- account balance。
- settlement source-of-truth。
- reconciliation source-of-truth。

Stage W.1 和未来组合研究层实现不得：

- write DB。
- write OMS。
- write Trade ledger。
- write production Position。
- write Accounting。
- mutate schema 或 Alembic migrations。
- call broker。
- call CTP。
- call SimNow。
- call live feed。
- call network。
- enable `ExecutionTarget.PAPER`。
- enable `ExecutionTarget.SIM`。
- enable `ExecutionTarget.LIVE`。
- 使用 raw CSV rows、raw vendor payloads、raw broker payloads 或 `raw_payload` 作为 identity、price、cash 或 portfolio facts。

默认 schema decision：NO schema。

任何 durable portfolio storage、run table、allocation table、portfolio position table 或 portfolio equity table 都必须单独 contract freeze 并接受 review。

## 后续路线

后续组合研究层阶段：

```text
W.2 ResearchPortfolio skeleton
W.3 multi-symbol fixture backtest
W.4 portfolio equity aggregation
C.1 Close / Exit research contract freeze
C.2 Exit skeleton
C.3 Realized PnL skeleton
C.4 Cash return integration
```

W.2 如被单独接受，只能实现内存内研究骨架。它必须保留 W.1 安全边界，不得新增 schema、DB writes、OMS / Trade / Position / Accounting mutation、broker / live / network connectivity 或 execution target enablement。

## Stage C.1 Close / Exit 研究契约冻结

基线：`stage-w3-backtest-research-portfolio-integration / d69a7cd`
以及 `stage-v19-local-research-backtest-mvp-baseline`。

Stage C.1 只改文档。本文冻结 research-only close / exit contract，
为后续 Exit skeleton、Realized PnL skeleton 和 Cash return integration
定义边界。本文不新增代码、测试、schema、Alembic migration、DB write、
broker 连接、live feed、network 集成或 execution target enablement。

### Position Lifecycle

研究专用 long-only lifecycle 冻结为：

```text
FLAT
-> OPEN_LONG
-> LONG
-> CLOSE
-> FLAT
```

当前 C.1 只冻结 `LONG -> CLOSE` 退出路径。`SHORT`、short open、
short cover、long/short reversal 和 cross-position close 均未冻结为可用能力。

### StrategyDecision.CLOSE

未来 `StrategyDecision` 必须冻结 `CLOSE` 语义：

- `CLOSE` 只表示退出已有 `LONG` research position。
- `CLOSE` 不是 `SELL SHORT`。
- `CLOSE` 不得开空、反手、增加仓位或跨 position 合并退出。
- 没有已有 matching long position 时必须 fail closed。

### Exit Order

未来 exit order conversion 必须经过专用 Backtest research 边界：

```text
StrategyDecision(CLOSE)
-> DecisionTranslator
-> Exit SimulatedOrder
```

`Exit SimulatedOrder` 仍是 in-memory Backtest research object。它必须继承
原 research position 的 `strategy_name`、`run_id`、resolver lineage、
`symbol`、`instrument_id`、`trade_instrument_id`、exchange 和 trading-day
context。它不得成为 OMS order、Trade ledger fact、Accounting fact、
broker order 或 live execution truth。

### Exit Fill

未来 exit fill 默认冻结为 Next Bar Open Exit Fill：

```text
close order created at bar N
-> filled at bar N+1 open
```

同 bar exit fill 禁止。没有下一根可用标准化 bar、resolver lineage 不匹配、
或下一根 bar 无 open price 时必须 fail closed，不得合成 exit fill。

### Realized PnL

long-only realized PnL 公式冻结为：

```text
realized_pnl = (exit_price - entry_price) * quantity
```

Stage C.1 不冻结 short PnL、fee、commission、slippage、margin、leverage、
multi-currency 或 settlement PnL。上述能力必须在单独 contract freeze 后
才能实现。

### Cash Return

研究资金流冻结为：

```text
entry: cash -= entry_notional
exit:  cash += exit_notional
```

`entry_notional` 和 `exit_notional` 均为 research-only notional。它们不得
mutate production account balance、Trade ledger、Position、Accounting、
Settlement、Margin、broker balance 或 live account facts。

### Fail-Closed 规则

以下情况必须 fail closed，并保持 research cash、positions、orders、
trades 和 PnL points 不变：

- close without position。
- close wrong symbol。
- close wrong resolver lineage。
- close wrong `strategy_name` 或 `run_id`。
- negative quantity 或 zero quantity。
- close quantity 大于当前 matching long research position quantity。
- cross-position close。
- `CLOSE` 被解释为 sell short。
- same bar exit fill。
- unresolved、expired、ambiguous 或 metadata-invalid resolver identity。

### Research Only

Exit order、exit trade 和 realized PnL 都是 Backtest research /
observability output。它们不是：

- OMS truth。
- Trade ledger。
- Accounting fact。
- Broker truth。
- production Position truth。
- settlement source-of-truth。

Stage C.1 不得 write DB、OMS、Trade ledger、production Position、
Accounting、Margin、Settlement 或 broker state；不得 mutate schema /
Alembic；不得 connect broker / CTP / SimNow / live feed / network；不得
enable `ExecutionTarget.PAPER`、`ExecutionTarget.SIM` 或
`ExecutionTarget.LIVE`。

### Future Stages

后续 research close / exit 阶段冻结为：

```text
C.2 Exit Skeleton
C.3 Realized PnL Skeleton
C.4 Cash Return Integration
```

## Stage C.2 Exit Skeleton Status

基线：`stage-c1-close-exit-research-contract-freeze / 6826086`。

Stage C.2 实现 research-only CLOSE skeleton，只生成 `Exit SimulatedOrder`。
该阶段不实现 exit fill、exit trade、realized PnL、cash return、schema、
DB write、broker/live/network 或 execution target enablement。

`StrategyDecision.CLOSE` 保持 long-only exit 语义。`ExitReferenceStrategy`
仅用于研究测试：bar 1 产生 `BUY`，bar 2+ 产生 `CLOSE`。

`DecisionTranslator` 支持：

```text
BUY   -> SimulatedOrder(intent=ENTRY, side=BUY, status=CREATED)
CLOSE -> SimulatedOrder(intent=EXIT, side=CLOSE, status=CREATED)
```

`DecisionTranslator` 不生成 `SimulatedTrade`。默认 `NoFillModel` 继续返回
`NO_FILL`，因此 C.2 不修改 equity、cash、research position 或 PnL curve。
`SELL` 仍不属于 long-only research skeleton，必须拒绝。

## Stage C.3 Exit Fill Skeleton Status

基线：`stage-c2-exit-order-skeleton / b130d8e`。

Stage C.3 让 `NextBarOpenFillModel` 支持 `SimulatedOrder(intent=EXIT,
side=CLOSE)`，并生成 research-only EXIT `SimulatedTrade`。该阶段保持
ENTRY order 的 next-bar-open fill 行为不变。

EXIT fill rules：

- 只使用 `created_bar_ts` 之后第一根同 resolver identity 的 bar。
- `fill_price = next_bar.open`。
- `fill_qty = order.quantity`。
- same bar 禁止成交。
- no next bar 返回 `DATA_GAP`，不生成 trade。
- identity mismatch 不成交。

ENTRY trade diagnostics 必须标记 `ENTRY`，EXIT trade diagnostics 必须标记
`EXIT`。两者都仍是 Backtest research / observability output，不是 Trade
ledger、OMS truth、Accounting fact、broker execution 或 exchange execution。

C.3 不实现 realized PnL、cash return、position close、equity curve update、
schema、DB write、broker/live/network 或 execution target enablement。

## Stage C.4 Realized PnL + Cash Return Skeleton Status

基线：`stage-c3-exit-fill-skeleton / 81b6f00`。

Stage C.4 在 research-only Backtest 内实现单 ENTRY trade + 单 EXIT trade
的 long-only close lifecycle。该阶段只支持一笔 long entry 和一笔 matching
exit；不支持 short、partial close、commission、slippage、margin、leverage
或多 position 配对。

Trade pairing rules：

- 必须有且只有一笔 `SimulatedTrade(intent=ENTRY)`。
- close lifecycle 必须有且只有一笔 `SimulatedTrade(intent=EXIT)`。
- ENTRY 与 EXIT 必须匹配 `symbol`、`instrument_id`、
  `trade_instrument_id`、exchange、`trading_day` 和 resolver lineage。
- ENTRY 与 EXIT quantity 必须相同。
- EXIT 不得早于 ENTRY。
- duplicate entry、duplicate exit、identity mismatch、quantity mismatch 和
  exit-before-entry 必须 fail closed。

Long-only realized PnL：

```text
realized_pnl = (exit_price - entry_price) * quantity
```

Research cash flow：

```text
entry: cash -= entry_price * quantity
exit:  cash += exit_price * quantity

final_cash = initial_cash - entry_notional + exit_notional
```

EXIT 后的研究持仓必须变为 `FLAT`、quantity 为 `0`、market value 为 `0`。
close 后的最后 PnL point 必须记录 realized PnL，unrealized PnL 为 `0`，
equity 等于 final cash。

`ExitReferenceStrategy + NextBarOpenFillModel` 的 C.4 验收行为：

- bar 1 产生 `BUY` decision。
- BUY 在 bar 2 open 生成 ENTRY trade。
- bar 2 产生 `CLOSE` decision。
- CLOSE 在 bar 3 open 生成 EXIT trade。
- EXIT 后不再处理额外 close lifecycle。
- 最终 cash 反映 entry notional 扣减和 exit notional 返还。
- 最终 equity 等于最终 cash。

Stage C.4 输出的 `ResearchPosition`、`ResearchPnLPoint`、
`ResearchPortfolio`、simulated orders 和 simulated trades 仍然只是 Backtest
research / observability output。realized PnL 不是 production accounting
truth；cash return 不是 broker balance、account balance、settlement、
margin 或 accounting ledger fact。

Stage C.4 不得 write DB、schema、Alembic、OMS、Trade ledger、production
Position、Accounting、Margin、Settlement 或 broker state；不得 connect
broker、CTP、SimNow、live feed 或 network；不得 enable
`ExecutionTarget.PAPER`、`ExecutionTarget.SIM` 或 `ExecutionTarget.LIVE`。
