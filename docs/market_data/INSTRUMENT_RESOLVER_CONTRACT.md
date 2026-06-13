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

Stage U.1 validation：

```bash
git diff --check
```
