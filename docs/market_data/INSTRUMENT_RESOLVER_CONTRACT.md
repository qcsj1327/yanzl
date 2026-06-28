# Stage U.1 Instrument Resolver / Market Data Contract Freeze

Baseline：`stage-t4-console-preview-stable / fa234eb`。

Stage U.1 is documentation-only. It freezes the future Instrument Resolver and
Market Data Source contract for domestic futures identity resolution. It does
not add code, schema, Alembic migration, `src` changes, tests, commit or tag.

The goal is to stop downstream modules and UI workflows from guessing futures
contract codes. Backtest, Paper, SIM and future Live flows must consume the same
resolver snapshot for the same `symbol + trading_day`.

## Identifier Contract

Instrument identity terms are frozen as follows：

- `symbol`：品种代码，例如 `ao`、`rb`、`ag`、`cu`、`IF`。
- `instrument_id`：行情合约，例如 `ao9999`、`rb9999`、`IF9999`。
- `trade_instrument_id`：实际交易合约，例如 `ao2609`、`rb2610`、`IF2606`。
- `exchange`：交易所。
- `trading_day`：交易日，由 trading calendar / session rule 给出。

`contract_role` values：

- `BASE_SYMBOL`：基础品种身份，只能表达品种，不代表可交易合约。
- `CONTINUOUS_MAIN`：主连 / 连续合约身份，用于行情、回测、策略观察。
- `TRADE_CONTRACT`：实际交易合约身份，可用于下单前的 typed command。
- `EXPIRED_CONTRACT`：已到期合约身份，只可用于历史回放 / 诊断 / 归档事实。

`raw_payload`、自由文本、文件名、UI label、行情源原始字符串和 broker
message 均不得成为 instrument identity source-of-truth。

## Resolver Responsibility

Future interface contract：

```python
InstrumentResolver.resolve(symbol, trading_day)
```

The resolver output must include：

- `symbol`。
- `instrument_id`。
- `trade_instrument_id`。
- `exchange`。
- `source`。
- `confidence`。
- `effective_from`。
- `effective_to`。
- `diagnostics`。

Resolver responsibility is limited to identity resolution：

- Resolver may normalize symbol casing and exchange-specific identity format。
- Resolver may choose the main / continuous contract and active trade contract
  according to deterministic rules bound to `trading_day`。
- Resolver must return diagnostics when identity is ambiguous, expired,
  missing or manually overridden。
- Resolver must not create strategy signals。
- Resolver must not decide direction, offset, quantity, price or order type。
- Resolver must not update OMS, Trade, Position, Margin, PnL, Settlement,
  Account or ledger facts。
- Resolver must not trigger broker, CTP, SimNow, live feed or network calls。

## Data Source Priority

Future resolver source priority is frozen as：

1. local instruments table / static contract registry。
2. local trading calendar / session。
3. historical market data metadata。
4. read-only market data adapter。
5. manual override only with explicit warning。

Manual override must be visibly labeled as override input. It must include
operator warning, source, reason and effective range. Manual override is not a
durable business fact unless a later accepted stage defines a typed durable
override schema.

## Main / Continuous Mapping

Main / continuous and trade contracts have separate roles：

- 主连 / 连续合约用于行情、回测和策略观察。
- 实际交易合约用于下单。
- 主连不能直接下单。
- `trade_instrument_id` must be traceable to a resolver result.
- roll logic must be deterministic and bound to `trading_day`.
- The same resolver input and same local registry snapshot must produce the
  same output.
- Roll diagnostics must explain effective range and selected source.

Backtest may observe `instrument_id=CONTINUOUS_MAIN`, but any generated order
intent / execution command must carry a resolver-derived `trade_instrument_id`
with role `TRADE_CONTRACT`.

## Console Impact

Current Operator Console fields `symbol`、`instrument_id` and
`trade_instrument_id` are temporary local dry-run fixture inputs only.

Future Console UI should ask ordinary users for：

- 品种 `symbol`。
- `trading_day`。
- mode：Paper / SIM。

Future Console UI should display resolver result preview：

- `symbol`。
- `instrument_id`。
- `trade_instrument_id`。
- `exchange`。
- `contract_role`。
- `source`。
- `confidence`。
- `effective_from / effective_to`。
- diagnostics and manual override warning when present。

Console must not require non-code users to guess `instrument_id` or
`trade_instrument_id` for normal Paper/SIM preview workflows once resolver
preview exists.

## Backtest / Paper / SIM / Live Consistency

For the same `trading_day + symbol`, all runtime modes must resolve instrument
identity from the same resolver snapshot：

- Backtest uses resolver snapshot。
- Paper uses resolver snapshot。
- SIM uses resolver snapshot。
- Future Live must also pass through resolver before any order command can be
  built。

Each module is forbidden from guessing contract identity independently.

Downstream facts must preserve resolver-derived identity lineage enough to
audit why a specific `instrument_id` and `trade_instrument_id` were used.

## Market Data Source Contract

Future read-only market data source interface：

```python
list_symbols()
list_contracts(symbol, trading_day)
get_main_contract(symbol, trading_day)
get_trade_contract(symbol, trading_day)
get_latest_quote(instrument_id)
get_bars(instrument_id, timeframe, start, end)
```

This interface is read-only：

- It may return typed metadata, quotes and bars。
- It must not create orders。
- It must not mutate OMS / Trade / Position / Accounting facts。
- It must not write DB rows unless a later Market Data ingestion stage
  explicitly accepts a typed fact persistence path。
- It must not enable broker/live/network submission。

## Safety Boundary

Stage U.1 forbids：

- CTP integration。
- SimNow integration。
- live broker integration。
- `ExecutionTarget.PAPER`, `ExecutionTarget.SIM` or `ExecutionTarget.LIVE`
  enablement。
- market data source driving order submission。
- market data source writing OMS, Trade, Position, Margin, PnL, Settlement or
  Accounting facts。
- `raw_payload` as identity source-of-truth。
- Console resolver preview as business source-of-truth。
- durable resolver snapshot schema without a later accepted schema stage。

## Future Implementation Recommendation

Stage U.2 may implement：

- static / local `InstrumentRegistry` fixture。
- `InstrumentResolver` interface。
- deterministic resolver result object。
- Console resolver preview。
- tests for symbol, trading day, main contract, trade contract, role,
  deterministic roll mapping, invalid symbol and manual override warning。

Stage U.2 must still not connect live feeds, CTP, SimNow, broker or network
submission. It must not enable non-`MOCK` execution targets.

## 真实行情解析器集成

`real_market_data` 数据源接入后，`InstrumentResolver` 仍是唯一身份来源。

集成规则：

- 默认解析器仍使用 `static_fixture`。
- `real_market_data` 必须显式注入 `ReadOnlyMarketDataAdapter`。
- 未注入适配器时，解析器返回未找到并给出“只读行情适配器未配置”诊断。
- 注入适配器后，解析器只消费适配器返回的标准化 `InstrumentContract`。
- AkShare 原始字段、原始行、原始载荷不得成为身份事实源。
- 主力合约和交易合约交易所不一致时失败关闭。
- 合约元数据缺失或无效时失败关闭。

下游仍只能使用解析器输出：

- `symbol`。
- `instrument_id`。
- `trade_instrument_id`。
- `exchange`。
- `trading_day`。
- `source`。
- `confidence`。
- `diagnostics`。

解析器仍不得创建信号、方向、数量、价格、订单或执行目标。

## Phase N 真实行情只读运行时

Phase N 在 `real_market_data` 数据源之上新增本地只读运行时：

- `MarketDataRuntime`。
- `MarketDataRuntimeConfig`。
- `MarketDataRuntimeStatus`。
- `MarketDataRuntimeSnapshot`。

运行时职责仅限于本地读取真实行情、维护内存缓存和输出诊断。它不是
Broker，不是 CTP，不是 SimNow，不是实盘入口，也不会下单。

默认状态固定为：

- 未启动。
- 未配置。
- 不会联网。
- 不会调用 AkShare。

只有同时满足以下条件时，运行时才允许读取 AkShare：

- `MarketDataRuntimeConfig.enabled=True`。
- 已配置 `trading_day`。
- 用户显式触发 `start()` 或 `poll_once(symbols)`。

`poll_once(symbols)` 支持的第一批品种为：

- `ao`。
- `rb`。
- `ag`。
- `cu`。

每个品种必须先通过现有 `InstrumentResolver` 解析身份。运行时只使用
resolver 输出的 `symbol`、`instrument_id`、`trade_instrument_id`、
`exchange` 和 `trading_day` 作为身份来源；AkShare 原始字段、原始行和
原始载荷不得替代 resolver identity。

轮询规则：

- 每个 symbol 独立返回状态和诊断。
- 单个 symbol 失败不得污染其他 symbol。
- 网络、API、空数据、异常或 resolver 未解析时返回 `BLOCKED` 或
  `DEGRADED`。
- 不自动补数据。
- 不自动猜合约。

内存缓存只保存最近一次结果：

- `latest_quote`。
- `latest_bars_summary`。
- `updated_at`。
- `source`。
- `diagnostics`。

缓存不写数据库，不写文件，不持久化为业务事实。

运行时诊断必须包含：

- AkShare 可用性。
- 配置状态。
- 是否已发生网络调用。
- 最近错误。
- 每个 symbol 状态。

安全边界保持不变：

- 不写 schema。
- 不执行 Alembic。
- 不写 DB。
- 不写 OMS / Trade / Position / Accounting / Margin / Settlement。
- 不连接 Broker。
- 不连接 CTP。
- 不连接 SimNow。
- 不启用 `ExecutionTarget.PAPER`、`ExecutionTarget.SIM` 或
  `ExecutionTarget.LIVE`。
- 不提交真实订单。

Stage U.1 validation：

```bash
git diff --check
```

## Stage U.2 Static Instrument Registry + Resolver Implementation

Baseline：`stage-u1-instrument-resolver-contract-freeze / 81bcaf1`。

Stage U.2 implements the first local deterministic resolver. It is intentionally
small and local-only：

- `src/futures_mvp/modules/market_data/models.py` defines
  `ContractRole`, `InstrumentContract`, `InstrumentResolution` and
  `InstrumentResolveStatus`。
- `src/futures_mvp/modules/market_data/registry.py` defines a static fixture
  `InstrumentRegistry`。
- `src/futures_mvp/modules/market_data/resolver.py` defines
  `InstrumentResolver.resolve(symbol, trading_day)`。

The registry is static fixture only, not a live market source. It currently
contains minimal local fixture coverage for：

- `ao`：base `ao`, main `ao9999`, trade `ao2609`, exchange `SHFE`。
- `rb`：base `rb`, main `rb9999`, trade `rb2610`, exchange `SHFE`。
- optional fixtures：`ag` / `cu`。

All implemented fixtures use `source=static_fixture` and explicit
`effective_from / effective_to` windows. They must not be treated as a complete
real market instrument table.

Implemented resolver behavior：

- normalizes `symbol` to deterministic lowercase。
- requires `trading_day` as ISO `YYYY-MM-DD` or `date` input。
- selects only contracts whose effective window covers `trading_day`。
- requires exactly one `CONTINUOUS_MAIN` and one `TRADE_CONTRACT`。
- returns `RESOLVED`, `NOT_FOUND`, `AMBIGUOUS`, `EXPIRED`,
  `INVALID_INPUT` or `METADATA_INVALID`。
- returns diagnostics that state `static fixture only, not live market source`。

Safety boundary remains unchanged：

- no live feed。
- no CTP。
- no SimNow。
- no broker or network calls。
- no schema or Alembic migration。
- no DB writes。
- no `ExecutionTarget.PAPER`, `ExecutionTarget.SIM` or
  `ExecutionTarget.LIVE` enablement。
- resolver output is not a strategy signal and does not decide direction,
  offset, price, quantity or order type。
- `raw_payload` remains forbidden as an identity source-of-truth。

Console integration in Stage U.2 uses `symbol + trading_day` for normal
configuration and fills `instrument_id`, `trade_instrument_id` and `exchange`
from the resolver result. Manual contract fields remain visible only as
advanced review fields labeled as resolver-generated and not recommended for
manual entry. Unresolved resolver status blocks dry-run config assembly and
does not fail open.

## Phase L Resolver Source Diagnostics

Baseline：`phase-rp-v1 / 76ec4cf`。

Phase L allows resolver diagnostics to identify the selected market data source
as either：

- `static_fixture`。
- `read_only_adapter_placeholder`。

The default remains `static_fixture`. If `read_only_adapter_placeholder` is
selected before a future provider is configured, resolver output must fail
closed with not configured diagnostics. It must not infer `instrument_id`,
`trade_instrument_id`, `exchange`, effective windows or metadata from adapter
raw payloads.

Resolver source diagnostics are lineage and observability only. They are not a
license to connect a broker, CTP, SimNow, live feed, live account, order path or
real capital path.

## Stage U.2.1 Console Resolver UI Polish

Baseline：`stage-u2-static-instrument-registry-resolver / 9996a7d`。

Stage U.2.1 is UI/docs/tests polish only. The resolver contract and safety
semantics are unchanged.

Operator Console normal configuration no longer exposes editable
`instrument_id`, `trade_instrument_id` or `exchange` fields. Operators provide
`symbol + trading_day`; resolver-generated identities are displayed read-only
in the resolver preview.

The resolver preview must continue to state that this is local static fixture
mapping only, not a live market source, and that no exchange connection is
made.

## Stage U.3.1 Static Registry Metadata + Fixture Coverage

Baseline：`stage-u21-console-resolver-ui-polish / 9912b24`。

Stage U.3.1 keeps the resolver local and deterministic. It adds static fixture
metadata to local contracts only：

- `product_name`。
- `tick_size`。
- `contract_multiplier`。
- `min_order_qty`。
- `price_limit_ref`。
- `trading_session_ref`。

These metadata values are static fixture metadata. They are not guaranteed to
be complete real-market values and must not be used for live trading.

Metadata is required for `RESOLVED`. The resolver must fail closed as
`METADATA_INVALID` when selected main or trade contract metadata is missing or
when `product_name`, `price_limit_ref` or `trading_session_ref` is empty, or
when `tick_size`, `contract_multiplier` or `min_order_qty` is not positive.

Fixture coverage includes `ao`, `rb`, `ag` and `cu`, each with base, continuous
main and trade contracts. Resolver diagnostics include the static source,
static fixture warning, selected main contract, selected trade contract,
effective window and metadata summary when available.

Stage U.3.1 still does not add DB persistence, schema, Alembic, live feed,
quote API, CTP, SimNow, broker, network or non-`MOCK` execution targets.

## Stage U.4.1 Backtest / Paper / SIM Resolver Consumer Contract Freeze

Baseline：`stage-u31-static-registry-metadata-coverage / e76811a`。

Stage U.4.1 is documentation-only. The detailed consumer contract is frozen in
`docs/market_data/RESOLVER_CONSUMER_CONTRACT.md`.

Backtest, Paper, SIM and Operator Console dry-run must consume
`InstrumentResolution` through `symbol + trading_day + mode`. Consumers must not
ask users, fixtures or strategy code to guess `instrument_id`,
`trade_instrument_id` or `exchange`.

Only `InstrumentResolveStatus.RESOLVED` may continue to command, order, report
or trade generation. `NOT_FOUND`, `INVALID_INPUT`, `EXPIRED`, `AMBIGUOUS` and
`METADATA_INVALID` must fail closed.

Downstream objects introduced by future stages must preserve resolver-derived
identity lineage：`symbol`, `instrument_id`, `trade_instrument_id`, `exchange`,
`trading_day`, resolver source, resolver confidence, effective window and
diagnostics reference or summary.

Resolver result remains an identity input, not order truth, trade truth,
position truth, accounting truth, signal truth, price truth, quantity truth or
direction truth. `raw_payload`, UI labels, filenames, broker raw fields and
manual IDs must not become identity fallbacks.

Default schema decision remains NO schema. Durable resolver snapshots require a
separate `Resolver Snapshot Persistence Contract Freeze`.
